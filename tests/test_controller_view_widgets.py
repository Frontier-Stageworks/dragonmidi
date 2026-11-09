"""Tests for the Controller View body, its control hierarchy/search, and the
Group selector (docs/specs/app-ui.md § Controller View, § Control Tree,
§ Control Search, § Group Selector).

Uses PySide6's offscreen platform plugin - no real display, no hardware,
safe to run in CI, matching `test_mapping_widgets.py`'s existing convention.

@spec UI-CTRLVIEW-001, UI-CTRLVIEW-002, UI-CTRLVIEW-003, UI-CTRLVIEW-004,
UI-CTRLVIEW-005, UI-CTRLVIEW-006, UI-CTRLVIEW-007, UI-CTRLVIEW-008
@spec UI-CTRLTREE-001 through UI-CTRLTREE-006
@spec UI-CTRLSEARCH-001 through UI-CTRLSEARCH-005
@spec UI-GROUPSEL-001, UI-GROUPSEL-002

UI-CTRLVIEW-009 ("no special Grid-stale handling") is not independently
tested here - it's a negative spec (the absence of a code path), already
true by construction since no stale-detection logic exists in this module
at all; see docs/llds/app-ui.md § Controller View body.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QFocusEvent  # noqa: E402

import dragonmidi.controller_view_widgets as cvw  # noqa: E402
from dragonmidi.controller_view_widgets import ControllerView, GroupSelectorRow  # noqa: E402
from dragonmidi.grid_controller import Ready, build_grid_controller  # noqa: E402
from dragonmidi.grid_modules import ModuleType  # noqa: E402
from dragonmidi.grid_topology import GridModule, GridTopology  # noqa: E402
from dragonmidi.mapping import NANOKONTROL2_PROFILE, STUDIO_PROFILE, MappingEngine  # noqa: E402
from dragonmidi.osc_io import AxisDiscovery  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


def _vsn1(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=49, module_type=ModuleType.VSN1, x=x, y=0, rotation=0)


def _grid_controller(*modules: GridModule):
    outcome = build_grid_controller(GridTopology(modules=tuple(modules), current_page=0))
    assert isinstance(outcome, Ready)
    return outcome.controller


def _select(view: ControllerView, key) -> None:
    """Selects the leaf item for `key`, the same way a real click on a
    selectable row would (Qt fires `currentItemChanged` either way)."""
    view._tree.setCurrentItem(view._item_by_key[key])


def _group_item(view: ControllerView, label: str):
    # Searches top-level and nested (Phase 1.3 module-tier) group items alike.
    return next(item for item in view._all_group_items() if item.text(0) == label)


# --- Hierarchy structure (@spec UI-CTRLTREE-001) ---


# @spec UI-CTRLTREE-001
def test_studio_tree_has_eight_channel_groups_plus_global() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    labels = [item.text(0) for item in view._group_items]
    assert labels == [f"Channel {i}" for i in range(1, 9)] + ["Transport & Global"]


# @spec UI-CTRLTREE-001
def test_channel_1_group_has_four_children_fader_knob_mute_solo() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    channel_1 = _group_item(view, "Channel 1")
    assert channel_1.childCount() == 4


# @spec UI-CTRLTREE-001
def test_pbf4_tree_has_four_channel_groups() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    labels = [item.text(0) for item in view._group_items]
    assert labels == ["Channel 1", "Channel 2", "Channel 3", "Channel 4"]
    channel_1 = _group_item(view, "Channel 1")
    assert channel_1.childCount() == 3  # fader, pot, button


# @spec UI-CTRLTREE-001
def test_vsn1_tree_has_buttons_and_jog_groups_not_channels() -> None:
    _qapp()
    controller = _grid_controller(_vsn1(0))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    labels = [item.text(0) for item in view._group_items]
    assert labels == ["Buttons", "Jog Wheel"]


# --- Group header click behavior (@spec UI-CTRLTREE-002, UI-CTRLTREE-003) ---


# @spec UI-CTRLTREE-002
def test_group_headers_are_not_selectable() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    from PySide6.QtCore import Qt

    for group_item in view._group_items:
        assert not (group_item.flags() & Qt.ItemFlag.ItemIsSelectable)


# @spec UI-CTRLTREE-002
def test_clicking_a_group_header_toggles_expansion_only() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    channel_1 = _group_item(view, "Channel 1")
    assert channel_1.isExpanded() is False

    view._on_item_clicked(channel_1, 0)
    assert channel_1.isExpanded() is True
    assert view._selected_key is None  # expanding must not select anything

    view._on_item_clicked(channel_1, 0)
    assert channel_1.isExpanded() is False


# @spec UI-CTRLTREE-003
def test_selecting_a_control_then_clicking_another_groups_header_preserves_selection() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    _select(view, fader_key)
    assert view._selected_key == fader_key

    channel_2 = _group_item(view, "Channel 2")
    view._on_item_clicked(channel_2, 0)

    assert view._selected_key == fader_key
    assert view._tree.currentItem() is view._item_by_key[fader_key]


# --- Selection / Inspector wiring (unchanged behavior, re-verified against the tree) ---


# @spec UI-CTRLVIEW-003
def test_no_row_selected_by_default() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    assert view._tree.currentItem() is None
    assert view._selected_key is None


# @spec UI-CTRLVIEW-005
def test_inspector_shows_placeholder_when_nothing_selected() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    texts = [view._inspector_layout.itemAt(i).widget().text() for i in range(view._inspector_layout.count())]
    assert any("Select a control" in text for text in texts)


# @spec UI-CTRLVIEW-003, UI-CTRLVIEW-006
def test_selecting_a_fader_row_shows_an_editable_axis_field() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    _select(view, fader_key)
    assert view._inspector_field is not None
    assert view._selected_key == fader_key


# @spec UI-CTRLVIEW-002
def test_solo_summary_shows_its_real_bank_specific_target_not_unassigned() -> None:
    """Regression guard: Solo is never actually "unassigned" - its target
    is a fixed, bank-specific formula (MAP-WS-002), not a configurable
    assignment. An earlier draft fell through to the generic "no matching
    RowView -> Unassigned" fallback for it, which is simply wrong, not just
    uninformative - caught re-reading against the Phase 1.1 spec's own
    worked example ("Solo - Select AX1"), not by a failing test."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view.refresh()
    solo_key_bank_1 = STUDIO_PROFILE.websocket_keys.solos[0]
    solo_key_bank_3 = STUDIO_PROFILE.websocket_keys.solos[2]
    assert "select-AX1" in view._item_by_key[solo_key_bank_1].text(0)
    assert "select-AX3" in view._item_by_key[solo_key_bank_3].text(0)
    assert "Unassigned" not in view._item_by_key[solo_key_bank_1].text(0)


# @spec UI-CTRLVIEW-002
def test_solo_summary_follows_the_active_group() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    solo_key_bank_1 = STUDIO_PROFILE.websocket_keys.solos[0]

    engine.step_active_group(1)  # now Group 2: bank_count(8) * (2-1) + 1 = 9
    view.refresh()

    assert "select-AX9" in view._item_by_key[solo_key_bank_1].text(0)


# @spec UI-CTRLVIEW-002 (Phase 1.2)
def test_knob_and_mute_summaries_show_the_real_per_channel_action_not_shared_text() -> None:
    """Phase 1.2 made the Knob/Mute action itself independently configurable
    per channel, so the summary can no longer reuse one generic rule-text
    string shared by every bank (the pre-Phase-1.2 behavior) - it must show
    each control's actual current action instead."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view.refresh()
    knob_key = next(iter(STUDIO_PROFILE.knob_to_fader))
    mute_key = next(iter(STUDIO_PROFILE.mute_to_fader))
    # Default action, no axis assigned yet to either control's channel.
    assert "Adjust" in view._item_by_key[knob_key].text(0)
    assert "Mute" in view._item_by_key[mute_key].text(0)


# @spec UI-CTRLVIEW-010 (Phase 1.2)
def test_selecting_a_knob_row_shows_an_action_editor() -> None:
    """A Rotary (Korg's Knob) is independently configurable as of Phase 1.2 -
    it now gets a real editor, not the "no settings yet" placeholder a
    generic "button"-typed control still gets."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    knob_key = next(iter(STUDIO_PROFILE.knob_to_fader))
    _select(view, knob_key)
    assert view._inspector_field is not None
    assert view._inspector_kind == "rotary"


# @spec UI-CTRLVIEW-007
def test_selecting_a_transport_button_row_shows_no_editor() -> None:
    """A non-bank-derived button (Play, a plain transport key) has no
    configurable action - it keeps the pre-Phase-1.2 placeholder."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    play_key = ("cc", 41)
    _select(view, play_key)
    assert view._inspector_field is None
    texts = [view._inspector_layout.itemAt(i).widget().text() for i in range(view._inspector_layout.count())]
    assert any("No settings available" in text for text in texts)


# @spec UI-CTRLVIEW-010, MAP-BTNACT-002, MAP-BTNACT-003
def test_selecting_a_mute_row_shows_an_action_editor_and_editing_it_persists() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    mute_key = next(iter(STUDIO_PROFILE.mute_to_fader))
    fader_key = STUDIO_PROFILE.mute_to_fader[mute_key]
    _select(view, mute_key)
    assert view._inspector_field is not None
    assert view._inspector_kind == "button"

    view._inspector_field._combo.setCurrentIndex(view._inspector_field._combo.findData("solo"))

    assert engine.button_action(fader_key) == "solo"


# @spec UI-CTRLVIEW-006
def test_editing_the_inspector_field_sets_the_axis_target_on_the_active_group() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    axes = AxisDiscovery()
    axes._axes = {"PAN": 0.0}
    view = ControllerView(engine, axes)
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    _select(view, fader_key)
    view.refresh()

    view._inspector_field._combo.setCurrentText("PAN")

    target = engine.axis_target(fader_key, engine.active_group)
    assert target is not None
    assert target.axis_name == "PAN"


# @spec UI-CTRLVIEW-008
def test_inspector_field_rebinds_to_newly_active_group() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    axes = AxisDiscovery()
    axes._axes = {"PAN": 0.0, "TILT": 0.0}
    view = ControllerView(engine, axes)
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    engine.set_axis_target(fader_key, 1, "PAN", 0.0, 100.0)
    engine.set_axis_target(fader_key, 2, "TILT", 0.0, 100.0)

    _select(view, fader_key)
    view.refresh()
    assert view._inspector_field._combo.currentText() == "PAN"

    engine.step_active_group(1)  # now Group 2
    view.refresh()
    assert view._inspector_field._combo.currentText() == "TILT"


# @spec UI-CTRLVIEW-003, UI-CTRLVIEW-006
def test_switching_selection_hides_the_previous_inspector_widget() -> None:
    """Regression guard for a real bug found by running the actual app with
    a real window (not caught by any headless test): a widget removed from
    the Inspector layout via `setParent(None)` alone was not reliably
    hidden once it had been shown as part of a real, OS-focused window - it
    was left `isVisible() == True` as an orphaned top-level window, floating
    over the main window. `_clear_inspector_layout` must `hide()` each
    widget explicitly, not rely on reparenting's side effect.

    Honesty note: this assertion passes under both the fixed code and the
    original buggy version when run here - `QWidget.hasFocus()`/real window
    activation never actually happens under the offscreen Qt platform this
    test suite runs under, so the precondition that triggers the bug can't
    be reproduced headlessly. Keeping this test documents the invariant and
    the known-fixed code path."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view.show()

    fader_keys = STUDIO_PROFILE.bank_fader_keys
    _select(view, fader_keys[0])
    first_field = view._inspector_field
    assert first_field is not None

    _select(view, fader_keys[1])

    assert first_field.isVisible() is False
    assert first_field.parent() is None


# @spec UI-CTRLVIEW-004
def test_controller_profile_switch_rebuilds_tree_and_clears_selection() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    _select(view, STUDIO_PROFILE.bank_fader_keys[0])
    assert view._selected_key is not None

    engine.set_profile(NANOKONTROL2_PROFILE)
    view.rebuild()

    assert view._selected_key is None
    assert view._tree.currentItem() is None
    labels = [item.text(0) for item in view._group_items]
    assert labels == [f"Channel {i}" for i in range(1, 9)] + ["Transport & Global"]


# --- Real PBF4/VSN1 Grid-controller coverage ---


# @spec UI-CTRLTREE-001
def test_real_pbf4_vsn1_grid_controller_populates_the_tree() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())

    # 3 modules (Phase 1.3): channel/Buttons groups are nested one level
    # under a "module" tier (UI-CTRLTREE-007) rather than appearing
    # top-level - see UI-CTRLTREE-007's own dedicated tests below for the
    # nesting structure itself.
    channel_labels = [item.text(0) for item in view._all_group_items() if item.text(0).startswith("Channel")]
    assert channel_labels == [f"Channel {i}" for i in range(1, 9)]
    buttons_group = _group_item(view, "Buttons")
    button_labels = {buttons_group.child(i).text(0) for i in range(buttons_group.childCount())}
    assert any("VSN1" in label for label in button_labels)


# @spec UI-CTRLTREE-001
def test_vsn1_only_grid_controller_has_no_channel_groups() -> None:
    _qapp()
    controller = _grid_controller(_vsn1(0))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    labels = [item.text(0) for item in view._group_items]
    assert not any(label.startswith("Channel") for label in labels)


# --- Search (@spec UI-CTRLSEARCH-001 through UI-CTRLSEARCH-005) ---


# @spec UI-CTRLSEARCH-001
def test_search_by_channel_number_shows_only_that_channel() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view._search_edit.setText("Channel 3")
    visible = [item.text(0) for item in view._group_items if not item.isHidden()]
    assert visible == ["Channel 3"]


# @spec UI-CTRLSEARCH-001, UI-CTRLSEARCH-002
def test_search_by_control_name_reveals_matching_controls_across_channels() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view._search_edit.setText("fader")
    visible_groups = [item for item in view._group_items if not item.isHidden()]
    assert len(visible_groups) == 8  # every channel has a Fader
    for group in visible_groups:
        assert group.isExpanded() is True
        visible_children = [group.child(i) for i in range(group.childCount()) if not group.child(i).isHidden()]
        visible_labels = [c.text(0) for c in visible_children]
        assert any("Fader" in label for label in visible_labels)
        # Knob's own rule text ("follows fader's axis...") also legitimately
        # contains "fader" - matching against full rendered text (label +
        # summary), not just the label, is intentional (UI-CTRLSEARCH-001).
        assert all("Fader" in label or "Knob" in label for label in visible_labels)


# @spec UI-CTRLSEARCH-003
def test_search_does_not_change_the_current_selection() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    _select(view, fader_key)

    view._search_edit.setText("Channel 5")

    assert view._selected_key == fader_key


# @spec UI-CTRLSEARCH-004
def test_clearing_search_restores_prior_expansion_state() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    channel_1 = _group_item(view, "Channel 1")
    channel_1.setExpanded(True)
    channel_2 = _group_item(view, "Channel 2")
    assert channel_2.isExpanded() is False

    view._search_edit.setText("fader")  # expands every matching group, including Channel 2
    assert channel_2.isExpanded() is True

    view._search_edit.setText("")  # cleared
    assert channel_1.isExpanded() is True  # restored to what it was before searching
    assert channel_2.isExpanded() is False


# @spec UI-CTRLSEARCH-005
def test_search_with_no_matches_shows_empty_state() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view._search_edit.setText("nonexistent-control-xyz")
    assert all(item.isHidden() for item in view._group_items)
    assert view._no_matches_item is not None
    assert view._no_matches_item.text(0) == cvw._NO_MATCHES_TEXT


# @spec UI-CTRLSEARCH-005
def test_empty_state_disappears_once_a_match_exists_again() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view._search_edit.setText("nonexistent-control-xyz")
    assert view._no_matches_item is not None
    view._search_edit.setText("fader")
    assert view._no_matches_item is None


# @spec UI-CTRLSEARCH-001
def test_search_matches_assignment_summary_text() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    axes = AxisDiscovery()
    axes._axes = {"PAN": 0.0}
    view = ControllerView(engine, axes)
    fader_key = STUDIO_PROFILE.bank_fader_keys[2]  # Channel 3
    engine.set_axis_target(fader_key, 1, "PAN", 0.0, 100.0)
    view.refresh()

    view._search_edit.setText("PAN")

    visible_groups = [item for item in view._group_items if not item.isHidden()]
    assert [g.text(0) for g in visible_groups] == ["Channel 3"]


# --- Group selector (unchanged from Phase 8, re-verified) ---


# @spec UI-GROUPSEL-001
def test_group_selector_starts_with_group_a_checked() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    assert selector._buttons[0].isChecked() is True
    assert all(not b.isChecked() for b in selector._buttons[1:])


# @spec UI-GROUPSEL-001
def test_active_group_button_has_the_explicit_active_color_applied() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    assert cvw.ACTIVE_GROUP_COLOR in selector._buttons[0].styleSheet()
    for button in selector._buttons[1:]:
        assert cvw.INACTIVE_GROUP_COLOR in button.styleSheet()
        assert cvw.ACTIVE_GROUP_COLOR not in button.styleSheet()


# @spec UI-GROUPSEL-001
def test_active_group_button_color_follows_stepping() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    selector._on_clicked(3)
    assert cvw.ACTIVE_GROUP_COLOR in selector._buttons[2].styleSheet()
    assert cvw.INACTIVE_GROUP_COLOR in selector._buttons[0].styleSheet()


# @spec UI-GROUPSEL-002
def test_clicking_group_c_steps_forward_twice_and_lands_on_group_3() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    selector._on_clicked(3)
    assert engine.active_group == 3
    assert selector._buttons[2].isChecked() is True
    assert not selector._buttons[0].isChecked()


# @spec UI-GROUPSEL-002
def test_clicking_the_already_active_group_does_not_step() -> None:
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    selector._on_clicked(1)
    assert engine.active_group == 1


# @spec UI-GROUPSEL-002
def test_clicking_does_not_trigger_the_qt_clicked_signal_from_sync() -> None:
    """Regression guard: `GroupSelectorRow.sync()` calls `setChecked`, which
    must not re-enter `_on_clicked` via the `clicked` signal (only `toggled`
    would fire on a programmatic change, and nothing here connects to it)."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    selector = GroupSelectorRow(engine)
    calls = []
    selector._on_clicked = lambda g: calls.append(g)  # type: ignore[method-assign]
    selector.sync()
    assert calls == []


# @spec UI-CTRLVIEW-003
def test_receiving_keyboard_focus_does_not_select_a_row() -> None:
    """QListWidget's base `focusInEvent` used to silently promote
    `currentRow()` from -1 to 0 on first real focus - the fix for that
    (Phase 8) turned out to be unnecessary for `QTreeWidget` once group
    headers are non-selectable: Qt has nothing selectable at index (0, 0)
    to promote to, so this already holds without a focus override."""
    _qapp()
    engine = MappingEngine(profile=STUDIO_PROFILE)
    view = ControllerView(engine, AxisDiscovery())
    view._tree.focusInEvent(QFocusEvent(QEvent.Type.FocusIn))
    assert view._tree.currentItem() is None
    assert view._selected_key is None


# --- Module-tier nesting for multi-module Grid (UI-CTRLTREE-007, Phase 1.3) ---


# @spec UI-CTRLTREE-007
def test_multi_module_grid_tree_nests_channels_under_module_headers() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())

    top_level_labels = [item.text(0) for item in view._group_items]
    assert top_level_labels == ["Module 1 (PBF4)", "Module 2 (VSN1)", "Module 3 (PBF4)"]
    module1 = view._group_items[0]
    assert module1.data(0, cvw._ITEM_KIND_ROLE) == "group"  # same tag as a top-level channel group
    channel_1 = module1.child(0)
    assert channel_1.text(0) == "Channel 1"
    assert channel_1.data(0, cvw._ITEM_KIND_ROLE) == "group"
    assert channel_1.childCount() > 0  # leaves (Fader/Knob/Mute) are nested one level deeper


# @spec UI-CTRLTREE-007
def test_single_module_grid_tree_is_unchanged_no_module_header() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    top_level_labels = [item.text(0) for item in view._group_items]
    assert top_level_labels == [f"Channel {i}" for i in range(1, 5)]


# @spec UI-CTRLTREE-007
def test_selecting_a_leaf_inside_a_nested_module_group_opens_its_inspector() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    _select(view, ("grid_fader", 1))
    assert view._selected_key == ("grid_fader", 1)


# @spec UI-CTRLTREE-002
def test_clicking_a_nested_module_group_header_toggles_expansion_without_selecting() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    channel_1 = _group_item(view, "Channel 1")
    assert channel_1.isExpanded() is False
    view._on_item_clicked(channel_1, 0)
    assert channel_1.isExpanded() is True
    assert view._selected_key is None


# --- Search through the module tier (UI-CTRLSEARCH-006, Phase 1.3) ---


# @spec UI-CTRLSEARCH-006
def test_search_finds_a_leaf_nested_two_levels_under_a_module_header() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    view.refresh()  # computes each leaf's rendered summary text search matches against

    view._search_edit.setText("fader 1")
    module1 = view._group_items[0]
    assert module1.isHidden() is False
    assert module1.isExpanded() is True
    channel_1 = module1.child(0)
    assert channel_1.isHidden() is False
    assert channel_1.isExpanded() is True
    # A sibling module with no matching descendant is hidden entirely.
    module2 = view._group_items[1]
    assert module2.isHidden() is True


# @spec UI-CTRLSEARCH-006
def test_search_matching_a_module_headers_own_label_shows_every_descendant() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    view.refresh()

    view._search_edit.setText("module 2")
    module2 = view._group_items[1]
    assert module2.isHidden() is False
    assert module2.isExpanded() is True
    for i in range(module2.childCount()):
        child = module2.child(i)
        assert child.isHidden() is False
        assert child.isExpanded() is True
        for j in range(child.childCount()):
            assert child.child(j).isHidden() is False


# @spec UI-CTRLSEARCH-006
def test_clearing_search_restores_prior_expansion_state_including_nested_groups() -> None:
    _qapp()
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    view = ControllerView(engine, AxisDiscovery())
    channel_1 = _group_item(view, "Channel 1")
    channel_1.setExpanded(True)
    channel_2 = _group_item(view, "Channel 2")
    assert channel_2.isExpanded() is False

    view._search_edit.setText("fader")  # expands every matching group, including Channel 2
    assert channel_2.isExpanded() is True

    view._search_edit.setText("")  # cleared
    assert channel_1.isExpanded() is True  # restored to what it was before searching
    assert channel_2.isExpanded() is False
