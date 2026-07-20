from __future__ import annotations

from dataclasses import dataclass

from .events import KeyCombo, MidiEvent, OscMessage, WebSocketCommand

CHANNEL = 15  # zero-indexed MIDI channel 16, the nanoKONTROL Studio's Native Mode channel
DEBOUNCE_SECONDS = 0.080

_Key = tuple[str, "int | None"]

# @spec MAP-AXIS-004
FADER_KEYS: frozenset[_Key] = frozenset(("cc", i) for i in range(8))

# @spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003
JOG_WHEEL_CC = 110
_JOG_WHEEL_KEY: _Key = ("cc", JOG_WHEEL_CC)

# @spec MAP-JOGKEY-001, MAP-JOGKEY-002
_STEP_MOCO_FORWARD = KeyCombo(frozenset({"alt", "shift"}), "right")
_STEP_MOCO_BACKWARD = KeyCombo(frozenset({"alt", "shift"}), "left")

# WebSocket-targeted controls - @spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-006, MAP-WS-007
_STOP_KEY: _Key = ("cc", 42)
_CYCLE_KEY: _Key = ("cc", 46)
_PREV_MARKER_KEY: _Key = ("cc", 61)
_NEXT_MARKER_KEY: _Key = ("cc", 62)
_SOLO_BANK_OFFSET = 32
_SOLO_KEYS: frozenset[_Key] = frozenset(("cc", _SOLO_BANK_OFFSET + i) for i in range(8))

# Bank membership: Bank N = Fader N, Knob N, Mute N (Record N/Select N excluded, no
# matching per-axis action exists for them - @spec MAP-BANK-006). Solo N is not a bank
# member here - it's an unconditional WebSocket target regardless of Fader N's axis
# state (@spec MAP-WS-002), so it's excluded from bank_fader_key()'s offsets below.
_KNOB_BANK_OFFSET = 16
_MUTE_BANK_OFFSET = 48
_KNOB_STEP_SCALE = 0.1  # axis position units per one MIDI raw-value increment


def bank_fader_key(key: _Key) -> "_Key | None":
    """Given a Knob/Mute key, return its bank's Fader key. `None` if `key`
    is not a bank member (a fader itself, Solo, a button/scene, or the jog wheel)."""
    kind, number = key
    if kind != "cc" or number is None:
        return None
    for offset in (_KNOB_BANK_OFFSET, _MUTE_BANK_OFFSET):
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


# Stop, Cycle, Solo 1-8, and Previous/Next Marker are WebSocket-targeted
# (process_websocket(), @spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-006, MAP-WS-007)
# and deliberately absent from this table - @spec MAP-WS-009.
OPINIONATED_MAP: dict[_Key, _MapEntry] = {
    **_fader_entries(),
    **_knob_entries(),
    **_mute_entries(),
    ("cc", 45): _MapEntry("press", "/dragonframe/shoot", args=(1,)),  # Transport Record
    ("cc", 41): _MapEntry("press", "/dragonframe/play"),
    ("cc", 43): _MapEntry("press", "/dragonframe/stepBackward"),  # Rewind (<<)
    ("cc", 44): _MapEntry("press", "/dragonframe/stepForward"),  # Fast Forward (>>)
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
    @spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-004, MAP-BANK-005, MAP-BANK-006, MAP-BANK-007
    @spec MAP-BANK-008
    @spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003, MAP-JOG-004, MAP-JOG-005
    @spec MAP-JOGKEY-001, MAP-JOGKEY-002, MAP-JOGKEY-003, MAP-JOGKEY-004, MAP-JOGKEY-005
    @spec MAP-JOGKEY-006, MAP-JOGKEY-007
    @spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-004, MAP-WS-005, MAP-WS-006
    @spec MAP-WS-007, MAP-WS-008, MAP-WS-009
    """

    def __init__(self) -> None:
        self._previous_value: dict[_Key, float] = {}
        self._pressed_state: dict[_Key, bool] = {}
        self._last_fired: dict[_Key, float] = {}
        self._axis_targets: dict[_Key, _AxisTarget] = {}
        # Faders explicitly switched to OSC encoder mode; absence = OSC axis mode (the
        # default - @spec MAP-AXIS-008).
        self._encoder_mode: set[_Key] = set()
        # Fallback estimate of each fader's axis's current absolute position, keyed by
        # fader key, built entirely from DragonMIDI's own sends. Used to clamp Knob N's
        # cumulative nudges to the fader's [min, max] range only when no live position
        # reading is available from Dragonframe (see `process`'s `axis_positions` param)
        # (@spec MAP-BANK-008).
        self._axis_position: dict[_Key, float] = {}
        # Cycle's last-selected axis index, -1 = nothing selected yet (@spec MAP-WS-005).
        self._cycle_index: int = -1

    def reset(self) -> None:
        self._previous_value.clear()
        self._pressed_state.clear()
        self._last_fired.clear()
        self._cycle_index = -1

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
        self._axis_position.pop(key, None)

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
        # A new axis name (or new min/max) invalidates any tracked position estimate,
        # even without a mode transition - it may be a different axis entirely.
        self._axis_position.pop(key, None)

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
        self._axis_position.pop(key, None)
        if not was_encoder_mode:
            self._discard_bank_knob_dedup(key)

    def process(self, event: MidiEvent, now: float, axis_positions: "dict[str, float] | None" = None) -> OscMessage | None:
        """`axis_positions` is the OSC Listener's most recently observed position per
        axis name (`AxisDiscovery.axes`), if available - used to clamp Knob N's nudges
        against Dragonframe's actual reported position rather than only an internal
        estimate. Optional: faders and buttons ignore it entirely.

        @spec MAP-BANK-008
        """
        if event.type == "korg_scene":
            key: _Key = ("korg_scene", None)
            entry = OPINIONATED_MAP.get(key)
        else:
            if event.channel != CHANNEL:
                return None
            key = (event.type, event.number)

            if key == _JOG_WHEEL_KEY:
                return self._process_jog(event)

            if key in FADER_KEYS and self.is_axis_mode(key):
                axis_target = self._axis_targets.get(key)
                if axis_target is not None:
                    return self._process_axis_target(key, event, axis_target)
                return None  # axis mode, no name chosen yet - @spec MAP-AXIS-009

            fader_key = bank_fader_key(key)
            if fader_key is not None and self.is_axis_mode(fader_key):
                axis_target = self._axis_targets.get(fader_key)
                if axis_target is not None:
                    return self._process_bank_derived(key, event, now, fader_key, axis_target, axis_positions)
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

        @spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003, MAP-JOG-004, MAP-JOG-005
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

        @spec MAP-JOGKEY-001, MAP-JOGKEY-002, MAP-JOGKEY-003, MAP-JOGKEY-004
        @spec MAP-JOGKEY-005, MAP-JOGKEY-006, MAP-JOGKEY-007
        """
        if event.type != "cc" or event.number != JOG_WHEEL_CC or event.channel != CHANNEL:
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
        if event.type != "cc" or event.channel != CHANNEL:
            return None
        key: _Key = (event.type, event.number)

        if key == _STOP_KEY:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("E-Stop")

        if key in _SOLO_KEYS:
            if not self._press_edge(key, event, now):
                return None
            axis_number = event.number - _SOLO_BANK_OFFSET + 1
            return WebSocketCommand(f"select-AX{axis_number}")

        if key == _CYCLE_KEY:
            if not self._press_edge(key, event, now):
                return None
            axis_count = len(axis_positions or {})
            if axis_count == 0:
                return None  # nothing to cycle through - @spec MAP-WS-004
            self._cycle_index = (self._cycle_index + 1) % axis_count
            return WebSocketCommand(f"select-AX{self._cycle_index + 1}")

        if key == _PREV_MARKER_KEY:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("Jog All", operation="+", params=(-1,))

        if key == _NEXT_MARKER_KEY:
            if not self._press_edge(key, event, now):
                return None
            return WebSocketCommand("Jog All", operation="+", params=(1,))

        return None
