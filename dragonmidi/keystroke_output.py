from __future__ import annotations

import logging
from typing import Any, Protocol

from .events import KeyCombo

logger = logging.getLogger(__name__)


class KeystrokeBackend(Protocol):
    def press(self, key: str) -> None: ...
    def release(self, key: str) -> None: ...


class KeystrokeOutputAdapter:
    """Synthesizes OS-level keystrokes for Dragonframe functions with no OSC equivalent.

    A narrow, secondary output path alongside the OSC Client - most controls never use
    it. Failures never propagate out of `send()`: this must not crash the app or
    interrupt MIDI/OSC processing for one failed synthesized keystroke.

    @spec KEY-SEND-001, KEY-SEND-002, KEY-SEND-003, KEY-SEND-004, KEY-SEND-005, KEY-SEND-006
    @spec KEY-BACKEND-001
    """

    def __init__(self, backend: KeystrokeBackend) -> None:
        self._backend = backend

    def send(self, combo: KeyCombo) -> None:
        pressed: list[str] = []
        try:
            for modifier in combo.modifiers:
                try:
                    self._backend.press(modifier)
                    pressed.append(modifier)
                except Exception:
                    logger.exception("Failed to press modifier %r for keystroke output", modifier)
            try:
                self._backend.press(combo.key)
                self._backend.release(combo.key)
            except Exception:
                logger.exception("Failed to send key %r for keystroke output", combo.key)
        finally:
            # Modifiers are always released, even if pressing the key above raised -
            # a stuck modifier at the OS level would corrupt every subsequent real
            # keystroke until manually cleared, a far worse failure than one missed send.
            for modifier in reversed(pressed):
                try:
                    self._backend.release(modifier)
                except Exception:
                    logger.exception("Failed to release modifier %r for keystroke output", modifier)


class PynputBackend:
    """The real KeystrokeBackend, backed by `pynput.keyboard.Controller`."""

    def __init__(self) -> None:
        from pynput.keyboard import Controller, Key

        self._controller = Controller()
        self._keys: dict[str, Any] = {
            "alt": Key.alt,
            "shift": Key.shift,
            "ctrl": Key.ctrl,
            "cmd": Key.cmd,
            "right": Key.right,
            "left": Key.left,
        }

    def press(self, key: str) -> None:
        self._controller.press(self._keys[key])

    def release(self, key: str) -> None:
        self._controller.release(self._keys[key])
