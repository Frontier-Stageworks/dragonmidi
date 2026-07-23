from __future__ import annotations

import threading
from collections.abc import Callable


def run_shutdown_sequence(steps: list[Callable[[], None]], timeout: float = 5.0) -> list[BaseException | None]:
    """Run each step in its own isolated, timeout-bounded attempt, in sequence.

    A failing or hanging step never blocks the steps after it; each step's outcome
    is captured independently.

    @spec UI-SHUTDOWN-001
    """
    results: list[BaseException | None] = []
    for step in steps:
        outcome: list[BaseException | None] = [None]

        def _run(box: list[BaseException | None] = outcome, fn: Callable[[], None] = step) -> None:
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001 - isolate arbitrary step failures
                box[0] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            results.append(TimeoutError(f"shutdown step timed out after {timeout}s"))
        else:
            results.append(outcome[0])
    return results
