from __future__ import annotations

from dataclasses import dataclass

from .mapping import FADER_KEYS, OPINIONATED_MAP, MappingEngine, bank_fader_key

_Key = tuple[str, "int | None"]


def _numbered(prefix: str, start_cc: int, count: int) -> dict[_Key, str]:
    return {("cc", start_cc + i): f"{prefix} {i + 1}" for i in range(count)}


CONTROL_NAMES: dict[_Key, str] = {
    **_numbered("Fader Channel", 0, 8),
    ("cc", 45): "Transport Record",
    ("cc", 41): "Play",
    ("cc", 42): "Stop",
    ("cc", 46): "Cycle",
    ("cc", 43): "Rewind",
    ("cc", 44): "Fast Forward",
    ("cc", 61): "Previous Marker",
    ("cc", 62): "Next Marker",
    ("cc", 58): "Previous Track",
    ("cc", 59): "Next Track",
    ("korg_scene", None): "Scene",
}

_TRIGGER_LABELS = {"absolute": "Absolute", "press": "Press"}


def midi_source_label(key: _Key) -> str:
    kind, number = key
    if kind == "korg_scene":
        return "Native Mode Scene"
    return f"CC{number}, ch16"


def _format_bound(value: float) -> str:
    return f"{value:g}"


def _target_label(key: _Key, engine: MappingEngine) -> tuple[str, str]:
    if key in FADER_KEYS:
        if engine.is_axis_mode(key):
            axis = engine.axis_target(key)
            if axis is not None:
                bounds = f"{_format_bound(axis.min_value)}-{_format_bound(axis.max_value)}"
                return "OSC axis", f"{axis.axis_name} ({bounds})"
            return "OSC axis", ""
    entry = OPINIONATED_MAP[key]
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


def build_rows(engine: MappingEngine) -> list[RowView]:
    """One row per opinionated-map entry, in table order - except Knob/Mute/Solo
    entries, which are bank-derived and folded into their bank's Fader Channel
    row rather than shown as their own rows (their OSC dispatch is unaffected).

    @spec UI-MAP-001, UI-MAP-002
    """
    rows = []
    for key, entry in OPINIONATED_MAP.items():
        if bank_fader_key(key) is not None:
            continue  # Knob/Mute/Solo: folded into the Fader Channel row, not its own row
        target_type, target = _target_label(key, engine)
        rows.append(
            RowView(
                key=key,
                name=CONTROL_NAMES[key],
                midi_source=midi_source_label(key),
                trigger=_TRIGGER_LABELS[entry.kind],
                target_type=target_type,
                target=target,
                editable=key in FADER_KEYS,
            )
        )
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
