from __future__ import annotations

from dataclasses import dataclass

from .mapping import JOG_WHEEL_CC, MappingEngine

_Key = tuple[str, "int | None"]

# @spec UI-MAP-001, UI-CFGDLG-008
JOG_WHEEL_ROW_KEY: _Key = ("cc", JOG_WHEEL_CC)
JOG_WHEEL_ARC_ROW_KEY: _Key = ("jog_wheel_keystroke", None)
KNOB_ROW_KEY: _Key = ("knob_summary", None)
MUTE_ROW_KEY: _Key = ("mute_summary", None)
SOLO_ROW_KEY: _Key = ("solo_websocket", None)  # not a real MIDI key - one summary row for all 8 Solo CCs


def midi_source_label(key: _Key, channel: int) -> str:
    """@spec UI-MAP-001, UI-CFGDLG-002"""
    kind, number = key
    if kind == "korg_scene":
        return "Native Mode Scene"
    return f"CC{number}, ch{channel + 1}"


def cc_range_label(keys, channel: int) -> str:
    numbers = sorted(number for _, number in keys)
    return f"CC{numbers[0]}-{numbers[-1]}, ch{channel + 1}"


@dataclass(frozen=True)
class RowView:
    key: _Key
    name: str
    midi_source: str
    target: str
    editable: bool


def build_fader_rows(engine: MappingEngine) -> list[RowView]:
    """The Mapping View's only content as of 2026-07-23: one row per Bank's fader,
    in Bank order, every row editable. The Target cell's actual content (the 5-Group
    axis-picker grid) isn't carried on the row itself - the widget queries
    `group_axis_picker_states`/`MappingEngine.axis_target` directly, live, on every
    tick, the same as before.

    @spec UI-MAP-001, UI-MAP-002
    """
    profile = engine.profile
    channel = profile.default_channel
    return [
        RowView(
            key=key,
            name=profile.control_names[key],
            midi_source=midi_source_label(key, channel),
            target="",
            editable=True,
        )
        for key in profile.bank_fader_keys
    ]


def _bank_summary_rows(engine: MappingEngine) -> list[RowView]:
    """Knob (pot) and Mute: one collapsed row each describing the shared
    bank-derived rule, not one row per Bank - generalizing Solo's pre-existing
    single-row treatment (2026-07-23, `docs/llds/app-ui.md § Configuration Dialog`).
    Their text is a static fact about the shared rule (the exact encoder/reset
    channel numbers are a fixed convention independent of CC assignment), not a
    live per-Bank value, so - unlike Solo below - it is not recomputed per Group.

    @spec UI-CFGDLG-006
    """
    profile = engine.profile
    channel = profile.default_channel
    rows: list[RowView] = []
    if profile.knob_to_fader:
        rows.append(
            RowView(
                key=KNOB_ROW_KEY,
                name="Knob (pot)",
                midi_source=cc_range_label(profile.knob_to_fader, channel),
                target="Bank-derived: follows fader's axis, or Encoder 9-16 if unassigned",
                editable=False,
            )
        )
    if profile.mute_to_fader:
        rows.append(
            RowView(
                key=MUTE_ROW_KEY,
                name="Mute",
                midi_source=cc_range_label(profile.mute_to_fader, channel),
                target="Bank-derived: setZero on assigned axis, or Reset encoder 1-8",
                editable=False,
            )
        )
    return rows


def _jog_wheel_rows(channel: int) -> list[RowView]:
    """The jog wheel isn't an OPINIONATED_MAP entry - its dispatch is special-cased
    in MappingEngine.process()/process_keystroke() (docs/llds/static-mapping.md
    § Jog Wheel Frame Stepping). It has two independent, fixed outputs, so it's
    shown as two read-only rows rather than stretching one row to hold two
    targets or adding a column that's empty for every other control. Only called
    for a profile with has_jog_wheel true (see build_configuration_rows below); a
    profile without one (the nanoKONTROL2) renders neither row.

    @spec UI-CFGDLG-008
    """
    midi_source = midi_source_label(JOG_WHEEL_ROW_KEY, channel)
    return [
        RowView(
            key=JOG_WHEEL_ROW_KEY,
            name="Jog Wheel",
            midi_source=midi_source,
            target="stepForward / stepBackward",
            editable=False,
        ),
        RowView(
            key=JOG_WHEEL_ARC_ROW_KEY,
            name="Jog Wheel (Arc)",
            midi_source=midi_source,
            target="Option+Shift+Right / Option+Shift+Left",
            editable=False,
        ),
    ]


def _websocket_target_rows(engine: MappingEngine) -> list[RowView]:
    """Stop, Cycle, Solo 1-8, and Previous/Next Marker target the WebSocket Output
    Adapter (docs/llds/websocket-output.md), not OSC. Present for any profile that
    declares these keys (`ControllerProfile.websocket_keys`) - a profile that omits
    one simply has no row for it, the same "absent, not disabled" treatment used
    elsewhere.

    @spec UI-CFGDLG-002, MAP-CONFIG-005
    """
    channel = engine.profile.default_channel
    ws_keys = engine.profile.websocket_keys
    rows: list[RowView] = []
    if ws_keys is None:
        return rows

    if ws_keys.stop is not None:
        rows.append(
            RowView(
                key=ws_keys.stop,
                name="Stop",
                midi_source=midi_source_label(ws_keys.stop, channel),
                target="E-Stop",
                editable=False,
            )
        )
    if ws_keys.cycle is not None:
        rows.append(
            RowView(
                key=ws_keys.cycle,
                name="Cycle",
                midi_source=midi_source_label(ws_keys.cycle, channel),
                target="select-AXn (cycling)",
                editable=False,
            )
        )
    if ws_keys.solos:
        g = engine.active_group
        low, high = 1 + 8 * (g - 1), 8 + 8 * (g - 1)
        rows.append(
            RowView(
                key=SOLO_ROW_KEY,
                name="Solo 1-8",
                midi_source=cc_range_label(ws_keys.solos, channel),
                # Recomputed every call from the active Group (@spec MAP-GROUP-002) -
                # "button N -> AXN" phrasing dropped in favor of the plain Group
                # number, avoiding an awkward "+0" term at Group 1.
                target=f"select-AX{low} – select-AX{high} (Group {g})",
                editable=False,
            )
        )
    if ws_keys.previous_marker is not None:
        rows.append(
            RowView(
                key=ws_keys.previous_marker,
                name="Previous Marker",
                midi_source=midi_source_label(ws_keys.previous_marker, channel),
                target="Jog All (backward)",
                editable=False,
            )
        )
    if ws_keys.next_marker is not None:
        rows.append(
            RowView(
                key=ws_keys.next_marker,
                name="Next Marker",
                midi_source=midi_source_label(ws_keys.next_marker, channel),
                target="Jog All (forward)",
                editable=False,
            )
        )
    return rows


_GROUP_SWITCH_TARGETS = {
    "previous": "Previous (wraps 5→1)",
    "next": "Next (wraps 5→1)",
}


def _group_switch_rows(engine: MappingEngine) -> list[RowView]:
    """Previous/Next Track are not `OPINIONATED_MAP` entries as of Phase 6
    (`MAP-GROUP-003`) - rendered as fixed rows here instead, the same treatment
    `_websocket_target_rows`/`_jog_wheel_rows` already give entries that aren't
    table lookups. Present for whichever direction(s) the active profile's
    `group_keys` declares.

    @spec UI-CFGDLG-009
    """
    channel = engine.profile.default_channel
    group_keys = engine.profile.group_keys
    rows: list[RowView] = []
    if group_keys is None:
        return rows

    if group_keys.previous is not None:
        rows.append(
            RowView(
                key=group_keys.previous,
                name="Previous Track",
                midi_source=midi_source_label(group_keys.previous, channel),
                target=_GROUP_SWITCH_TARGETS["previous"],
                editable=False,
            )
        )
    if group_keys.next is not None:
        rows.append(
            RowView(
                key=group_keys.next,
                name="Next Track",
                midi_source=midi_source_label(group_keys.next, channel),
                target=_GROUP_SWITCH_TARGETS["next"],
                editable=False,
            )
        )
    return rows


def build_configuration_rows(engine: MappingEngine) -> list[RowView]:
    """The Configuration Dialog's rows (2026-07-23): every control's assignment
    that isn't the Fader row itself (handled specially by the widget, since it
    hosts the single engine-wide Axis/Encoder switch rather than a RowView) - one
    collapsed row each for Knob (pot), Mute, and Solo, plus every single-instance
    control (Play, Record, Rewind, Fast Forward, Scene, Stop, Cycle, Previous/Next
    Marker, the jog wheel, Previous/Next Track), unchanged in content from the
    pre-2026-07-23 Mapping View, just relocated. None of these rows are editable.

    @spec UI-CFGDLG-002, UI-CFGDLG-006, UI-CFGDLG-007, UI-CFGDLG-008, UI-CFGDLG-009
    """
    profile = engine.profile
    channel = profile.default_channel
    rows: list[RowView] = list(_bank_summary_rows(engine))
    for key, entry in profile.opinionated_map.items():
        if key in profile.fader_keys or profile.bank_fader_key(key) is not None:
            continue  # Fader (main window) / Knob & Mute (collapsed above)
        rows.append(
            RowView(
                key=key,
                name=profile.control_names[key],
                midi_source=midi_source_label(key, channel),
                target=entry.address,
                editable=False,
            )
        )
    rows.extend(_websocket_target_rows(engine))
    if profile.has_jog_wheel:
        rows.extend(_jog_wheel_rows(channel))
    rows.extend(_group_switch_rows(engine))
    return rows


@dataclass(frozen=True)
class AxisPickerState:
    enabled: bool
    placeholder: str | None
    candidates: tuple[str, ...]
    current: str | None


def axis_picker_state(configured_name: str | None, axes: dict[str, float] | None) -> AxisPickerState:
    """Renders the axis-name picker's three discovery states, always carrying
    the row's configured name through as `current` regardless of whether it's
    still a live candidate.

    @spec UI-MAP-004, UI-MAP-005, UI-MAP-008
    """
    if axes is None:
        return AxisPickerState(enabled=False, placeholder="Discovering…", candidates=(), current=configured_name)
    if not axes:
        return AxisPickerState(enabled=False, placeholder="No axes found", candidates=(), current=configured_name)
    return AxisPickerState(enabled=True, placeholder=None, candidates=tuple(sorted(axes)), current=configured_name)


def group_axis_picker_states(engine: MappingEngine, key: _Key, axes: dict[str, float] | None) -> tuple[AxisPickerState, ...]:
    """The 5 per-Group axis-picker states for one fader row (leftmost = Group 1).
    All 5 share the same discovered-name candidate list, since axis discovery is
    project-wide, not per-Group - only each picker's `current` selection varies.
    Independent of the engine-wide fader mode (`UI-MAP-018`): the grid always
    reflects the stored (Bank, Group) table regardless of whether `process()` is
    currently consulting it.

    @spec UI-MAP-014
    """
    return tuple(
        axis_picker_state(
            configured_name=(target.axis_name if (target := engine.axis_target(key, group)) is not None else None),
            axes=axes,
        )
        for group in range(1, 6)
    )


def active_group_lights(engine: MappingEngine) -> tuple[bool, ...]:
    """5 booleans, one per Group (leftmost = Group 1) - True for the currently
    active Group, False for every other. Recomputed fresh on every call, the same
    "no cached state" pattern as `build_fader_rows`/`axis_picker_state`.

    @spec UI-MAP-015
    """
    return tuple(group == engine.active_group for group in range(1, 6))


def parse_axis_field(text: str) -> float | None:
    """@spec UI-MAP-007"""
    try:
        return float(text)
    except ValueError:
        return None
