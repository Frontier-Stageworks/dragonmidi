from __future__ import annotations

import queue
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def drain_queue(q: queue.Queue[T], handler: Callable[[T], None]) -> int:
    """Fully drain a queue on every call, with no per-call cap.

    @spec UI-THREAD-001
    """
    count = 0
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            break
        handler(item)
        count += 1
    return count
