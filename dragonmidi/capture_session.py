"""Guided Capture Session - Qt-free (docs/llds/midi-monitor.md § Guided
Capture Session). Walks the active controller's currently-unconfirmed
controls one at a time, recording what each one's physical actuation sent.
Produces a report only: no write path into `MappingEngine`, the Preset
Store, or a controller definition file exists anywhere in this module.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .events import MidiEvent
from .midi_monitor import MonitorEvent

if TYPE_CHECKING:
    from .active_controller import ActiveController


@dataclass(frozen=True)
class CaptureStep:
    """@spec MON-GUIDE-001"""

    label: str  # e.g. "Record 3", or "Set Marker" for a global control


@dataclass(frozen=True)
class CaptureResult:
    """@spec MON-GUIDE-006, MON-GUIDE-007, MON-GUIDE-010"""

    label: str
    skipped: bool
    raw: MidiEvent | None  # None iff skipped
    device_name: str | None


def build_capture_steps(controller: "ActiveController") -> list[CaptureStep]:
    """Reads `unconfirmed_channel_controls`/`unconfirmed_global_controls` off
    `controller` via `getattr(..., ())` - absent for a controller family with
    no such concept (Intech Grid today), matching `setup_hint`'s existing
    duck-typed, Protocol-absent precedent (`docs/llds/app-ui.md`).

    @spec MON-GUIDE-001, MON-GUIDE-002
    """
    steps: list[CaptureStep] = []
    for label in getattr(controller, "unconfirmed_channel_controls", ()):
        for n in range(1, controller.bank_count + 1):
            steps.append(CaptureStep(f"{label} {n}"))
    for label in getattr(controller, "unconfirmed_global_controls", ()):
        steps.append(CaptureStep(label))
    return steps


class GuidedCaptureSession:
    """@spec MON-GUIDE-003, MON-GUIDE-004, MON-GUIDE-005, MON-GUIDE-006, MON-GUIDE-007, MON-GUIDE-008"""

    def __init__(self, profile_name: str, steps: Sequence[CaptureStep]) -> None:
        self.profile_name = profile_name
        self._steps = tuple(steps)
        self._index = 0
        self._pending: MonitorEvent | None = None
        self._results: list[CaptureResult] = []

    @property
    def current_step(self) -> CaptureStep | None:
        """`None` once every step has been confirmed or skipped (@spec MON-GUIDE-008)."""
        if self._index >= len(self._steps):
            return None
        return self._steps[self._index]

    @property
    def pending(self) -> MonitorEvent | None:
        return self._pending

    @property
    def results(self) -> Sequence[CaptureResult]:
        return tuple(self._results)

    @property
    def finished(self) -> bool:
        return self._index >= len(self._steps)

    @property
    def total_steps(self) -> int:
        return len(self._steps)

    def offer(self, entry: MonitorEvent) -> None:
        """Replaces the current step's pending candidate - never accumulates
        one. A no-op once finished (nothing left to offer to).

        @spec MON-GUIDE-005
        """
        if self.finished:
            return
        self._pending = entry

    def confirm(self) -> None:
        """Locks in whatever is currently pending as a non-skipped result and
        advances. A no-op once finished.

        @spec MON-GUIDE-006
        """
        step = self.current_step
        if step is None:
            return
        pending = self._pending
        self._results.append(
            CaptureResult(
                label=step.label,
                skipped=False,
                raw=pending.raw if pending is not None else None,
                device_name=pending.device_name if pending is not None else None,
            )
        )
        self._advance()

    def skip(self) -> None:
        """Records the current step as skipped, regardless of any pending
        candidate, and advances. A no-op once finished.

        @spec MON-GUIDE-007
        """
        step = self.current_step
        if step is None:
            return
        self._results.append(CaptureResult(label=step.label, skipped=True, raw=None, device_name=None))
        self._advance()

    def _advance(self) -> None:
        self._index += 1
        self._pending = None


def _raw_to_dict(raw: MidiEvent | None) -> dict | None:
    if raw is None:
        return None
    return {
        "type": raw.type,
        "channel": raw.channel,
        "number": raw.number,
        "raw_value": raw.raw_value,
    }


def build_report(profile_name: str, results: Sequence[CaptureResult], *, clock: Callable[[], float] = time.time) -> dict:
    """@spec MON-GUIDE-010"""
    return {
        "profile_name": profile_name,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(clock())),
        "results": [
            {
                "label": result.label,
                "skipped": result.skipped,
                "raw": _raw_to_dict(result.raw),
                "device_name": result.device_name,
            }
            for result in results
        ],
    }


def save_capture_session(directory: Path, profile_name: str, results: Sequence[CaptureResult], *, clock: Callable[[], float] = time.time) -> Path:
    """Writes one JSON file per completed session, to `directory /
    f"{profile_name}-{timestamp}.json"` - unsanitized, matching
    `preset_store.py`'s existing `f"{profile_name}.json"` precedent. Creates
    `directory` if needed, matching every other `~/Documents/DragonMIDI/...`
    writer in this app.

    @spec MON-GUIDE-010
    """
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(clock()))
    path = directory / f"{profile_name}-{timestamp}.json"
    report = build_report(profile_name, results, clock=clock)
    path.write_text(json.dumps(report, indent=2))
    return path
