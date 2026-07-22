"""Tests for the Controller Profile Loader - discovery, merging, and validation of
Controller Profile config files from the bundled and user-local locations
(docs/specs/midi-input.md § Controller Profile Loading).

@spec PROFILE-LOAD-001, PROFILE-LOAD-002, PROFILE-LOAD-003, PROFILE-LOAD-004
@spec PROFILE-LOAD-005, PROFILE-LOAD-006, PROFILE-LOAD-007, PROFILE-LOAD-008
@spec PROFILE-LOAD-009, PROFILE-LOAD-010, PROFILE-LOAD-011
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dragonmidi.controller_profile_loader import load_controller_profiles

_DEFAULT_CONTROLS = {
    "faders": list(range(8)),
    "knobs": list(range(16, 24)),
    "mutes": list(range(48, 56)),
    "solos": list(range(32, 40)),
    "transport": {"play": 41},
}


def _write_profile(directory: Path, filename: str, **overrides) -> Path:
    fields = {
        "name": "Test Controller",
        "match_substring": "testcontroller",
        "has_native_mode": False,
        "default_channel": 1,
        "has_jog_wheel": False,
        "has_scene_button": False,
        "controls": _DEFAULT_CONTROLS,
    }
    fields.update(overrides)
    path = directory / filename
    path.write_text(yaml.safe_dump(fields))
    return path


@pytest.fixture
def bundled_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bundled"
    d.mkdir()
    return d


@pytest.fixture
def user_dir(tmp_path: Path) -> Path:
    return tmp_path / "documents" / "DragonMIDI" / "controllers"  # deliberately not pre-created


# --- PROFILE-LOAD-001: discovery from both locations, merged result ---


# @spec PROFILE-LOAD-001
def test_discovers_profiles_from_both_bundled_and_user_local_dirs(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="Bundled A", match_substring="bundleda")
    _write_profile(user_dir, "b.yaml", name="User B", match_substring="userb")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert {p.name for p in result.profiles} == {"Bundled A", "User B"}


# --- PROFILE-LOAD-002: recognized extensions ---


# @spec PROFILE-LOAD-002
def test_recognizes_yaml_and_yml_but_ignores_other_extensions(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="A", match_substring="a")
    _write_profile(bundled_dir, "b.yml", name="B", match_substring="b")
    (bundled_dir / "c.json").write_text("{}")
    (bundled_dir / "readme.txt").write_text("not a profile")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert {p.name for p in result.profiles} == {"A", "B"}
    assert result.failures == ()


# --- PROFILE-LOAD-003: same-name override, full substitution ---


# @spec PROFILE-LOAD-003
def test_user_local_profile_fully_replaces_a_same_named_bundled_profile(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "shared.yaml", name="Shared", match_substring="bundledpattern", default_channel=1)
    _write_profile(user_dir, "shared.yaml", name="Shared", match_substring="userpattern", default_channel=5)
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    matches = [p for p in result.profiles if p.name == "Shared"]
    assert len(matches) == 1
    # match_substring came from the user-local file, not the bundled one - proves full
    # substitution rather than a field-by-field merge.
    assert matches[0].match_substring == "userpattern"
    assert matches[0].default_channel == 4  # 5 (1-based, user file) -> 4 (0-based)


# --- PROFILE-LOAD-004: merge order is user-local first, then non-colliding bundled ---


# @spec PROFILE-LOAD-004
def test_merged_order_is_user_local_first_then_bundled(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="Bundled", match_substring="bundled")
    _write_profile(user_dir, "b.yaml", name="Local", match_substring="local")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert [p.name for p in result.profiles] == ["Local", "Bundled"]


# --- PROFILE-LOAD-005: a malformed file is skipped, not fatal to the rest ---


# @spec PROFILE-LOAD-005
def test_malformed_file_is_skipped_and_recorded_without_blocking_others(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "good.yaml", name="Good", match_substring="good")
    bad_path = bundled_dir / "bad.yaml"
    bad_path.write_text("not: [valid, yaml, structure: for a profile at all: [[[")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert [p.name for p in result.profiles] == ["Good"]
    assert len(result.failures) == 1
    assert result.failures[0].path == bad_path


# --- PROFILE-LOAD-006: match_substring collision across different names is warned, not refused ---


# @spec PROFILE-LOAD-006
def test_overlapping_match_substring_across_different_names_logs_but_loads_both(
    bundled_dir: Path, user_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="Alpha", match_substring="widget")
    _write_profile(bundled_dir, "b.yaml", name="Beta", match_substring="widget")
    with caplog.at_level("WARNING"):
        result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert {p.name for p in result.profiles} == {"Alpha", "Beta"}
    assert result.failures == ()
    assert any("Alpha" in r.message and "Beta" in r.message for r in caplog.records)


# --- PROFILE-LOAD-007: missing user-local folder is auto-created and seeded ---


# @spec PROFILE-LOAD-007
def test_missing_user_local_dir_is_created_and_seeded(bundled_dir: Path, user_dir: Path) -> None:
    assert not user_dir.exists()
    load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert user_dir.is_dir()
    assert (user_dir / "README.md").is_file()
    assert list(user_dir.glob("*.example"))


# --- PROFILE-LOAD-008: default_channel is authored 1-based, stored 0-based ---


@pytest.mark.parametrize(("file_value", "expected"), [(1, 0), (16, 15), (5, 4)])
# @spec PROFILE-LOAD-008
def test_default_channel_converted_from_1_based_to_0_based(bundled_dir: Path, user_dir: Path, file_value: int, expected: int) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="A", match_substring="a", default_channel=file_value)
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert result.profiles[0].default_channel == expected


# --- PROFILE-LOAD-009: setup_hint carried through, None when absent ---


# @spec PROFILE-LOAD-009
def test_setup_hint_present_is_carried_through(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="A", match_substring="a", setup_hint="Do the thing first")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert result.profiles[0].setup_hint == "Do the thing first"


# @spec PROFILE-LOAD-009
def test_setup_hint_absent_is_none(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="A", match_substring="a")
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert result.profiles[0].setup_hint is None


# --- PROFILE-LOAD-010: general field validation ---


@pytest.mark.parametrize(
    "overrides",
    [
        {"default_channel": 0},
        {"default_channel": 17},
        {"has_native_mode": "yes"},
    ],
)
# @spec PROFILE-LOAD-010
def test_invalid_top_level_field_values_fail_validation(bundled_dir: Path, user_dir: Path, overrides: dict) -> None:
    user_dir.mkdir(parents=True)
    _write_profile(bundled_dir, "a.yaml", name="A", match_substring="a", **overrides)
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert result.profiles == ()
    assert len(result.failures) == 1


# @spec PROFILE-LOAD-010
def test_missing_required_field_fails_validation(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    path = bundled_dir / "a.yaml"
    path.write_text(yaml.safe_dump({"match_substring": "a"}))  # missing `name`
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert result.profiles == ()
    assert len(result.failures) == 1
    assert result.failures[0].path == path


# --- PROFILE-LOAD-011: failure count and identifying paths are exposed ---


# @spec PROFILE-LOAD-011
def test_load_result_exposes_failure_count_and_paths(bundled_dir: Path, user_dir: Path) -> None:
    user_dir.mkdir(parents=True)
    bad1 = bundled_dir / "bad1.yaml"
    bad1.write_text("not: valid: yaml: at all: [[[")
    bad2 = bundled_dir / "bad2.yaml"
    bad2.write_text(yaml.safe_dump({"match_substring": "x"}))  # missing name
    result = load_controller_profiles(bundled_dir=bundled_dir, user_dir=user_dir)
    assert len(result.failures) == 2
    assert {f.path for f in result.failures} == {bad1, bad2}
