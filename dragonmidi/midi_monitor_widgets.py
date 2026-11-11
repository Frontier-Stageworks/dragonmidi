"""The MIDI Input Monitor's Qt presentation layer (docs/llds/midi-monitor.md).
Reads/writes a shared `MidiMonitor` passed in by `app.py`; owns no MIDI
connection, no output adapter, and no knowledge of Grid/Korg specifics beyond
the formatting helpers in `midi_monitor.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .midi_monitor import MidiMonitor, format_channel, format_event_type, format_module, format_number, format_resolved

_COLUMNS = ("Time", "Device", "Type", "Channel", "Number", "Value", "Module", "Resolved")


def _format_timestamp(ts: float) -> str:
    local = time.localtime(ts)
    millis = int((ts - int(ts)) * 1000)
    return f"{time.strftime('%H:%M:%S', local)}.{millis:03d}"


class MidiMonitorDialog(QDialog):
    """@spec MON-UI-001 through MON-UI-009, MON-DIAG-004 through MON-DIAG-008"""

    def __init__(self, monitor: MidiMonitor, on_enter_diagnostic: Callable[[], None]) -> None:
        super().__init__()
        self.setWindowTitle("MIDI Input Monitor")
        self._monitor = monitor
        self._on_enter_diagnostic = on_enter_diagnostic
        self._last_rendered_version = -1

        layout = QVBoxLayout(self)

        self._diagnostic_checkbox = QCheckBox("Diagnostic mode (block Dragonframe output while open)")
        self._diagnostic_checkbox.toggled.connect(self._on_diagnostic_toggled)
        layout.addWidget(self._diagnostic_checkbox)

        self._captured_label = QLabel("No input captured yet.")
        layout.addWidget(self._captured_label)

        controls_row = QHBoxLayout()
        self._capture_button = QPushButton("Capture Next Input")
        self._capture_button.clicked.connect(self._on_capture_clicked)
        controls_row.addWidget(self._capture_button)
        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self._on_clear_clicked)
        controls_row.addWidget(self._clear_button)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, 1)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self.resize(640, 360)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """@spec MON-DIAG-004, MON-DIAG-005: fires on every open, not only
        the first - reopening is always safe-by-default again."""
        super().showEvent(event)
        self._diagnostic_checkbox.blockSignals(True)
        self._diagnostic_checkbox.setChecked(True)
        self._diagnostic_checkbox.blockSignals(False)
        self._enter_diagnostic()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """@spec MON-DIAG-008: unconditional, regardless of the checkbox's
        state at close time."""
        self._exit_diagnostic()
        super().closeEvent(event)

    def _enter_diagnostic(self) -> None:
        self._monitor.diagnostic_active = True
        self._on_enter_diagnostic()

    def _exit_diagnostic(self) -> None:
        self._monitor.diagnostic_active = False

    def _on_diagnostic_toggled(self, checked: bool) -> None:
        """@spec MON-DIAG-005, MON-DIAG-007"""
        if checked:
            self._enter_diagnostic()
        else:
            self._exit_diagnostic()

    def _on_capture_clicked(self) -> None:
        """@spec MON-UI-005, MON-UI-006"""
        self._monitor.request_capture_next()
        self._captured_label.setText("Waiting for next input…")

    def _on_clear_clicked(self) -> None:
        """@spec MON-UI-004"""
        self._monitor.clear()
        self._last_rendered_version = self._monitor.version
        self._table.setRowCount(0)
        self._captured_label.setText("Waiting for next input…" if self._monitor.capture_pending else "No input captured yet.")

    def refresh(self) -> None:
        """Called every tick from `app.py`'s existing `_on_tick()` - skips
        all Qt work when nothing changed since the last call.

        @spec MON-UI-002, MON-UI-003, MON-UI-007, MON-UI-008
        """
        if self._monitor.version == self._last_rendered_version:
            return
        self._last_rendered_version = self._monitor.version

        events = self._monitor.events
        self._table.setRowCount(len(events))
        for row, entry in enumerate(events):
            raw = entry.raw
            values = (
                _format_timestamp(entry.timestamp),
                entry.device_name or "-",
                format_event_type(raw),
                format_channel(raw.channel),
                format_number(raw.number),
                str(raw.raw_value),
                format_module(entry.module),
                format_resolved(entry.resolved),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if entry.captured:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self._table.setItem(row, col, item)

        last = self._monitor.last_captured
        if last is not None:
            raw = last.raw
            self._captured_label.setText(
                f"Captured: {_format_timestamp(last.timestamp)} — {format_event_type(raw)} "
                f"{format_channel(raw.channel)} #{format_number(raw.number)} = {raw.raw_value} "
                f"— {format_module(last.module)} / {format_resolved(last.resolved)}"
            )
