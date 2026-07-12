from __future__ import annotations


class FakeClock:
    """A settable monotonic-style clock for deterministic liveness/debounce tests.

    Defined here (not just in conftest.py) so Hypothesis-decorated tests can
    construct a fresh instance per generated example instead of sharing one
    pytest-fixture instance across all examples in a single test invocation.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def set(self, value: float) -> None:
        self._now = value
