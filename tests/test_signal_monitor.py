"""Tests for the Signal Monitor (docs/specs/app-ui.md § Signal Monitor).

@spec UI-MONITOR-001, UI-MONITOR-002, UI-MONITOR-003
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.signal_monitor import ChannelState, SignalMonitor
from tests.support import FakeClock

# --- UI-MONITOR-001: never-seen channel is not live ---


# @spec UI-MONITOR-001
def test_fresh_channel_is_quiet_not_live(fake_clock) -> None:
    monitor = SignalMonitor(liveness_window=2.0, clock=fake_clock)
    assert monitor.state("midi") == ChannelState.QUIET
    assert monitor.state("dragonframe") == ChannelState.QUIET


# --- UI-MONITOR-002: liveness is a strict function of elapsed time vs. window ---


# @spec UI-MONITOR-002
@given(
    window=st.floats(min_value=0.01, max_value=10.0),
    elapsed=st.floats(min_value=0.0, max_value=20.0),
)
def test_liveness_matches_elapsed_vs_window(window: float, elapsed: float) -> None:
    # A fresh FakeClock per example: a shared pytest fixture would leak mutated
    # clock state across Hypothesis-generated examples within one test run.
    clock = FakeClock()
    monitor = SignalMonitor(liveness_window=window, clock=clock)
    monitor.mark_activity("midi")
    clock.advance(elapsed)
    expected_live = elapsed < window
    assert (monitor.state("midi") == ChannelState.LIVE) == expected_live


# @spec UI-MONITOR-002
def test_liveness_boundary_is_strict_not_inclusive(fake_clock) -> None:
    monitor = SignalMonitor(liveness_window=2.0, clock=fake_clock)
    monitor.mark_activity("midi")
    fake_clock.advance(2.0)  # exactly at the window
    assert monitor.state("midi") == ChannelState.QUIET


# @spec UI-MONITOR-002
@given(window=st.floats(min_value=0.01, max_value=10.0))
def test_repeated_activity_resets_the_liveness_clock(window: float) -> None:
    clock = FakeClock()
    monitor = SignalMonitor(liveness_window=window, clock=clock)
    monitor.mark_activity("midi")
    clock.advance(window * 0.9)
    monitor.mark_activity("midi")  # fresh activity before going quiet
    clock.advance(window * 0.9)
    assert monitor.state("midi") == ChannelState.LIVE


# --- UI-MONITOR-003: error flag takes precedence over both live and quiet ---


# @spec UI-MONITOR-003
@given(has_recent_activity=st.booleans(), error=st.booleans())
def test_error_flag_precedence_over_liveness(has_recent_activity: bool, error: bool) -> None:
    clock = FakeClock()
    monitor = SignalMonitor(liveness_window=2.0, clock=clock)
    if has_recent_activity:
        monitor.mark_activity("dragonframe")
    monitor.set_error("dragonframe", error)

    state = monitor.state("dragonframe")
    if error:
        assert state == ChannelState.ERROR
    elif has_recent_activity:
        assert state == ChannelState.LIVE
    else:
        assert state == ChannelState.QUIET


# @spec UI-MONITOR-003
def test_clearing_error_flag_reveals_underlying_liveness(fake_clock) -> None:
    monitor = SignalMonitor(liveness_window=2.0, clock=fake_clock)
    monitor.mark_activity("midi")
    monitor.set_error("midi", True)
    assert monitor.state("midi") == ChannelState.ERROR
    monitor.set_error("midi", False)
    assert monitor.state("midi") == ChannelState.LIVE  # activity was still recent


# @spec UI-MONITOR-003
def test_channels_are_independent(fake_clock) -> None:
    monitor = SignalMonitor(liveness_window=2.0, clock=fake_clock)
    monitor.mark_activity("midi")
    monitor.set_error("dragonframe", True)
    assert monitor.state("midi") == ChannelState.LIVE
    assert monitor.state("dragonframe") == ChannelState.ERROR
