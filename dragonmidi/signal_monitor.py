from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ChannelState(Enum):
    LIVE = "live"
    ERROR = "error"
    QUIET = "quiet"


@dataclass
class _Channel:
    last_activity: float | None = None
    error: bool = False


class SignalMonitor:
    """Recency-based liveness tracker for the MIDI and Dragonframe channels.

    @spec UI-MONITOR-001, UI-MONITOR-002, UI-MONITOR-003
    """

    def __init__(self, liveness_window: float = 2.0, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = liveness_window
        self._clock = clock
        self._channels: dict[str, _Channel] = {
            "midi": _Channel(),
            "dragonframe": _Channel(),
        }

    def mark_activity(self, channel: str) -> None:
        self._channels[channel].last_activity = self._clock()

    def set_error(self, channel: str, active: bool) -> None:
        self._channels[channel].error = active

    def state(self, channel: str) -> ChannelState:
        entry = self._channels[channel]
        if entry.error:
            return ChannelState.ERROR
        if entry.last_activity is None:
            return ChannelState.QUIET
        if (self._clock() - entry.last_activity) < self._window:
            return ChannelState.LIVE
        return ChannelState.QUIET
