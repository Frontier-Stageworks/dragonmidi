"""Tests for Grid module definitions (docs/llds/intech-grid.md § Module Definitions).

Source-verified HWCFG and element-index tables (Intech Studio `grid-protocol`,
GPL-3.0-only, independently reimplemented - see `grid_modules.py`'s docstring).

@spec GRID-TOPO-004
"""

from __future__ import annotations

from dragonmidi.grid_modules import MODULE_DEFINITIONS, PBF4_DEFINITION, VSN1_DEFINITION, ModuleType, module_type_from_hwcfg


# --- HWCFG lookup table (GRID-TOPO-004) ---


def test_all_pbf4_hwcfg_revisions_resolve_to_pbf4() -> None:
    for hwcfg in (64, 65, 67, 75):
        assert module_type_from_hwcfg(hwcfg) is ModuleType.PBF4


def test_all_vsn1_hwcfg_revisions_resolve_to_vsn1() -> None:
    for hwcfg in (49, 81, 57, 89, 59, 91):
        assert module_type_from_hwcfg(hwcfg) is ModuleType.VSN1


def test_unknown_hwcfg_resolves_to_none_not_a_crash() -> None:
    assert module_type_from_hwcfg(255) is None
    assert module_type_from_hwcfg(0) is None
    assert module_type_from_hwcfg(1_000_000) is None


# --- PBF4 element table ---


def test_pbf4_element_roles_by_index() -> None:
    roles = {e.index: e.role for e in PBF4_DEFINITION.elements}
    for i in range(0, 4):
        assert roles[i] == "potentiometer"
    for i in range(4, 8):
        assert roles[i] == "fader"
    for i in range(8, 12):
        assert roles[i] == "button"


def test_pbf4_has_no_system_or_lcd_element() -> None:
    indices = {e.index for e in PBF4_DEFINITION.elements}
    assert 255 not in indices
    assert all(e.role != "lcd" for e in PBF4_DEFINITION.elements)
    assert len(PBF4_DEFINITION.elements) == 12


# --- VSN1 element table ---


def test_vsn1_element_roles_by_index() -> None:
    # Index 8 carries two elements (confirmed 2026-11-04 against real
    # hardware: the endless encoder also has a push-button at the same
    # index, disambiguated by message type in grid_controller.py) - a plain
    # {index: role} dict can't hold both, so check the two roles at index 8
    # directly instead.
    elements_by_index: dict[int, list[str]] = {}
    for e in VSN1_DEFINITION.elements:
        elements_by_index.setdefault(e.index, []).append(e.role)
    for i in range(0, 8):
        assert elements_by_index[i] == ["button"]
    assert set(elements_by_index[8]) == {"endless", "jog_button"}
    for i in range(9, 13):
        assert elements_by_index[i] == ["button"]
    assert elements_by_index[13] == ["lcd"]


def test_vsn1_has_12_buttons_1_jog_1_jog_button_1_lcd() -> None:
    by_role: dict[str, int] = {}
    for e in VSN1_DEFINITION.elements:
        by_role[e.role] = by_role.get(e.role, 0) + 1
    assert by_role["button"] == 12
    assert by_role["endless"] == 1
    assert by_role["jog_button"] == 1
    assert by_role["lcd"] == 1


# --- VSN1L/VSN1R collapse to one definition ---


def test_vsn1l_and_vsn1r_share_the_same_definition() -> None:
    left_hwcfgs = (49, 57, 59)  # RevA/RevB/RevH
    right_hwcfgs = (81, 89, 91)
    for hwcfg in left_hwcfgs + right_hwcfgs:
        assert module_type_from_hwcfg(hwcfg) is ModuleType.VSN1


def test_module_definitions_tuple_contains_exactly_pbf4_and_vsn1() -> None:
    names = {d.name for d in MODULE_DEFINITIONS}
    assert names == {"PBF4", "VSN1"}
