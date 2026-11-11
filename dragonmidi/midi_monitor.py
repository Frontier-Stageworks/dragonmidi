"""The MIDI Input Monitor's Qt-free domain logic (docs/llds/midi-monitor.md):
a shared observation point `app.py`'s MIDI dispatch records every raw event
into, and `midi_monitor_widgets.MidiMonitorDialog` renders from. Owns no MIDI
connection, no Grid resolution logic, and no output adapter - purely a bounded
log plus the one `diagnostic_active` flag the dispatch path checks.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from .events import MidiEvent
from .grid_controller import ModuleRef

_DEFAULT_CAPACITY = 500

_TYPE_LABELS: dict[str, str] = {
    "cc": "CC",
    "pitchbend": "Pitch Bend",
    "program": "Program Change",
    "aftertouch": "Aftertouch",
    "polytouch": "Poly Aftertouch",
    "korg_scene": "KORG Scene",
}


def format_event_type(event: MidiEvent) -> str:
    """@spec MON-UI-002"""
    if event.type == "note":
        return "Note On" if event.is_press else "Note Off"
    return _TYPE_LABELS.get(event.type, event.type)


def format_channel(channel: int | None) -> str:
    """Matches `mapping_view_model.midi_source_label`'s existing +1 display
    convention - a distinct function since that one is scoped to declared
    mapping keys, not arbitrary raw event display.

    @spec MON-UI-003
    """
    return "-" if channel is None else f"ch{channel + 1}"


def format_number(number: int | None) -> str:
    """@spec MON-UI-003"""
    return "-" if number is None else str(number)


def format_module(module: ModuleRef | None) -> str:
    """@spec MON-UI-002, MON-UI-003"""
    return "-" if module is None else f"{module.module_type} #{module.ordinal}"


def format_resolved(resolved: tuple[str, int | None] | None) -> str:
    """@spec MON-UI-002, MON-UI-003"""
    if resolved is None:
        return "-"
    kind, number = resolved
    return kind if number is None else f"{kind} {number}"


@dataclass(frozen=True)
class MonitorEvent:
    """One recorded, immutable observation. `raw` is exactly the `MidiEvent`
    `app.py` received, before Grid resolution - never overwritten, so the
    wire-level CC/note identity survives even once `resolved`/`module` are
    also known (@spec MON-CAPTURE-003).

    @spec MON-CAPTURE-004, MON-CAPTURE-005
    """

    timestamp: float  # time.time(), wall-clock, for display only
    device_name: str | None
    raw: MidiEvent
    resolved: tuple[str, int | None] | None
    module: ModuleRef | None
    captured: bool


class MidiMonitor:
    """@spec MON-CAPTURE-001, MON-CAPTURE-006, MON-CAPTURE-007"""

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._events: deque[MonitorEvent] = deque(maxlen=capacity)
        # Plain attributes, mutated directly by MidiMonitorDialog and read
        # directly by app.py's dispatch path - both run on the Qt main
        # thread, matching every other plain-bool UI-thread flag in this app
        # (e.g. DragonMidiWindow._dirty). No lock needed.
        self.diagnostic_active: bool = False
        self.capture_pending: bool = False
        self._last_captured: MonitorEvent | None = None
        self._version: int = 0

    @property
    def events(self) -> Sequence[MonitorEvent]:
        """Oldest-first, bounded to this monitor's capacity."""
        return tuple(self._events)

    @property
    def last_captured(self) -> MonitorEvent | None:
        return self._last_captured

    @property
    def version(self) -> int:
        """Increments on every `record()`/`clear()` - lets a renderer skip
        work on a tick where nothing changed (@spec MON-UI-008)."""
        return self._version

    def record(
        self,
        raw: MidiEvent,
        *,
        device_name: str | None,
        resolved: tuple[str, int | None] | None,
        module: ModuleRef | None,
    ) -> MonitorEvent:
        """@spec MON-CAPTURE-002, MON-CAPTURE-003, MON-CAPTURE-006, MON-UI-005"""
        captured = self.capture_pending
        if captured:
            self.capture_pending = False
        entry = MonitorEvent(
            timestamp=time.time(),
            device_name=device_name,
            raw=raw,
            resolved=resolved,
            module=module,
            captured=captured,
        )
        self._events.append(entry)  # deque(maxlen=...) evicts the oldest automatically
        if captured:
            self._last_captured = entry
        self._version += 1
        return entry

    def request_capture_next(self) -> None:
        """Setting an already-`True` flag is a no-op by construction - this
        is what makes a second press while already pending idempotent
        (@spec MON-UI-006), with no extra guard needed."""
        self.capture_pending = True

    def clear(self) -> None:
        """Empties the log only - leaves `diagnostic_active`/`capture_pending`
        untouched (@spec MON-UI-004)."""
        self._events.clear()
        self._last_captured = None
        self._version += 1
