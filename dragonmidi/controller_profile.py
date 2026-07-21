from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


@dataclass(frozen=True)
class ControllerProfile:
    """Per-device knowledge shared by the MIDI Input Adapter (`midi_input.py`) and the
    Static Mapping Engine (`mapping.py`), so neither hardcodes a single controller's
    quirks. Two instances ship: the nanoKONTROL Studio and the nanoKONTROL2
    (`mapping.STUDIO_PROFILE`, `mapping.NANOKONTROL2_PROFILE`).

    @spec MIDI-PROFILE-001
    """

    name: str
    match_substring: str
    has_native_mode: bool
    default_channel: int
    has_jog_wheel: bool
    has_scene_button: bool
    opinionated_map: Mapping[Any, Any]

    def matches(self, port_name: str) -> bool:
        """Fuzzy name match against an enumerated MIDI port name: strip
        non-alphanumeric characters, lowercase, and check for the profile's
        match substring.

        @spec MIDI-CONN-002
        """
        return self.match_substring in _normalize(port_name)
