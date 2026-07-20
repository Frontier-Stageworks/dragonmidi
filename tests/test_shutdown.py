"""Tests for the shutdown sequence runner (docs/specs/app-ui.md § Threading and Shutdown).

@spec UI-SHUTDOWN-001
"""

from __future__ import annotations

import threading
import time

from dragonmidi.shutdown import run_shutdown_sequence


# @spec UI-SHUTDOWN-001
def test_all_steps_run_even_when_one_raises() -> None:
    call_order: list[str] = []

    def step_a() -> None:
        call_order.append("a")

    def step_b() -> None:
        call_order.append("b")
        raise RuntimeError("Native Mode release failed")

    def step_c() -> None:
        call_order.append("c")

    results = run_shutdown_sequence([step_a, step_b, step_c], timeout=1.0)

    assert call_order == ["a", "b", "c"]  # c must run despite b's failure
    assert results[0] is None
    assert isinstance(results[1], RuntimeError)
    assert results[2] is None


# @spec UI-SHUTDOWN-001
def test_step_exception_does_not_propagate_out_of_the_sequence() -> None:
    def raises() -> None:
        raise ValueError("boom")

    # Must not raise, even though every step fails.
    results = run_shutdown_sequence([raises, raises], timeout=1.0)
    assert all(isinstance(r, ValueError) for r in results)


# @spec UI-SHUTDOWN-001
def test_hanging_step_times_out_and_subsequent_steps_still_run() -> None:
    call_order: list[str] = []

    def hangs() -> None:
        call_order.append("start-hang")
        time.sleep(5.0)  # far longer than the test's timeout below
        call_order.append("finished-hang")  # should not happen before the assertions run

    def quick() -> None:
        call_order.append("quick")

    start = time.monotonic()
    results = run_shutdown_sequence([hangs, quick], timeout=0.1)
    elapsed = time.monotonic() - start

    assert elapsed < 1.0  # did not wait for the full 5s sleep
    assert call_order[0] == "start-hang"
    assert "quick" in call_order  # the next step ran despite the prior one hanging
    assert isinstance(results[0], TimeoutError)
    assert results[1] is None


# @spec UI-SHUTDOWN-001
def test_steps_run_in_sequence_not_concurrently_when_all_succeed() -> None:
    # A step that briefly sleeps should have fully completed before the next one starts,
    # proving steps are not simply fired off in parallel and raced.
    events: list[str] = []
    lock = threading.Lock()

    def slow_step() -> None:
        with lock:
            events.append("slow-start")
        time.sleep(0.05)
        with lock:
            events.append("slow-end")

    def next_step() -> None:
        with lock:
            events.append("next-start")

    run_shutdown_sequence([slow_step, next_step], timeout=1.0)
    assert events == ["slow-start", "slow-end", "next-start"]
