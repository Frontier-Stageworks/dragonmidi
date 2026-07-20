from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from PySide6.QtWidgets import (
    QComboBox,
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
from .mapping_view_model import AxisPickerState, axis_picker_state, build_rows, parse_axis_field
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


class _AxisTargetEditor(QWidget):
    """The fader Target-column widget: either a read-only encoder label, or an
    axis-name picker + min/max fields, toggled by the row's Target-type combo.

    @spec UI-MAP-003, UI-MAP-006, UI-MAP-007
    """

    def __init__(self, on_axis_change: Callable[[str, float, float], None]) -> None:
        super().__init__()
        self._on_axis_change = on_axis_change

        self._encoder_label = QLabel("")

        axis_row = QWidget()
        axis_layout = QHBoxLayout(axis_row)
        axis_layout.setContentsMargins(0, 0, 0, 0)
        self._axis_combo = QComboBox()
        self._min_edit = QLineEdit("0")
        self._max_edit = QLineEdit("100")
        self._min_edit.setFixedWidth(50)
        self._max_edit.setFixedWidth(50)
        axis_layout.addWidget(self._axis_combo, 1)
        axis_layout.addWidget(self._min_edit)
        axis_layout.addWidget(self._max_edit)
        self._axis_row = axis_row

        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._encoder_label)
        self._stack.addWidget(axis_row)

        self._axis_combo.currentTextChanged.connect(self._emit_change)
        self._min_edit.textChanged.connect(self._emit_change)
        self._max_edit.textChanged.connect(self._emit_change)

    def show_encoder(self, text: str) -> None:
        self._encoder_label.setText(text)
        self._stack.setCurrentWidget(self._encoder_label)

    def show_axis_picker(self) -> None:
        self._stack.setCurrentWidget(self._axis_row)

    def sync_picker(self, state: AxisPickerState, current_min: float, current_max: float) -> None:
        """Repopulate the axis combo from the current discovery state while
        preserving the user's in-progress selection (UI-MAP-004/UI-MAP-008).

        Called every UI tick, so this must be a no-op when nothing has actually
        changed, and must never touch the combo while its popup is open -
        otherwise a user mid-click has the list torn down under them (~33x/sec).
        """
        if self._axis_combo.view().isVisible():
            return  # don't disturb an open dropdown

        names = list(state.candidates)
        if state.current and state.current not in names:
            names.insert(0, f"{state.current} (not found)")
        desired_items = [_NO_AXIS_SELECTED, *names]
        current_items = [self._axis_combo.itemText(i) for i in range(self._axis_combo.count())]
        if current_items != desired_items:
            with _signals_blocked(self._axis_combo):
                selected = self._axis_combo.currentText()
                self._axis_combo.clear()
                self._axis_combo.addItems(desired_items)
                if selected in desired_items:
                    self._axis_combo.setCurrentText(selected)

        desired_enabled = state.enabled or bool(state.current)
        if self._axis_combo.isEnabled() != desired_enabled:
            self._axis_combo.setEnabled(desired_enabled)

        if state.placeholder is not None and not state.current and self._axis_combo.currentText() != _NO_AXIS_SELECTED:
            with _signals_blocked(self._axis_combo):
                self._axis_combo.setCurrentText(_NO_AXIS_SELECTED)

        if not self._min_edit.hasFocus():
            text = _format_number(current_min)
            if self._min_edit.text() != text:
                with _signals_blocked(self._min_edit):
                    self._min_edit.setText(text)
        if not self._max_edit.hasFocus():
            text = _format_number(current_max)
            if self._max_edit.text() != text:
                with _signals_blocked(self._max_edit):
                    self._max_edit.setText(text)

    def _emit_change(self, *_args: object) -> None:
        name = self._axis_combo.currentText().split(" (not found)")[0]
        if not name:
            return
        min_value = parse_axis_field(self._min_edit.text())
        max_value = parse_axis_field(self._max_edit.text())
        if min_value is None or max_value is None:
            return
        self._on_axis_change(name, min_value, max_value)


class MappingView(QWidget):
    """The Mapping View: one row per opinionated-map entry; fader rows are
    editable (OSC encoder <-> OSC axis). Embedded directly in the main window
    as a section below the host/port configuration form, not a separate window.

    @spec UI-MAP-001, UI-MAP-002, UI-MAP-009, UI-MAP-010
    """

    _COLUMNS = ["Name", "MIDI", "Trigger", "Target type", "Target"]

    def __init__(self, mapping_engine: MappingEngine, axis_discovery: AxisDiscovery, on_rescan: Callable[[], None]) -> None:
        super().__init__()
        self._engine = mapping_engine
        self._axis_discovery = axis_discovery

        rows = build_rows(self._engine)
        self._table = QTableWidget(len(rows), len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._editors: dict = {}

        for row_index, row in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(row.midi_source))
            self._table.setItem(row_index, 2, QTableWidgetItem(row.trigger))
            if row.editable:
                type_combo = QComboBox()
                type_combo.addItems(["OSC encoder", "OSC axis"])
                editor = _AxisTargetEditor(on_axis_change=lambda name, mn, mx, k=row.key: self._on_axis_change(k, name, mn, mx))
                type_combo.currentTextChanged.connect(lambda text, k=row.key: self._on_type_changed(k, text))
                self._table.setCellWidget(row_index, 3, type_combo)
                self._table.setCellWidget(row_index, 4, editor)
                self._editors[row.key] = (type_combo, editor)
            else:
                self._table.setItem(row_index, 3, QTableWidgetItem(row.target_type))
                self._table.setItem(row_index, 4, QTableWidgetItem(row.target))

        rescan_button = QPushButton("Rescan axes")
        rescan_button.clicked.connect(on_rescan)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addWidget(rescan_button)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.resizeColumnsToContents()

        self.refresh()

    def table_width_hint(self) -> int:
        """Total width needed to show every column without clipping/scrolling -
        used by the main window to size itself on first show."""
        width = self._table.verticalHeader().width() + self._table.frameWidth() * 2
        for column in range(self._table.columnCount()):
            width += self._table.columnWidth(column)
        return width

    def _on_type_changed(self, key, text: str) -> None:
        _type_combo, editor = self._editors[key]
        if text == "OSC axis":
            self._engine.enter_axis_mode(key)
            editor.show_axis_picker()
        else:
            editor.show_encoder("")  # replaced on the next refresh() tick
            self._engine.clear_axis_target(key)

    def _on_axis_change(self, key, name: str, min_value: float, max_value: float) -> None:
        self._engine.set_axis_target(key, name, min_value, max_value)

    def refresh(self) -> None:
        """Recomputes every fader row's editor from live engine/discovery state.

        Runs on every UI tick, so - same as `_AxisTargetEditor.sync_picker` -
        this must not touch a combo box while its popup is open, and must not
        force a text change that's already in effect.

        @spec UI-MAP-004
        """
        rows = {row.key: row for row in build_rows(self._engine)}
        for key, (type_combo, editor) in self._editors.items():
            row = rows[key]
            axis_target = self._engine.axis_target(key)
            axis_mode = self._engine.is_axis_mode(key)
            desired_type = "OSC axis" if axis_mode else "OSC encoder"
            if not type_combo.view().isVisible() and type_combo.currentText() != desired_type:
                with _signals_blocked(type_combo):
                    type_combo.setCurrentText(desired_type)

            if not axis_mode:
                editor.show_encoder(row.target)
                current_name, current_min, current_max = None, 0.0, 100.0
            else:
                editor.show_axis_picker()
                if axis_target is not None:
                    current_name = axis_target.axis_name
                    current_min, current_max = axis_target.min_value, axis_target.max_value
                else:
                    current_name, current_min, current_max = None, 0.0, 100.0
            state = axis_picker_state(current_name, self._axis_discovery.axes)
            editor.sync_picker(state, current_min, current_max)
