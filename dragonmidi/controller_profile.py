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
    quirks. Discovered from Controller Profile config files (`controller_profile_loader.py`,
    @spec PROFILE-LOAD-001) rather than hardcoded; two ship bundled today, the
    nanoKONTROL Studio and the nanoKONTROL2 (`mapping.STUDIO_PROFILE`,
    `mapping.NANOKONTROL2_PROFILE`).

    `opinionated_map`, `websocket_keys`, `fader_keys`, `knob_to_fader`,
    `mute_to_fader`, `fader_to_knob`, and `control_names` are all derived from the
    config file's `controls:` block (`mapping.ControlsConfig`) by `mapping.py`'s
    `build_*` functions at profile-construction time - this module stays ignorant
    of `mapping.py`'s internal types (loosely typed as `Any`/`Mapping[Any, Any]`
    here) to avoid a circular import, since `mapping.py` imports `ControllerProfile`
    from here.

    @spec MIDI-PROFILE-001
    """

    name: str
    match_substring: str
    has_native_mode: bool
    default_channel: int
    has_jog_wheel: bool
    has_scene_button: bool
    opinionated_map: Mapping[Any, Any]
    websocket_keys: Any = None
    setup_hint: "str | None" = None
    # Bank membership - positional, not CC-arithmetic (@spec MAP-CONFIG-008):
    fader_keys: "frozenset[Any]" = frozenset()
    knob_to_fader: Mapping[Any, Any] = None  # type: ignore[assignment]
    mute_to_fader: Mapping[Any, Any] = None  # type: ignore[assignment]
    fader_to_knob: Mapping[Any, Any] = None  # type: ignore[assignment]
    control_names: Mapping[Any, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Frozen dataclass - can't assign fields directly; enforce empty-dict
        # defaults for the Mapping fields without letting a single mutable
        # default dict be shared across every instance that doesn't pass one.
        if self.knob_to_fader is None:
            object.__setattr__(self, "knob_to_fader", {})
        if self.mute_to_fader is None:
            object.__setattr__(self, "mute_to_fader", {})
        if self.fader_to_knob is None:
            object.__setattr__(self, "fader_to_knob", {})
        if self.control_names is None:
            object.__setattr__(self, "control_names", {})

    def matches(self, port_name: str) -> bool:
        """Fuzzy name match against an enumerated MIDI port name: strip
        non-alphanumeric characters, lowercase, and check for the profile's
        match substring.

        @spec MIDI-CONN-002
        """
        return self.match_substring in _normalize(port_name)

    def bank_fader_key(self, key: Any) -> Any:
        """Given a Knob/Mute key, return its bank's Fader key by positional index
        (Bank N = index N-1 in each of faders/knobs/mutes), not CC arithmetic -
        `None` if `key` is not a bank member for this profile.
        """
        return self.knob_to_fader.get(key) or self.mute_to_fader.get(key)
