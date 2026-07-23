from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .mapping import MappingEngine
from .mapping_view_model import (
    SOLO_ROW_KEY,
    AxisPickerState,
    active_group_lights,
    build_configuration_rows,
    build_fader_rows,
    cc_range_label,
    group_axis_picker_states,
    parse_axis_field,
)
from .osc_io import AxisDiscovery

_NO_AXIS_SELECTED = ""


def _format_number(value: float) -> str:
    return f"{value:g}"


@contextmanager
def _signals_blocked(*widgets: QWidget) -> Iterator[None]:
    """Suppress signal emission from `widgets` for the duration of the block,
    restoring each one's prior state on exit even if the block raises."""
    for widget in widgets:
        widget.blockSignals(True)
    try:
        yield
    finally:
        for widget in widgets:
            widget.blockSignals(False)


_GROUP_COUNT = 5


def _vline() -> QFrame:
    """A thin vertical rule separating adjacent Group columns (A/B/C/D/E) -
    used identically in both `_GroupHeaderRow` and `_AxisTargetEditor` so the
    lines are continuous from the letter header down through the picker rows."""
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class _AxisTargetEditor(QWidget):
    """The fader Target-column widget: 5 per-Group blocks (leftmost = Group 1),
    each two rows tall - the axis-name picker on top, its min ("m")/max ("M")
    fields side by side below it. Makes every fader row double-height compared
    to the table's other rows (2026-07-23, user's explicit layout request).
    Always shows the picker grid regardless of the engine-wide fader mode
    (`MappingEngine.is_axis_mode()`, `docs/llds/static-mapping.md § Fader Axis
    Mode`) - that mode is controlled from the Configuration Dialog's Fader row
    (`_FaderModeRow` below), not from here; this row's own content doesn't
    change based on it (@spec UI-MAP-018).

    @spec UI-MAP-006, UI-MAP-007, UI-MAP-014, UI-MAP-017
    """

    def __init__(self, on_axis_change: Callable[[int, str, float, float], None], on_axis_clear: Callable[[int], None]) -> None:
        super().__init__()
        self._on_axis_change = on_axis_change
        self._on_axis_clear = on_axis_clear

        axis_layout = QHBoxLayout(self)
        axis_layout.setContentsMargins(0, 0, 0, 0)
        self._group_combos: list[QComboBox] = []
        self._group_min_edits: list[QLineEdit] = []
        self._group_max_edits: list[QLineEdit] = []
        for group_index in range(1, _GROUP_COUNT + 1):
            if group_index > 1:
                axis_layout.addWidget(_vline())
            group_block = QWidget()
            group_layout = QVBoxLayout(group_block)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(2)

            combo = QComboBox()
            combo.currentTextChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            group_layout.addWidget(combo)

            bounds_row = QWidget()
            bounds_layout = QHBoxLayout(bounds_row)
            bounds_layout.setContentsMargins(0, 0, 0, 0)
            min_edit = QLineEdit("0")
            max_edit = QLineEdit("100")
            min_edit.setFixedWidth(40)
            max_edit.setFixedWidth(40)
            min_edit.textChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            max_edit.textChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            bounds_layout.addWidget(QLabel("m"))
            bounds_layout.addWidget(min_edit)
            bounds_layout.addWidget(QLabel("M"))
            bounds_layout.addWidget(max_edit)
            bounds_layout.addStretch(1)
            group_layout.addWidget(bounds_row)

            axis_layout.addWidget(group_block, 1)
            self._group_combos.append(combo)
            self._group_min_edits.append(min_edit)
            self._group_max_edits.append(max_edit)

    def sync_picker(self, group_index: int, state: AxisPickerState, current_min: float, current_max: float) -> None:
        """Repopulate one Group's axis combo from the current discovery state
        while preserving the user's in-progress selection (UI-MAP-004/UI-MAP-008),
        independent of every other Group's picker on this row.

        Called every UI tick, so this must be a no-op when nothing has actually
        changed, and must never touch the combo while its popup is open -
        otherwise a user mid-click has the list torn down under them (~33x/sec).
        """
        combo = self._group_combos[group_index - 1]
        min_edit = self._group_min_edits[group_index - 1]
        max_edit = self._group_max_edits[group_index - 1]

        if combo.view().isVisible():
            return  # don't disturb an open dropdown

        names = list(state.candidates)
        display_current = state.current
        if state.current and state.current not in names:
            display_current = f"{state.current} (not found)"
            names.insert(0, display_current)
        desired_items = [_NO_AXIS_SELECTED, *names]
        current_items = [combo.itemText(i) for i in range(combo.count())]
        if current_items != desired_items:
            with _signals_blocked(combo):
                combo.clear()
                combo.addItems(desired_items)

        # Always reflect the engine's actual configured value, not whatever the
        # widget happened to display before - a QComboBox is not free-text-editable
        # (no in-progress typing to preserve, unlike the min/max fields below), and
        # `state.current` may have come from somewhere other than this combo's own
        # signal (e.g. the Preset Store loading a value at startup, MAP-STORE-002) -
        # only preserving the widget's prior text would leave such a load invisible.
        desired_text = display_current or _NO_AXIS_SELECTED
        if combo.currentText() != desired_text:
            with _signals_blocked(combo):
                combo.setCurrentText(desired_text)

        desired_enabled = state.enabled or bool(state.current)
        if combo.isEnabled() != desired_enabled:
            combo.setEnabled(desired_enabled)

        if not min_edit.hasFocus():
            text = _format_number(current_min)
            if min_edit.text() != text:
                with _signals_blocked(min_edit):
                    min_edit.setText(text)
        if not max_edit.hasFocus():
            text = _format_number(current_max)
            if max_edit.text() != text:
                with _signals_blocked(max_edit):
                    max_edit.setText(text)

    def _emit_change(self, group_index: int) -> None:
        combo = self._group_combos[group_index - 1]
        min_edit = self._group_min_edits[group_index - 1]
        max_edit = self._group_max_edits[group_index - 1]
        name = combo.currentText().split(" (not found)")[0]
        if not name:
            self._on_axis_clear(group_index)  # @spec UI-MAP-017: clear_group_axis_target, not the row toggle
            return
        min_value = parse_axis_field(min_edit.text())
        max_value = parse_axis_field(max_edit.text())
        if min_value is None or max_value is None:
            return
        self._on_axis_change(group_index, name, min_value, max_value)


_GROUP_LETTERS = "ABCDE"
# 14px (unstyled default) -> 21px (2026-07-23, first pass) -> 32px (2026-07-23,
# a further 50% on top of that): each round was the user's explicit request.
_DOT_FONT_SIZE_PX = 32


class _GroupIndicatorRow(QWidget):
    """5 lights, one per Group (leftmost = Group 1) - blue when active, grey
    otherwise, centered in the row, each with its A-E column letter directly
    above it (matching `_GroupHeaderRow`'s letters over the picker grid below).
    Plain dots for now; exact sizing/spacing is not yet finalized
    (`docs/llds/app-ui.md`).

    @spec UI-MAP-015
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(QLabel("Group:"))
        self._dots: list[QLabel] = []
        for letter in _GROUP_LETTERS:
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(0)
            column_layout.setAlignment(Qt.AlignCenter)
            letter_label = QLabel(letter)
            letter_label.setAlignment(Qt.AlignCenter)
            letter_label.setStyleSheet("font-weight: 600;")
            dot = QLabel("●")
            dot.setAlignment(Qt.AlignCenter)
            column_layout.addWidget(letter_label)
            column_layout.addWidget(dot)
            layout.addWidget(column)
            self._dots.append(dot)
        layout.addStretch(1)

    def sync(self, lights: tuple) -> None:
        for dot, lit in zip(self._dots, lights):
            color = "#2f6fed" if lit else "#888888"
            dot.setStyleSheet(f"color: {color}; font-size: {_DOT_FONT_SIZE_PX}px;")


class _GroupHeaderRow(QWidget):
    """Column letters A-E, one per Group picker, lettering which of a fader row's
    5 two-row Group blocks (picker on top, m/M bounds below) belongs to which
    Group. Placed as an actual row 0 in the same QTableWidget as the fader rows
    (not a separate widget above it), so its column boundaries are guaranteed to
    match theirs exactly - a widget floating above the table has no reliable way
    to line up with a column Qt itself sizes via resizeColumnsToContents(). Each
    letter takes the same stretch-1 slot per Group as `_AxisTargetEditor`'s
    per-Group block, so it centers above that Group's whole block.
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for index, letter in enumerate(_GROUP_LETTERS):
            if index > 0:
                layout.addWidget(_vline())
            label = QLabel(letter)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-weight: 600;")
            layout.addWidget(label, 1)


class MappingView(QWidget):
    """The Mapping View: one row per Bank's fader, every row editable (5 Group
    axis pickers each). Embedded directly in the main window as a section below
    the host/port configuration form, not a separate window. As of 2026-07-23,
    every other control's row lives in the Configuration Dialog instead
    (`ConfigurationDialog` below) - this view's only content is the fader grid.

    @spec UI-MAP-001, UI-MAP-002, UI-MAP-009, UI-MAP-010, UI-MAP-014, UI-MAP-015
    """

    _COLUMNS = ["Name", "MIDI", "Target"]

    def __init__(
        self,
        mapping_engine: MappingEngine,
        axis_discovery: AxisDiscovery,
        on_rescan: Callable[[], None],
        on_group_axis_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._engine = mapping_engine
        self._axis_discovery = axis_discovery
        self._on_group_axis_changed = on_group_axis_changed

        self._group_indicator = _GroupIndicatorRow()

        rows = build_fader_rows(self._engine)
        # +1 for the A-E Group-letter header row (row 0), a real table row so its
        # column boundaries are guaranteed to match every fader row's below it.
        self._table = QTableWidget(len(rows) + 1, len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._editors: dict = {}

        for column in range(2):
            self._table.setItem(0, column, QTableWidgetItem(""))
        self._table.setCellWidget(0, 2, _GroupHeaderRow())

        for offset, row in enumerate(rows):
            row_index = offset + 1
            self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(row.midi_source))
            editor = _AxisTargetEditor(
                on_axis_change=lambda g, name, mn, mx, k=row.key: self._on_axis_change(k, g, name, mn, mx),
                on_axis_clear=lambda g, k=row.key: self._on_axis_clear(k, g),
            )
            self._table.setCellWidget(row_index, 2, editor)
            self._editors[row.key] = editor

        rescan_button = QPushButton("Rescan axes")
        rescan_button.clicked.connect(on_rescan)
        rescan_row = QHBoxLayout()
        rescan_row.addWidget(rescan_button)
        rescan_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._group_indicator)
        layout.addWidget(self._table)
        layout.addLayout(rescan_row)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.resizeColumnsToContents()
        # Fader rows are now double-height (picker + m/M bounds stacked per
        # Group, user's explicit layout request, 2026-07-23) - every other row
        # stays its normal single-line height, since only cellWidgets (not plain
        # QTableWidgetItem rows) actually need the extra vertical space.
        self._table.resizeRowsToContents()

        self.refresh()

    def table_width_hint(self) -> int:
        """Total width needed to show every column without clipping/scrolling -
        used by the main window to size itself on first show."""
        width = self._table.verticalHeader().width() + self._table.frameWidth() * 2
        for column in range(self._table.columnCount()):
            width += self._table.columnWidth(column)
        return width

    def _on_axis_change(self, key, group: int, name: str, min_value: float, max_value: float) -> None:
        self._engine.set_axis_target(key, group, name, min_value, max_value)
        self._notify_group_axis_changed()

    def _on_axis_clear(self, key, group: int) -> None:
        self._engine.clear_group_axis_target(key, group)
        self._notify_group_axis_changed()

    def _notify_group_axis_changed(self) -> None:
        """@spec MAP-STORE-004: save on every set/clear, no separate Save step."""
        if self._on_group_axis_changed is not None:
            self._on_group_axis_changed()

    def refresh(self) -> None:
        """Recomputes every fader row's editor from live engine/discovery state
        and the Group indicator row.

        Runs on every UI tick, so - same as `_AxisTargetEditor.sync_picker` -
        this must not touch a combo box while its popup is open, and must not
        force a text change that's already in effect. Every row always shows
        its picker grid regardless of the engine-wide fader mode (@spec
        UI-MAP-018) - that mode is surfaced in the Configuration Dialog instead.

        @spec UI-MAP-004, UI-MAP-014, UI-MAP-015
        """
        self._group_indicator.sync(active_group_lights(self._engine))

        for key, editor in self._editors.items():
            states = group_axis_picker_states(self._engine, key, self._axis_discovery.axes)
            for group_index, state in enumerate(states, start=1):
                axis_target = self._engine.axis_target(key, group_index)
                current_min, current_max = (axis_target.min_value, axis_target.max_value) if axis_target is not None else (0.0, 100.0)
                editor.sync_picker(group_index, state, current_min, current_max)


class _FaderModeCell(QWidget):
    """The Configuration Dialog's Fader row's Target cell: a single Axis/Encoder
    switch governing all 8 faders at once (`docs/llds/static-mapping.md § Fader
    Axis Mode`, 2026-07-23 reversal of the pre-existing per-fader toggle) - the
    only interactive cell anywhere in the dialog's table, embedded as a cell
    widget the same way `_AxisTargetEditor` is in the Mapping View.

    @spec UI-CFGDLG-003
    """

    _AXIS_MODE_TEXT = "Axis mode"
    _ENCODER_MODE_TEXT = "Encoder mode"

    def __init__(self, on_mode_change: Callable[[bool], None]) -> None:
        super().__init__()
        self._on_mode_change = on_mode_change
        self._combo = QComboBox()
        self._combo.addItems([self._AXIS_MODE_TEXT, self._ENCODER_MODE_TEXT])
        self._combo.currentIndexChanged.connect(self._emit_change)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._combo)
        layout.addStretch(1)

    def sync(self, is_axis_mode: bool) -> None:
        desired_index = 0 if is_axis_mode else 1
        if self._combo.currentIndex() != desired_index:
            with _signals_blocked(self._combo):
                self._combo.setCurrentIndex(desired_index)

    def _emit_change(self, index: int) -> None:
        self._on_mode_change(index == 0)


class ConfigurationDialog(QDialog):
    """A modal dialog, opened by the Configuration button beneath the Controller
    dropdown - not embedded in the main window. Holds every control's assignment
    that isn't the Mapping View's fader-to-axis grid, one row per control *type*
    (Fader/Knob/Mute/Solo collapse to a single row each, not one per Bank), the
    Fader row's Target cell hosting the engine-wide axis/encoder mode switch the
    same way every other row's Target cell holds that control's assignment.
    Rebuilds its full row set on every Controller Profile switch (unlike the
    Mapping View's build-once pattern), since which rows exist (Scene, jog
    wheel, Track) varies by profile. Opens sized to its table's full content
    width, so no column is clipped on first show.

    @spec UI-CFGDLG-001, UI-CFGDLG-002, UI-CFGDLG-003,
    UI-CFGDLG-006, UI-CFGDLG-007, UI-CFGDLG-008, UI-CFGDLG-009, UI-CFGDLG-010
    """

    _COLUMNS = ["Name", "MIDI", "Target"]

    def __init__(self, mapping_engine: MappingEngine) -> None:
        super().__init__()
        self.setWindowTitle("Configuration")
        self._engine = mapping_engine

        self._fader_mode_cell: _FaderModeCell | None = None
        self._dynamic_target_items: dict = {}

        self._table = QTableWidget(0, len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._rebuild_rows()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addWidget(close_button)
        close_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(close_row)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.resizeColumnsToContents()

        self.refresh()
        self.resize(self.table_width_hint() + 40, 600)

    def table_width_hint(self) -> int:
        """Total width needed to show every column without clipping/scrolling -
        mirrors `MappingView.table_width_hint()`, used once to size the dialog
        on first show."""
        width = self._table.verticalHeader().width() + self._table.frameWidth() * 2
        for column in range(self._table.columnCount()):
            width += self._table.columnWidth(column)
        return width

    def _on_fader_mode_change(self, axis: bool) -> None:
        self._engine.set_fader_mode(axis)

    def _rebuild_rows(self) -> None:
        """(Re)constructs the table's row set from the engine's current profile,
        including the Fader row (row 0) - not itself part of
        `build_configuration_rows()`'s output, since its Target cell is a live
        widget rather than text. Called at construction and again on every
        Controller Profile switch (`rebuild_for_profile_change` below), since
        which rows exist (Scene, jog wheel, Track) varies by profile.

        @spec UI-CFGDLG-003, UI-CFGDLG-010
        """
        rows = build_configuration_rows(self._engine)
        self._table.setRowCount(len(rows) + 1)
        self._dynamic_target_items = {}

        profile = self._engine.profile
        self._table.setItem(0, 0, QTableWidgetItem("Fader"))
        self._table.setItem(0, 1, QTableWidgetItem(cc_range_label(profile.fader_keys, profile.default_channel)))
        self._fader_mode_cell = _FaderModeCell(on_mode_change=self._on_fader_mode_change)
        self._table.setCellWidget(0, 2, self._fader_mode_cell)

        for offset, row in enumerate(rows):
            row_index = offset + 1
            self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(row.midi_source))
            target_item = QTableWidgetItem(row.target)
            self._table.setItem(row_index, 2, target_item)
            # Solo's Target text is recomputed every tick from the active Group
            # (@spec UI-CFGDLG-007); every other row's text is a one-time fact
            # set here and never revisited.
            if row.key == SOLO_ROW_KEY:
                self._dynamic_target_items[row.key] = target_item
        self._table.resizeColumnsToContents()

    def rebuild_for_profile_change(self) -> None:
        """@spec UI-CFGDLG-010"""
        self._rebuild_rows()

    def refresh(self) -> None:
        """Recomputes the Fader mode switch and the Solo row's Group-aware text.
        Runs on every UI tick, whether or not the dialog is currently visible -
        matching the Mapping View's own always-refresh pattern - so it's always
        current the moment it's shown.
        """
        if self._fader_mode_cell is not None:
            self._fader_mode_cell.sync(self._engine.is_axis_mode())

        rows = {row.key: row for row in build_configuration_rows(self._engine)}
        for key, item in self._dynamic_target_items.items():
            row = rows.get(key)
            if row is not None and item.text() != row.target:
                item.setText(row.target)
