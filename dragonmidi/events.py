from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MidiEvent:
    """A normalized MIDI event, independent of the underlying MIDI library.

    @spec MIDI-EVT-001
    """

    type: str
    channel: int | None
    number: int | None
    raw_value: int
    normalized: float
    is_press: bool
    is_release: bool


@dataclass(frozen=True)
class OscMessage:
    address: str
    args: tuple


@dataclass(frozen=True)
class KeyCombo:
    """A synthesized OS-level keystroke: modifiers held down, then `key` tapped.

    @spec KEY-SEND-001
    """

    modifiers: frozenset[str]
    key: str
