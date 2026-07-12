from __future__ import annotations

from dataclasses import dataclass

from .events import MidiEvent, OscMessage

CHANNEL = 15  # zero-indexed MIDI channel 16, the nanoKONTROL Studio's Native Mode channel
DEBOUNCE_SECONDS = 0.080

_Key = tuple[str, "int | None"]


def decode_sign_magnitude(raw: int) -> int:
    """KORG sign-magnitude relative decode: 0/64 -> 0, 1-63 -> +, 65-127 -> -.

    @spec MAP-TABLE-004
    """
    if raw in (0, 64):
        return 0
    if 1 <= raw <= 63:
        return raw
    return -(raw - 64)


@dataclass(frozen=True)
class _MapEntry:
    kind: str  # "absolute" | "press" | "relative"
    address: str
    args: tuple = ()


def _fader_entries() -> dict[_Key, _MapEntry]:
    return {("cc", i): _MapEntry("absolute", f"/dragonframe/encoder/{i + 1}") for i in range(8)}


def _knob_entries() -> dict[_Key, _MapEntry]:
    return {("cc", 16 + i): _MapEntry("absolute", f"/dragonframe/encoder/{9 + i}") for i in range(8)}


def _mute_entries() -> dict[_Key, _MapEntry]:
    return {("cc", 48 + i): _MapEntry("press", f"/dragonframe/encoderReset/{i + 1}") for i in range(8)}


def _solo_entries() -> dict[_Key, _MapEntry]:
    return {("cc", 32 + i): _MapEntry("press", f"/dragonframe/encoderReset/{9 + i}") for i in range(8)}


OPINIONATED_MAP: dict[_Key, _MapEntry] = {
    **_fader_entries(),
    **_knob_entries(),
    **_mute_entries(),
    **_solo_entries(),
    ("cc", 47): _MapEntry("press", "/dragonframe/encoderReset/17"),  # Return to Zero
    ("cc", 45): _MapEntry("press", "/dragonframe/shoot", args=(1,)),  # Transport Record
    ("cc", 41): _MapEntry("press", "/dragonframe/play"),
    ("cc", 42): _MapEntry("press", "/dragonframe/live"),
    ("cc", 44): _MapEntry("press", "/dragonframe/shootVideoAssist"),
    ("cc", 46): _MapEntry("press", "/dragonframe/mute"),
    ("cc", 60): _MapEntry("press", "/dragonframe/delete"),
    ("cc", 110): _MapEntry("relative", "/dragonframe/encoder/17"),  # jog wheel
    ("korg_scene", None): _MapEntry("press", "/dragonframe/black"),
}


class MappingEngine:
    """Opinionated, hard-coded MIDI-event -> Dragonframe-OSC translator.

    @spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-004, MAP-TABLE-005
    @spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
    """

    def __init__(self) -> None:
        self._previous_value: dict[_Key, float] = {}
        self._pressed_state: dict[_Key, bool] = {}
        self._last_fired: dict[_Key, float] = {}

    def reset(self) -> None:
        self._previous_value.clear()
        self._pressed_state.clear()
        self._last_fired.clear()

    def tracked_controls(self) -> set[_Key]:
        return set(self._previous_value) | set(self._pressed_state) | set(self._last_fired)

    def process(self, event: MidiEvent, now: float) -> OscMessage | None:
        if event.type == "korg_scene":
            key: _Key = ("korg_scene", None)
            entry = OPINIONATED_MAP.get(key)
        else:
            if event.channel != CHANNEL:
                return None
            key = (event.type, event.number)
            entry = OPINIONATED_MAP.get(key)

        if entry is None:
            return None

        if entry.kind == "absolute":
            previous = self._previous_value.get(key)
            self._previous_value[key] = event.normalized
            if previous is not None and previous == event.normalized:
                return None
            return OscMessage(entry.address, (float(event.normalized),))

        if entry.kind == "relative":
            delta = decode_sign_magnitude(event.raw_value)
            if delta == 0:
                return None
            return OscMessage(entry.address, (float(delta),))

        # kind == "press": fires on the rising edge (not-pressed -> pressed) only.
        was_pressed = self._pressed_state.get(key, False)
        self._pressed_state[key] = event.is_press
        if was_pressed or not event.is_press:
            return None
        last = self._last_fired.get(key)
        if last is not None and (now - last) < DEBOUNCE_SECONDS:
            return None
        self._last_fired[key] = now
        return OscMessage(entry.address, entry.args)
