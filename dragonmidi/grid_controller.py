"""The Active Grid Controller (docs/llds/intech-grid.md § Active Grid Controller,
§ MIDI -> Module/Element Resolution). Builds a `GridRuntimeController` from a
settled `GridTopology`, satisfying the same `ActiveController` shape
`ControllerProfile` does, without being a `ControllerProfile` instance - Grid's
shape is discovered at runtime, not declared in a YAML file.

Construction fails closed (`GridControllerBuildOutcome`): a multi-row topology,
more than one recognized VSN1, or any raw-MIDI-address collision between two
recognized elements all abort construction entirely rather than producing a
partial or best-guess controller.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from .events import MidiEvent
from .grid_modules import GridElement, ModuleType, definition_for_type
from .grid_topology import GridTopology, normalize_linear_order, validate_single_row
from .mapping import ControlsConfig, _MapEntry, _fader_entries, build_bank_membership
from .name_matching import fuzzy_contains

_Key = tuple[str, "int | None"]

# Corrected against real hardware (2026-11-04): a real Grid's CoreMIDI port
# name is simply "Grid" (the device's bare USB product string), not the
# "Intech Grid MIDI" per-interface descriptor string this project's source
# research had assumed would be exposed - "intechgridmidi" never matches
# normalized "grid" since it's the longer string. "grid" matches both the
# real bare name and, were a future firmware/platform ever to expose the
# fuller decorated name instead, that too ("grid" is a substring of
# "intechgridmidi").
GRID_MIDI_MATCH_SUBSTRING = "grid"
GRID_PROFILE_NAME = "Intech Grid"


# --- Construction outcomes (fail-closed, no partial results) ---


@dataclass(frozen=True)
class UnsupportedTopology:
    reason: str


@dataclass(frozen=True)
class AddressCollision:
    raw_key: _Key
    first_logical_key: _Key
    second_logical_key: _Key


class GridRuntimeController:
    """Satisfies `active_controller.ActiveController` structurally. Not a
    frozen dataclass - its fields are derived from a topology snapshot, and
    `mark_stale()` mutates `is_stale` in place (docs/llds/intech-grid.md
    § Topology Change Policy)."""

    name: str = GRID_PROFILE_NAME
    has_native_mode: bool = False
    has_jog_wheel: bool = False
    has_scene_button: bool = False
    websocket_keys = None
    group_keys = None

    def __init__(
        self,
        *,
        default_channel: int,
        bank_count: int,
        bank_fader_keys: tuple[_Key, ...],
        fader_keys: frozenset[_Key],
        opinionated_map: Mapping[_Key, _MapEntry],
        control_names: Mapping[_Key, str],
        address_table: Mapping[_Key, _Key],
        topology: GridTopology,
        knob_to_fader: Mapping[_Key, _Key] | None = None,
        mute_to_fader: Mapping[_Key, _Key] | None = None,
    ) -> None:
        self.default_channel = default_channel
        self.bank_count = bank_count
        self.bank_fader_keys = bank_fader_keys
        self.fader_keys = fader_keys
        # PBF4's Rotary (potentiometer) and Button elements, Phase 1.2 - populated
        # exactly like a Korg profile's Knob/Mute, since PBF4's pot/button share
        # their channel's fader's own numeric index within and across modules
        # (docs/llds/intech-grid.md § Module Definitions; see build_grid_controller's
        # `knob_to_fader`/`mute_to_fader` construction). Empty for a VSN1-only
        # topology, same as before Phase 1.2.
        self.knob_to_fader: dict[_Key, _Key] = dict(knob_to_fader or {})
        self.mute_to_fader: dict[_Key, _Key] = dict(mute_to_fader or {})
        self.fader_to_knob: dict[_Key, _Key] = {fader_key: knob_key for knob_key, fader_key in self.knob_to_fader.items()}
        self.opinionated_map = opinionated_map
        self.control_names = control_names
        self.address_table = address_table
        self.topology = topology
        self.is_stale = False

    def bank_fader_key(self, key: _Key) -> _Key | None:
        return self.knob_to_fader.get(key) or self.mute_to_fader.get(key)

    def matches(self, port_name: str) -> bool:
        return fuzzy_contains(GRID_MIDI_MATCH_SUBSTRING, port_name)

    def mark_stale(self) -> None:
        self.is_stale = True


@dataclass(frozen=True)
class Ready:
    controller: GridRuntimeController


# --- Logical-control role -> key-tag mapping, by module type ---

_PBF4_ROLE_TAGS = {"fader": "grid_fader", "potentiometer": "grid_pbf4_pot", "button": "grid_pbf4_button"}
_VSN1_ROLE_TAGS = {"button": "grid_vsn1_button", "endless": "grid_vsn1_jog", "jog_button": "grid_vsn1_jog_button"}

# Both carry at most one instance per module - identified by `(tag, None)`,
# the same shape `grid_vsn1_jog` already used, rather than a counted index.
_SINGULAR_CONTROL_NAMES = {"grid_vsn1_jog": "VSN1 Jog", "grid_vsn1_jog_button": "VSN1 Jog Push"}


def _raw_key_for(module_x: int, module_y: int, page: int, element: GridElement) -> _Key:
    """Grid's own documented factory-default ("MIDI Auto") formula, using raw
    (un-normalized) module coordinates - never the normalized left-to-right
    rank. Source: `grid-fw/common/src/lua/simplemidi.lua` (GPL-3.0-only,
    independently reimplemented).

    `jog_button` shares the endless element's index on real VSN1 hardware
    (confirmed 2026-11-04) - pressing it straight down sends Note On/Off on
    the same raw number turning it sends CC on, disambiguated here purely by
    message type exactly like every other button role.

    @spec GRID-MIDI-001, GRID-MIDI-002, GRID-CTRL-010
    """
    number = (32 + module_x * 16 + element.index) % 128
    msg_type = "note" if element.role in ("button", "jog_button") else "cc"
    return (msg_type, number)


def build_grid_controller(topology: GridTopology) -> "Ready | UnsupportedTopology | AddressCollision":
    """@spec GRID-CTRL-001 through GRID-CTRL-009, GRID-TOPO-010, GRID-TOPO-011"""
    if not validate_single_row(topology):
        return UnsupportedTopology("modules span more than one row (y coordinate)")

    recognized_vsn1_count = sum(1 for m in topology.modules if m.module_type is ModuleType.VSN1)
    if recognized_vsn1_count > 1:
        return UnsupportedTopology("more than one recognized VSN1 module is present")

    ordered = normalize_linear_order(topology.modules)

    control_names: dict[_Key, str] = {}
    address_table: dict[_Key, _Key] = {}
    fader_raw_ccs: list[int] = []  # synthetic "CC numbers" (logical indices) fed to build_bank_membership
    counters = {"grid_fader": 0, "grid_pbf4_pot": 0, "grid_pbf4_button": 0, "grid_vsn1_button": 0}

    def _record(raw_key: _Key, logical_key: _Key) -> AddressCollision | None:
        existing = address_table.get(raw_key)
        if existing is not None and existing != logical_key:
            return AddressCollision(raw_key=raw_key, first_logical_key=existing, second_logical_key=logical_key)
        address_table[raw_key] = logical_key
        return None

    for module in ordered:
        if module.module_type is None:
            continue  # unrecognized - contributes no elements, doesn't threaten uniqueness (§6)
        definition = definition_for_type(module.module_type)
        for element in sorted(definition.elements, key=lambda e: e.index):
            if element.role == "lcd":
                continue  # not an input control in Phase 1
            role_tags = _PBF4_ROLE_TAGS if module.module_type is ModuleType.PBF4 else _VSN1_ROLE_TAGS
            tag = role_tags.get(element.role)
            if tag is None:
                continue

            if tag in _SINGULAR_CONTROL_NAMES:
                logical_key: _Key = (tag, None)
                control_names[logical_key] = _SINGULAR_CONTROL_NAMES[tag]
            else:
                counters[tag] += 1
                index = counters[tag]
                logical_key = (tag, index)
                display = {
                    "grid_fader": f"Grid Fader {index}",
                    "grid_pbf4_pot": f"Grid Pot {index}",
                    "grid_pbf4_button": f"Grid PBF4 Button {index}",
                    "grid_vsn1_button": f"VSN1 Button {index}",
                }[tag]
                control_names[logical_key] = display
                if tag == "grid_fader":
                    fader_raw_ccs.append(index)

            raw_key = _raw_key_for(module.x, module.y, topology.current_page, element)
            collision = _record(raw_key, logical_key)
            if collision is not None:
                return collision

    bank_count = counters["grid_fader"]
    membership = build_bank_membership(
        ControlsConfig(faders=tuple(fader_raw_ccs), knobs=(), mutes=(), solos=(), transport={}, jog_wheel=None),
        key_type="grid_fader",
    )
    opinionated_map = _fader_entries(fader_raw_ccs, key_type="grid_fader")

    # PBF4's pot/button per-tag counters increment in lockstep with its fader's own
    # (every PBF4 module contributes exactly one of each per channel, in the same
    # per-module order - docs/llds/intech-grid.md § Module Definitions), so index i's
    # pot/fader/button always belong to the same physical channel strip across any
    # number/order of PBF4 modules mixed with VSN1 modules (whose elements never
    # touch these three counters at all). `min(..., bank_count)` is defensive only -
    # it's always equal today, since no other module type contributes a fader.
    # @spec GRID-CTRL-011
    pot_count = min(counters["grid_pbf4_pot"], bank_count)
    button_count = min(counters["grid_pbf4_button"], bank_count)
    knob_to_fader = {("grid_pbf4_pot", i): ("grid_fader", i) for i in range(1, pot_count + 1)}
    mute_to_fader = {("grid_pbf4_button", i): ("grid_fader", i) for i in range(1, button_count + 1)}

    controller = GridRuntimeController(
        default_channel=topology.current_page % 16,
        bank_count=bank_count,
        bank_fader_keys=membership["bank_fader_keys"],
        fader_keys=membership["fader_keys"],
        opinionated_map=opinionated_map,
        control_names=control_names,
        address_table=address_table,
        topology=topology,
        knob_to_fader=knob_to_fader,
        mute_to_fader=mute_to_fader,
    )
    return Ready(controller=controller)


def resolve_grid_event(event: MidiEvent, controller: GridRuntimeController) -> MidiEvent | None:
    """Resolves a raw Grid `MidiEvent` into one carrying a stable logical
    identity, by looking up `(event.type, event.number)` in the controller's
    `address_table`. Returns `None` - never guesses - if the controller is
    stale or the event matches nothing.

    @spec GRID-MIDI-003, GRID-MIDI-004, GRID-MIDI-005, GRID-MIDI-006, GRID-MIDI-007
    """
    if controller.is_stale:
        return None
    logical = controller.address_table.get((event.type, event.number))
    if logical is None:
        return None
    logical_type, logical_number = logical
    return replace(event, type=logical_type, number=logical_number)


def route_midi_event(event: MidiEvent, *, grid_active: bool, controller: GridRuntimeController | None) -> MidiEvent | None:
    """The one Grid-specific branch `app.py`'s MIDI input dispatch needs,
    deliberately kept out of every output path (OSC/WebSocket/keystroke) -
    those only ever see whatever this function returns, exactly as they see a
    Korg event. When Grid isn't the active controller, `event` passes through
    completely untouched (the existing static-profile path is unaffected).
    When Grid is active but no settled `GridRuntimeController` exists yet (or
    the event doesn't resolve), returns `None` - dropped safely, never guessed.

    @spec GRID-MAP-001
    """
    if not grid_active:
        return event
    if controller is None:
        return None
    return resolve_grid_event(event, controller)
