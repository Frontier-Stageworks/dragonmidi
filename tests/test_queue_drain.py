"""Tests for the queue-drain helper (docs/specs/app-ui.md § Threading and the Qt Bridge).

@spec UI-THREAD-001
"""

from __future__ import annotations

import queue

from hypothesis import given, settings
from hypothesis import strategies as st

from dragonmidi.queue_drain import drain_queue


@given(items=st.lists(st.integers(), max_size=2000))
@settings(max_examples=50)
# @spec UI-THREAD-001
def test_drain_delivers_every_item_in_order_with_no_cap(items: list[int]) -> None:
    q: "queue.Queue[int]" = queue.Queue()
    for item in items:
        q.put(item)

    received: list[int] = []
    count = drain_queue(q, received.append)

    assert received == items  # FIFO order, nothing dropped, no per-call cap
    assert count == len(items)
    assert q.empty()


# @spec UI-THREAD-001
def test_draining_an_already_empty_queue_calls_handler_zero_times() -> None:
    q: "queue.Queue[int]" = queue.Queue()
    calls = []
    count = drain_queue(q, calls.append)
    assert count == 0
    assert calls == []


# @spec UI-THREAD-001
def test_second_drain_after_first_finds_nothing_new() -> None:
    q: "queue.Queue[int]" = queue.Queue()
    q.put(1)
    q.put(2)
    first_pass: list[int] = []
    drain_queue(q, first_pass.append)
    second_pass: list[int] = []
    count = drain_queue(q, second_pass.append)
    assert first_pass == [1, 2]
    assert second_pass == []
    assert count == 0


# @spec UI-THREAD-001
def test_item_enqueued_by_the_handler_mid_drain_is_picked_up_in_the_same_pass() -> None:
    # A "full drain, no cap" strategy keeps consuming until the queue reports empty,
    # so an item enqueued by the handler itself must still be caught in this same call.
    q: "queue.Queue[int]" = queue.Queue()
    q.put(1)
    seen: list[int] = []

    def handler(item: int) -> None:
        seen.append(item)
        if item == 1:
            q.put(2)

    count = drain_queue(q, handler)
    assert seen == [1, 2]
    assert count == 2
    assert q.empty()
