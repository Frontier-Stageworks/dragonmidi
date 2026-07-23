"""Tests for the Preset Store - file I/O and validation for the (Bank, Group)
axis-assignment table (docs/specs/static-mapping.md § Preset Store).

@spec MAP-STORE-001, MAP-STORE-002, MAP-STORE-003, MAP-STORE-004
@spec MAP-STORE-005, MAP-STORE-006, MAP-STORE-007
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dragonmidi.preset_store import load_group_axis_targets, save_group_axis_targets

_VALID_ENTRY = {"axis_name": "PAN", "min": 0.0, "max": 100.0}


@pytest.fixture
def configs_dir(tmp_path: Path) -> Path:
    return tmp_path / "documents" / "DragonMIDI" / "configurations"  # deliberately not pre-created


# --- MAP-STORE-001: one file per profile, named after it ---


# @spec MAP-STORE-001
def test_save_creates_the_configurations_dir_and_a_file_named_after_the_profile(configs_dir: Path) -> None:
    save_group_axis_targets(configs_dir, "nanoKONTROL Studio", {1: {1: _VALID_ENTRY}})
    assert configs_dir.is_dir()
    assert (configs_dir / "nanoKONTROL Studio.json").exists()


# @spec MAP-STORE-001
def test_save_then_load_round_trips_bank_and_group_indices(configs_dir: Path) -> None:
    table = {1: {1: {"axis_name": "PAN", "min": 0.0, "max": 100.0}}, 3: {2: {"axis_name": "TILT", "min": -50.0, "max": 50.0}}}
    save_group_axis_targets(configs_dir, "nanoKONTROL Studio", table)
    loaded = load_group_axis_targets(configs_dir, "nanoKONTROL Studio")
    assert loaded == table


# @spec MAP-STORE-001
def test_two_profiles_get_independent_files(configs_dir: Path) -> None:
    save_group_axis_targets(configs_dir, "nanoKONTROL Studio", {1: {1: _VALID_ENTRY}})
    save_group_axis_targets(configs_dir, "nanoKONTROL2", {2: {1: _VALID_ENTRY}})
    assert load_group_axis_targets(configs_dir, "nanoKONTROL Studio") == {1: {1: _VALID_ENTRY}}
    assert load_group_axis_targets(configs_dir, "nanoKONTROL2") == {2: {1: _VALID_ENTRY}}


# --- MAP-STORE-002: missing file is not an error, not a bulk-populate loop ---


# @spec MAP-STORE-002
def test_load_with_no_file_returns_an_empty_table(configs_dir: Path) -> None:
    assert load_group_axis_targets(configs_dir, "Never Saved") == {}


# @spec MAP-STORE-002
def test_load_with_no_configurations_dir_at_all_returns_an_empty_table(tmp_path: Path) -> None:
    never_created = tmp_path / "does" / "not" / "exist"
    assert load_group_axis_targets(never_created, "Anything") == {}


# --- MAP-STORE-003: bounds validation, invalid entries skipped with a logged warning ---


# @spec MAP-STORE-003
def test_bank_index_zero_is_rejected_not_misassigned_via_negative_indexing(configs_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    # The specific bug this validation closes: an unvalidated bank_index of 0 would
    # previously resolve via Python's negative-indexing to the *last* fader (Bank 8)
    # instead of being rejected as out of range.
    path = configs_dir
    path.mkdir(parents=True)
    (path / "Test.json").write_text(json.dumps({"bank_axes": {"0": {"1": _VALID_ENTRY}}}))
    loaded = load_group_axis_targets(configs_dir, "Test")
    assert loaded == {}
    assert "bank" in caplog.text.lower()


@pytest.mark.parametrize("bad_bank_index", ["0", "9", "-1", "not_a_number"])
# @spec MAP-STORE-003
def test_out_of_range_or_non_numeric_bank_index_is_skipped(configs_dir: Path, bad_bank_index: str) -> None:
    configs_dir.mkdir(parents=True)
    (configs_dir / "Test.json").write_text(json.dumps({"bank_axes": {bad_bank_index: {"1": _VALID_ENTRY}}}))
    assert load_group_axis_targets(configs_dir, "Test") == {}


@pytest.mark.parametrize("bad_group_index", ["0", "6", "-1", "not_a_number"])
# @spec MAP-STORE-003
def test_out_of_range_or_non_numeric_group_index_is_skipped(configs_dir: Path, bad_group_index: str) -> None:
    configs_dir.mkdir(parents=True)
    (configs_dir / "Test.json").write_text(json.dumps({"bank_axes": {"1": {bad_group_index: _VALID_ENTRY}}}))
    assert load_group_axis_targets(configs_dir, "Test") == {}


@pytest.mark.parametrize(
    "bad_entry",
    [
        {"axis_name": 123, "min": 0.0, "max": 100.0},  # axis_name not a string
        {"axis_name": "PAN", "min": "zero", "max": 100.0},  # min not numeric
        {"axis_name": "PAN", "min": 0.0},  # missing max
        {"min": 0.0, "max": 100.0},  # missing axis_name
    ],
)
# @spec MAP-STORE-003
def test_malformed_entry_shape_is_skipped(configs_dir: Path, bad_entry: dict) -> None:
    configs_dir.mkdir(parents=True)
    (configs_dir / "Test.json").write_text(json.dumps({"bank_axes": {"1": {"1": bad_entry}}}))
    assert load_group_axis_targets(configs_dir, "Test") == {}


# @spec MAP-STORE-003
def test_invalid_entries_do_not_block_the_files_other_valid_entries(configs_dir: Path) -> None:
    configs_dir.mkdir(parents=True)
    (configs_dir / "Test.json").write_text(
        json.dumps(
            {
                "bank_axes": {
                    "0": {"1": _VALID_ENTRY},  # invalid bank index - skipped
                    "2": {"1": {"axis_name": "TILT", "min": 0.0, "max": 100.0}},  # valid - must still load
                }
            }
        )
    )
    loaded = load_group_axis_targets(configs_dir, "Test")
    assert loaded == {2: {1: {"axis_name": "TILT", "min": 0.0, "max": 100.0}}}


# @spec MAP-STORE-003
def test_completely_malformed_json_is_treated_like_a_missing_file(configs_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    configs_dir.mkdir(parents=True)
    (configs_dir / "Test.json").write_text("{not valid json")
    assert load_group_axis_targets(configs_dir, "Test") == {}


# --- MAP-STORE-004: save rewrites the whole table, not a diff/merge ---


# @spec MAP-STORE-004
def test_save_fully_replaces_the_previous_contents_not_merges(configs_dir: Path) -> None:
    save_group_axis_targets(configs_dir, "Test", {1: {1: _VALID_ENTRY}, 2: {1: _VALID_ENTRY}})
    save_group_axis_targets(configs_dir, "Test", {1: {1: _VALID_ENTRY}})  # Bank 2's entry dropped
    loaded = load_group_axis_targets(configs_dir, "Test")
    assert loaded == {1: {1: _VALID_ENTRY}}


# @spec MAP-STORE-004
def test_save_with_an_empty_table_still_writes_a_valid_empty_file(configs_dir: Path) -> None:
    save_group_axis_targets(configs_dir, "Test", {1: {1: _VALID_ENTRY}})
    save_group_axis_targets(configs_dir, "Test", {})
    assert load_group_axis_targets(configs_dir, "Test") == {}


# --- MAP-STORE-005: write failure fails silently, doesn't raise ---


# @spec MAP-STORE-005
def test_save_failure_does_not_raise(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # A file sitting where the configurations directory needs to be created makes
    # directory creation fail - simulates a disk/permissions-style write failure
    # without depending on platform-specific permission bits.
    blocking_file = tmp_path / "configurations"
    blocking_file.write_text("i am a file, not a directory")
    save_group_axis_targets(blocking_file, "Test", {1: {1: _VALID_ENTRY}})  # must not raise
    assert "fail" in caplog.text.lower() or "error" in caplog.text.lower()


# --- MAP-STORE-006: active Group index is never part of this file's shape ---


# @spec MAP-STORE-006
def test_saved_file_never_contains_an_active_group_field(configs_dir: Path) -> None:
    save_group_axis_targets(configs_dir, "Test", {1: {1: _VALID_ENTRY}})
    raw = json.loads((configs_dir / "Test.json").read_text())
    assert "active_group" not in raw


# --- MAP-STORE-007: plain synchronous functions, no async/threading involved ---


# @spec MAP-STORE-007
def test_load_and_save_are_plain_synchronous_functions(configs_dir: Path) -> None:
    import inspect

    assert not inspect.iscoroutinefunction(load_group_axis_targets)
    assert not inspect.iscoroutinefunction(save_group_axis_targets)
    # A save followed immediately by a load in the same thread must see the write -
    # there is no deferred/background completion to race against.
    save_group_axis_targets(configs_dir, "Test", {1: {1: _VALID_ENTRY}})
    assert load_group_axis_targets(configs_dir, "Test") == {1: {1: _VALID_ENTRY}}
