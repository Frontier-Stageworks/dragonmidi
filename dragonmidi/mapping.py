from __future__ import annotations

from dataclasses import dataclass

from .events import MidiEvent, OscMessage

CHANNEL = 15  # zero-indexed MIDI channel 16, the nanoKONTROL Studio's Native Mode channel
DEBOUNCE_SECONDS = 0.080

_Key = tuple[str, "int | None"]

# @spec MAP-AXIS-004
FADER_KEYS: frozenset[_Key] = frozenset(("cc", i) for i in range(8))

# Bank membership: Bank N = Fader N, Knob N, Mute N, Solo N (Record N/Select N excluded, no
# matching per-axis OSC action exists for them - @spec MAP-BANK-006).
_KNOB_BANK_OFFSET = 16
_MUTE_BANK_OFFSET = 48
_SOLO_BANK_OFFSET = 32
_KNOB_STEP_SCALE = 0.1  # axis position units per one MIDI raw-value increment


def bank_fader_key(key: _Key) -> "_Key | None":
    """Given a Knob/Mute/Solo key, return its bank's Fader key. `None` if `key`
    is not a bank member (a fader itself, a button/scene, or the jog wheel)."""
    kind, number = key
    if kind != "cc" or number is None:
        return None
    for offset in (_KNOB_BANK_OFFSET, _MUTE_BANK_OFFSET, _SOLO_BANK_OFFSET):
        if offset <= number < offset + 8:
            return ("cc", number - offset)
    return None


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
    ("cc", 45): _MapEntry("press", "/dragonframe/shoot", args=(1,)),  # Transport Record
    ("cc", 41): _MapEntry("press", "/dragonframe/play"),
    ("cc", 42): _MapEntry("press", "/dragonframe/live"),
    ("cc", 46): _MapEntry("press", "/dragonframe/loop"),  # Cycle
    ("cc", 43): _MapEntry("press", "/dragonframe/stepBackward"),  # Rewind (<<)
    ("cc", 44): _MapEntry("press", "/dragonframe/stepForward"),  # Fast Forward (>>)
    ("cc", 61): _MapEntry("press", "/dragonframe/stepBackward"),  # Previous Marker
    ("cc", 62): _MapEntry("press", "/dragonframe/stepForward"),  # Next Marker
    ("cc", 58): _MapEntry("press", "/dragonframe/stepBackward"),  # Previous Track
    ("cc", 59): _MapEntry("press", "/dragonframe/stepForward"),  # Next Track
    ("korg_scene", None): _MapEntry("press", "/dragonframe/black"),
}


class MappingEngine:
    """Opinionated, hard-coded MIDI-event -> Dragonframe-OSC translator.

    @spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-005
    @spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
    @spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-004, MAP-AXIS-006, MAP-AXIS-007
    @spec MAP-AXIS-008, MAP-AXIS-009, MAP-AXIS-010
    @spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-003, MAP-BANK-004, MAP-BANK-005, MAP-BANK-006, MAP-BANK-007
    """

    def __init__(self) -> None:
        self._previous_value: dict[_Key, float] = {}
        self._pressed_state: dict[_Key, bool] = {}
        self._last_fired: dict[_Key, float] = {}
        self._axis_targets: dict[_Key, _AxisTarget] = {}
        # Faders explicitly switched to OSC encoder mode; absence = OSC axis mode (the
        # default - @spec MAP-AXIS-008).
        self._encoder_mode: set[_Key] = set()

    def reset(self) -> None:
        self._previous_value.clear()
        self._pressed_state.clear()
        self._last_fired.clear()

    def tracked_controls(self) -> set[_Key]:
        return set(self._previous_value) | set(self._pressed_state) | set(self._last_fired)

    def is_axis_mode(self, key: _Key) -> bool:
        """@spec MAP-AXIS-010"""
        return key not in self._encoder_mode

    def _discard_bank_knob_dedup(self, fader_key: _Key) -> None:
        """@spec MAP-BANK-007"""
        knob_key = ("cc", fader_key[1] + _KNOB_BANK_OFFSET)
        self._previous_value.pop(knob_key, None)

    def enter_axis_mode(self, key: _Key) -> None:
        """Switch a fader into OSC axis (direct) mode without selecting a name yet.
        A no-op if already in axis mode.

        @spec MAP-AXIS-010
        """
        if key not in FADER_KEYS:
            raise ValueError(f"OSC axis (direct) mode is only available for fader controls, got {key!r}")
        was_encoder_mode = key in self._encoder_mode
        self._encoder_mode.discard(key)
        if was_encoder_mode:
            self._discard_bank_knob_dedup(key)

    def set_axis_target(self, key: _Key, axis_name: str, min_value: float, max_value: float) -> None:
        """Retarget a fader to send gotoPosition to a named Dragonframe axis.

        @spec MAP-AXIS-002, MAP-AXIS-004
        """
        if key not in FADER_KEYS:
            raise ValueError(f"OSC axis (direct) target is only available for fader controls, got {key!r}")
        was_encoder_mode = key in self._encoder_mode
        self._encoder_mode.discard(key)
        if was_encoder_mode:
            self._discard_bank_knob_dedup(key)
        self._axis_targets[key] = _AxisTarget(axis_name, min_value, max_value)
        # Switching target discards prior dedup state for this key (LLD: "switching a
        # mapping entry's target type discards the previous target's configuration").
        self._previous_value.pop(key, None)

    def axis_target(self, key: _Key) -> _AxisTarget | None:
        """Read-only lookup of a fader's current OSC axis (direct) target, if any."""
        return self._axis_targets.get(key)

    def clear_axis_target(self, key: _Key) -> None:
        """Revert a fader from its OSC axis (direct) target back to its opinionated
        OSC encoder channel target. A no-op if the key has no axis target set.

        @spec MAP-AXIS-007
        """
        was_encoder_mode = key in self._encoder_mode
        self._encoder_mode.add(key)
        self._axis_targets.pop(key, None)
        self._previous_value.pop(key, None)
        if not was_encoder_mode:
            self._discard_bank_knob_dedup(key)

    def process(self, event: MidiEvent, now: float) -> OscMessage | None:
        if event.type == "korg_scene":
            key: _Key = ("korg_scene", None)
            entry = OPINIONATED_MAP.get(key)
        else:
            if event.channel != CHANNEL:
                return None
            key = (event.type, event.number)

            if key in FADER_KEYS and self.is_axis_mode(key):
                axis_target = self._axis_targets.get(key)
                if axis_target is not None:
                    return self._process_axis_target(key, event, axis_target)
                return None  # axis mode, no name chosen yet - @spec MAP-AXIS-009

            fader_key = bank_fader_key(key)
            if fader_key is not None and self.is_axis_mode(fader_key):
                axis_target = self._axis_targets.get(fader_key)
                if axis_target is not None:
                    return self._process_bank_derived(key, event, now, axis_target)
                # Bank's fader is in axis mode but has no name yet: falls through to
                # this control's own opinionated entry below, same as MAP-BANK-004's
                # "no axis assigned" fallback.

            entry = OPINIONATED_MAP.get(key)

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

    def _process_press(
        self, key: _Key, event: MidiEvent, now: float, address: str, args: tuple = ()
    ) -> OscMessage | None:
        """Fires on the rising edge (not-pressed -> pressed) only, debounced."""
        was_pressed = self._pressed_state.get(key, False)
        self._pressed_state[key] = event.is_press
        if was_pressed or not event.is_press:
            return None
        last = self._last_fired.get(key)
        if last is not None and (now - last) < DEBOUNCE_SECONDS:
            return None
        self._last_fired[key] = now
        return OscMessage(address, args)

    def _process_axis_target(self, key: _Key, event: MidiEvent, axis_target: _AxisTarget) -> OscMessage | None:
        """@spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-006"""
        previous = self._previous_value.get(key)
        self._previous_value[key] = event.normalized
        if previous is not None and previous == event.normalized:
            return None
        position = axis_target.min_value + event.normalized * (axis_target.max_value - axis_target.min_value)
        address = f"/dragonframe/axis/{axis_target.axis_name}/gotoPosition"
        return OscMessage(address, (float(position),))

    def _process_bank_derived(
        self, key: _Key, event: MidiEvent, now: float, axis_target: _AxisTarget
    ) -> OscMessage | None:
        """@spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-003, MAP-BANK-005"""
        _, number = key
        axis_path = f"/dragonframe/axis/{axis_target.axis_name}"
        if _KNOB_BANK_OFFSET <= number < _KNOB_BANK_OFFSET + 8:
            previous = self._previous_value.get(key)
            self._previous_value[key] = event.raw_value
            if previous is None:
                return None  # no baseline yet - this reading only establishes one
            raw_delta = event.raw_value - previous
            if raw_delta == 0:
                return None
            return OscMessage(f"{axis_path}/stepPosition", (float(raw_delta) * _KNOB_STEP_SCALE,))
        if _MUTE_BANK_OFFSET <= number < _MUTE_BANK_OFFSET + 8:
            return self._process_press(key, event, now, f"{axis_path}/setZero")
        # Solo
        return self._process_press(key, event, now, f"{axis_path}/setHome")
