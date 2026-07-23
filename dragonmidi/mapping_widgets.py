from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .mapping import MappingEngine
from .mapping_view_model import AxisPickerState, active_group_lights, build_rows, group_axis_picker_states, parse_axis_field
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
    """The fader Target-column widget: either a read-only encoder label, or 5
    per-Group blocks (leftmost = Group 1), each two rows tall - the axis-name
    picker on top, its min ("m")/max ("M") fields side by side below it. Makes
    every fader row double-height compared to the table's other rows (2026-07-23,
    user's explicit layout request). Replaces the pre-Phase-6 single picker.
    `show_encoder`/`show_axis_picker` are called from `MappingView.refresh()`
    based on `MappingEngine.is_axis_mode` alone - there is no longer a UI control
    to switch a fader between the two (Trigger and Target type columns, including
    the OSC encoder/OSC axis combo, were removed from the Mapping View entirely,
    2026-07-23); the engine's own encoder-mode machinery is unchanged, just not
    user-toggleable from this view.

    @spec UI-MAP-006, UI-MAP-007, UI-MAP-014, UI-MAP-017
    """

    def __init__(self, on_axis_change: Callable[[int, str, float, float], None], on_axis_clear: Callable[[int], None]) -> None:
        super().__init__()
        self._on_axis_change = on_axis_change
        self._on_axis_clear = on_axis_clear

        self._encoder_label = QLabel("")

        axis_row = QWidget()
        axis_layout = QHBoxLayout(axis_row)
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
        self._axis_row = axis_row

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._encoder_label)
        self._stack.addWidget(axis_row)

    def show_encoder(self, text: str) -> None:
        self._encoder_label.setText(text)
        self._stack.setCurrentWidget(self._encoder_label)

    def show_axis_picker(self) -> None:
        self._stack.setCurrentWidget(self._axis_row)

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
    """The Mapping View: one row per opinionated-map entry; fader rows are
    editable (OSC encoder <-> OSC axis, 5 pickers per Group once in axis mode).
    Embedded directly in the main window as a section below the host/port
    configuration form, not a separate window.

    @spec UI-MAP-001, UI-MAP-002, UI-MAP-009, UI-MAP-010, UI-MAP-014, UI-MAP-015
    """

    _COLUMNS = ["Name", "MIDI", "Target"]

    def __init__(
        self,
        mapping_engine: MappingEngine,
        axis_discovery: AxisDiscovery,
        on_rescan: Callable[[], None],
        on_group_axis_changed: "Callable[[], None] | None" = None,
    ) -> None:
        super().__init__()
        self._engine = mapping_engine
        self._axis_discovery = axis_discovery
        self._on_group_axis_changed = on_group_axis_changed

        self._group_indicator = _GroupIndicatorRow()

        rows = build_rows(self._engine)
        # +1 for the A-E Group-letter header row (row 0), a real table row so its
        # column boundaries are guaranteed to match every fader row's below it.
        self._table = QTableWidget(len(rows) + 1, len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._editors: dict = {}
        # Non-editable rows whose Target text isn't fixed at construction time -
        # currently just Solo 1-8, whose text is recomputed from the active Group
        # on every tick (@spec UI-MAP-013). Re-read in refresh() below; every other
        # non-editable row's text is a one-time fact set here and never revisited.
        self._dynamic_target_items: dict = {}

        for column in range(2):
            self._table.setItem(0, column, QTableWidgetItem(""))
        self._table.setCellWidget(0, 2, _GroupHeaderRow())

        for offset, row in enumerate(rows):
            row_index = offset + 1
            self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(row.midi_source))
            if row.editable:
                editor = _AxisTargetEditor(
                    on_axis_change=lambda g, name, mn, mx, k=row.key: self._on_axis_change(k, g, name, mn, mx),
                    on_axis_clear=lambda g, k=row.key: self._on_axis_clear(k, g),
                )
                self._table.setCellWidget(row_index, 2, editor)
                self._editors[row.key] = editor
            else:
                target_item = QTableWidgetItem(row.target)
                self._table.setItem(row_index, 2, target_item)
                if row.key == ("solo_websocket", None):
                    self._dynamic_target_items[row.key] = target_item

        rescan_button = QPushButton("Rescan axes")
        rescan_button.clicked.connect(on_rescan)

        layout = QVBoxLayout(self)
        layout.addWidget(self._group_indicator)
        layout.addWidget(self._table)
        layout.addWidget(rescan_button)

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
        """Recomputes every fader row's editor from live engine/discovery state,
        the Group indicator row, and the Solo row's Group-aware text.

        Runs on every UI tick, so - same as `_AxisTargetEditor.sync_picker` -
        this must not touch a combo box while its popup is open, and must not
        force a text change that's already in effect.

        @spec UI-MAP-004, UI-MAP-013, UI-MAP-014, UI-MAP-015
        """
        self._group_indicator.sync(active_group_lights(self._engine))

        rows = {row.key: row for row in build_rows(self._engine)}

        for key, item in self._dynamic_target_items.items():
            row = rows.get(key)
            if row is not None and item.text() != row.target:
                item.setText(row.target)

        for key, editor in self._editors.items():
            row = rows[key]
            # Every fader stays in OSC axis mode as of this UI simplification -
            # the OSC encoder <-> OSC axis toggle was removed from the Mapping
            # View (user's explicit choice, 2026-07-23); MappingEngine's
            # encoder-mode machinery itself is untouched, so this still defers
            # to `is_axis_mode` rather than assuming.
            axis_mode = self._engine.is_axis_mode(key)
            if not axis_mode:
                editor.show_encoder(row.target)
                continue

            editor.show_axis_picker()
            states = group_axis_picker_states(self._engine, key, self._axis_discovery.axes)
            for group_index, state in enumerate(states, start=1):
                axis_target = self._engine.axis_target(key, group_index)
                current_min, current_max = (axis_target.min_value, axis_target.max_value) if axis_target is not None else (0.0, 100.0)
                editor.sync_picker(group_index, state, current_min, current_max)
