"""Tests for the MIDI Input Adapter (docs/specs/midi-input.md).

@spec MIDI-CONN-001, MIDI-CONN-002, MIDI-CONN-003, MIDI-CONN-004, MIDI-CONN-005
@spec MIDI-CONN-006, MIDI-CONN-007
@spec MIDI-NATIVE-001, MIDI-NATIVE-002, MIDI-NATIVE-003, MIDI-NATIVE-004
@spec MIDI-EVT-001, MIDI-EVT-003, MIDI-EVT-004
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Callable

from hypothesis import example, given
from hypothesis import strategies as st

from dragonmidi.midi_input import MidiInputAdapter, is_nanokontrol_studio, native_mode_message, normalize_raw


# ---------------------------------------------------------------------------
# Fuzzy device-name matching
# ---------------------------------------------------------------------------

TARGET = "nanoKONTROL Studio"
SEPARATORS = ["", " ", "-", "_", "  "]
UNRELATED_NAMES = [
    "Launchpad Mini MK3",
    "Komplete Kontrol S49",
    "USB MIDI Device",
    "",
    "IAC Driver Bus 1",
    "nanoKEY Studio",  # deliberately close but not a match: no "kontrol"
]


@given(
    prefix=st.sampled_from(["", "KORG ", "korg "]),
    sep1=st.sampled_from(SEPARATORS),
    casing=st.sampled_from([str.lower, str.upper, str.title, lambda s: s]),
    suffix=st.sampled_from(["", " SLIDER/KNOB", " Port 1", "-1"]),
)
# @spec MIDI-CONN-002
def test_real_device_name_variants_all_match(prefix, sep1, casing, suffix) -> None:
    name = f"{prefix}nano{sep1}KONTROL{sep1}Studio{suffix}"
    name = casing(name)
    assert is_nanokontrol_studio(name)


@given(name=st.sampled_from(UNRELATED_NAMES))
# @spec MIDI-CONN-002
def test_unrelated_device_names_never_match(name: str) -> None:
    assert not is_nanokontrol_studio(name)


@given(name=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=30))
@example("")
# @spec MIDI-CONN-002
def test_random_strings_without_the_target_substring_never_match(name: str) -> None:
    import re

    normalized = re.sub(r"[^a-z0-9]+", "", name.lower())
    if "nanokontrolstudio" in normalized:
        return  # hypothesis got unlucky and generated a real match; not a counterexample
    assert not is_nanokontrol_studio(name)


# ---------------------------------------------------------------------------
# Native Mode SysEx builder
# ---------------------------------------------------------------------------

@given(channel=st.integers(min_value=0, max_value=15), enter=st.booleans())
# @spec MIDI-NATIVE-001, MIDI-NATIVE-002
def test_native_mode_message_encodes_channel_and_direction(channel: int, enter: bool) -> None:
    data = native_mode_message(channel, enter)
    assert data[1] & 0xF0 == 0x40
    assert data[1] & 0x0F == channel
    assert data[-1] == (1 if enter else 0)


@given(channel=st.integers(min_value=0, max_value=15))
# @spec MIDI-NATIVE-001, MIDI-NATIVE-002
def test_native_mode_enter_and_exit_differ_only_in_last_byte(channel: int) -> None:
    enter_msg = native_mode_message(channel, True)
    exit_msg = native_mode_message(channel, False)
    assert enter_msg[:-1] == exit_msg[:-1]
    assert enter_msg[-1] != exit_msg[-1]


# ---------------------------------------------------------------------------
# Raw MIDI normalization
# ---------------------------------------------------------------------------

@given(control=st.integers(min_value=0, max_value=127), value=st.integers(min_value=0, max_value=127), channel=st.integers(min_value=0, max_value=15))
# @spec MIDI-EVT-001
def test_normalize_cc(control: int, value: int, channel: int) -> None:
    raw = SimpleNamespace(type="control_change", channel=channel, control=control, value=value)
    event = normalize_raw(raw)
    assert event is not None
    assert event.type == "cc"
    assert event.channel == channel
    assert event.number == control
    assert event.raw_value == value
    assert event.normalized == value / 127.0


VALID_SCENE_SYSEX = (0x42, 0x40, 0x00, 0x01, 0x37, 0x05, 0x00, 0x00, 0x41, 0x40, 0x40, 0x7F, 0x00)


# @spec MIDI-EVT-001
def test_normalize_valid_scene_button_sysex() -> None:
    raw = SimpleNamespace(type="sysex", data=VALID_SCENE_SYSEX)
    event = normalize_raw(raw)
    assert event is not None
    assert event.type == "korg_scene"
    assert event.channel == 0
    assert event.is_press


@given(mutated_index=st.integers(min_value=0, max_value=12), replacement=st.integers(min_value=0, max_value=255))
# @spec MIDI-EVT-001
def test_normalize_rejects_corrupted_scene_sysex(mutated_index: int, replacement: int) -> None:
    data = list(VALID_SCENE_SYSEX)
    if mutated_index == 1:
        return  # channel nibble is intentionally free-form; mutating it is still a valid message
    if mutated_index == 11:
        return  # the value byte itself is free-form (0-127 is a legitimate press amount)
    if data[mutated_index] == replacement:
        return  # not actually corrupted
    data[mutated_index] = replacement
    raw = SimpleNamespace(type="sysex", data=tuple(data))
    assert normalize_raw(raw) is None


# @spec MIDI-EVT-001
def test_normalize_unknown_type_returns_none() -> None:
    raw = SimpleNamespace(type="something_unrecognized")
    assert normalize_raw(raw) is None


# ---------------------------------------------------------------------------
# MidiInputAdapter: fake backend, no hardware required
# ---------------------------------------------------------------------------

class FakeOutputPort:
    def __init__(self, name: str, fail_on_channel: int | None = None) -> None:
        self.name = name
        self.sent: list = []
        self.closed = False
        self._fail_on_channel = fail_on_channel

    def send(self, message) -> None:
        channel = message[1] & 0x0F
        if self._fail_on_channel is not None and channel == self._fail_on_channel:
            raise RuntimeError("simulated send failure")
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True


class FakeInputPort:
    def __init__(self, name: str, callback: Callable) -> None:
        self.name = name
        self.callback = callback
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, inputs=None, outputs=None, fail_output_channel: int | None = None) -> None:
        self.inputs = list(inputs or [])
        self.outputs = list(outputs or [])
        self.open_input_calls: list[str] = []
        self.open_output_calls: list[str] = []
        self.output_ports: dict[str, FakeOutputPort] = {}
        self.list_inputs_calls = 0
        self.reentry_hook: Callable[[], None] | None = None
        self.fail_output_channel = fail_output_channel

    def list_inputs(self) -> list[str]:
        self.list_inputs_calls += 1
        if self.reentry_hook is not None:
            hook, self.reentry_hook = self.reentry_hook, None
            hook()
        return list(self.inputs)

    def list_outputs(self) -> list[str]:
        return list(self.outputs)

    def open_input(self, name: str, callback: Callable) -> FakeInputPort:
        self.open_input_calls.append(name)
        return FakeInputPort(name, callback)

    def open_output(self, name: str) -> FakeOutputPort:
        self.open_output_calls.append(name)
        port = FakeOutputPort(name, fail_on_channel=self.fail_output_channel)
        self.output_ports[name] = port  # tests inspect this directly to verify real SysEx content
        return port


def make_adapter(backend, **overrides):
    defaults = dict(
        on_activity=lambda: None,
        on_event=lambda event: None,
        on_connection_change=lambda connected, name: None,
        on_error=lambda active: None,
        on_reset_mapping=lambda: None,
    )
    defaults.update(overrides)
    return MidiInputAdapter(backend, **defaults)


# @spec MIDI-CONN-001, MIDI-CONN-002
def test_poll_discovery_connects_to_matching_port() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=["nanoKONTROL Studio"])
    connections: list[tuple[bool, str | None]] = []
    adapter = make_adapter(backend, on_connection_change=lambda c, n: connections.append((c, n)))
    adapter.poll_discovery()
    assert adapter.connected
    assert adapter.device_name == "nanoKONTROL Studio"
    assert connections == [(True, "nanoKONTROL Studio")]


# @spec MIDI-CONN-002
def test_poll_discovery_does_nothing_without_a_match() -> None:
    backend = FakeBackend(inputs=["Some Other Device"])
    adapter = make_adapter(backend)
    adapter.poll_discovery()
    assert not adapter.connected
    assert backend.open_input_calls == []


# @spec MIDI-CONN-003
def test_duplicate_matches_connect_to_first_in_enumeration_order() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio A", "nanoKONTROL Studio B"], outputs=[])
    adapter = make_adapter(backend)
    adapter.poll_discovery()
    assert adapter.device_name == "nanoKONTROL Studio A"
    assert backend.open_input_calls == ["nanoKONTROL Studio A"]


# @spec MIDI-CONN-004, MIDI-CONN-006
def test_reentrant_poll_tick_does_not_double_connect() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    adapter = make_adapter(backend)
    backend.reentry_hook = adapter.poll_discovery  # simulate an overlapping tick firing mid-operation
    adapter.poll_discovery()
    assert backend.open_input_calls == ["nanoKONTROL Studio"]  # only the outer call actually connected


# @spec MIDI-CONN-005
def test_port_vanishing_from_list_triggers_disconnect() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=["nanoKONTROL Studio"])
    connections: list[tuple[bool, str | None]] = []
    adapter = make_adapter(backend, on_connection_change=lambda c, n: connections.append((c, n)))
    adapter.poll_discovery()
    assert adapter.connected

    backend.inputs = []  # device unplugged
    adapter.poll_discovery()
    assert not adapter.connected
    assert adapter.device_name is None
    assert connections[-1] == (False, None)


# @spec MIDI-CONN-007
def test_connection_status_independent_of_native_mode_error() -> None:
    # No matching output port -> Native Mode fails -> error flag set, but the adapter is
    # still "connected" with a device name (MIDI-CONN-007 is a separate axis from error state).
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    errors: list[bool] = []
    adapter = make_adapter(backend, on_error=errors.append)
    adapter.poll_discovery()
    assert adapter.connected
    assert adapter.device_name == "nanoKONTROL Studio"
    assert errors == [False, True]  # cleared at attempt start, then set because no output port matched


# @spec MIDI-NATIVE-001
def test_native_mode_enter_sent_to_all_16_channels() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=["nanoKONTROL Studio"])
    adapter = make_adapter(backend)
    adapter.poll_discovery()
    port = backend.output_ports["nanoKONTROL Studio"]
    assert len(port.sent) == 16
    channels_seen = {message[1] & 0x0F for message in port.sent}
    assert channels_seen == set(range(16))
    assert all(message[-1] == 1 for message in port.sent)  # all are "enter", not "exit"


# @spec MIDI-NATIVE-002
def test_native_mode_exit_sent_despite_one_channel_failing_and_port_still_closes() -> None:
    backend = FakeBackend(
        inputs=["nanoKONTROL Studio"], outputs=["nanoKONTROL Studio"], fail_output_channel=5,
    )
    adapter = make_adapter(backend)
    adapter.poll_discovery()
    port = backend.output_ports["nanoKONTROL Studio"]
    port.sent.clear()  # discard the enter-handshake sends; isolate the exit handshake below

    adapter.disconnect()

    # Channel 5's send raised and is never appended by FakeOutputPort.send; the other
    # 15 channels must still have gone out, and the port must close regardless.
    assert len(port.sent) == 15
    channels_seen = {message[1] & 0x0F for message in port.sent}
    assert channels_seen == set(range(16)) - {5}
    assert all(message[-1] == 0 for message in port.sent)  # all are "exit", not "enter"
    assert port.closed
    assert not adapter.connected


# @spec MIDI-NATIVE-003
def test_native_mode_failure_sets_error_flag() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])  # no matching output
    errors: list[bool] = []
    adapter = make_adapter(backend, on_error=errors.append)
    adapter.poll_discovery()
    assert errors == [False, True]


# @spec MIDI-NATIVE-004
def test_error_flag_cleared_at_start_of_each_connect_attempt() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    errors: list[bool] = []
    adapter = make_adapter(backend, on_error=errors.append)
    adapter.poll_discovery()  # attempt 1: clear (False), then fails -> True
    assert errors == [False, True]

    adapter.disconnect()
    backend.outputs = ["nanoKONTROL Studio"]  # now a matching output exists
    adapter.poll_discovery()  # attempt 2: clear (False), then succeeds -> no further True
    assert errors == [False, True, False]


# @spec MIDI-EVT-001
def test_normalized_event_reaches_on_event_callback() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    events: list = []
    adapter = make_adapter(backend, on_event=events.append)
    adapter.poll_discovery()
    input_port = _get_open_input_port(backend, adapter)
    input_port.callback(SimpleNamespace(type="control_change", channel=15, control=0, value=64))
    assert len(events) == 1
    assert events[0].type == "cc"
    assert events[0].number == 0


# @spec MIDI-EVT-003
def test_activity_recorded_even_when_normalization_fails() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    activity_count = {"n": 0}
    events: list = []
    adapter = make_adapter(
        backend, on_activity=lambda: activity_count.__setitem__("n", activity_count["n"] + 1), on_event=events.append
    )
    adapter.poll_discovery()
    input_port = _get_open_input_port(backend, adapter)
    input_port.callback(SimpleNamespace(type="sysex", data=(0x01, 0x02, 0x03)))  # garbage, fails to normalize
    assert activity_count["n"] == 1
    assert events == []


# @spec MIDI-EVT-004
def test_mapping_reset_invoked_on_fresh_connect() -> None:
    backend = FakeBackend(inputs=["nanoKONTROL Studio"], outputs=[])
    reset_calls = {"n": 0}
    adapter = make_adapter(backend, on_reset_mapping=lambda: reset_calls.__setitem__("n", reset_calls["n"] + 1))
    adapter.poll_discovery()
    assert reset_calls["n"] == 1


def _get_open_input_port(backend: FakeBackend, adapter: MidiInputAdapter) -> FakeInputPort:
    # The adapter stores the live input port internally; tests reach in to drive its
    # callback directly, simulating an incoming MIDI message from the hardware thread.
    return adapter._input_port
