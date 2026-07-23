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


class _AxisTargetEditor(QWidget):
    """The fader Target-column widget: either a read-only encoder label, or 5
    per-Group axis-name pickers + min/max fields (leftmost = Group 1), toggled by
    the row's Target-type combo. Replaces the pre-Phase-6 single picker.

    @spec UI-MAP-003, UI-MAP-006, UI-MAP-007, UI-MAP-014, UI-MAP-017
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
            combo = QComboBox()
            min_edit = QLineEdit("0")
            max_edit = QLineEdit("100")
            min_edit.setFixedWidth(40)
            max_edit.setFixedWidth(40)
            combo.currentTextChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            min_edit.textChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            max_edit.textChanged.connect(lambda _text, g=group_index: self._emit_change(g))
            axis_layout.addWidget(combo, 1)
            axis_layout.addWidget(min_edit)
            axis_layout.addWidget(max_edit)
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


class _GroupIndicatorRow(QWidget):
    """5 small lights, one per Group (leftmost = Group 1) - blue when active, grey
    otherwise. Plain dots for now; sizing/spacing is not yet finalized
    (`docs/llds/app-ui.md`).

    @spec UI-MAP-015
    """

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Group:"))
        self._dots = [QLabel("●") for _ in range(_GROUP_COUNT)]
        for dot in self._dots:
            layout.addWidget(dot)
        layout.addStretch(1)

    def sync(self, lights: tuple) -> None:
        for dot, lit in zip(self._dots, lights):
            dot.setStyleSheet(f"color: {'#2f6fed' if lit else '#888888'};")


class MappingView(QWidget):
    """The Mapping View: one row per opinionated-map entry; fader rows are
    editable (OSC encoder <-> OSC axis, 5 pickers per Group once in axis mode).
    Embedded directly in the main window as a section below the host/port
    configuration form, not a separate window.

    @spec UI-MAP-001, UI-MAP-002, UI-MAP-009, UI-MAP-010, UI-MAP-014, UI-MAP-015
    """

    _COLUMNS = ["Name", "MIDI", "Trigger", "Target type", "Target"]

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
        self._table = QTableWidget(len(rows), len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._editors: dict = {}
        # Non-editable rows whose Target text isn't fixed at construction time -
        # currently just Solo 1-8, whose text is recomputed from the active Group
        # on every tick (@spec UI-MAP-013). Re-read in refresh() below; every other
        # non-editable row's text is a one-time fact set here and never revisited.
        self._dynamic_target_items: dict = {}

        for row_index, row in enumerate(rows):
            self._table.setItem(row_index, 0, QTableWidgetItem(row.name))
            self._table.setItem(row_index, 1, QTableWidgetItem(row.midi_source))
            self._table.setItem(row_index, 2, QTableWidgetItem(row.trigger))
            if row.editable:
                type_combo = QComboBox()
                type_combo.addItems(["OSC encoder", "OSC axis"])
                editor = _AxisTargetEditor(
                    on_axis_change=lambda g, name, mn, mx, k=row.key: self._on_axis_change(k, g, name, mn, mx),
                    on_axis_clear=lambda g, k=row.key: self._on_axis_clear(k, g),
                )
                type_combo.currentTextChanged.connect(lambda text, k=row.key: self._on_type_changed(k, text))
                self._table.setCellWidget(row_index, 3, type_combo)
                self._table.setCellWidget(row_index, 4, editor)
                self._editors[row.key] = (type_combo, editor)
            else:
                self._table.setItem(row_index, 3, QTableWidgetItem(row.target_type))
                target_item = QTableWidgetItem(row.target)
                self._table.setItem(row_index, 4, target_item)
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
            self._notify_group_axis_changed()

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

        for key, (type_combo, editor) in self._editors.items():
            row = rows[key]
            axis_mode = self._engine.is_axis_mode(key)
            desired_type = "OSC axis" if axis_mode else "OSC encoder"
            if not type_combo.view().isVisible() and type_combo.currentText() != desired_type:
                with _signals_blocked(type_combo):
                    type_combo.setCurrentText(desired_type)

            if not axis_mode:
                editor.show_encoder(row.target)
                continue

            editor.show_axis_picker()
            states = group_axis_picker_states(self._engine, key, self._axis_discovery.axes)
            for group_index, state in enumerate(states, start=1):
                axis_target = self._engine.axis_target(key, group_index)
                current_min, current_max = (axis_target.min_value, axis_target.max_value) if axis_target is not None else (0.0, 100.0)
                editor.sync_picker(group_index, state, current_min, current_max)
