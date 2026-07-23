"""Tests for the Keystroke Output Adapter (docs/specs/keystroke-output.md).

@spec KEY-SEND-001, KEY-SEND-002, KEY-SEND-003, KEY-SEND-004, KEY-SEND-005, KEY-SEND-006
@spec KEY-BACKEND-001
"""

from __future__ import annotations

from dragonmidi.events import KeyCombo
from dragonmidi.keystroke_output import KeystrokeOutputAdapter


class FakeKeystrokeBackend:
    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self._fail_on = fail_on or set()

    def press(self, key: str) -> None:
        if key in self._fail_on:
            raise RuntimeError(f"simulated press failure: {key}")
        self.calls.append(("press", key))

    def release(self, key: str) -> None:
        if key in self._fail_on:
            raise RuntimeError(f"simulated release failure: {key}")
        self.calls.append(("release", key))


# --- KEY-SEND-001: press modifiers, then key down/up, then release modifiers ---


# @spec KEY-SEND-001
def test_send_presses_modifiers_then_key_then_releases_in_reverse_modifier_order() -> None:
    combo = KeyCombo(frozenset({"alt", "shift"}), "right")
    backend = FakeKeystrokeBackend()
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(combo)

    calls = backend.calls
    assert calls.count(("press", "right")) == 1
    assert calls.count(("release", "right")) == 1
    key_press_idx = calls.index(("press", "right"))
    key_release_idx = calls.index(("release", "right"))
    assert key_release_idx == key_press_idx + 1  # key pressed then immediately released

    before = calls[:key_press_idx]
    after = calls[key_release_idx + 1 :]
    assert all(kind == "press" and key in combo.modifiers for kind, key in before)
    assert all(kind == "release" and key in combo.modifiers for kind, key in after)
    assert {key for _, key in before} == combo.modifiers
    assert {key for _, key in after} == combo.modifiers

    modifier_press_order = [key for _, key in before]
    modifier_release_order = [key for _, key in after]
    assert modifier_release_order == list(reversed(modifier_press_order))


# @spec KEY-SEND-001
def test_send_with_no_modifiers_just_presses_and_releases_the_key() -> None:
    backend = FakeKeystrokeBackend()
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset(), "right"))

    assert backend.calls == [("press", "right"), ("release", "right")]


# @spec KEY-SEND-001
def test_send_single_modifier_order_is_fully_deterministic() -> None:
    backend = FakeKeystrokeBackend()
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset({"shift"}), "left"))

    assert backend.calls == [
        ("press", "shift"),
        ("press", "left"),
        ("release", "left"),
        ("release", "shift"),
    ]


# --- KEY-SEND-002: modifiers always released, even if the key press raises ---


# @spec KEY-SEND-002
def test_send_still_releases_modifiers_when_key_press_raises() -> None:
    backend = FakeKeystrokeBackend(fail_on={"right"})
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset({"alt", "shift"}), "right"))  # must not raise

    presses = [key for kind, key in backend.calls if kind == "press"]
    releases = [key for kind, key in backend.calls if kind == "release"]
    assert set(presses) == {"alt", "shift"}  # "right"'s press failed, never recorded
    assert set(releases) == {"alt", "shift"}  # but both modifiers were still released


# @spec KEY-SEND-002
def test_send_still_releases_remaining_modifiers_when_one_modifier_press_raises() -> None:
    backend = FakeKeystrokeBackend(fail_on={"alt"})
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset({"alt", "shift"}), "right"))  # must not raise

    releases = [key for kind, key in backend.calls if kind == "release"]
    assert "shift" in releases  # the modifier that *did* press is still cleaned up


# --- KEY-SEND-003: backend failures are caught and logged, never raised ---


# @spec KEY-SEND-003
def test_send_swallows_total_backend_failure_without_raising() -> None:
    backend = FakeKeystrokeBackend(fail_on={"alt", "shift", "right"})
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset({"alt", "shift"}), "right"))  # must not raise


# @spec KEY-SEND-003
def test_send_swallows_unrecognized_key_lookup_failure() -> None:
    class RaisesOnUnknownKey:
        def press(self, key: str) -> None:
            if key == "unknown":
                raise KeyError(key)

        def release(self, key: str) -> None:
            if key == "unknown":
                raise KeyError(key)

    adapter = KeystrokeOutputAdapter(RaisesOnUnknownKey())
    adapter.send(KeyCombo(frozenset(), "unknown"))  # must not raise


# --- KEY-SEND-004: no debounce or dedup ---


# @spec KEY-SEND-004
def test_send_repeated_identical_combo_performs_the_full_sequence_every_time() -> None:
    backend = FakeKeystrokeBackend()
    adapter = KeystrokeOutputAdapter(backend)
    combo = KeyCombo(frozenset(), "right")

    adapter.send(combo)
    adapter.send(combo)

    assert backend.calls.count(("press", "right")) == 2
    assert backend.calls.count(("release", "right")) == 2


# --- KEY-SEND-005 / KEY-SEND-006: no frontmost-app check, no permission pre-flight ---


# @spec KEY-SEND-005, KEY-SEND-006
def test_send_requires_no_focus_or_permission_check_to_succeed() -> None:
    # send() takes only a combo - no frontmost-app or permission state is consulted
    # or required before the backend is called.
    backend = FakeKeystrokeBackend()
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset(), "right"))

    assert ("press", "right") in backend.calls


# --- KEY-BACKEND-001: swappable backend, not hard-coded to any specific implementation ---


# @spec KEY-BACKEND-001
def test_adapter_works_with_any_object_implementing_press_and_release() -> None:
    class MinimalBackend:
        def __init__(self) -> None:
            self.pressed: list[str] = []
            self.released: list[str] = []

        def press(self, key: str) -> None:
            self.pressed.append(key)

        def release(self, key: str) -> None:
            self.released.append(key)

    backend = MinimalBackend()
    adapter = KeystrokeOutputAdapter(backend)

    adapter.send(KeyCombo(frozenset({"shift"}), "left"))

    assert backend.pressed == ["shift", "left"]
    assert backend.released == ["left", "shift"]
