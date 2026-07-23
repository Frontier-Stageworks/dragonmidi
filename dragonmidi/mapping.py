from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .controller_profile import ControllerProfile
from .events import KeyCombo, MidiEvent, OscMessage, WebSocketCommand

STUDIO_CHANNEL = 15  # zero-indexed MIDI channel 16, the nanoKONTROL Studio's Native Mode channel
NANOKONTROL2_CHANNEL = 0  # zero-indexed MIDI channel 1, the nanoKONTROL2's factory CC-mode default (unverified - @spec MAP-PROFILE-002)
CHANNEL = STUDIO_CHANNEL  # backward-compat alias; pre-dates multi-profile support
DEBOUNCE_SECONDS = 0.080

_Key = tuple[str, "int | None"]

# @spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003
JOG_WHEEL_CC = 110
_JOG_WHEEL_KEY: _Key = ("cc", JOG_WHEEL_CC)

# @spec MAP-JOGKEY-001, MAP-JOGKEY-002
_STEP_MOCO_FORWARD = KeyCombo(frozenset({"alt", "shift"}), "right")
_STEP_MOCO_BACKWARD = KeyCombo(frozenset({"alt", "shift"}), "left")

_KNOB_STEP_SCALE = 0.1  # axis position units per one MIDI raw-value increment


@dataclass(frozen=True)
class _MapEntry:
    kind: str  # "absolute" | "press"
    address: str
    args: tuple = ()


@dataclass(frozen=True)
class _AxisTarget:
    axis_name: str
    min_value: float
    max_value: float


class ControlsConfigError(ValueError):
    """Raised when a Controller Profile config file's `controls:` block is invalid.

    @spec MAP-CONFIG-006, MAP-CONFIG-007
    """


@dataclass(frozen=True)
class ControlsConfig:
    """The parsed `controls:` block of a Controller Profile config file
    (`docs/llds/static-mapping.md § Controller Profile Config Schema`).

    @spec MAP-CONFIG-002
    """

    faders: tuple[int, ...]
    knobs: tuple[int, ...]
    mutes: tuple[int, ...]
    solos: tuple[int, ...]
    transport: Mapping[str, int]
    jog_wheel: "int | None"


@dataclass(frozen=True)
class WebSocketKeys:
    """CC-sourced keys for the WebSocket-targeted controls (Stop, Cycle, Solo 1-8,
    Previous/Next Marker), per active Controller Profile - no longer fixed module
    constants, since a config's CC numbers for these need not match the
    nanoKONTROL family's.

    @spec MAP-CONFIG-005
    """

    stop: "_Key | None"
    cycle: "_Key | None"
    previous_marker: "_Key | None"
    next_marker: "_Key | None"
    solos: tuple[_Key, ...]


@dataclass(frozen=True)
class GroupKeys:
    """CC-sourced keys for Group switching (Previous/Next Track), per active
    Controller Profile - parallel to WebSocketKeys, but Track produces neither an
    OSC message nor a WebSocket command (@spec MAP-GROUP-003).

    @spec MAP-GROUP-003
    """

    previous: "_Key | None"
    next: "_Key | None"


# Bank membership: Bank N = Fader N, Knob N, Mute N (Record N/Select N excluded, no
# matching per-axis action exists for them - @spec MAP-BANK-006). Solo N is not a bank
# member - it's an unconditional WebSocket target regardless of Fader N's axis state
# (@spec MAP-WS-002). Determined by positional index (Bank N = index N-1 in each of
# faders/knobs/mutes), not CC arithmetic - a config's knobs/mutes CCs need not be
# arithmetically related to its faders' (edge audit 2026-07-22).
_TRANSPORT_OSC_TARGETS: dict[str, tuple[str, str, tuple]] = {
    "record": ("press", "/dragonframe/shoot", (1,)),
    "play": ("press", "/dragonframe/play", ()),
    "rewind": ("press", "/dragonframe/stepBackward", ()),
    "fast_forward": ("press", "/dragonframe/stepForward", ()),
    # previous_track/next_track are deliberately absent as of Phase 6 - they are
    # Group-switch-targeted (MAP-GROUP-003), not OSC entries, the same "removed from
    # OPINIONATED_MAP entirely" treatment MAP-WS-009 gives Stop/Cycle/Solo/Marker.
}

_TRANSPORT_DISPLAY_NAMES: dict[str, str] = {
    "record": "Transport Record",
    "play": "Play",
    "rewind": "Rewind",
    "fast_forward": "Fast Forward",
    "previous_track": "Previous Track",
    "next_track": "Next Track",
}


def _fader_entries(ccs: Sequence[int]) -> dict[_Key, _MapEntry]:
    return {("cc", cc): _MapEntry("absolute", f"/dragonframe/encoder/{i + 1}") for i, cc in enumerate(ccs)}


def _knob_entries(ccs: Sequence[int]) -> dict[_Key, _MapEntry]:
    return {("cc", cc): _MapEntry("absolute", f"/dragonframe/encoder/{9 + i}") for i, cc in enumerate(ccs)}


def _mute_entries(ccs: Sequence[int]) -> dict[_Key, _MapEntry]:
    return {("cc", cc): _MapEntry("press", f"/dragonframe/encoderReset/{i + 1}") for i, cc in enumerate(ccs)}


def _transport_entries(transport: Mapping[str, int]) -> dict[_Key, _MapEntry]:
    """Only the OSC-targeted transport roles - stop/cycle/previous_marker/next_marker
    are WebSocket-targeted (`build_websocket_keys`) and deliberately excluded here
    (@spec MAP-WS-009, MAP-CONFIG-005)."""
    entries: dict[_Key, _MapEntry] = {}
    for name, (kind, address, args) in _TRANSPORT_OSC_TARGETS.items():
        cc = transport.get(name)
        if cc is not None:
            entries[("cc", cc)] = _MapEntry(kind, address, args=args)
    return entries


def validate_controls_config(controls: ControlsConfig, has_jog_wheel: bool) -> None:
    """@spec MAP-CONFIG-006, MAP-CONFIG-007"""
    for field_name in ("faders", "knobs", "mutes", "solos"):
        values = getattr(controls, field_name)
        if len(values) != 8:
            raise ControlsConfigError(f"'{field_name}' must have exactly 8 entries, got {len(values)}")
    if has_jog_wheel and controls.jog_wheel is None:
        raise ControlsConfigError("has_jog_wheel is true but 'jog_wheel' CC is missing")


def build_opinionated_map(controls: ControlsConfig, has_scene_button: bool) -> dict[_Key, _MapEntry]:
    """Synthesizes an opinionated map from a profile's declared CC numbers, replacing
    the old per-profile hardcoded literal dicts (@spec MAP-CONFIG-001).

    @spec MAP-CONFIG-002, MAP-CONFIG-004
    """
    entries: dict[_Key, _MapEntry] = {
        **_fader_entries(controls.faders),
        **_knob_entries(controls.knobs),
        **_mute_entries(controls.mutes),
        **_transport_entries(controls.transport),
    }
    if has_scene_button:
        entries[("korg_scene", None)] = _MapEntry("press", "/dragonframe/black")
    return entries


def build_websocket_keys(controls: ControlsConfig) -> WebSocketKeys:
    """@spec MAP-CONFIG-005"""

    def _key(name: str) -> "_Key | None":
        cc = controls.transport.get(name)
        return ("cc", cc) if cc is not None else None

    return WebSocketKeys(
        stop=_key("stop"),
        cycle=_key("cycle"),
        previous_marker=_key("previous_marker"),
        next_marker=_key("next_marker"),
        solos=tuple(("cc", cc) for cc in controls.solos),
    )


def build_bank_membership(controls: ControlsConfig) -> "dict[str, object]":
    """Positional (not CC-arithmetic) Fader<->Knob/Mute pairing: Bank N = index N-1
    in each of `faders`/`knobs`/`mutes`. Returns the five pieces `ControllerProfile`
    stores directly (`fader_keys`, `knob_to_fader`, `mute_to_fader`, `fader_to_knob`,
    `bank_fader_keys`)."""
    fader_keys = frozenset(("cc", cc) for cc in controls.faders)
    knob_to_fader = {("cc", knob_cc): ("cc", fader_cc) for fader_cc, knob_cc in zip(controls.faders, controls.knobs)}
    mute_to_fader = {("cc", mute_cc): ("cc", fader_cc) for fader_cc, mute_cc in zip(controls.faders, controls.mutes)}
    fader_to_knob = {fader_key: knob_key for knob_key, fader_key in knob_to_fader.items()}
    # Ordered (index 0 = Bank 1), unlike fader_keys' frozenset - needed by the Preset
    # Store to translate a persisted Bank index back to a fader key (@spec MAP-STORE-001).
    bank_fader_keys = tuple(("cc", cc) for cc in controls.faders)
    return {
        "fader_keys": fader_keys,
        "knob_to_fader": knob_to_fader,
        "mute_to_fader": mute_to_fader,
        "fader_to_knob": fader_to_knob,
        "bank_fader_keys": bank_fader_keys,
    }


def build_group_keys(controls: ControlsConfig) -> GroupKeys:
    """@spec MAP-GROUP-003, MAP-GROUP-006"""

    def _key(name: str) -> "_Key | None":
        cc = controls.transport.get(name)
        return ("cc", cc) if cc is not None else None

    return GroupKeys(previous=_key("previous_track"), next=_key("next_track"))


def build_control_names(controls: ControlsConfig, has_scene_button: bool) -> dict[_Key, str]:
    """Mapping View display names built from the active profile's config, replacing
    the old module-level CC-keyed `CONTROL_NAMES` literal in `mapping_view_model.py`."""
    names: dict[_Key, str] = {("cc", cc): f"Fader Channel {i + 1}" for i, cc in enumerate(controls.faders)}
    for name, cc in controls.transport.items():
        label = _TRANSPORT_DISPLAY_NAMES.get(name)
        if label is not None:
            names[("cc", cc)] = label
    if has_scene_button:
        names[("korg_scene", None)] = "Scene"
    return names


def build_profile(
    *,
    name: str,
    match_substring: str,
    has_native_mode: bool,
    default_channel: int,
    has_jog_wheel: bool,
    has_scene_button: bool,
    controls: ControlsConfig,
    setup_hint: "str | None" = None,
) -> ControllerProfile:
    """Assembles a `ControllerProfile` from a `ControlsConfig`, validating it first
    and deriving every controls-dependent field (opinionated map, WebSocket keys,
    bank membership, display names) the same way for a bundled/hardcoded profile
    (below) or one loaded from a config file (`controller_profile_loader.py`)."""
    validate_controls_config(controls, has_jog_wheel)
    bank = build_bank_membership(controls)
    return ControllerProfile(
        name=name,
        match_substring=match_substring,
        has_native_mode=has_native_mode,
        default_channel=default_channel,
        has_jog_wheel=has_jog_wheel,
        has_scene_button=has_scene_button,
        opinionated_map=build_opinionated_map(controls, has_scene_button),
        websocket_keys=build_websocket_keys(controls),
        group_keys=build_group_keys(controls),
        setup_hint=setup_hint,
        control_names=build_control_names(controls, has_scene_button),
        **bank,
    )


_SHARED_TRANSPORT: dict[str, int] = {
    "record": 45,
    "play": 41,
    "stop": 42,
    "rewind": 43,
    "fast_forward": 44,
    "cycle": 46,
    "previous_marker": 61,
    "next_marker": 62,
    "previous_track": 58,
    "next_track": 59,
}

# The bundled profiles' controls, mirroring `dragonmidi/controllers/*.yaml`
# (@spec MAP-CONFIG-003's migration invariant: these must synthesize maps
# byte-identical to this project's pre-Phase-5 hardcoded constants).
STUDIO_CONTROLS = ControlsConfig(
    faders=tuple(range(8)),
    knobs=tuple(range(16, 24)),
    mutes=tuple(range(48, 56)),
    solos=tuple(range(32, 40)),
    transport=dict(_SHARED_TRANSPORT),
    jog_wheel=JOG_WHEEL_CC,
)

NANOKONTROL2_CONTROLS = ControlsConfig(
    faders=tuple(range(8)),
    knobs=tuple(range(16, 24)),
    mutes=tuple(range(48, 56)),
    solos=tuple(range(32, 40)),
    transport=dict(_SHARED_TRANSPORT),
    jog_wheel=None,
)

# @spec MIDI-PROFILE-002
STUDIO_PROFILE = build_profile(
    name="nanoKONTROL Studio",
    match_substring="nanokontrolstudio",
    has_native_mode=True,
    default_channel=STUDIO_CHANNEL,
    has_jog_wheel=True,
    has_scene_button=True,
    controls=STUDIO_CONTROLS,
)

# @spec MIDI-PROFILE-003
NANOKONTROL2_PROFILE = build_profile(
    name="nanoKONTROL2",
    match_substring="nanokontrol2",
    has_native_mode=False,
    default_channel=NANOKONTROL2_CHANNEL,
    has_jog_wheel=False,
    has_scene_button=False,
    controls=NANOKONTROL2_CONTROLS,
    setup_hint="Hold SET MARKER + CYCLE while powering on for CC mode",
)

OPINIONATED_MAP_STUDIO: dict[_Key, _MapEntry] = STUDIO_PROFILE.opinionated_map
OPINIONATED_MAP = OPINIONATED_MAP_STUDIO  # backward-compat alias; pre-dates multi-profile support
OPINIONATED_MAP_NANOKONTROL2: dict[_Key, _MapEntry] = NANOKONTROL2_PROFILE.opinionated_map


class MappingEngine:
    """Opinionated, hard-coded MIDI-event -> Dragonframe-OSC translator.

    @spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-005
    @spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
    @spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-004, MAP-AXIS-006, MAP-AXIS-007
    @spec MAP-AXIS-008, MAP-AXIS-009, MAP-AXIS-010
    @spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-004, MAP-BANK-005, MAP-BANK-006, MAP-BANK-007
    @spec MAP-BANK-008
    @spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003, MAP-JOG-004, MAP-JOG-005
    @spec MAP-JOGKEY-001, MAP-JOGKEY-002, MAP-JOGKEY-003, MAP-JOGKEY-004, MAP-JOGKEY-005
    @spec MAP-JOGKEY-006, MAP-JOGKEY-007
    @spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-004, MAP-WS-005, MAP-WS-006
    @spec MAP-WS-007, MAP-WS-008, MAP-WS-009
    @spec MAP-PROFILE-001, MAP-PROFILE-002, MAP-PROFILE-003, MAP-PROFILE-004
    @spec MAP-JOG-000, MAP-JOGKEY-000
    @spec MAP-GROUP-001, MAP-GROUP-002, MAP-GROUP-003, MAP-GROUP-004, MAP-GROUP-005
    @spec MAP-GROUP-006, MAP-GROUP-007, MAP-GROUP-008, MAP-GROUP-009, MAP-GROUP-010
    @spec MAP-GROUP-011, MAP-GROUP-012
    @spec MAP-STORE-002
    """

    def __init__(self, profile: ControllerProfile = STUDIO_PROFILE) -> None:
        self._profile = profile
        self._previous_value: dict[_Key, float] = {}
        self._pressed_state: dict[_Key, bool] = {}
        self._last_fired: dict[_Key, float] = {}
        # Keyed by (fader_key, group), group in 1..5 - one axis assignment per (Bank,
        # Group) pairing, not one per Bank (@spec MAP-GROUP-008).
        self._group_axis_targets: dict[tuple[_Key, int], _AxisTarget] = {}
        # Engine-wide OSC axis (direct) vs. OSC encoder mode, governing all 8 faders
        # together (2026-07-23 reversal of the pre-existing per-fader `_encoder_mode`
        # set) - False = axis mode, the default (@spec MAP-AXIS-008, MAP-AXIS-010).
        self._global_encoder_mode: bool = False
        # Fallback estimate of each fader's axis's current absolute position, keyed by
        # fader key, built entirely from DragonMIDI's own sends. Used to clamp Knob N's
        # cumulative nudges to the fader's [min, max] range only when no live position
        # reading is available from Dragonframe (see `process`'s `axis_positions` param)
        # (@spec MAP-BANK-008).
        self._axis_position: dict[_Key, float] = {}
        # Cycle's last-selected axis index, -1 = nothing selected yet (@spec MAP-WS-005).
        self._cycle_index: int = -1
        # Active Group, 1-5 - unlike _cycle_index, 1 is always a valid starting state,
        # not a "nothing selected" sentinel (@spec MAP-GROUP-002).
        self._active_group: int = 1

    @property
    def active_group(self) -> int:
        """Read-only - only changes through a legitimate Track </> press, the same
        encapsulation `_cycle_index` already has.

        @spec MAP-GROUP-002
        """
        return self._active_group

    def reset(self) -> None:
        self._previous_value.clear()
        self._pressed_state.clear()
        self._last_fired.clear()
        self._cycle_index = -1
        # _active_group and _group_axis_targets deliberately survive an ordinary
        # reconnect clear - only a Controller Profile switch resets them
        # (@spec MAP-GROUP-007, see set_profile below).

    @property
    def profile(self) -> ControllerProfile:
        return self._profile

    def set_profile(self, profile: ControllerProfile) -> None:
        """Switch the active Controller Profile: swaps the opinionated map and
        clears every piece of tracked state, including axis assignments and
        encoder-mode overrides - broader than `reset()`, since the previous
        profile's per-control configuration is meaningless against a different
        control set and channel. Independent of whether a matching device has
        yet been found under the new profile (`MIDI-PROFILE-005`).

        @spec MAP-PROFILE-004
        """
        self._profile = profile
        self.reset()
        self._group_axis_targets.clear()
        self._global_encoder_mode = False
        self._axis_position.clear()
        self._active_group = 1  # @spec MAP-GROUP-007

    def tracked_controls(self) -> set[_Key]:
        return set(self._previous_value) | set(self._pressed_state) | set(self._last_fired)

    def is_axis_mode(self) -> bool:
        """@spec MAP-AXIS-010"""
        return not self._global_encoder_mode

    def _discard_bank_knob_dedup(self, fader_key: _Key) -> None:
        """@spec MAP-BANK-007"""
        knob_key = self._profile.fader_to_knob.get(fader_key)
        if knob_key is not None:
            self._previous_value.pop(knob_key, None)

    def _step_active_group(self, direction: int) -> None:
        """Steps `_active_group` by `direction` (+1/-1), wrapping at the 1-5
        boundary rather than clamping, and discards dedup/position state for every
        Bank if the engine-wide mode is currently OSC axis (direct) - a no-op under
        OSC encoder mode, since no Bank's target depends on Group there.

        @spec MAP-GROUP-004, MAP-GROUP-011
        """
        self._active_group = ((self._active_group - 1 + direction) % 5) + 1
        if self.is_axis_mode():
            for fader_key in self._profile.bank_fader_keys:
                self._previous_value.pop(fader_key, None)
                self._axis_position.pop(fader_key, None)
                self._discard_bank_knob_dedup(fader_key)

    def set_fader_mode(self, axis: bool) -> None:
        """Engine-wide fader mode switch (2026-07-23), governing all 8 faders
        simultaneously - replaces the pre-existing per-fader `enter_axis_mode`/
        `clear_axis_target` pair. A no-op if the engine is already in the requested
        mode. Never touches `_group_axis_targets` in either direction: flipping only
        changes which behavior `process()` exhibits, so a previously-configured
        (Bank, Group) assignment resumes driving output unchanged once axis mode is
        restored, with no re-entry required (@spec MAP-AXIS-007, MAP-AXIS-011).

        @spec MAP-AXIS-010, MAP-AXIS-012, MAP-BANK-007
        """
        if axis == self.is_axis_mode():
            return
        self._global_encoder_mode = not axis
        for fader_key in self._profile.bank_fader_keys:
            self._previous_value.pop(fader_key, None)
            self._axis_position.pop(fader_key, None)
            self._discard_bank_knob_dedup(fader_key)

    def set_axis_target(self, key: _Key, group: int, axis_name: str, min_value: float, max_value: float) -> None:
        """Retarget Bank `key`'s fader to send gotoPosition to a named Dragonframe
        axis, for the given Group (1-5) - independent of whichever Group is
        currently active (@spec MAP-GROUP-008).

        @spec MAP-AXIS-002, MAP-AXIS-004, MAP-GROUP-008, MAP-GROUP-009, MAP-GROUP-010
        """
        if key not in self._profile.fader_keys:
            raise ValueError(f"OSC axis (direct) target is only available for fader controls, got {key!r}")
        self._group_axis_targets[(key, group)] = _AxisTarget(axis_name, min_value, max_value)
        if group == self._active_group:
            # Switching target discards prior dedup state for this key (LLD: "switching a
            # mapping entry's target type discards the previous target's configuration").
            # Scoped to the active Group only - editing a background Group's assignment
            # must not disturb the active Group's in-flight dedup/position state
            # (@spec MAP-GROUP-010).
            self._previous_value.pop(key, None)
            self._axis_position.pop(key, None)

    def axis_target(self, key: _Key, group: int) -> _AxisTarget | None:
        """Read-only lookup of a fader's current OSC axis (direct) target for the
        given Group, if any.

        @spec MAP-GROUP-008
        """
        return self._group_axis_targets.get((key, group))

    def clear_group_axis_target(self, key: _Key, group: int) -> None:
        """Clear only one Group's axis assignment for a fader, leaving the
        engine-wide fader mode and every other Group's assignment for that fader
        untouched. A no-op if that (key, group) pair has no axis target set.

        @spec MAP-GROUP-009, MAP-GROUP-010
        """
        self._group_axis_targets.pop((key, group), None)
        if group == self._active_group:
            self._previous_value.pop(key, None)
            self._axis_position.pop(key, None)

    def load_group_axis_targets(self, bank_axes: "dict[int, dict[int, dict]]") -> None:
        """Bulk-populate `_group_axis_targets` directly from the Preset Store's
        validated, JSON-native shape (`{bank_index: {group_index: {"axis_name",
        "min", "max"}}}`), translating Bank index -> fader key via
        `ControllerProfile.bank_fader_keys`. No save side effect - this is the
        bulk-populate load path, not a loop of `set_axis_target` calls. Does not
        touch dedup/position state, since no live device input has occurred yet.
        Does not touch the engine-wide fader mode either (2026-07-23): mode is
        orthogonal to this table and is never persisted (`MAP-STORE-006`).

        @spec MAP-STORE-002
        """
        bank_fader_keys = self._profile.bank_fader_keys
        for bank_index, groups in bank_axes.items():
            if not (1 <= bank_index <= len(bank_fader_keys)):
                continue
            fader_key = bank_fader_keys[bank_index - 1]
            for group, entry in groups.items():
                self._group_axis_targets[(fader_key, group)] = _AxisTarget(entry["axis_name"], entry["min"], entry["max"])

    def dump_group_axis_targets(self) -> "dict[int, dict[int, dict]]":
        """Reverse of `load_group_axis_targets`, for the Preset Store to write out.

        @spec MAP-STORE-002
        """
        bank_index_by_fader_key = {key: i + 1 for i, key in enumerate(self._profile.bank_fader_keys)}
        result: dict[int, dict[int, dict]] = {}
        for (fader_key, group), target in self._group_axis_targets.items():
            bank_index = bank_index_by_fader_key.get(fader_key)
            if bank_index is None:
                continue
            result.setdefault(bank_index, {})[group] = {
                "axis_name": target.axis_name,
                "min": target.min_value,
                "max": target.max_value,
            }
        return result

    def process(self, event: MidiEvent, now: float, axis_positions: "dict[str, float] | None" = None) -> OscMessage | None:
        """`axis_positions` is the OSC Listener's most recently observed position per
        axis name (`AxisDiscovery.axes`), if available - used to clamp Knob N's nudges
        against Dragonframe's actual reported position rather than only an internal
        estimate. Optional: faders and buttons ignore it entirely.

        @spec MAP-BANK-008
        """
        if event.type == "korg_scene":
            if not self._profile.has_scene_button:
                return None  # no Scene button on this profile (e.g. nanoKONTROL2) - @spec MAP-TABLE-001
            key: _Key = ("korg_scene", None)
            entry = self._profile.opinionated_map.get(key)
        else:
            if event.channel != self._profile.default_channel:
                return None
            key = (event.type, event.number)

            # Checked immediately after the channel-match check, before every other
            # dispatch path (including the jog wheel below) - a CC collision between
            # a Group-switch key and any other control resolves in favor of Group
            # switching (@spec MAP-GROUP-005).
            group_keys = self._profile.group_keys
            if group_keys is not None:
                if key == group_keys.previous:
                    if self._press_edge(key, event, now):
                        self._step_active_group(-1)
                    return None
                if key == group_keys.next:
                    if self._press_edge(key, event, now):
                        self._step_active_group(1)
                    return None

            if self._profile.has_jog_wheel and key == _JOG_WHEEL_KEY:
                return self._process_jog(event)

            if key in self._profile.fader_keys and self.is_axis_mode():
                axis_target = self._group_axis_targets.get((key, self._active_group))
                if axis_target is not None:
                    return self._process_axis_target(key, event, axis_target)
                return None  # axis mode, no name chosen yet - @spec MAP-AXIS-009

            fader_key = self._profile.bank_fader_key(key)
            if fader_key is not None and self.is_axis_mode():
                axis_target = self._group_axis_targets.get((fader_key, self._active_group))
                if axis_target is not None:
                    return self._process_bank_derived(key, event, now, fader_key, axis_target, axis_positions)
                # Bank's fader is in axis mode but has no name yet: falls through to
                # this control's own opinionated entry below, same as MAP-BANK-004's
                # "no axis assigned" fallback.

            entry = self._profile.opinionated_map.get(key)

        if entry is None:
            return None

        if entry.kind == "absolute":
            previous = self._previous_value.get(key)
            self._previous_value[key] = event.normalized
            if previous is not None and previous == event.normalized:
                return None
            return OscMessage(entry.address, (float(event.normalized),))

        # kind == "press"
        return self._process_press(key, event, now, entry.address, entry.args)

    def _press_edge(self, key: _Key, event: MidiEvent, now: float) -> bool:
        """Rising-edge detection with debounce (`MAP-DEBOUNCE-001`), shared by every
        press-type output regardless of whether it ends up producing an OSC message
        (`_process_press`) or a WebSocket command (`process_websocket`,
        `MAP-WS-008`) - each key belongs to exactly one of the two, so there's no
        double-consumption of this shared state. Always updates `_pressed_state`;
        returns whether this call should actually fire.
        """
        was_pressed = self._pressed_state.get(key, False)
        self._pressed_state[key] = event.is_press
        if was_pressed or not event.is_press:
            return False
        last = self._last_fired.get(key)
        if last is not None and (now - last) < DEBOUNCE_SECONDS:
            return False
        self._last_fired[key] = now
        return True

    def _process_press(self, key: _Key, event: MidiEvent, now: float, address: str, args: tuple = ()) -> OscMessage | None:
        """Fires on the rising edge (not-pressed -> pressed) only, debounced."""
        if not self._press_edge(key, event, now):
            return None
        return OscMessage(address, args)

    def _process_axis_target(self, key: _Key, event: MidiEvent, axis_target: _AxisTarget) -> OscMessage | None:
        """@spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-006"""
        previous = self._previous_value.get(key)
        self._previous_value[key] = event.normalized
        if previous is not None and previous == event.normalized:
            return None
        position = axis_target.min_value + event.normalized * (axis_target.max_value - axis_target.min_value)
        self._axis_position[key] = position
        address = f"/dragonframe/axis/{axis_target.axis_name}/gotoPosition"
        return OscMessage(address, (float(position),))

    def _process_bank_derived(
        self,
        key: _Key,
        event: MidiEvent,
        now: float,
        fader_key: _Key,
        axis_target: _AxisTarget,
        axis_positions: "dict[str, float] | None",
    ) -> OscMessage | None:
        """@spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-005, MAP-BANK-008"""
        axis_path = f"/dragonframe/axis/{axis_target.axis_name}"
        if key in self._profile.knob_to_fader:
            previous = self._previous_value.get(key)
            self._previous_value[key] = event.raw_value
            if previous is None:
                return None  # no baseline yet - this reading only establishes one
            raw_delta = event.raw_value - previous
            if raw_delta == 0:
                return None
            delta = float(raw_delta) * _KNOB_STEP_SCALE

            low, high = sorted((axis_target.min_value, axis_target.max_value))
            live_position = (axis_positions or {}).get(axis_target.axis_name)
            # Prefer Dragonframe's own last-reported position (authoritative, self-
            # correcting) over the internal estimate, which only serves as a fallback
            # for when no live reading is available yet for this axis.
            current_position = live_position if live_position is not None else self._axis_position.get(fader_key, low)
            new_position = current_position + delta
            if low <= new_position <= high:
                # Common case: no clamping needed - use the exact delta rather than
                # recovering it via position subtraction, which can reintroduce
                # floating-point error even when no clamping actually occurred.
                clamped_delta = delta
                clamped_position = new_position
            else:
                clamped_position = max(low, min(high, new_position))
                clamped_delta = clamped_position - current_position
                if clamped_delta == 0:
                    return None  # already at the boundary in the requested direction
            self._axis_position[fader_key] = clamped_position
            return OscMessage(f"{axis_path}/stepPosition", (float(clamped_delta),))
        # Mute (the only other bank-derived kind - Solo is WebSocket-targeted, MAP-WS-002)
        return self._process_press(key, event, now, f"{axis_path}/setZero")

    def _process_jog(self, event: MidiEvent) -> OscMessage | None:
        """Decodes the jog wheel's KORG sign-magnitude relative value: 1-63 is clockwise,
        65-127 is counterclockwise, 0/64 is no movement. Direction only - magnitude is
        ignored, one message is one step, with no debounce, dedup, or tracked state.

        @spec MAP-JOG-000, MAP-JOG-001, MAP-JOG-002, MAP-JOG-003, MAP-JOG-004, MAP-JOG-005
        """
        raw = event.raw_value
        if raw == 0 or raw == 64:
            return None
        if raw < 64:
            return OscMessage("/dragonframe/stepForward", ())
        return OscMessage("/dragonframe/stepBackward", ())

    def process_keystroke(self, event: MidiEvent) -> KeyCombo | None:
        """Second, independent output path alongside `process()`, for entries whose
        Dragonframe function has no OSC equivalent. Currently only the jog wheel
        produces anything - it drives Arc Motion Control's "Step Moco Forward"/"Step
        Moco Back" via their default Hot Key, since Dragonframe exposes no OSC message
        for that action. Evaluated independently of `process()`'s OSC output for the
        same event; neither suppresses the other. Stateless - allocates and consults
        no per-control state.

        @spec MAP-JOGKEY-000, MAP-JOGKEY-001, MAP-JOGKEY-002, MAP-JOGKEY-003, MAP-JOGKEY-004
        @spec MAP-JOGKEY-005, MAP-JOGKEY-006, MAP-JOGKEY-007
        """
        if not self._profile.has_jog_wheel:
            return None  # this profile has no jog wheel (e.g. nanoKONTROL2) - @spec MAP-JOGKEY-000
        if event.type != "cc" or event.number != JOG_WHEEL_CC or event.channel != self._profile.default_channel:
            return None
        raw = event.raw_value
        if raw == 0 or raw == 64:
            return None
        return _STEP_MOCO_FORWARD if raw < 64 else _STEP_MOCO_BACKWARD

    def process_websocket(self, event: MidiEvent, now: float, axis_positions: "dict[str, float] | None" = None) -> WebSocketCommand | None:
        """Third, independent output path alongside `process()`/`process_keystroke()`,
        for Stop, Cycle, Solo 1-8, and Previous/Next Marker - the WebSocket-targeted
        controls (`docs/llds/static-mapping.md § WebSocket-Targeted Controls`). Each of
        these keys is absent from `OPINIONATED_MAP`/bank derivation entirely
        (`MAP-WS-009`, `MAP-WS-002`), so `process()` never matches them; this method is
        their only output. Shares press-edge/debounce state with `process()` via
        `_press_edge` (`MAP-WS-008`).

        `axis_positions` is reused from the same `AxisDiscovery.axes` snapshot passed to
        `process()` for the same event, purely for its length (the discovered axis
        count) - Cycle uses it to wrap around, per the accepted assumption that
        Dragonframe's WebSocket-side AX1/AX2/... numbering matches OSC discovery order
        (`docs/llds/static-mapping.md`).

        @spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-004, MAP-WS-005
        @spec MAP-WS-006, MAP-WS-007, MAP-WS-008, MAP-WS-009
        """
        if event.type != "cc" or event.channel != self._profile.default_channel:
            return None
        key: _Key = (event.type, event.number)
        ws_keys = self._profile.websocket_keys

        if ws_keys is None:
            return None  # profile declares no WebSocket-targeted keys at all

        if key == ws_keys.stop:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("E-Stop")

        if key in ws_keys.solos:
            if not self._press_edge(key, event, now):
                return None
            # Group-aware as of Phase 6: Solo N in Group g addresses N + 8*(g-1)
            # (@spec MAP-WS-002, MAP-GROUP-002).
            axis_number = ws_keys.solos.index(key) + 1 + 8 * (self._active_group - 1)
            return WebSocketCommand(f"select-AX{axis_number}")

        if key == ws_keys.cycle:
            if not self._press_edge(key, event, now):
                return None
            axis_count = len(axis_positions or {})
            if axis_count == 0:
                return None  # nothing to cycle through - @spec MAP-WS-004
            self._cycle_index = (self._cycle_index + 1) % axis_count
            return WebSocketCommand(f"select-AX{self._cycle_index + 1}")

        if key == ws_keys.previous_marker:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("Jog All", operation="+", params=(-1,))

        if key == ws_keys.next_marker:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("Jog All", operation="+", params=(1,))

        return None
