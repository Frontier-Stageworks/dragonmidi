"""Tests for the MIDI Input Monitor's Qt-free domain logic
(docs/specs/midi-monitor.md).

@spec MON-CAPTURE-002, MON-CAPTURE-003, MON-CAPTURE-004, MON-CAPTURE-005, MON-CAPTURE-006
@spec MON-UI-002, MON-UI-003, MON-UI-004, MON-UI-005, MON-UI-006, MON-UI-008
"""

from __future__ import annotations

from dragonmidi.events import MidiEvent
from dragonmidi.grid_controller import ModuleRef
from dragonmidi.midi_monitor import (
    MidiMonitor,
    format_channel,
    format_event_type,
    format_module,
    format_number,
    format_resolved,
)


def _cc(number: int = 36, channel: int = 0, raw_value: int = 64) -> MidiEvent:
    return MidiEvent(type="cc", channel=channel, number=number, raw_value=raw_value, normalized=raw_value / 127, is_press=False, is_release=False)


def _note(is_press: bool, velocity: int = 100) -> MidiEvent:
    return MidiEvent(type="note", channel=0, number=60, raw_value=velocity, normalized=velocity / 127, is_press=is_press, is_release=not is_press)


# --- Recording preserves raw identity (MON-CAPTURE-003) ---


def test_record_preserves_the_raw_event_exactly() -> None:
    monitor = MidiMonitor()
    raw = _cc(number=36, channel=0, raw_value=100)

    entry = monitor.record(raw, device_name="nanoKONTROL2", resolved=("grid_fader", 1), module=ModuleRef(ordinal=2, module_type="PBF4"))

    assert entry.raw is raw
    assert entry.raw.number == 36  # the wire-level CC survives even though resolved/module are also known
    assert entry.resolved == ("grid_fader", 1)
    assert entry.module == ModuleRef(ordinal=2, module_type="PBF4")
    assert entry.device_name == "nanoKONTROL2"


def test_on_record_is_invoked_synchronously_with_the_just_appended_event() -> None:
    """@spec MON-CAPTURE-009"""
    monitor = MidiMonitor()
    seen: list = []
    monitor.on_record = seen.append

    entry = monitor.record(_cc(42), device_name="X", resolved=None, module=None)

    assert seen == [entry]
    assert entry in monitor.events  # appended before the callback fires


def test_on_record_is_not_called_when_unset() -> None:
    """@spec MON-CAPTURE-009"""
    monitor = MidiMonitor()
    monitor.record(_cc(), device_name=None, resolved=None, module=None)  # must not raise with on_record left at its default None


def test_record_appends_in_order_and_is_visible_via_events() -> None:
    monitor = MidiMonitor()
    first = monitor.record(_cc(1), device_name=None, resolved=None, module=None)
    second = monitor.record(_cc(2), device_name=None, resolved=None, module=None)

    assert list(monitor.events) == [first, second]


# --- Never guesses an identity Grid hasn't confirmed (MON-CAPTURE-004, 005) ---


def test_unresolved_event_carries_no_resolved_or_module_identity() -> None:
    monitor = MidiMonitor()
    entry = monitor.record(_cc(99), device_name="Intech Grid", resolved=None, module=None)
    assert entry.resolved is None
    assert entry.module is None


# --- Bounded ring buffer (MON-CAPTURE-006) ---


def test_capacity_evicts_the_oldest_event_first() -> None:
    monitor = MidiMonitor(capacity=3)
    entries = [monitor.record(_cc(n), device_name=None, resolved=None, module=None) for n in range(5)]

    assert list(monitor.events) == entries[-3:]
    assert len(monitor.events) == 3


# --- version tracks changes so a renderer can skip idle ticks (MON-UI-008) ---


def test_version_increments_on_record_and_clear_only() -> None:
    monitor = MidiMonitor()
    v0 = monitor.version
    monitor.record(_cc(), device_name=None, resolved=None, module=None)
    v1 = monitor.version
    assert v1 != v0

    monitor.clear()
    v2 = monitor.version
    assert v2 != v1


# --- Capture Next Input: one-shot, idempotent while pending (MON-UI-005, 006) ---


def test_request_capture_next_marks_only_the_following_event() -> None:
    monitor = MidiMonitor()
    before = monitor.record(_cc(1), device_name=None, resolved=None, module=None)
    assert before.captured is False

    monitor.request_capture_next()
    captured = monitor.record(_cc(2), device_name=None, resolved=None, module=None)
    after = monitor.record(_cc(3), device_name=None, resolved=None, module=None)

    assert captured.captured is True
    assert after.captured is False
    assert monitor.last_captured is captured
    assert monitor.capture_pending is False  # consumed by the event it marked


def test_requesting_capture_next_twice_before_an_event_arrives_is_a_no_op() -> None:
    monitor = MidiMonitor()
    monitor.request_capture_next()
    monitor.request_capture_next()  # idempotent - still just "pending"
    assert monitor.capture_pending is True

    entry = monitor.record(_cc(), device_name=None, resolved=None, module=None)
    assert entry.captured is True
    assert monitor.capture_pending is False  # exactly one event consumed the request


# --- Clear empties the log but leaves diagnostic/pending state alone (MON-UI-004) ---


def test_clear_empties_the_log_without_touching_diagnostic_or_pending_state() -> None:
    monitor = MidiMonitor()
    monitor.record(_cc(), device_name=None, resolved=None, module=None)
    monitor.diagnostic_active = True
    monitor.request_capture_next()

    monitor.clear()

    assert list(monitor.events) == []
    assert monitor.last_captured is None
    assert monitor.diagnostic_active is True
    assert monitor.capture_pending is True


# --- Formatting helpers: never raise, never print Python's None (MON-UI-003) ---


def test_format_event_type_distinguishes_note_on_and_off() -> None:
    assert format_event_type(_note(is_press=True)) == "Note On"
    assert format_event_type(_note(is_press=False)) == "Note Off"
    assert format_event_type(_cc()) == "CC"


def test_format_event_type_handles_every_normalize_raw_type() -> None:
    pitchbend = MidiEvent(type="pitchbend", channel=0, number=None, raw_value=0, normalized=0.5, is_press=False, is_release=True)
    program = MidiEvent(type="program", channel=0, number=5, raw_value=5, normalized=5 / 127, is_press=True, is_release=False)
    aftertouch = MidiEvent(type="aftertouch", channel=0, number=None, raw_value=10, normalized=10 / 127, is_press=True, is_release=False)
    polytouch = MidiEvent(type="polytouch", channel=0, number=60, raw_value=10, normalized=10 / 127, is_press=True, is_release=False)
    korg_scene = MidiEvent(type="korg_scene", channel=0, number=None, raw_value=127, normalized=1.0, is_press=True, is_release=False)

    assert format_event_type(pitchbend) == "Pitch Bend"
    assert format_event_type(program) == "Program Change"
    assert format_event_type(aftertouch) == "Aftertouch"
    assert format_event_type(polytouch) == "Poly Aftertouch"
    assert format_event_type(korg_scene) == "KORG Scene"


def test_format_channel_and_number_render_a_placeholder_for_none() -> None:
    assert format_channel(None) == "-"
    assert format_number(None) == "-"
    assert format_channel(0) == "ch1"  # matches the app's existing +1 display convention
    assert format_number(36) == "36"


def test_format_module_and_resolved_render_a_placeholder_when_absent() -> None:
    assert format_module(None) == "-"
    assert format_resolved(None) == "-"
    assert format_module(ModuleRef(ordinal=2, module_type="PBF4")) == "PBF4 #2"
    assert format_resolved(("grid_fader", 3)) == "grid_fader 3"
    assert format_resolved(("grid_vsn1_jog", None)) == "grid_vsn1_jog"
