"""Tests for the Grid lifecycle orchestrator: discovery -> settle -> build ->
stale-on-structural-change (docs/llds/intech-grid.md § Initialization Lifecycle,
§ Topology Change Policy, § Grid CDC Transport's ambiguous-chains rule).

Uses a fake `GridTransport` and the project's existing `FakeClock` - no
hardware, no real serial port, no background thread. Heartbeats are
delivered periodically (every 0.2s, under Grid's real ~250ms cadence and well
under the 0.5s disconnect timeout) for as long as a test wants a module to
stay "connected" - matching real hardware's continuous heartbeat stream, the
same discipline `test_grid_topology.py`'s `_keep_alive()` helper uses.

@spec GRID-DISCOVER-003, GRID-DISCOVER-004, GRID-DISCOVER-005, GRID-TOPO-007
@spec GRID-TOPO-012, GRID-MIDI-005
"""

from __future__ import annotations

import threading

from tests.support import FakeClock

from dragonmidi.grid_lifecycle import GridLifecycle, GridStatus, grid_status_is_error, grid_status_text
from dragonmidi.grid_protocol import encode_heartbeat_frame

HEARTBEAT_INTERVAL = 0.2


class FakeGridConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeGridTransport:
    def __init__(self, candidates: list[tuple[str, int, int]] | None = None) -> None:
        self.candidates = list(candidates or [])
        self.opened: list[str] = []
        self._callback = None
        self.connection: FakeGridConnection | None = None

    def list_candidate_ports(self):
        return list(self.candidates)

    def open(self, port_name: str, callback) -> FakeGridConnection:
        self.opened.append(port_name)
        self._callback = callback
        self.connection = FakeGridConnection()
        return self.connection

    def deliver(self, data: bytes) -> None:
        assert self._callback is not None, "deliver() called before open()"
        self._callback(data)


_GRIDMASTER_FRAME = encode_heartbeat_frame(heartbeat_type=1, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0, page=0)


def _run_for(
    clock: FakeClock,
    lifecycle: GridLifecycle,
    transport: FakeGridTransport,
    seconds: float,
    frames: list[bytes],
    step: float = HEARTBEAT_INTERVAL,
) -> None:
    """Advances the fake clock in `step` increments across `seconds`,
    delivering every frame in `frames` and polling the lifecycle on each tick -
    simulating a continuous, real heartbeat stream for that duration."""
    elapsed = 0.0
    while elapsed < seconds:
        for frame in frames:
            transport.deliver(frame)
        clock.advance(step)
        elapsed += step
        lifecycle.poll()


# --- Discovery states (GRID-DISCOVER-003/004/005) ---


def test_no_candidates_stays_waiting() -> None:
    transport = FakeGridTransport(candidates=[])
    lifecycle = GridLifecycle(transport, clock=FakeClock())
    lifecycle.poll()
    assert lifecycle.status is GridStatus.WAITING


def test_multiple_candidates_is_ambiguous_and_opens_nothing() -> None:
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC), ("COM2", 0x303A, 0x8123)])
    lifecycle = GridLifecycle(transport, clock=FakeClock())
    lifecycle.poll()
    assert lifecycle.status is GridStatus.AMBIGUOUS
    assert transport.opened == []


def test_single_candidate_opens_and_initializes() -> None:
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=FakeClock())
    lifecycle.poll()
    assert lifecycle.status is GridStatus.INITIALIZING
    assert transport.opened == ["COM1"]


# --- Settle -> Ready (GRID-TOPO-007) ---


def test_settles_to_active_after_the_settle_window_and_stays_active_with_continued_heartbeats() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()  # opens the port

    _run_for(clock, lifecycle, transport, seconds=1.5, frames=[_GRIDMASTER_FRAME])
    assert lifecycle.status is GridStatus.ACTIVE
    assert lifecycle.controller is not None
    assert lifecycle.controller.bank_count == 4  # a single PBF4


# --- Unsupported topology (multi-row) ---


def test_multi_row_topology_reports_unsupported_status() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()
    second_row_frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=1, rotation=0, port_rotation=0)
    _run_for(clock, lifecycle, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME, second_row_frame])
    assert lifecycle.status is GridStatus.UNSUPPORTED
    assert lifecycle.controller is None


# --- Stale on structural change, immediately, no live rebuild (GRID-TOPO-012, GRID-MIDI-005) ---


def test_structural_change_after_active_marks_stale_immediately() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()
    _run_for(clock, lifecycle, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    assert lifecycle.status is GridStatus.ACTIVE
    controller_before = lifecycle.controller

    # A new module appears - a structural change - must flip to STALE right away,
    # without waiting for a fresh settle window. The gridmaster keeps heartbeating
    # throughout, so only the new module's appearance explains the transition.
    new_module_frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module_frame)
    clock.advance(0.01)
    lifecycle.poll()
    assert lifecycle.status is GridStatus.STALE
    assert controller_before.is_stale is True


def test_stale_does_not_auto_rebuild_on_further_polling() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()
    _run_for(clock, lifecycle, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    new_module_frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module_frame)
    clock.advance(0.01)
    lifecycle.poll()
    assert lifecycle.status is GridStatus.STALE

    # Keep both modules heartbeating well past another settle window - still
    # stale, no live rebuild, even though the topology would now settle cleanly.
    _run_for(clock, lifecycle, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME, new_module_frame])
    assert lifecycle.status is GridStatus.STALE


def test_reinitialize_rebuilds_from_a_fresh_settle() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()
    _run_for(clock, lifecycle, transport, seconds=1.0, frames=[_GRIDMASTER_FRAME])
    new_module_frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    transport.deliver(_GRIDMASTER_FRAME)
    transport.deliver(new_module_frame)
    clock.advance(0.01)
    lifecycle.poll()
    assert lifecycle.status is GridStatus.STALE

    lifecycle.reinitialize()
    assert lifecycle.status is GridStatus.WAITING
    assert lifecycle.controller is None
    # Re-discover and re-settle against the new (2-module) topology.
    lifecycle.poll()
    _run_for(clock, lifecycle, transport, seconds=1.5, frames=[_GRIDMASTER_FRAME, new_module_frame])
    assert lifecycle.status is GridStatus.ACTIVE
    assert lifecycle.controller.bank_count == 8


# --- Thread safety: the real SerialGridTransport reads on a background
# --- thread, so `_on_bytes` must never touch `_accumulator`/`_builder`
# --- directly - only `poll()`, called from the Qt main thread, may.


def test_bytes_delivered_from_a_background_thread_are_processed_safely() -> None:
    clock = FakeClock()
    transport = FakeGridTransport(candidates=[("COM1", 0x03EB, 0xECAC)])
    lifecycle = GridLifecycle(transport, clock=clock, settle_window=0.5)
    lifecycle.poll()  # opens the port

    elapsed = 0.0
    while elapsed < 1.5:
        # Deliver from an actual background thread, exactly as
        # `_SerialGridConnection._read_loop` does, instead of the test's own
        # thread - proving `_on_bytes` -> `poll()` is safe across threads.
        thread = threading.Thread(target=transport.deliver, args=(_GRIDMASTER_FRAME,))
        thread.start()
        thread.join()
        clock.advance(HEARTBEAT_INTERVAL)
        elapsed += HEARTBEAT_INTERVAL
        lifecycle.poll()

    assert lifecycle.status is GridStatus.ACTIVE
    assert lifecycle.controller is not None
    assert lifecycle.controller.bank_count == 4


# --- Status text / error mapping onto the existing 3-state indicator
# --- (docs/llds/intech-grid.md § UI Implications's five-state table) ---


def test_grid_status_text_is_none_for_active_so_the_normal_device_name_logic_applies() -> None:
    assert grid_status_text(GridStatus.ACTIVE, reason=None) is None


def test_grid_status_text_is_distinct_and_non_none_for_every_other_state() -> None:
    texts = {
        status: grid_status_text(status, reason="modules span more than one row")
        for status in GridStatus
        if status is not GridStatus.ACTIVE
    }
    assert all(text is not None for text in texts.values())
    assert len(set(texts.values())) == len(texts)  # every non-active state reads distinctly


def test_grid_status_text_includes_the_unsupported_reason() -> None:
    text = grid_status_text(GridStatus.UNSUPPORTED, reason="more than one recognized VSN1 module is present")
    assert "more than one recognized VSN1 module is present" in text


def test_grid_status_is_error_for_failure_states_only() -> None:
    error_states = {GridStatus.UNSUPPORTED, GridStatus.COLLISION, GridStatus.STALE, GridStatus.AMBIGUOUS}
    for status in GridStatus:
        assert grid_status_is_error(status) == (status in error_states)
