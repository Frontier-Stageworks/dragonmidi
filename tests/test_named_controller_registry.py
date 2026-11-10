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
    configurations_for_grid,
    configurations_for_profile,
    create_grid_named_controller,
    create_static_named_controller,
    default_display_name,
    ensure_static_named_controller,
    load_registry,
    next_grid_id,
    next_static_sibling_id,
    rename_named_controller,
    resolve_grid_named_controller,
    save_named_controller,
    shape_matches_connected_hardware,
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


# --- Named Configuration: many per hardware key (NAMEDCTRL-CONFIG-*, Phase 1.4) ---


def test_ensure_static_named_controller_sets_is_builtin(tmp_path) -> None:
    nc = ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    assert nc.is_builtin is True


def test_create_static_named_controller_sets_is_builtin_false(tmp_path) -> None:
    ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    sibling = create_static_named_controller(tmp_path, "nanoKONTROL2", "Studio Setup A")
    assert sibling.is_builtin is False
    assert sibling.kind == "static"
    assert sibling.profile_name == "nanoKONTROL2"
    assert sibling.display_name == "Studio Setup A"


def test_configurations_for_profile_returns_only_matching_profile_name_in_created_at_order(tmp_path) -> None:
    ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    create_static_named_controller(tmp_path, "nanoKONTROL2", "Studio Setup A")
    ensure_static_named_controller(tmp_path, "nanoKONTROL Studio")  # different profile - excluded

    results = configurations_for_profile(tmp_path, "nanoKONTROL2")
    assert [c.display_name for c in results] == ["nanoKONTROL2", "Studio Setup A"]
    assert all(c.profile_name == "nanoKONTROL2" for c in results)


def test_next_static_sibling_id_starts_at_2_and_does_not_reissue_after_a_lower_deletion(tmp_path) -> None:
    ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    assert next_static_sibling_id(tmp_path, "nanoKONTROL2") == "nanoKONTROL2 (2)"

    create_static_named_controller(tmp_path, "nanoKONTROL2", "A")  # "nanoKONTROL2 (2)"
    create_static_named_controller(tmp_path, "nanoKONTROL2", "B")  # "nanoKONTROL2 (3)"
    sibling = create_static_named_controller(tmp_path, "nanoKONTROL2", "C")  # "nanoKONTROL2 (4)"
    assert sibling.id == "nanoKONTROL2 (4)"

    # Delete the lower-numbered "(2)" - a count-based scheme would now regenerate
    # the already-taken "(4)"; scanning the highest surviving suffix must not.
    (tmp_path / "nanoKONTROL2 (2).json").unlink()
    assert next_static_sibling_id(tmp_path, "nanoKONTROL2") == "nanoKONTROL2 (5)"


def test_create_static_named_controller_twice_produces_distinct_loadable_ids(tmp_path) -> None:
    ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    first = create_static_named_controller(tmp_path, "nanoKONTROL2", "Setup A")
    second = create_static_named_controller(tmp_path, "nanoKONTROL2", "Setup B")
    assert first.id != second.id
    ids = {c.id for c in configurations_for_profile(tmp_path, "nanoKONTROL2")}
    assert {first.id, second.id} <= ids


def test_configurations_for_grid_returns_every_shape_unfiltered(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4",))
    resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4", "VSN1", "PBF4"))

    results = configurations_for_grid(tmp_path)
    assert {c.module_shape for c in results} == {("PBF4",), ("PBF4", "VSN1", "PBF4")}


def test_migrated_grid_record_is_builtin_zero_candidate_record_is_not(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    configurations_dir.mkdir(parents=True)
    (configurations_dir / "Intech Grid.json").write_text(json.dumps({"bank_axes": {}}), encoding="utf-8")

    migrated = resolve_grid_named_controller(tmp_path, configurations_dir, ("PBF4",))
    assert isinstance(migrated, Activated)
    assert migrated.controller.is_builtin is True

    fresh_shape = resolve_grid_named_controller(tmp_path, configurations_dir, ("VSN1",))
    assert isinstance(fresh_shape, Activated)
    assert fresh_shape.controller.is_builtin is False


def test_shape_matches_connected_hardware_is_exact_order_sensitive_equality() -> None:
    nc = NamedController(id="grid-1", display_name="Rig", kind="grid", module_shape=("PBF4", "VSN1"))
    assert shape_matches_connected_hardware(nc, ("PBF4", "VSN1")) is True
    assert shape_matches_connected_hardware(nc, ("VSN1", "PBF4")) is False
    assert shape_matches_connected_hardware(nc, ("PBF4",)) is False


def test_pre_phase_1_4_registry_file_with_no_is_builtin_key_loads_as_false(tmp_path) -> None:
    """Legacy compatibility: a `NamedController` file written before Phase
    1.4 added `is_builtin` has no such key at all - it must still load
    (NAMEDCTRL-DATA-003's "a stale file never blocks the rest" posture),
    parsing as `is_builtin = False` rather than raising or guessing True."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "id": "nanoKONTROL2",
        "display_name": "nanoKONTROL2",
        "kind": "static",
        "profile_name": "nanoKONTROL2",
        "module_shape": None,
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    (tmp_path / "nanoKONTROL2.json").write_text(json.dumps(legacy_payload), encoding="utf-8")

    loaded = load_registry(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].is_builtin is False


def test_ensure_static_named_controller_self_heals_a_pre_phase_1_4_record_to_builtin(tmp_path) -> None:
    """A record shaped `id == profile_name`, `kind == "static"` can only
    ever have been created by `ensure_static_named_controller` itself - a
    pre-Phase-1.4 installation's existing file (no `is_builtin` key) is
    retroactively upgraded on next use, so an upgrading user's existing
    default configuration gets the same protection a fresh install's does,
    rather than staying permanently unprotected."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    legacy_payload = {
        "id": "nanoKONTROL2",
        "display_name": "nanoKONTROL2",
        "kind": "static",
        "profile_name": "nanoKONTROL2",
        "module_shape": None,
        "created_at": "2026-07-01T00:00:00+00:00",
    }
    (tmp_path / "nanoKONTROL2.json").write_text(json.dumps(legacy_payload), encoding="utf-8")

    healed = ensure_static_named_controller(tmp_path, "nanoKONTROL2")
    assert healed.is_builtin is True
    assert healed.display_name == "nanoKONTROL2"  # untouched otherwise
    assert healed.created_at == "2026-07-01T00:00:00+00:00"  # untouched otherwise

    reloaded = {c.id: c for c in load_registry(tmp_path)}
    assert reloaded["nanoKONTROL2"].is_builtin is True  # persisted, not just in-memory
    assert len(reloaded) == 1  # same file, not a new one


def test_many_configurations_may_share_a_hardware_key_without_error(tmp_path) -> None:
    configurations_dir = tmp_path / "configurations"
    shape = ("PBF4", "VSN1")
    create_grid_named_controller(tmp_path, shape, "Stewart Platform Controller")
    create_grid_named_controller(tmp_path, shape, "Focus Puller Rig")
    # Deliberately many saved configurations sharing one shape is not, on its
    # own, an error - only resolve_grid_named_controller's connect-time
    # auto-resolution treats 2+ matches as something to block on.
    assert len(configurations_for_grid(tmp_path)) == 2
    outcome = resolve_grid_named_controller(tmp_path, configurations_dir, shape)
    assert isinstance(outcome, Ambiguous)
