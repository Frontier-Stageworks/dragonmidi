"""Tests for the Controller Profile dropdown's choice representation
(docs/llds/intech-grid.md § Active Grid Controller - "the application must be
able to offer 'Intech Grid' before a GridRuntimeController exists").

@spec GRID-CTRL-007
"""

from __future__ import annotations

from dragonmidi.controller_profile import ControllerProfile
from dragonmidi.controller_selection import GRID_CHOICE_NAME, GridChoice, StaticChoice, build_controller_choices


def _profile(name: str) -> ControllerProfile:
    return ControllerProfile(
        name=name,
        match_substring=name.lower(),
        has_native_mode=False,
        default_channel=0,
        has_jog_wheel=False,
        has_scene_button=False,
        opinionated_map={},
    )


def test_build_controller_choices_wraps_every_loaded_profile() -> None:
    profiles = (_profile("nanoKONTROL Studio"), _profile("nanoKONTROL2"))
    choices = build_controller_choices(profiles)
    assert choices[0] == StaticChoice(profile=profiles[0])
    assert choices[1] == StaticChoice(profile=profiles[1])


def test_build_controller_choices_appends_the_grid_choice_last() -> None:
    choices = build_controller_choices((_profile("nanoKONTROL Studio"),))
    assert isinstance(choices[-1], GridChoice)
    assert choices[-1].name == GRID_CHOICE_NAME == "Intech Grid"


def test_grid_choice_carries_no_profile_data() -> None:
    # The whole point: a GridChoice exists before any GridRuntimeController does.
    choice = GridChoice()
    assert not hasattr(choice, "profile")


def test_choice_names_for_dropdown_population() -> None:
    profiles = (_profile("nanoKONTROL Studio"),)
    choices = build_controller_choices(profiles)
    assert [c.name for c in choices] == ["nanoKONTROL Studio", "Intech Grid"]
