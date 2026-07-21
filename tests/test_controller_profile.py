"""Tests for the ControllerProfile shape and fuzzy name matching
(docs/specs/midi-input.md § Controller Profiles).

@spec MIDI-PROFILE-001, MIDI-CONN-002
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from dragonmidi.controller_profile import ControllerProfile

SEPARATORS = ["", " ", "-", "_", "  "]
UNRELATED_NAMES = [
    "Launchpad Mini MK3",
    "Komplete Kontrol S49",
    "USB MIDI Device",
    "",
    "IAC Driver Bus 1",
    "nanoKEY Studio",  # deliberately close but not a match: no "kontrol"
]


def _profile(match_substring: str) -> ControllerProfile:
    return ControllerProfile(
        name="test",
        match_substring=match_substring,
        has_native_mode=False,
        default_channel=0,
        has_jog_wheel=False,
        has_scene_button=False,
        opinionated_map={},
    )


# ---------------------------------------------------------------------------
# Studio-shaped substring ("nanokontrolstudio") - mirrors the prior
# is_nanokontrol_studio() behavior this profile-driven mechanism replaces.
# ---------------------------------------------------------------------------


@given(
    prefix=st.sampled_from(["", "KORG ", "korg "]),
    sep1=st.sampled_from(SEPARATORS),
    casing=st.sampled_from([str.lower, str.upper, str.title, lambda s: s]),
    suffix=st.sampled_from(["", " SLIDER/KNOB", " Port 1", "-1"]),
)
# @spec MIDI-CONN-002
def test_studio_pattern_matches_real_device_name_variants(prefix, sep1, casing, suffix) -> None:
    name = f"{prefix}nano{sep1}KONTROL{sep1}Studio{suffix}"
    name = casing(name)
    assert _profile("nanokontrolstudio").matches(name)


@given(name=st.sampled_from(UNRELATED_NAMES))
# @spec MIDI-CONN-002
def test_studio_pattern_never_matches_unrelated_names(name: str) -> None:
    assert not _profile("nanokontrolstudio").matches(name)


# ---------------------------------------------------------------------------
# nanoKONTROL2's substring ("nanokontrol2") - must not collide with the
# Studio's pattern in either direction (docs/llds/midi-input.md § Controller
# Profiles: "the two substrings can't collide with each other's port names").
# ---------------------------------------------------------------------------


@given(
    prefix=st.sampled_from(["", "KORG ", "korg "]),
    sep1=st.sampled_from(SEPARATORS),
    casing=st.sampled_from([str.lower, str.upper, str.title, lambda s: s]),
    suffix=st.sampled_from(["", " SLIDER/KNOB", " Port 1", "-1"]),
)
# @spec MIDI-CONN-002, MIDI-PROFILE-003
def test_nanokontrol2_pattern_matches_real_device_name_variants(prefix, sep1, casing, suffix) -> None:
    name = f"{prefix}nano{sep1}KONTROL{sep1}2{suffix}"
    name = casing(name)
    assert _profile("nanokontrol2").matches(name)


@given(name=st.sampled_from(UNRELATED_NAMES + ["nanoKONTROL Studio", "KORG nanoKONTROL Studio SLIDER/KNOB"]))
# @spec MIDI-CONN-002, MIDI-PROFILE-002, MIDI-PROFILE-003
def test_nanokontrol2_pattern_never_matches_studio_or_unrelated_names(name: str) -> None:
    assert not _profile("nanokontrol2").matches(name)


@given(name=st.sampled_from(["nanoKONTROL2", "nanoKONTROL2 CTRL", "KORG nanoKONTROL2"]))
# @spec MIDI-CONN-002, MIDI-PROFILE-002
def test_studio_pattern_never_matches_nanokontrol2_names(name: str) -> None:
    assert not _profile("nanokontrolstudio").matches(name)


@given(name=st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=30))
@example("")
# @spec MIDI-CONN-002
def test_random_strings_without_the_target_substring_never_match(name: str) -> None:
    import re

    normalized = re.sub(r"[^a-z0-9]+", "", name.lower())
    if "nanokontrol2" in normalized:
        return  # hypothesis got unlucky and generated a real match; not a counterexample
    assert not _profile("nanokontrol2").matches(name)
