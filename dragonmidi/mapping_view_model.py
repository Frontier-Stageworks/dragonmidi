from __future__ import annotations

from dataclasses import dataclass

from .mapping import JOG_WHEEL_CC, MappingEngine

_Key = tuple[str, "int | None"]

# @spec UI-MAP-012
JOG_WHEEL_ROW_KEY: _Key = ("cc", JOG_WHEEL_CC)
JOG_WHEEL_ARC_ROW_KEY: _Key = ("jog_wheel_keystroke", None)

_TRIGGER_LABELS = {"absolute": "Absolute", "press": "Press"}


def midi_source_label(key: _Key, channel: int) -> str:
    """@spec UI-MAP-012, UI-MAP-013"""
    kind, number = key
    if kind == "korg_scene":
        return "Native Mode Scene"
    return f"CC{number}, ch{channel + 1}"


def _format_bound(value: float) -> str:
    return f"{value:g}"


def _target_label(key: _Key, engine: MappingEngine) -> tuple[str, str]:
    if key in engine.profile.fader_keys:
        if engine.is_axis_mode(key):
            axis = engine.axis_target(key)
            if axis is not None:
                bounds = f"{_format_bound(axis.min_value)}-{_format_bound(axis.max_value)}"
                return "OSC axis", f"{axis.axis_name} ({bounds})"
            return "OSC axis", ""
    entry = engine.profile.opinionated_map[key]
    if entry.address.startswith("/dragonframe/encoderReset/"):
        return "OSC encoder", f"Reset encoder {entry.address.rsplit('/', 1)[-1]}"
    if entry.address.startswith("/dragonframe/encoder/"):
        return "OSC encoder", f"Encoder {entry.address.rsplit('/', 1)[-1]}"
    return "OSC action", entry.address


@dataclass(frozen=True)
class RowView:
    key: _Key
    name: str
    midi_source: str
    trigger: str
    target_type: str
    target: str
    editable: bool


def _jog_wheel_rows(channel: int) -> list[RowView]:
    """The jog wheel isn't an OPINIONATED_MAP entry - its dispatch is special-cased
    in MappingEngine.process()/process_keystroke() (docs/llds/static-mapping.md
    § Jog Wheel Frame Stepping). It has two independent, fixed outputs, so it's
    shown as two read-only rows rather than stretching one row to hold two
    targets or adding a column that's empty for every other control. Only called
    for a profile with has_jog_wheel true (see build_rows below); a profile
    without one (the nanoKONTROL2) renders neither row.

    @spec UI-MAP-012
    """
    midi_source = midi_source_label(JOG_WHEEL_ROW_KEY, channel)
    return [
        RowView(
            key=JOG_WHEEL_ROW_KEY,
            name="Jog Wheel",
            midi_source=midi_source,
            trigger="Directional",
            target_type="OSC action",
            target="stepForward / stepBackward",
            editable=False,
        ),
        RowView(
            key=JOG_WHEEL_ARC_ROW_KEY,
            name="Jog Wheel (Arc)",
            midi_source=midi_source,
            trigger="Directional",
            target_type="Keystroke",
            target="Option+Shift+Right / Option+Shift+Left",
            editable=False,
        ),
    ]


_SOLO_ROW_KEY: _Key = ("solo_websocket", None)  # not a real MIDI key - one summary row for all 8 Solo CCs


def _websocket_target_rows(engine: MappingEngine) -> list[RowView]:
    """Stop, Cycle, Solo 1-8, and Previous/Next Marker target the WebSocket Output
    Adapter (docs/llds/websocket-output.md), not OSC. Stop/Cycle/Marker were removed
    from OPINIONATED_MAP entirely (MAP-WS-009) and Solo was removed from bank
    derivation (MAP-WS-002), so none of them are reachable via build_rows()'s
    opinionated-map loop below - rendered as fixed rows here instead, the same
    treatment as the jog wheel's rows for entries that aren't table lookups. Solo
    gets one summary row for all 8 buttons, not eight near-identical rows and not
    folded into the fader rows (docs/llds/app-ui.md § Mapping View). Present for any
    profile that declares these keys (`ControllerProfile.websocket_keys`) - a profile
    that omits one (e.g. no `cycle` in its `controls:` block) simply has no row for
    it, the same "absent, not disabled" treatment used elsewhere.

    @spec UI-MAP-001, UI-MAP-013, MAP-CONFIG-005
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
                trigger="Press",
                target_type="WebSocket",
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
                trigger="Press",
                target_type="WebSocket",
                target="select-AXn (cycling)",
                editable=False,
            )
        )
    if ws_keys.solos:
        solo_ccs = sorted(number for _, number in ws_keys.solos)
        rows.append(
            RowView(
                key=_SOLO_ROW_KEY,
                name="Solo 1-8",
                midi_source=f"CC{solo_ccs[0]}-{solo_ccs[-1]}, ch{channel + 1}",
                trigger="Press",
                target_type="WebSocket",
                target="select-AX1 – select-AX8 (button N → AXN)",
                editable=False,
            )
        )
    if ws_keys.previous_marker is not None:
        rows.append(
            RowView(
                key=ws_keys.previous_marker,
                name="Previous Marker",
                midi_source=midi_source_label(ws_keys.previous_marker, channel),
                trigger="Press",
                target_type="WebSocket",
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
                trigger="Press",
                target_type="WebSocket",
                target="Jog All (forward)",
                editable=False,
            )
        )
    return rows


def build_rows(engine: MappingEngine) -> list[RowView]:
    """One row per entry in the active Controller Profile's opinionated map, in
    table order - except Knob/Mute entries, which are bank-derived and folded into
    their bank's Fader Channel row rather than shown as their own rows (their OSC
    dispatch is unaffected) - plus the WebSocket-targeted rows (UI-MAP-013) and,
    only for a profile with a jog wheel, two further rows for it (UI-MAP-012),
    both appended last. A profile without a Scene button or jog wheel simply has
    no such entry/rows to render - not a disabled placeholder, an absence.

    @spec UI-MAP-001, UI-MAP-002, UI-MAP-012, UI-MAP-013
    """
    profile = engine.profile
    channel = profile.default_channel
    rows = []
    for key, entry in profile.opinionated_map.items():
        if profile.bank_fader_key(key) is not None:
            continue  # Knob/Mute: folded into the Fader Channel row, not its own row
        target_type, target = _target_label(key, engine)
        rows.append(
            RowView(
                key=key,
                name=profile.control_names[key],
                midi_source=midi_source_label(key, channel),
                trigger=_TRIGGER_LABELS[entry.kind],
                target_type=target_type,
                target=target,
                editable=key in profile.fader_keys,
            )
        )
    rows.extend(_websocket_target_rows(engine))
    if profile.has_jog_wheel:
        rows.extend(_jog_wheel_rows(channel))
    return rows


@dataclass(frozen=True)
class AxisPickerState:
    enabled: bool
    placeholder: "str | None"
    candidates: tuple[str, ...]
    current: "str | None"


def axis_picker_state(configured_name: "str | None", axes: "dict[str, float] | None") -> AxisPickerState:
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


def parse_axis_field(text: str) -> "float | None":
    """@spec UI-MAP-007"""
    try:
        return float(text)
    except ValueError:
        return None
