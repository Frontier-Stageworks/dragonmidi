"""Shared fuzzy name-matching helper, extracted from `controller_profile.py` so
`GridRuntimeController` (docs/llds/intech-grid.md § Controller-Defined bank_count
and MIDI-Port Discovery) can reuse the exact same normalization without
depending on `controller_profile.py` - a module whose whole purpose is
YAML-declared static profiles, which Grid genuinely isn't."""

from __future__ import annotations

import re


def normalize_name(name: str) -> str:
    """Strip non-alphanumeric characters and lowercase - the same normalization
    `ControllerProfile.matches()` has always used for fuzzy MIDI/serial port
    name matching."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def fuzzy_contains(match_substring: str, name: str) -> bool:
    """True if `match_substring` (already expected to be pre-normalized, e.g.
    `"nanokontrolstudio"`) appears in `name` once `name` is normalized the same way."""
    return match_substring in normalize_name(name)
