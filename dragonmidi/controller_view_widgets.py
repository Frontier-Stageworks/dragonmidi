"""The Controller View page's Qt widgets (`docs/llds/app-ui.md § Controller
View body`) and the shared header's Group selector row - defined here even
though `app.py` composes the header itself (`docs/llds/app-ui.md § Main
Window Shell`).

@spec UI-CTRLVIEW-001, UI-CTRLVIEW-002, UI-CTRLVIEW-003, UI-CTRLVIEW-004,
UI-CTRLVIEW-005, UI-CTRLVIEW-006, UI-CTRLVIEW-007, UI-CTRLVIEW-008, UI-CTRLVIEW-009
@spec UI-GROUPSEL-001, UI-GROUPSEL-002
@spec UI-CTRLTREE-001 through UI-CTRLTREE-006, UI-CTRLSEARCH-001 through UI-CTRLSEARCH-005
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from .control_descriptor import ControlDescriptor, build_control_descriptors
from .control_grouping import ControlGroup, build_control_groups
from .inspector_registry import has_editor
from .mapping import (
    BUTTON_ACTION_MUTE,
    BUTTON_ACTION_NONE,
    BUTTON_ACTION_SOLO,
    BUTTON_ACTIONS,
    ROTARY_ACTION_ADJUST,
    ROTARY_ACTION_NONE,
    ROTARY_ACTIONS,
    MappingEngine,
)
from .mapping_view_model import (
    ACTIVE_GROUP_COLOR,
    GROUP_LETTERS,
    INACTIVE_GROUP_COLOR,
    build_configuration_rows,
    build_fader_rows,
    group_axis_picker_states,
    group_step_plan,
)
from .mapping_widgets import _ActionComboField, _SingleAxisTargetField
from .osc_io import AxisDiscovery

_ROTARY_ACTION_LABELS = {
    ROTARY_ACTION_ADJUST: "Follow Channel (adjust assigned axis)",
    ROTARY_ACTION_NONE: "Unassigned",
}
_BUTTON_ACTION_LABELS = {
    BUTTON_ACTION_MUTE: "Mute (zero assigned axis)",
    BUTTON_ACTION_SOLO: "Solo (select this channel)",
    BUTTON_ACTION_NONE: "Unassigned",
}

_ACTIVE_GROUP_BUTTON_STYLE = f"background-color: {ACTIVE_GROUP_COLOR}; color: white; font-weight: 600;"
_INACTIVE_GROUP_BUTTON_STYLE = f"background-color: #e5e5e5; color: {INACTIVE_GROUP_COLOR}; font-weight: 600;"

_SUMMARY_SEPARATOR = "    "
_NO_SETTINGS_TEXT = "No settings available for this control yet."
_PLACEHOLDER_TEXT = "Select a control to edit its settings."
_SEARCH_PLACEHOLDER = "Search controls..."
_NO_MATCHES_TEXT = "No matching controls."

# `QTreeWidgetItem.data(0, _ITEM_KIND_ROLE)` is `"group"` or `"control"` -
# how `_on_item_clicked`/`_on_current_item_changed` tell a channel/group
# header apart from a selectable physical-control leaf, without relying on
# `parent() is None` alone (the synthetic "no matches" item is also a
# top-level item with no parent, but isn't a group either).
_ITEM_KIND_ROLE = Qt.ItemDataRole.UserRole
_ITEM_PAYLOAD_ROLE = Qt.ItemDataRole.UserRole + 1


class _ControlTreeWidget(QTreeWidget):
    """Plain `QTreeWidget`, except for one override: Qt's base
    `focusInEvent` can still promote `currentItem()` to index (0, 0) the
    first time the widget actually receives keyboard focus, even when that
    item is non-selectable (a group header) - "current" and "selected" are
    distinct concepts in Qt's model, so removing `ItemIsSelectable` alone
    doesn't prevent this. Harmless functionally (`_on_current_item_changed`
    already ignores anything that isn't a `"control"` leaf), but it would
    leave a lingering focus-rectangle on a group header the user never
    interacted with - clearing it back to no-current keeps that from
    happening (found while writing this class's own test, not by running
    the real app - this one caught in headless testing)."""

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        current = self.currentItem()
        if current is not None and current.data(0, _ITEM_KIND_ROLE) != "control":
            self.setCurrentItem(None)


class GroupSelectorRow(QWidget):
    """A-E Group selector, steppable via `MappingEngine.step_active_group`
    (`MAP-GROUP-013`) - the same Group dimension `_GroupIndicatorRow`
    (`mapping_widgets.py`) already shows inside Table View's fader grid, now
    also surfaced in the shared header (`docs/llds/app-ui.md § Main Window
    Shell`). No new Group state is introduced.

    @spec UI-GROUPSEL-001, UI-GROUPSEL-002
    """

    def __init__(self, mapping_engine: MappingEngine) -> None:
        super().__init__()
        self._engine = mapping_engine
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._buttons: list[QPushButton] = []
        for index, letter in enumerate(GROUP_LETTERS, start=1):
            button = QPushButton(letter)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, target=index: self._on_clicked(target))
            layout.addWidget(button)
            self._buttons.append(button)
        self.sync()

    def _on_clicked(self, target_group: int) -> None:
        """@spec UI-GROUPSEL-002: fewest `step_active_group` calls needed,
        taking the wraparound direction when it's shorter; zero calls when
        `target_group` is already active."""
        direction, count = group_step_plan(self._engine.active_group, target_group)
        for _ in range(count):
            self._engine.step_active_group(direction)
        self.sync()

    def sync(self) -> None:
        """@spec UI-GROUPSEL-001: recomputed every UI tick, same cadence as
        `_GroupIndicatorRow`. Active/inactive coloring is set explicitly here,
        not left to a QPushButton's native `:checked` look - this app's
        global stylesheet doesn't define `:checked`, so that look rendered
        inconsistently depending on window-focus state (found by running the
        real app and looking at it, not caught by any headless test). Explicit
        styling, matching `_GroupIndicatorRow`'s own blue/grey exactly, is
        reliable regardless of platform/focus state."""
        active = self._engine.active_group
        for index, button in enumerate(self._buttons, start=1):
            checked = index == active
            if button.isChecked() != checked:
                # `setChecked` does not emit `clicked` (only `toggled`), so this
                # never re-enters `_on_clicked` - no signal-blocking needed.
                button.setChecked(checked)
            button.setStyleSheet(_ACTIVE_GROUP_BUTTON_STYLE if checked else _INACTIVE_GROUP_BUTTON_STYLE)


class ControllerView(QWidget):
    """The Controller View body page: an expandable, hardware-aware control
    hierarchy on the left (Phase 1.1 - channel groups replacing the flat
    per-control list), a contextual Inspector on the right. Reads and writes
    the same `MappingEngine` Table View already does, through the same
    existing methods/functions - no second mapping state.

    @spec UI-CTRLVIEW-001 through UI-CTRLVIEW-009
    @spec UI-CTRLTREE-001 through UI-CTRLTREE-006, UI-CTRLSEARCH-001 through UI-CTRLSEARCH-005
    """

    def __init__(self, mapping_engine: MappingEngine, axis_discovery: AxisDiscovery, on_group_axis_changed=None) -> None:
        super().__init__()
        self._engine = mapping_engine
        self._axis_discovery = axis_discovery
        # Fires on any persisted-config change the Inspector makes - an axis-target
        # edit (its original purpose) or, as of Phase 1.2, a Rotary/Button action
        # edit. The parameter name predates the latter and is kept as-is to avoid
        # an unrelated rename across app.py's wiring.
        self._on_group_axis_changed = on_group_axis_changed
        self._descriptors: list[ControlDescriptor] = []
        self._descriptor_by_key: dict = {}
        self._item_by_key: dict = {}
        self._group_items: list[QTreeWidgetItem] = []
        self._no_matches_item: QTreeWidgetItem | None = None
        self._selected_key = None
        self._inspector_field: _SingleAxisTargetField | _ActionComboField | None = None
        # Which branch populated `_inspector_field` - discriminates how
        # `_sync_inspector_field()` should read the engine back into it
        # ("fader" | "rotary" | "button"), `None` when no field is shown.
        self._inspector_kind: str | None = None
        # Captured the first time a search becomes non-empty, restored when
        # it's cleared - `None` means "not currently filtering" (@spec
        # UI-CTRLSEARCH-004).
        self._expanded_group_ids_before_filter: set[str] | None = None

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(_SEARCH_PLACEHOLDER)
        self._search_edit.textChanged.connect(self._on_search_changed)

        self._tree = _ControlTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.currentItemChanged.connect(self._on_current_item_changed)

        left_column = QVBoxLayout()
        left_column.addWidget(self._search_edit)
        left_column.addWidget(self._tree, 1)
        left_container = QWidget()
        left_container.setLayout(left_column)

        self._inspector_container = QWidget()
        self._inspector_layout = QVBoxLayout(self._inspector_container)

        layout = QHBoxLayout(self)
        layout.addWidget(left_container, 1)
        layout.addWidget(self._inspector_container, 1)

        self._rebuild_rows()

    def rebuild(self) -> None:
        """Rebuilds the control hierarchy from the engine's current profile
        and clears the selection - the Controller View's counterpart to
        `MappingView.rebuild()`/`ConfigurationDialog.rebuild_for_profile_change()`,
        called from the same Controller Profile switch handler.

        @spec UI-CTRLVIEW-004
        """
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        self._descriptors = build_control_descriptors(build_fader_rows(self._engine), build_configuration_rows(self._engine), self._engine.profile)
        self._descriptor_by_key = {d.key: d for d in self._descriptors}
        groups = build_control_groups(self._descriptors, self._engine.profile)

        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_key = {}
        self._group_items = []
        self._no_matches_item = None
        for group in groups:
            self._group_items.append(self._build_group_item(group))
        self._tree.blockSignals(False)

        self._search_edit.blockSignals(True)
        self._search_edit.clear()
        self._search_edit.blockSignals(False)
        self._expanded_group_ids_before_filter = None

        self._selected_key = None
        self._show_inspector_placeholder()
        self.refresh()

    def _build_group_item(self, group: ControlGroup, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        """@spec UI-CTRLTREE-001, UI-CTRLTREE-002: a group header has no
        `ItemIsSelectable` flag - clicking it can never make it
        `currentItem()`, which is what lets a previously selected control's
        highlight survive a header click elsewhere (`UI-CTRLTREE-003`). A
        `"module"`-kind group's `children` (Phase 1.3, `UI-CTRLTREE-007`) are
        rendered the same way - as nested group-header items, tagged
        identically to a top-level group - rather than as a second item kind,
        so click/expand/selection handling needs no branch for them. This is
        one additional, non-recursive level: `ControlGroup.children` is never
        itself nested, so this method never calls itself more than twice
        deep."""
        group_item = QTreeWidgetItem([group.label])
        group_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        group_item.setData(0, _ITEM_KIND_ROLE, "group")
        group_item.setData(0, _ITEM_PAYLOAD_ROLE, group.id)
        if parent is None:
            self._tree.addTopLevelItem(group_item)
        else:
            parent.addChild(group_item)
        if group.children:
            for child in group.children:
                self._build_group_item(child, parent=group_item)
        else:
            for descriptor in group.controls:
                leaf = QTreeWidgetItem([descriptor.label])
                leaf.setData(0, _ITEM_KIND_ROLE, "control")
                leaf.setData(0, _ITEM_PAYLOAD_ROLE, descriptor.key)
                group_item.addChild(leaf)
                self._item_by_key[descriptor.key] = leaf
        return group_item

    def _all_group_items(self) -> list[QTreeWidgetItem]:
        """Every `"group"`-kind item, top-level and nested (Phase 1.3) -
        used only for expand-state bookkeeping across a search (below), not
        for the top-level build/filter loops, which iterate `_group_items`
        directly."""
        result: list[QTreeWidgetItem] = []

        def _walk(item: QTreeWidgetItem) -> None:
            result.append(item)
            for i in range(item.childCount()):
                child = item.child(i)
                if child.data(0, _ITEM_KIND_ROLE) == "group":
                    _walk(child)

        for top in self._group_items:
            _walk(top)
        return result

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """@spec UI-CTRLTREE-002: clicking a group header toggles
        expand/collapse and nothing else - it must not select a mapping or
        touch the Inspector. Leaf clicks are handled by
        `_on_current_item_changed` instead (Qt already makes a clicked
        selectable leaf the new `currentItem()` on its own)."""
        if item.data(0, _ITEM_KIND_ROLE) == "group":
            item.setExpanded(not item.isExpanded())

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        """@spec UI-CTRLVIEW-003, UI-CTRLTREE-003: only a `"control"` leaf
        changes the selection/Inspector. `current` is never a group header
        in practice (non-selectable items can't become `currentItem()` via
        a click), but the explicit check keeps this correct even if Qt's
        keyboard navigation ever surfaces one."""
        if current is None or current.data(0, _ITEM_KIND_ROLE) != "control":
            return
        key = current.data(0, _ITEM_PAYLOAD_ROLE)
        descriptor = self._descriptor_by_key.get(key)
        if descriptor is None:
            return
        self._selected_key = descriptor.key
        self._show_inspector_for(descriptor)

    # --- Search / filter (@spec UI-CTRLSEARCH-001 through UI-CTRLSEARCH-005) ---

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        if query and self._expanded_group_ids_before_filter is None:
            # First keystroke of a new search - remember what was expanded
            # (top-level and nested, Phase 1.3) so clearing the search can
            # restore it (UI-CTRLSEARCH-004).
            self._expanded_group_ids_before_filter = {item.data(0, _ITEM_PAYLOAD_ROLE) for item in self._all_group_items() if item.isExpanded()}
        self._apply_filter(query)
        if not query:
            self._expanded_group_ids_before_filter = None

    def _apply_filter(self, query: str) -> None:
        """Matches against each leaf's already-rendered text (label +
        summary, set by `refresh()`) plus its group's label - cheap string
        containment checks over text already computed for display, not a
        new recomputation path (@spec UI-CTRLSEARCH-005). Does not touch
        `_selected_key` or the Inspector either way (@spec UI-CTRLSEARCH-003).
        Recurses through the one additional module/nested-group level
        (Phase 1.3, @spec UI-CTRLSEARCH-006) via `_filter_item` below - no
        new matching rule, just the same one applied one level deeper."""
        if not query:
            # Restore every group item - top-level and nested (Phase 1.3) -
            # not just the top level; a nested group expanded only by the
            # search (e.g. a matching Channel inside a non-matching sibling
            # Module) must collapse back too, the same as a top-level one.
            restore = self._expanded_group_ids_before_filter
            for group_item in self._all_group_items():
                group_item.setHidden(False)
                if restore is not None:
                    group_item.setExpanded(group_item.data(0, _ITEM_PAYLOAD_ROLE) in restore)
            self._update_no_matches_item(show=False)
            return

        any_match = False
        for group_item in self._group_items:
            if self._filter_item(group_item, query, inherited_match=False):
                any_match = True
        self._update_no_matches_item(show=bool(query) and not any_match)

    def _filter_item(self, item: QTreeWidgetItem, query: str, *, inherited_match: bool) -> bool:
        """A group (top-level or nested) is visible if its own label matches
        or `inherited_match` is already true (a matching ancestor's label
        makes every descendant visible, unfiltered - the same rule the
        original single-level implementation applied to its direct
        children, generalized here to cascade through nested groups too),
        or at least one child is itself visible. Returns whether `item` ended
        up visible."""
        own_match = inherited_match or query in item.text(0).lower()
        child_match_found = False
        for child_index in range(item.childCount()):
            child = item.child(child_index)
            if child.data(0, _ITEM_KIND_ROLE) == "group":
                child_visible = self._filter_item(child, query, inherited_match=own_match)
            else:
                child_visible = own_match or query in child.text(0).lower()
                child.setHidden(not child_visible)
            child_match_found = child_match_found or child_visible
        visible = own_match or child_match_found
        item.setHidden(not visible)
        if visible:
            item.setExpanded(True)
        return visible

    def _update_no_matches_item(self, show: bool) -> None:
        """@spec UI-CTRLSEARCH-005: a simple empty state, not a dead list."""
        if show and self._no_matches_item is None:
            item = QTreeWidgetItem([_NO_MATCHES_TEXT])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(0, _ITEM_KIND_ROLE, "empty_state")
            self._tree.addTopLevelItem(item)
            self._no_matches_item = item
        elif not show and self._no_matches_item is not None:
            index = self._tree.indexOfTopLevelItem(self._no_matches_item)
            if index != -1:
                self._tree.takeTopLevelItem(index)
            self._no_matches_item = None

    def _clear_inspector_layout(self) -> None:
        """Explicitly `hide()` before detaching - relying on `setParent(None)`
        alone to hide a removed widget is not reliable once that widget has
        actually been shown as part of a real, OS-focused window (observed
        only by running the real app: a detached `_SingleAxisTargetField`
        could be left `isVisible() == True` as an orphaned top-level window,
        floating over the main window, even though the identical detach call
        correctly hides an unfocused widget in isolation). `hide()` is
        Qt's own explicit, unconditional visibility API - it does not depend
        on reparenting's side effects."""
        while self._inspector_layout.count():
            item = self._inspector_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)

    def _show_inspector_placeholder(self) -> None:
        """@spec UI-CTRLVIEW-005"""
        self._clear_inspector_layout()
        self._inspector_field = None
        self._inspector_kind = None
        self._inspector_layout.addWidget(QLabel(_PLACEHOLDER_TEXT))

    def _show_inspector_for(self, descriptor: ControlDescriptor) -> None:
        """@spec UI-CTRLVIEW-006, UI-CTRLVIEW-010 (Phase 1.2): a Fader gets its
        existing 1-Group axis-target field unchanged; a Rotary or a
        bank-derived Button (a Knob-role/Mute-role control - PBF4's Rotary/
        Button included, now that they're wired like Korg's Knob/Mute) gets
        its own independent action-assignment field. Every other control
        (transport, Scene, Solo, VSN1 buttons/jog, ...) falls to the
        existing "no settings yet" placeholder - @spec UI-CTRLVIEW-007."""
        self._clear_inspector_layout()
        profile = self._engine.profile
        bank_derived_button = descriptor.control_type == "button" and descriptor.key in profile.mute_to_fader
        if not has_editor(descriptor.control_type, bank_derived=bank_derived_button):
            self._inspector_field = None
            self._inspector_kind = None
            configuration_rows = {row.key: row for row in build_configuration_rows(self._engine)}
            self._inspector_layout.addWidget(QLabel(descriptor.label))
            self._inspector_layout.addWidget(QLabel(_NO_SETTINGS_TEXT))
            self._inspector_layout.addWidget(QLabel(self._summary_text(descriptor, configuration_rows)))
            return

        if descriptor.control_type == "fader":
            # @spec UI-CTRLVIEW-006: one field for the active Group only, not
            # the 5-Group grid `_AxisTargetEditor` renders in Table View.
            field = _SingleAxisTargetField(
                on_change=lambda name, mn, mx, k=descriptor.key: self._on_axis_change(k, name, mn, mx),
                on_clear=lambda k=descriptor.key: self._on_axis_clear(k),
            )
            self._inspector_kind = "fader"
        elif descriptor.control_type == "rotary":
            fader_key = profile.bank_fader_key(descriptor.key)
            field = _ActionComboField(
                options=tuple((action, _ROTARY_ACTION_LABELS[action]) for action in ROTARY_ACTIONS),
                on_change=lambda action, fk=fader_key: self._on_rotary_action_change(fk, action),
            )
            self._inspector_kind = "rotary"
        else:  # bank-derived "button"
            fader_key = profile.mute_to_fader[descriptor.key]
            field = _ActionComboField(
                options=tuple((action, _BUTTON_ACTION_LABELS[action]) for action in BUTTON_ACTIONS),
                on_change=lambda action, fk=fader_key: self._on_button_action_change(fk, action),
            )
            self._inspector_kind = "button"

        self._inspector_field = field
        self._inspector_layout.addWidget(QLabel(descriptor.label))
        self._inspector_layout.addWidget(field)
        self._sync_inspector_field()

    def _on_axis_change(self, key, name: str, min_value: float, max_value: float) -> None:
        # Reads `self._engine.active_group` at call time, not at closure-creation
        # time - this is what makes a Group switch (UI-GROUPSEL-002) rebind this
        # same field to the new Group with no extra wiring (@spec UI-CTRLVIEW-008).
        self._engine.set_axis_target(key, self._engine.active_group, name, min_value, max_value)
        self._notify_group_axis_changed()

    def _on_axis_clear(self, key) -> None:
        self._engine.clear_group_axis_target(key, self._engine.active_group)
        self._notify_group_axis_changed()

    def _on_rotary_action_change(self, fader_key, action: str) -> None:
        """@spec UI-CTRLVIEW-010, MAP-BTNACT-002"""
        self._engine.set_rotary_action(fader_key, action)
        self._notify_group_axis_changed()

    def _on_button_action_change(self, fader_key, action: str) -> None:
        """@spec UI-CTRLVIEW-010, MAP-BTNACT-003"""
        self._engine.set_button_action(fader_key, action)
        self._notify_group_axis_changed()

    def _notify_group_axis_changed(self) -> None:
        if self._on_group_axis_changed is not None:
            self._on_group_axis_changed()

    def _summary_text(self, descriptor: ControlDescriptor, configuration_rows: dict) -> str:
        """@spec UI-CTRLVIEW-002. Rotary/bank-derived Button (Phase 1.2) now
        show their *actual* per-channel assigned action - genuinely bank-
        specific since Phase 1.2 made the action itself independently
        configurable, no longer the single generic rule text every bank
        used to share. Solo keeps its own real, bank-specific computed
        value: it's never actually "unassigned" (its target is a fixed
        formula, `MAP-WS-002`). The final fallback ("Unassigned" for a
        descriptor with no matching `RowView` at all) covers a control with a
        `control_names` label but no `opinionated_map` entry yet - e.g. a
        VSN1 button, per `control_descriptor.py`'s three-source union."""
        profile = self._engine.profile
        active_group = self._engine.active_group
        if descriptor.control_type == "fader":
            state = group_axis_picker_states(self._engine, descriptor.key, self._axis_discovery.axes)[active_group - 1]
            return f"{state.current} · Axis" if state.current else "Unassigned"
        if descriptor.control_type == "rotary":
            fader_key = profile.bank_fader_key(descriptor.key)
            if self._engine.rotary_action(fader_key) == ROTARY_ACTION_NONE:
                return "Unassigned"
            target = self._engine.axis_target(fader_key, active_group)
            return f"Adjust {target.axis_name}" if target is not None else "Adjust · no axis assigned"
        if descriptor.key in profile.mute_to_fader:
            fader_key = profile.mute_to_fader[descriptor.key]
            action = self._engine.button_action(fader_key)
            if action == BUTTON_ACTION_NONE:
                return "Unassigned"
            if action == BUTTON_ACTION_SOLO:
                bank_index = profile.bank_fader_keys.index(fader_key) + 1
                axis_number = bank_index + profile.bank_count * (active_group - 1)
                return f"select-AX{axis_number}"
            target = self._engine.axis_target(fader_key, active_group)
            return f"Mute {target.axis_name}" if target is not None else "Mute · no axis assigned"
        ws_keys = profile.websocket_keys
        if ws_keys is not None and descriptor.key in ws_keys.solos:
            bank_number = ws_keys.solos.index(descriptor.key) + 1
            axis_number = bank_number + profile.bank_count * (active_group - 1)
            return f"select-AX{axis_number}"
        row = configuration_rows.get(descriptor.key)
        return row.target if row is not None else "Unassigned"

    def _sync_inspector_field(self) -> None:
        if self._inspector_field is None or self._selected_key is None:
            return
        if self._inspector_kind == "fader":
            active_group = self._engine.active_group
            axis_target = self._engine.axis_target(self._selected_key, active_group)
            current_min, current_max = (axis_target.min_value, axis_target.max_value) if axis_target is not None else (0.0, 100.0)
            state = group_axis_picker_states(self._engine, self._selected_key, self._axis_discovery.axes)[active_group - 1]
            self._inspector_field.sync(state, current_min, current_max)
        elif self._inspector_kind == "rotary":
            fader_key = self._engine.profile.bank_fader_key(self._selected_key)
            self._inspector_field.sync(self._engine.rotary_action(fader_key))
        elif self._inspector_kind == "button":
            fader_key = self._engine.profile.mute_to_fader.get(self._selected_key)
            if fader_key is not None:
                self._inspector_field.sync(self._engine.button_action(fader_key))

    def refresh(self) -> None:
        """Recomputes every row's summary text and the Inspector's live
        content, if a fader is selected. Runs every UI tick, same cadence as
        `MappingView.refresh()`/`ConfigurationDialog.refresh()`.

        @spec UI-CTRLVIEW-002, UI-CTRLVIEW-008, UI-CTRLVIEW-009
        """
        configuration_rows = {row.key: row for row in build_configuration_rows(self._engine)}
        for descriptor in self._descriptors:
            text = f"{descriptor.label}{_SUMMARY_SEPARATOR}{self._summary_text(descriptor, configuration_rows)}"
            item = self._item_by_key.get(descriptor.key)
            if item is not None and item.text(0) != text:
                item.setText(0, text)
        self._sync_inspector_field()
