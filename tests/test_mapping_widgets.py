"""Tests for the Mapping View's structural rebuild on a controller switch to a
different `bank_count` - the Intech Grid integration gap this project's own
Open Questions had already flagged (docs/llds/app-ui.md) and Intech Grid's
variable `bank_count` makes load-bearing.

Uses PySide6's offscreen platform plugin - no real display, no hardware,
safe to run in CI. Deliberately narrow: this file tests `MappingView.rebuild()`
directly rather than constructing the full `DragonMidiWindow` (which opens
real network sockets at construction) - see `test_grid_app_integration.py`
for the pure, Qt-independent controller-selection logic app.py's own glue
delegates to.

@spec GRID-MAP-002
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dragonmidi.grid_controller import Ready, build_grid_controller  # noqa: E402
from dragonmidi.grid_modules import ModuleType  # noqa: E402
from dragonmidi.grid_topology import GridModule, GridTopology  # noqa: E402
from dragonmidi.mapping import MappingEngine, STUDIO_PROFILE  # noqa: E402
from dragonmidi.mapping_view_model import AxisPickerState  # noqa: E402
from dragonmidi.mapping_widgets import MappingView, _SingleAxisTargetField  # noqa: E402
from dragonmidi.osc_io import AxisDiscovery  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


def _grid_controller(module_count: int):
    modules = tuple(_pbf4(x) for x in range(module_count))
    outcome = build_grid_controller(GridTopology(modules=modules, current_page=0))
    assert isinstance(outcome, Ready)
    return outcome.controller


def test_initial_construction_shows_one_row_per_bank_of_the_starting_profile() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = MappingView(engine, AxisDiscovery(), on_rescan=lambda: None)
    assert len(view._editors) == 8
    assert set(view._editors) == set(STUDIO_PROFILE.bank_fader_keys)


def test_rebuild_after_switching_to_a_smaller_grid_chain() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = MappingView(engine, AxisDiscovery(), on_rescan=lambda: None)

    engine.set_profile(_grid_controller(module_count=1))  # 1 PBF4 -> bank_count=4
    view.rebuild()
    assert len(view._editors) == 4
    assert set(view._editors) == set(engine.profile.bank_fader_keys)


def test_rebuild_after_switching_to_a_larger_grid_chain() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = MappingView(engine, AxisDiscovery(), on_rescan=lambda: None)

    engine.set_profile(_grid_controller(module_count=8))  # 8 PBF4 -> bank_count=32
    view.rebuild()
    assert len(view._editors) == 32
    assert set(view._editors) == set(engine.profile.bank_fader_keys)


def test_rebuild_back_to_a_static_profile_after_grid_discards_stale_grid_rows() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = MappingView(engine, AxisDiscovery(), on_rescan=lambda: None)

    engine.set_profile(_grid_controller(module_count=3))  # bank_count=12
    view.rebuild()
    assert len(view._editors) == 12

    engine.set_profile(STUDIO_PROFILE)
    view.rebuild()
    assert len(view._editors) == 8
    assert all(key[0] == "cc" for key in view._editors)  # no stale grid_fader rows survive


def test_rebuild_does_not_crash_the_group_indicator_or_table_sizing() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = MappingView(engine, AxisDiscovery(), on_rescan=lambda: None)
    engine.set_profile(_grid_controller(module_count=1))
    view.rebuild()
    assert view.table_width_hint() > 0
    assert view.table_height_hint() > 0
    view.refresh()  # must not raise against the rebuilt row set


# @spec UI-CTRLVIEW-006 (the Inspector embeds exactly one of these, standalone)
def test_single_axis_target_field_emits_change_once_name_and_bounds_are_valid() -> None:
    _qapp()
    changes: list[tuple[str, float, float]] = []
    clears = []
    field = _SingleAxisTargetField(
        on_change=lambda name, mn, mx: changes.append((name, mn, mx)), on_clear=lambda: clears.append(True)
    )

    field.sync(AxisPickerState(enabled=True, placeholder=None, candidates=("PAN", "TILT"), current=None), 0.0, 100.0)
    field._combo.setCurrentText("PAN")

    assert changes == [("PAN", 0.0, 100.0)]
    assert clears == []


# @spec UI-MAP-017
def test_single_axis_target_field_calls_on_clear_when_selection_cleared() -> None:
    _qapp()
    changes: list[tuple[str, float, float]] = []
    clears = []
    field = _SingleAxisTargetField(
        on_change=lambda name, mn, mx: changes.append((name, mn, mx)), on_clear=lambda: clears.append(True)
    )

    field.sync(AxisPickerState(enabled=True, placeholder=None, candidates=("PAN",), current="PAN"), 0.0, 100.0)
    field._combo.setCurrentText("")

    assert clears == [True]


# @spec UI-MAP-008
def test_single_axis_target_field_shows_a_stale_configured_name_greyed() -> None:
    _qapp()
    field = _SingleAxisTargetField(on_change=lambda *a: None, on_clear=lambda: None)
    stale_state = AxisPickerState(enabled=True, placeholder=None, candidates=("TILT",), current="PAN")
    field.sync(stale_state, 0.0, 100.0)
    assert field._combo.currentText() == "PAN (not found)"


def test_axis_target_editor_composes_five_independent_single_axis_target_fields() -> None:
    """@spec UI-MAP-014: pure-extraction regression guard - `_AxisTargetEditor`
    must still behave as 5 independently-syncable Group pickers after the
    `_SingleAxisTargetField` extraction (Phase 8)."""
    _qapp()
    from dragonmidi.mapping_widgets import _AxisTargetEditor

    changes: list[tuple[int, str, float, float]] = []
    editor = _AxisTargetEditor(
        on_axis_change=lambda g, name, mn, mx: changes.append((g, name, mn, mx)),
        on_axis_clear=lambda g: None,
    )
    assert len(editor._fields) == 5
    state = AxisPickerState(enabled=True, placeholder=None, candidates=("PAN",), current=None)
    editor.sync_picker(3, state, 0.0, 100.0)
    editor._fields[2]._combo.setCurrentText("PAN")
    assert changes == [(3, "PAN", 0.0, 100.0)]
