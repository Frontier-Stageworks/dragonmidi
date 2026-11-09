"""Grid lifecycle orchestrator (docs/llds/intech-grid.md § Initialization
Lifecycle, § Topology Change Policy, § Grid CDC Transport's ambiguous-chains
rule). Ties together `GridTransport` discovery, `GridFrameAccumulator`
parsing, `GridTopologyBuilder` settle/structural-change tracking, and
`build_grid_controller()` construction into the single `poll()`-driven state
machine `app.py`'s composition root drives, mirroring `MidiInputAdapter`'s
existing poll/connect pattern (`docs/llds/midi-input.md § Device Discovery and
Auto-Connect`) for a second transport.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from enum import Enum

from .events import MidiEvent
from .grid_controller import (
    GRID_PROFILE_NAME,
    AddressCollision,
    GridRuntimeController,
    Ready,
    UnsupportedTopology,
    build_grid_controller,
    route_midi_event,
)
from .grid_protocol import GridFrameAccumulator
from .grid_topology import DEFAULT_SETTLE_WINDOW_SECONDS, GridTopologyBuilder
from .grid_transport import GridConnection, GridTransport
from .queue_drain import drain_queue


class GridStatus(Enum):
    WAITING = "waiting"  # no candidate port yet, or not yet settled
    AMBIGUOUS = "ambiguous"  # more than one candidate Grid CDC port found
    INITIALIZING = "initializing"  # a port is open, topology hasn't settled yet
    ACTIVE = "active"
    UNSUPPORTED = "unsupported"  # settled, but the topology fails validation (multi-row, multi-VSN1)
    COLLISION = "collision"  # settled, but address-table construction found a collision
    STALE = "stale"  # was ACTIVE; a structural change invalidated it - requires reinitialize()


class GridLifecycle:
    """@spec GRID-DISCOVER-003, GRID-DISCOVER-004, GRID-DISCOVER-005, GRID-TOPO-007
    @spec GRID-TOPO-012, GRID-MIDI-005
    """

    def __init__(
        self,
        transport: GridTransport,
        *,
        clock: Callable[[], float] = time.monotonic,
        settle_window: float = DEFAULT_SETTLE_WINDOW_SECONDS,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._settle_window = settle_window
        self._connection: GridConnection | None = None
        self._byte_queue: queue.Queue[bytes] = queue.Queue()
        self._accumulator = GridFrameAccumulator()
        self._builder = GridTopologyBuilder(settle_window=settle_window)
        self._controller: GridRuntimeController | None = None
        self._built_at: float | None = None
        self._status = GridStatus.WAITING
        self._unsupported_reason: str | None = None

    @property
    def status(self) -> GridStatus:
        return self._status

    @property
    def controller(self) -> GridRuntimeController | None:
        return self._controller

    @property
    def unsupported_reason(self) -> str | None:
        return self._unsupported_reason

    def poll(self) -> None:
        # Drains bytes queued by `_on_bytes` - always called here, on whatever
        # thread `poll()` itself runs on (the Qt main thread in `app.py`), so
        # `_accumulator`/`_builder` are only ever touched from one thread even
        # though the real `SerialGridTransport` reads on a background thread
        # (mirrors `MidiInputAdapter`'s on_event=queue.put + drain-on-tick).
        drain_queue(self._byte_queue, self._handle_bytes)
        now = self._clock()

        if self._connection is None:
            self._poll_discovery()
            return

        if self._controller is not None:
            if not self._controller.is_stale and self._builder.has_changed_since(self._built_at, now):
                self._controller.mark_stale()
                self._status = GridStatus.STALE
            return  # ACTIVE or STALE: no live rebuild either way (§10)

        topology = self._builder.settled(now)
        if topology is None:
            return  # still INITIALIZING

        outcome = build_grid_controller(topology)
        if isinstance(outcome, Ready):
            self._controller = outcome.controller
            self._built_at = now
            self._status = GridStatus.ACTIVE
        elif isinstance(outcome, UnsupportedTopology):
            self._status = GridStatus.UNSUPPORTED
            self._unsupported_reason = outcome.reason
        elif isinstance(outcome, AddressCollision):
            self._status = GridStatus.COLLISION

    def _poll_discovery(self) -> None:
        candidates = self._transport.list_candidate_ports()
        if len(candidates) == 0:
            self._status = GridStatus.WAITING
            return
        if len(candidates) > 1:
            self._status = GridStatus.AMBIGUOUS
            return
        port_name, _vid, _pid = candidates[0]
        self._connection = self._transport.open(port_name, self._on_bytes)
        self._status = GridStatus.INITIALIZING

    def _on_bytes(self, data: bytes) -> None:
        """The transport's read callback - may run on a background thread
        (the real `SerialGridTransport` does). Only ever enqueues; `poll()`
        is where `_accumulator`/`_builder` are actually touched."""
        self._byte_queue.put(data)

    def _handle_bytes(self, data: bytes) -> None:
        now = self._clock()
        for heartbeat in self._accumulator.feed(data):
            self._builder.observe(heartbeat, now=now)

    def reinitialize(self) -> None:
        """Reselecting "Intech Grid" from the Controller Profile dropdown
        calls this: closes the current connection (if any) and resets to a
        fresh discovery/settle cycle - the only supported way to pick up a
        structural change (docs/llds/intech-grid.md § Topology Change Policy)."""
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._byte_queue = queue.Queue()
        self._accumulator = GridFrameAccumulator()
        self._builder = GridTopologyBuilder(settle_window=self._settle_window)
        self._controller = None
        self._built_at = None
        self._status = GridStatus.WAITING
        self._unsupported_reason = None


class GridAppCoordinator:
    """The Qt-independent decisions `app.py`'s composition root needs to make
    Intech Grid a real selectable controller, wrapping a `GridLifecycle`
    without owning any widget. Every method here is a direct question the
    app's Controller Profile dropdown and MIDI dispatch path ask once per
    event or tick - deliberately small enough to unit test without Qt, a real
    serial port, or a `QMainWindow` (docs/llds/intech-grid.md § Application
    Integration).

    `app.py` still owns installing a newly-ready controller into the
    MappingEngine/MidiInputAdapter and rebuilding the Mapping View/
    Configuration dialog - this class only decides *when* that must happen
    (`poll()`'s return value) and *whether* an incoming MIDI event should
    reach the Mapping Engine at all (`route_event()`).
    """

    def __init__(self, grid_lifecycle: GridLifecycle) -> None:
        self._grid_lifecycle = grid_lifecycle
        self.grid_active = False

    @property
    def lifecycle(self) -> GridLifecycle:
        return self._grid_lifecycle

    @property
    def status(self) -> GridStatus:
        return self._grid_lifecycle.status

    @property
    def unsupported_reason(self) -> str | None:
        return self._grid_lifecycle.unsupported_reason

    def select_static(self) -> None:
        """The user picked a static (YAML) Controller Profile from the
        dropdown. If Grid was active, cleanly releases its CDC connection;
        otherwise a no-op."""
        if self.grid_active:
            self._grid_lifecycle.reinitialize()
        self.grid_active = False

    def select_grid(self) -> None:
        """The user picked "Intech Grid" from the dropdown - including
        reselecting it after STALE/UNSUPPORTED/COLLISION, which always
        performs a fresh discovery/settle cycle (there is no other supported
        way to pick up a structural change)."""
        self.grid_active = True
        self._grid_lifecycle.reinitialize()

    def poll(self) -> GridRuntimeController | None:
        """Call once per UI tick. A no-op unless Grid is the active
        selection. Returns the `GridRuntimeController` exactly once, on the
        tick it first becomes ready - the signal `app.py` uses to install it
        as the active MappingEngine/MIDI controller and rebuild the Mapping
        View for its `bank_count`. Returns `None` on every other tick,
        including all later ticks against the same ready controller."""
        if not self.grid_active:
            return None
        previous = self._grid_lifecycle.controller
        self._grid_lifecycle.poll()
        current = self._grid_lifecycle.controller
        if current is not None and current is not previous:
            return current
        return None

    def should_poll_midi_discovery(self) -> bool:
        """False only while Grid is selected but not yet settled
        (WAITING/AMBIGUOUS/INITIALIZING) - there is no profile pattern to
        match a MIDI port against yet, and polling would otherwise try to
        reconnect against whichever static profile was previously active.
        True once Grid is ACTIVE or STALE (its MIDI port pattern is known,
        matching should continue normally) and whenever Grid isn't selected
        at all."""
        return not (self.grid_active and self._grid_lifecycle.controller is None)

    def route_event(self, event: MidiEvent) -> MidiEvent | None:
        """The one Grid-specific branch the MIDI input dispatch path needs,
        before the event reaches the Mapping Engine. Passes `event` through
        untouched when Grid isn't active (the static-profile path is
        unaffected); drops it (`None`) when Grid is active but not yet ready,
        or once stale/unresolvable."""
        return route_midi_event(event, grid_active=self.grid_active, controller=self._grid_lifecycle.controller)

    def status_override(self) -> str | None:
        """What `status_presenter.midi_indicator()`'s `status_override`
        parameter should receive this tick - `None` whenever Grid isn't the
        active selection (the ordinary connected/waiting-text logic applies
        unchanged), otherwise Grid's own current-state text (`None` for
        ACTIVE too, letting the ordinary logic take back over once settled).
        """
        if not self.grid_active:
            return None
        return grid_status_text(self.status, self.unsupported_reason)

    def is_error(self) -> bool:
        """Whether the Status UI's existing error-dot flag should be set this
        tick on Grid's account - always `False` when Grid isn't active."""
        return self.grid_active and grid_status_is_error(self.status)


_STATUS_TEXT: dict[GridStatus, str] = {
    GridStatus.WAITING: f"Waiting for {GRID_PROFILE_NAME}…",
    GridStatus.AMBIGUOUS: f"{GRID_PROFILE_NAME}: multiple devices found — disconnect one",
    GridStatus.INITIALIZING: f"{GRID_PROFILE_NAME}: initializing topology…",
    GridStatus.COLLISION: f"{GRID_PROFILE_NAME}: address collision — reselect to retry",
    GridStatus.STALE: f"{GRID_PROFILE_NAME}: topology changed — reselect to apply",
}

_ERROR_STATUSES = frozenset({GridStatus.UNSUPPORTED, GridStatus.COLLISION, GridStatus.STALE, GridStatus.AMBIGUOUS})


def grid_status_text(status: GridStatus, reason: str | None) -> str | None:
    """The Status UI's existing free-text connection-status line can show any
    of these verbatim (docs/llds/intech-grid.md § UI Implications's five-state
    table) - no new widget. `None` for `ACTIVE` specifically: once active, the
    normal "connected device name, or waiting for {profile}" logic
    (`status_presenter.midi_indicator()`) already says the right thing."""
    if status is GridStatus.ACTIVE:
        return None
    if status is GridStatus.UNSUPPORTED:
        return f"{GRID_PROFILE_NAME}: unsupported topology ({reason})" if reason else f"{GRID_PROFILE_NAME}: unsupported topology"
    return _STATUS_TEXT[status]


def grid_status_is_error(status: GridStatus) -> bool:
    """Whether this status should light the Status UI's existing *error* dot -
    repurposed for Grid the same way it already carries a different concrete
    meaning per profile (Native Mode failure for the Studio, OSC listener-bind
    failure elsewhere)."""
    return status in _ERROR_STATUSES
