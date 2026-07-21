"""Tests for the Status UI's pure presentation logic (docs/specs/app-ui.md § Status UI).

@spec UI-STATUS-001, UI-STATUS-002, UI-STATUS-003, UI-STATUS-004
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.signal_monitor import ChannelState, SignalMonitor
from dragonmidi.status_presenter import (
    compute_status_snapshot,
    dragonframe_indicator,
    midi_indicator,
    show_nanokontrol2_setup_hint,
)

# --- UI-STATUS-002: label reflects connection status, independent of channel state ---


@given(state=st.sampled_from(list(ChannelState)), device_name=st.text(min_size=1, max_size=20))
# @spec UI-STATUS-002
def test_connected_label_shows_device_name_regardless_of_channel_state(state, device_name: str) -> None:
    view = midi_indicator(state, connected=True, device_name=device_name, profile_name="nanoKONTROL Studio")
    assert view.label == device_name


@given(
    state=st.sampled_from(list(ChannelState)),
    stale_device_name=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
)
# @spec UI-STATUS-002
def test_disconnected_label_always_shows_waiting_text(state, stale_device_name) -> None:
    view = midi_indicator(state, connected=False, device_name=stale_device_name, profile_name="nanoKONTROL Studio")
    assert view.label == "Waiting for nanoKONTROL Studio…"


@given(state=st.sampled_from(list(ChannelState)))
# @spec UI-STATUS-002
def test_disconnected_label_reflects_the_active_profile_name(state) -> None:
    view = midi_indicator(state, connected=False, device_name=None, profile_name="nanoKONTROL2")
    assert view.label == "Waiting for nanoKONTROL2…"


# --- UI-STATUS-004: dot state and label are independent axes; may disagree ---


@given(state=st.sampled_from(list(ChannelState)), connected=st.booleans(), device_name=st.text(min_size=1, max_size=20))
# @spec UI-STATUS-004
def test_presenter_never_derives_dot_state_from_connection_status(state, connected: bool, device_name: str) -> None:
    view = midi_indicator(state, connected=connected, device_name=device_name, profile_name="nanoKONTROL Studio")
    assert view.state == state  # passed through untouched, proving the two axes are independent


# @spec UI-STATUS-004
def test_error_dot_can_coexist_with_a_connected_device_name() -> None:
    # The scenario this whole design exists for: a real controller is plugged in
    # (label shows its name) but its Native Mode handshake failed (dot shows error).
    view = midi_indicator(ChannelState.ERROR, connected=True, device_name="nanoKONTROL Studio", profile_name="nanoKONTROL Studio")
    assert view.state == ChannelState.ERROR
    assert view.label == "nanoKONTROL Studio"


# --- UI-STATUS-003: Dragonframe row shows the listen port ---


@given(port=st.integers(min_value=1, max_value=65535), state=st.sampled_from(list(ChannelState)))
# @spec UI-STATUS-003
def test_dragonframe_indicator_label_includes_listen_port(port: int, state) -> None:
    view = dragonframe_indicator(state, listen_port=port)
    assert str(port) in view.label
    assert view.state == state


# --- UI-STATUS-001: both indicators are derived from exactly one Signal Monitor read per channel ---


class _CountingMonitor:
    """Wraps a real SignalMonitor and counts calls to .state(), to catch a torn read."""

    def __init__(self, inner: SignalMonitor) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def state(self, channel: str) -> ChannelState:
        self.calls.append(channel)
        return self._inner.state(channel)


# @spec UI-STATUS-001
def test_snapshot_reads_each_channel_state_exactly_once(fake_clock) -> None:
    monitor = _CountingMonitor(SignalMonitor(liveness_window=2.0, clock=fake_clock))
    snapshot = compute_status_snapshot(
        monitor,
        midi_connected=True,
        midi_device_name="nanoKONTROL Studio",
        listen_port=7011,
        midi_profile_name="nanoKONTROL Studio",
    )
    assert monitor.calls.count("midi") == 1
    assert monitor.calls.count("dragonframe") == 1
    assert len(monitor.calls) == 2
    assert snapshot.midi.label == "nanoKONTROL Studio"
    assert snapshot.dragonframe.label == "127.0.0.1:7011 (listen)"


# @spec UI-STATUS-002
def test_snapshot_waiting_label_reflects_selected_profile_when_disconnected(fake_clock) -> None:
    monitor = SignalMonitor(liveness_window=2.0, clock=fake_clock)
    snapshot = compute_status_snapshot(
        monitor,
        midi_connected=False,
        midi_device_name=None,
        listen_port=7011,
        midi_profile_name="nanoKONTROL2",
    )
    assert snapshot.midi.label == "Waiting for nanoKONTROL2…"


# --- UI-PROFILE-003: nanoKONTROL2 setup hint visibility ---


# @spec UI-PROFILE-003
def test_setup_hint_shown_only_for_nanokontrol2() -> None:
    assert show_nanokontrol2_setup_hint("nanoKONTROL2") is True
    assert show_nanokontrol2_setup_hint("nanoKONTROL Studio") is False


@given(name=st.text(min_size=1, max_size=20).filter(lambda n: n != "nanoKONTROL2"))
# @spec UI-PROFILE-003
def test_setup_hint_hidden_for_any_other_profile_name(name: str) -> None:
    assert show_nanokontrol2_setup_hint(name) is False
