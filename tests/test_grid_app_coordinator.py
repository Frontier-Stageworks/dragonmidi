"""Tests for `GridAppCoordinator` - the Qt-independent state machine
`app.py`'s composition root delegates to for every Grid-specific decision
(when to poll MIDI discovery, when a controller just became ready, how to
route an incoming event, what status to show). Constructed directly against a
fake `GridTransport` and the project's `FakeClock` - no Qt, no hardware.

@spec GRID-DISCOVER-003, GRID-DISCOVER-004, GRID-TOPO-007, GRID-TOPO-012
@spec GRID-MIDI-004, GRID-MIDI-005, GRID-MAP-001
@spec GRID-APP-001, GRID-APP-002, GRID-APP-003, GRID-APP-004, GRID-APP-005
"""

from __future__ import annotations

from tests.support import FakeClock
from tests.test_grid_lifecycle import _GRIDMASTER_FRAME, FakeGridTransport, _run_for

from dragonmidi.events import MidiEvent
from dragonmidi.grid_lifecycle import GridAppCoordinator, GridLifecycle, GridStatus
from dragonmidi.grid_protocol import encode_heartbeat_frame


def _event(number: int = 36) -> MidiEvent:
    return MidiEvent(type="cc", channel=0, number=number, raw_value=64, normalized=0.5, is_press=False, is_release=False)


def _coordinator(candidates=None, settle_window: float = 0.5):
    clock = FakeClock()
    transport = FakeGridTransport(candidates=candidates or [("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=settle_window)
    return GridAppCoordinator(lifecycle), transport, clock


# --- Not selected: everything is a pure pass-through / no-op ---


def test_not_selected_passes_events_through_unchanged() -> None:
    coordinator, _, _ = _coordinator()
    event = _event()
    assert coordinator.route_event(event) is event


def test_not_selected_never_blocks_midi_discovery() -> None:
    coordinator, _, _ = _coordinator()
    assert coordinator.should_poll_midi_discovery() is True


def test_not_selected_poll_is_a_noop() -> None:
    coordinator, transport, clock = _coordinator()
    assert coordinator.poll() is None
    assert transport.opened == []  # never even started discovery


# --- Selecting Grid starts its lifecycle and blocks MIDI discovery until ready ---


def test_select_grid_starts_discovery_and_blocks_midi_polling_until_ready() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    assert coordinator.grid_active is True
    assert coordinator.should_poll_midi_discovery() is False  # nothing settled yet
    coordinator.poll()  # drives GridLifecycle's own discovery step
    assert transport.opened == ["COM1"]


def test_poll_returns_the_controller_exactly_once_when_it_becomes_ready() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()  # opens the port

    ready_results = []
    elapsed = 0.0
    while elapsed < 1.0:
        transport.deliver(_GRIDMASTER_FRAME)
        clock.advance(0.2)
        elapsed += 0.2
        result = coordinator.poll()
        if result is not None:
            ready_results.append(result)

    assert coordinator.status is GridStatus.ACTIVE
    assert len(ready_results) == 1  # signalled exactly once, on the tick it became ready
    assert ready_results[0] is coordinator.lifecycle.controller
    assert coordinator.should_poll_midi_discovery() is True  # unblocked once ready


def test_ready_controller_resolves_grid_events_and_drops_unmatched_ones() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    assert coordinator.status is GridStatus.ACTIVE

    matching_event = _event(36)  # x=0 fader element idx4 -> cc 36
    result = coordinator.route_event(matching_event)
    assert result is not None
    assert (result.type, result.number) == ("grid_fader", 1)

    unmatched_event = _event(99)
    assert coordinator.route_event(unmatched_event) is None


# --- Stale: stops resolving, status reflects it, until reselection ---


def test_structural_change_after_active_stops_resolving_events() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    assert coordinator.status is GridStatus.ACTIVE

    new_module = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module)
    clock.advance(0.01)
    coordinator.poll()
    assert coordinator.status is GridStatus.STALE
    assert coordinator.route_event(_event(36)) is None  # was previously resolvable, now dropped


def test_reselecting_grid_performs_a_fresh_initialization() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    new_module = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module)
    clock.advance(0.01)
    coordinator.poll()
    assert coordinator.status is GridStatus.STALE

    coordinator.select_grid()  # "reselecting Intech Grid from the dropdown"
    assert coordinator.status is GridStatus.WAITING
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME, new_module])
    assert coordinator.status is GridStatus.ACTIVE
    assert coordinator.lifecycle.controller.bank_count == 8


# --- Switching away cleanly releases the CDC connection ---


def test_select_static_after_grid_was_active_closes_the_connection() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    assert transport.connection is not None
    assert transport.connection.closed is False

    coordinator.select_static()
    assert coordinator.grid_active is False
    assert transport.connection.closed is True

    event = _event()
    assert coordinator.route_event(event) is event  # pass-through again once inactive


def test_select_static_when_grid_was_never_selected_is_a_safe_noop() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_static()
    assert coordinator.grid_active is False
    assert transport.connection is None  # never opened, nothing to close


# --- Ambiguous chains ---


def test_multiple_candidates_reports_ambiguous_status() -> None:
    coordinator, transport, clock = _coordinator(candidates=[("COM1", 0x03EB, 0xECAC), ("COM2", 0x303A, 0x8123)])
    coordinator.select_grid()
    coordinator.poll()
    assert coordinator.status is GridStatus.AMBIGUOUS
    assert transport.opened == []


# --- Status/error-dot glue the existing Status UI borrows (@spec GRID-APP-005) ---


def test_status_override_and_is_error_are_inert_when_not_selected() -> None:
    coordinator, _, _ = _coordinator()
    assert coordinator.status_override() is None
    assert coordinator.is_error() is False


def test_status_override_and_is_error_while_pending() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    assert coordinator.status is GridStatus.INITIALIZING
    assert coordinator.status_override() == "Intech Grid: initializing topology…"
    assert coordinator.is_error() is False


def test_status_override_is_none_once_active_but_is_error_stays_false() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    assert coordinator.status is GridStatus.ACTIVE
    assert coordinator.status_override() is None  # ordinary connected/waiting-text logic applies
    assert coordinator.is_error() is False


def test_status_override_and_is_error_once_stale() -> None:
    coordinator, transport, clock = _coordinator()
    coordinator.select_grid()
    coordinator.poll()
    _run_for(clock, coordinator, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    new_module = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module)
    clock.advance(0.01)
    coordinator.poll()
    assert coordinator.status is GridStatus.STALE
    assert coordinator.status_override() == "Intech Grid: topology changed — reselect to apply"
    assert coordinator.is_error() is True


def test_ambiguous_status_override_and_is_error() -> None:
    coordinator, transport, clock = _coordinator(candidates=[("COM1", 0x03EB, 0xECAC), ("COM2", 0x303A, 0x8123)])
    coordinator.select_grid()
    coordinator.poll()
    assert coordinator.status_override() == "Intech Grid: multiple devices found — disconnect one"
    assert coordinator.is_error() is True
