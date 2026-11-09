"""Grid runtime topology model (docs/llds/intech-grid.md § Runtime Topology Model).

A module's identity *is* its (x, y) position - no stable per-module serial
number exists in the heartbeat payload (source: Intech Studio `grid-fw`,
GPL-3.0-only; no such field was found). `GridTopologyBuilder` accumulates
heartbeats into per-slot state and answers "is this settled" and "what,
exactly, counts as a structural change" as pure functions of a caller-supplied
`now`, rather than mutating state on a timer - this keeps settle/staleness
behavior independent of how often the caller happens to poll.

500ms (`DISCONNECT_TIMEOUT_SECONDS`) is Grid's own disconnect-timeout constant
(source: `GRID_PARAMETER_UART_DISCONNECTTIMEOUT_us`), reused rather than
invented. The settle window is this project's own tunable constant - see
`GridTopologyBuilder`'s docstring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .grid_modules import ModuleType, module_type_from_hwcfg
from .grid_protocol import GridHeartbeat

DISCONNECT_TIMEOUT_SECONDS = 0.5

# Phase 1 initial value - hardware-unvalidated, subject to revision once real
# heartbeat jitter is observed (docs/llds/intech-grid.md § Open Questions).
DEFAULT_SETTLE_WINDOW_SECONDS = 0.5


@dataclass(frozen=True)
class GridModule:
    heartbeat_type: int
    hwcfg: int
    module_type: ModuleType | None
    x: int
    y: int
    rotation: int


@dataclass(frozen=True)
class GridTopology:
    modules: tuple[GridModule, ...]
    current_page: int


@dataclass
class _Slot:
    heartbeat_type: int
    hwcfg: int
    rotation: int
    last_seen: float
    last_changed: float  # the `now` this slot was created, or last structurally changed


class GridTopologyBuilder:
    """Accumulates Grid heartbeats; `observe()` feeds one in, `settled(now)`
    returns a `GridTopology` snapshot once settle conditions hold, else `None`.

    @spec GRID-TOPO-005, GRID-TOPO-006, GRID-TOPO-007, GRID-TOPO-008
    """

    def __init__(self, settle_window: float = DEFAULT_SETTLE_WINDOW_SECONDS) -> None:
        self._settle_window = settle_window
        self._slots: dict[tuple[int, int], _Slot] = {}
        self._current_page: int | None = None
        self._last_page_change: float | None = None
        self._gridmaster_ever_seen = False

    def observe(self, heartbeat: GridHeartbeat, now: float) -> None:
        """@spec GRID-TOPO-005, GRID-TOPO-006"""
        key = (heartbeat.x, heartbeat.y)
        existing = self._slots.get(key)
        expired = existing is not None and (now - existing.last_seen) > DISCONNECT_TIMEOUT_SECONDS
        is_new_or_changed = (
            existing is None
            or expired
            or existing.heartbeat_type != heartbeat.heartbeat_type
            or existing.hwcfg != heartbeat.hwcfg
            or existing.rotation != heartbeat.rotation
        )
        last_changed = now if is_new_or_changed else existing.last_changed
        self._slots[key] = _Slot(
            heartbeat_type=heartbeat.heartbeat_type,
            hwcfg=heartbeat.hwcfg,
            rotation=heartbeat.rotation,
            last_seen=now,
            last_changed=last_changed,
        )

        if heartbeat.heartbeat_type == 1:
            self._gridmaster_ever_seen = True
            if self._current_page != heartbeat.page:
                self._current_page = heartbeat.page
                self._last_page_change = now

    def _active_slots(self, now: float) -> dict[tuple[int, int], _Slot]:
        return {key: slot for key, slot in self._slots.items() if (now - slot.last_seen) <= DISCONNECT_TIMEOUT_SECONDS}

    def _last_structural_change(self, now: float) -> float | None:
        """@spec GRID-TOPO-006 - a pure function of `now`, not a mutated
        timestamp, so staleness never depends on how often the caller polls."""
        events: list[float] = []
        if self._last_page_change is not None:
            events.append(self._last_page_change)
        for slot in self._slots.values():
            events.append(slot.last_changed)
            expiry = slot.last_seen + DISCONNECT_TIMEOUT_SECONDS
            if expiry <= now:
                events.append(expiry)  # the moment this slot became expired is itself a structural change
        return max(events) if events else None

    def has_changed_since(self, baseline: float, now: float) -> bool:
        """True the instant any structural change (§3's definition) has
        occurred after `baseline` - unlike `settled()`, this is never gated by
        the settle window; an already-built controller must go stale
        immediately on change, not after waiting out another settle period.

        @spec GRID-TOPO-012
        """
        last_change = self._last_structural_change(now)
        return last_change is not None and last_change > baseline

    def settled(self, now: float) -> GridTopology | None:
        """@spec GRID-TOPO-007, GRID-TOPO-008"""
        if not self._gridmaster_ever_seen or self._current_page is None:
            return None
        last_change = self._last_structural_change(now)
        if last_change is None or (now - last_change) < self._settle_window:
            return None
        active = self._active_slots(now)
        modules = tuple(
            GridModule(
                heartbeat_type=slot.heartbeat_type,
                hwcfg=slot.hwcfg,
                module_type=module_type_from_hwcfg(slot.hwcfg),
                x=x,
                y=y,
                rotation=slot.rotation,
            )
            for (x, y), slot in active.items()
        )
        return GridTopology(modules=modules, current_page=self._current_page)


def normalize_linear_order(modules: Sequence[GridModule]) -> tuple[GridModule, ...]:
    """Sorts by absolute `x` ascending; the result's *position* in this
    sequence - not any module's `x` value - is every downstream numbering
    rule's basis. Invariant to a constant offset applied to every module's `x`
    (a USB-root change).

    @spec GRID-TOPO-009
    """
    return tuple(sorted(modules, key=lambda m: m.x))


def validate_single_row(topology: GridTopology) -> bool:
    """True only if every module - recognized or not - shares one `y`. Checked
    against the complete module set, before module-type recognition is even
    consulted; an empty topology trivially passes (nothing to disagree).

    @spec GRID-TOPO-010, GRID-TOPO-011
    """
    ys = {m.y for m in topology.modules}
    return len(ys) <= 1


__all__ = [
    "DISCONNECT_TIMEOUT_SECONDS",
    "DEFAULT_SETTLE_WINDOW_SECONDS",
    "GridModule",
    "GridTopology",
    "GridTopologyBuilder",
    "normalize_linear_order",
    "validate_single_row",
]
