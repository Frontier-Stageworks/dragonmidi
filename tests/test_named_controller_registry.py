"""Tests for the Named Controller Registry: Korg's trivial 1:1 wrapping, Grid's
shape-based zero/one/many matching, legacy migration, and rename
(docs/llds/named-controller.md).

@spec NAMEDCTRL-DATA-001, NAMEDCTRL-DATA-002, NAMEDCTRL-DATA-003, NAMEDCTRL-DATA-004
@spec NAMEDCTRL-STATIC-001, NAMEDCTRL-STATIC-002
@spec NAMEDCTRL-MATCH-001, NAMEDCTRL-MATCH-002, NAMEDCTRL-MATCH-003, NAMEDCTRL-MATCH-004
@spec NAMEDCTRL-MATCH-005, NAMEDCTRL-MATCH-006
@spec NAMEDCTRL-MIGRATE-001, NAMEDCTRL-MIGRATE-002, NAMEDCTRL-MIGRATE-003
"""

from __future__ import annotations

import json

import pytest

from dragonmidi.named_controller_registry import (
    Activated,
    Ambiguous,
    default_display_name,
    ensure_static_named_controller,
    load_registry,
    next_grid_id,
    rename_named_controller,
    resolve_grid_named_controller,
    save_named_controller,
)
from dragonmidi.named_controller_registry import NamedController


# --- Korg: trivial 1:1 wrapping (NAMEDCTRL-STATIC-001, NAMEDCTRL-STATIC-002) ---


def test_ensure_static_named_controller_creates_on_first_call(tmp_path) -> None:
    nc = ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    assert nc.id == "nanoKONTROL2"
    assert nc.display_name == "nanoKONTROL2"
    assert nc.kind == "static"
    assert nc.profile_name == "nanoKONTROL2"
    assert (tmp_path / "nanoKONTROL2.json").is_file()


def test_ensure_static_named_controller_returns_existing_unchanged_on_second_call(tmp_path) -> None:
    first = ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    renamed = rename_named_controller(tmp_path, "nanoKONTROL2", "My Studio Rig")
    second = ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    assert second.id == first.id == "nanoKONTROL2"
    assert second.display_name == renamed.display_name == "My Studio Rig"
    assert len(load_registry(tmp_path)) == 1  # no duplicate created


# --- Grid: zero/one/many matching (NAMEDCTRL-MATCH-*) ---


def test_resolve_grid_zero_candidates_creates_grid_1_with_default_name(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    outcome = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1", "PBF4"))
    assert isinstance(outcome, Activated)
    assert outcome.controller.id == "grid-1"
    assert outcome.controller.display_name == "Intech Grid (PBF4+VSN1+PBF4)"
    assert outcome.controller.module_shape == ("PBF4", "VSN1", "PBF4")


def test_resolve_grid_different_shape_creates_grid_2_independent_of_grid_1(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    first = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4",))
    second = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "PBF4", "PBF4"))
    assert isinstance(first, Activated) and isinstance(second, Activated)
    assert first.controller.id == "grid-1"
    assert second.controller.id == "grid-2"


def test_resolve_grid_same_shape_resolved_twice_returns_the_same_id_no_duplicate(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    first = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1"))
    second = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1"))
    assert isinstance(first, Activated) and isinstance(second, Activated)
    assert first.controller.id == second.controller.id
    assert len(load_registry(tmp_path)) == 1


def test_resolve_grid_two_saved_controllers_sharing_a_shape_is_ambiguous(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    shape = ("PBF4", "VSN1", "PBF4")
    a = NamedController(id="grid-1", display_name="Stewart Platform Controller", kind="grid", module_shape=shape)
    b = NamedController(id="grid-2", display_name="Focus Puller Rig", kind="grid", module_shape=shape)
    save_named_controller(tmp_path, a)
    save_named_controller(tmp_path, b)

    outcome = resolve_grid_named_controller(tmp_path, configurations_dir, shape)
    assert isinstance(outcome, Ambiguous)
    assert {c.id for c in outcome.candidates} == {"grid-1", "grid-2"}
    # Nothing new is created while ambiguous.
    assert len(load_registry(tmp_path)) == 2


def test_next_grid_id_uses_highest_existing_suffix_not_a_count(tmp_path) -> None:
    # grid-2 deleted, leaving grid-1 and grid-3 - a count-based scheme would
    # regenerate the already-taken "grid-3".
    save_named_controller(tmp_path, NamedController(id="grid-1", display_name="A", kind="grid", module_shape=("PBF4",)))
    save_named_controller(tmp_path, NamedController(id="grid-3", display_name="B", kind="grid", module_shape=("VSN1",)))
    assert next_grid_id(tmp_path) == "grid-4"


def test_default_display_name_joins_shape_with_plus() -> None:
    assert default_display_name(("PBF4", "VSN1", "PBF4")) == "Intech Grid (PBF4+VSN1+PBF4)"


# --- Legacy migration (NAMEDCTRL-MIGRATE-*) ---


def test_legacy_migration_fires_once_when_a_legacy_preset_file_exists(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    configurations_dir.mkdir(parents=True)
    (configurations_dir / "Intech Grid.json").write_text(json.dumps({"bank_axes": {}}), encoding="utf-8")

    outcome = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1", "PBF4"))
    assert isinstance(outcome, Activated)
    assert outcome.controller.id == "Intech Grid"
    assert outcome.controller.module_shape == ("PBF4", "VSN1", "PBF4")


def test_legacy_migration_does_not_retrigger_on_a_different_shape(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    configurations_dir.mkdir(parents=True)
    (configurations_dir / "Intech Grid.json").write_text(json.dumps({"bank_axes": {}}), encoding="utf-8")

    first = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1", "PBF4"))
    second = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "PBF4"))
    assert isinstance(first, Activated) and first.controller.id == "Intech Grid"
    # The second, different shape is new - resolved via ordinary zero-candidate
    # creation (grid-1), not a second migration.
    assert isinstance(second, Activated)
    assert second.controller.id == "grid-1"
    assert len(load_registry(tmp_path)) == 2


def test_no_migration_without_a_legacy_file_falls_through_to_ordinary_creation(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"  # does not exist at all
    outcome = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4",))
    assert isinstance(outcome, Activated)
    assert outcome.controller.id == "grid-1"


# --- Rename (NAMEDCTRL-DATA-004) ---


def test_rename_changes_only_display_name(tmp_path) -> None:
    save_named_controller(tmp_path, NamedController(id="grid-1", display_name="Old Name", kind="grid", module_shape=("PBF4",)))
    renamed = rename_named_controller(tmp_path, "grid-1", "Stewart Platform Controller")
    assert renamed.id == "grid-1"
    assert renamed.display_name == "Stewart Platform Controller"
    assert renamed.kind == "grid"
    assert renamed.module_shape == ("PBF4",)
    reloaded = {c.id: c for c in load_registry(tmp_path)}
    assert reloaded["grid-1"].display_name == "Stewart Platform Controller"
    assert len(reloaded) == 1  # same file, not a new one


def test_rename_unknown_id_raises(tmp_path) -> None:
    with pytest.raises(ValueError):
        rename_named_controller(tmp_path, "does-not-exist", "New Name")


# --- Malformed files (NAMEDCTRL-DATA-003) ---


def test_malformed_registry_file_is_skipped_not_raised(tmp_path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "broken.json").write_text("not valid json {{{", encoding="utf-8")
    (tmp_path / "wrong_shape.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")  # missing required fields
    save_named_controller(tmp_path, NamedController(id="grid-1", display_name="Fine", kind="grid", module_shape=("PBF4",)))

    loaded = load_registry(tmp_path)
    assert [c.id for c in loaded] == ["grid-1"]
