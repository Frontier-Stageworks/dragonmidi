"""The MIDI Input Monitor's Qt presentation layer (docs/llds/midi-monitor.md).
Reads/writes a shared `MidiMonitor` passed in by `app.py`; owns no MIDI
connection, no output adapter, and no knowledge of Grid/Korg specifics beyond
the formatting helpers in `midi_monitor.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .capture_session import (
    GuidedCaptureSession,
    GuidedVerifySession,
    actual_key,
    build_capture_steps,
    build_verify_steps,
    save_capture_session,
    save_verify_session,
)
from .control_descriptor import build_control_descriptors
from .mapping_view_model import build_configuration_rows, build_fader_rows
from .midi_monitor import MidiMonitor, format_channel, format_event_type, format_module, format_number, format_resolved

if TYPE_CHECKING:
    from .mapping import MappingEngine

_COLUMNS = ("Time", "Device", "Type", "Channel", "Number", "Value", "Module", "Resolved")


def _format_timestamp(ts: float) -> str:
    local = time.localtime(ts)
    millis = int((ts - int(ts)) * 1000)
    return f"{time.strftime('%H:%M:%S', local)}.{millis:03d}"


class MidiMonitorDialog(QDialog):
    """@spec MON-UI-001 through MON-UI-009, MON-DIAG-004 through MON-DIAG-008
    @spec MON-GUIDE-001 through MON-GUIDE-013
    """

    def __init__(
        self,
        monitor: MidiMonitor,
        on_enter_diagnostic: Callable[[], None],
        get_mapping_engine: Callable[[], "MappingEngine"],
        capture_sessions_dir: Path,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MIDI Input Monitor")
        self._monitor = monitor
        self._on_enter_diagnostic = on_enter_diagnostic
        self._get_mapping_engine = get_mapping_engine
        self._capture_sessions_dir = capture_sessions_dir
        self._last_rendered_version = -1
        self._guided_session: GuidedCaptureSession | None = None
        self._verify_session: GuidedVerifySession | None = None

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

        guided_box = QGroupBox("Guided Capture")
        guided_layout = QVBoxLayout(guided_box)
        self._guided_status_label = QLabel("")
        guided_layout.addWidget(self._guided_status_label)
        self._guided_pending_label = QLabel("")
        guided_layout.addWidget(self._guided_pending_label)
        guided_buttons_row = QHBoxLayout()
        self._guided_start_button = QPushButton("Start Guided Capture")
        self._guided_start_button.clicked.connect(self._on_guided_start_clicked)
        guided_buttons_row.addWidget(self._guided_start_button)
        self._guided_confirm_button = QPushButton("Confirm && Next")
        self._guided_confirm_button.clicked.connect(self._on_guided_confirm_clicked)
        guided_buttons_row.addWidget(self._guided_confirm_button)
        self._guided_skip_button = QPushButton("Skip")
        self._guided_skip_button.clicked.connect(self._on_guided_skip_clicked)
        guided_buttons_row.addWidget(self._guided_skip_button)
        self._guided_save_button = QPushButton("Save Session")
        self._guided_save_button.clicked.connect(self._on_guided_save_clicked)
        guided_buttons_row.addWidget(self._guided_save_button)
        self._guided_cancel_button = QPushButton("Cancel")
        self._guided_cancel_button.clicked.connect(self._on_guided_cancel_clicked)
        guided_buttons_row.addWidget(self._guided_cancel_button)
        guided_buttons_row.addStretch(1)
        guided_layout.addLayout(guided_buttons_row)
        layout.addWidget(guided_box)
        self._update_guided_ui()

        verify_box = QGroupBox("Guided Verify")
        verify_layout = QVBoxLayout(verify_box)
        self._verify_status_label = QLabel("")
        verify_layout.addWidget(self._verify_status_label)
        self._verify_pending_label = QLabel("")
        verify_layout.addWidget(self._verify_pending_label)
        verify_buttons_row = QHBoxLayout()
        self._verify_start_button = QPushButton("Start Guided Verify")
        self._verify_start_button.clicked.connect(self._on_verify_start_clicked)
        verify_buttons_row.addWidget(self._verify_start_button)
        self._verify_retry_button = QPushButton("Retry")
        self._verify_retry_button.clicked.connect(self._on_verify_retry_clicked)
        verify_buttons_row.addWidget(self._verify_retry_button)
        self._verify_next_button = QPushButton("Next")
        self._verify_next_button.clicked.connect(self._on_verify_next_clicked)
        verify_buttons_row.addWidget(self._verify_next_button)
        self._verify_save_button = QPushButton("Save Report")
        self._verify_save_button.clicked.connect(self._on_verify_save_clicked)
        verify_buttons_row.addWidget(self._verify_save_button)
        self._verify_cancel_button = QPushButton("Cancel")
        self._verify_cancel_button.clicked.connect(self._on_verify_cancel_clicked)
        verify_buttons_row.addWidget(self._verify_cancel_button)
        verify_buttons_row.addStretch(1)
        verify_layout.addLayout(verify_buttons_row)
        self._verify_log = QPlainTextEdit()
        self._verify_log.setReadOnly(True)
        self._verify_log.setMaximumHeight(80)
        verify_layout.addWidget(self._verify_log)
        layout.addWidget(verify_box)
        self._update_verify_ui()

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
        state at close time. @spec MON-GUIDE-011-adjacent, MON-VERIFY-adjacent:
        a running session is entirely in-memory - closing the dialog discards
        it with no prompt, same as never starting one."""
        self._exit_diagnostic()
        self._end_guided_session()
        self._end_verify_session()
        super().closeEvent(event)

    def _get_active_controller(self):
        return self._get_mapping_engine().profile

    def _build_descriptors(self):
        engine = self._get_mapping_engine()
        return build_control_descriptors(build_fader_rows(engine), build_configuration_rows(engine), engine.profile)

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

    # --- Guided Capture (docs/llds/midi-monitor.md § Guided Capture Session) ---

    def _on_guided_start_clicked(self) -> None:
        """@spec MON-GUIDE-001, MON-GUIDE-002, MON-GUIDE-003, MON-GUIDE-009"""
        controller = self._get_active_controller()
        steps = build_capture_steps(controller)
        if not steps:
            return  # Start is disabled in this state; defensive no-op
        self._guided_session = GuidedCaptureSession(controller.name, steps)
        # Forces diagnostic mode back on even if the user had unchecked it
        # before starting - a session's safety guarantee must not depend on
        # the checkbox's state at the moment Start was clicked.
        self._diagnostic_checkbox.blockSignals(True)
        self._diagnostic_checkbox.setChecked(True)
        self._diagnostic_checkbox.blockSignals(False)
        self._enter_diagnostic()
        self._monitor.on_record = self._guided_session.offer
        self._update_guided_ui()

    def _on_guided_confirm_clicked(self) -> None:
        """@spec MON-GUIDE-006"""
        if self._guided_session is None:
            return
        self._guided_session.confirm()
        self._update_guided_ui()

    def _on_guided_skip_clicked(self) -> None:
        """@spec MON-GUIDE-007"""
        if self._guided_session is None:
            return
        self._guided_session.skip()
        self._update_guided_ui()

    def _on_guided_save_clicked(self) -> None:
        """@spec MON-GUIDE-010"""
        session = self._guided_session
        if session is None or not session.finished:
            return
        path = save_capture_session(self._capture_sessions_dir, session.profile_name, session.results)
        self._guided_status_label.setText(f"Saved to {path}")
        self._end_guided_session()

    def _on_guided_cancel_clicked(self) -> None:
        """@spec MON-GUIDE-011"""
        self._end_guided_session()

    def _end_guided_session(self) -> None:
        """Discards any running/finished session in memory - no file is
        written unless Save already ran. Re-enables the diagnostic checkbox
        and un-registers the monitor's `on_record` hook."""
        self._guided_session = None
        self._monitor.on_record = None
        self._update_guided_ui()

    def _update_guided_ui(self) -> None:
        session = self._guided_session
        self._diagnostic_checkbox.setEnabled(session is None and self._verify_session is None)  # @spec MON-GUIDE-009

        if session is None:
            if self._verify_session is not None:
                # Mutual exclusion: only one guided session (capture or verify) at a time.
                self._guided_start_button.setEnabled(False)
                self._guided_status_label.setText("Guided Verify is running.")
                self._guided_pending_label.setText("")
                self._guided_confirm_button.setEnabled(False)
                self._guided_skip_button.setEnabled(False)
                self._guided_save_button.setEnabled(False)
                self._guided_cancel_button.setEnabled(False)
                return
            controller = self._get_active_controller()
            has_steps = len(build_capture_steps(controller)) > 0
            self._guided_start_button.setEnabled(has_steps)
            self._guided_status_label.setText("" if has_steps else "No unconfirmed controls for this profile.")
            self._guided_pending_label.setText("")
            self._guided_confirm_button.setEnabled(False)
            self._guided_skip_button.setEnabled(False)
            self._guided_save_button.setEnabled(False)
            self._guided_cancel_button.setEnabled(False)
            return

        self._guided_start_button.setEnabled(False)
        self._guided_cancel_button.setEnabled(True)

        if session.finished:
            captured = sum(1 for r in session.results if not r.skipped)
            skipped = sum(1 for r in session.results if r.skipped)
            self._guided_status_label.setText(f"Finished: {captured} captured, {skipped} skipped.")
            self._guided_pending_label.setText("")
            self._guided_confirm_button.setEnabled(False)
            self._guided_skip_button.setEnabled(False)
            self._guided_save_button.setEnabled(True)
            return

        step = session.current_step
        self._guided_status_label.setText(f"Step {len(session.results) + 1} of {session.total_steps}: press/move “{step.label}”")
        pending = session.pending
        if pending is None:
            self._guided_pending_label.setText("Waiting for input…")
        else:
            raw = pending.raw
            self._guided_pending_label.setText(
                f"Pending: {format_event_type(raw)} {format_channel(raw.channel)} #{format_number(raw.number)} = {raw.raw_value}"
            )
        self._guided_confirm_button.setEnabled(pending is not None)  # @spec MON-GUIDE-004
        self._guided_skip_button.setEnabled(True)
        self._guided_save_button.setEnabled(False)

    # --- Guided Verify (docs/llds/midi-monitor.md § Guided Verify Session) ---

    def _on_verify_start_clicked(self) -> None:
        """@spec MON-VERIFY-001, MON-VERIFY-002, MON-VERIFY-003, MON-VERIFY-010"""
        if self._guided_session is not None:
            return  # mutual exclusion - Start is disabled in this state; defensive no-op
        descriptors = self._build_descriptors()
        steps = build_verify_steps(descriptors)
        if not steps:
            return
        self._verify_session = GuidedVerifySession(self._get_active_controller().name, steps)
        # Same safety guarantee as Guided Capture's Start - forces diagnostic
        # mode back on regardless of the checkbox's state at this moment.
        # More load-bearing here: Guided Verify's step list includes every
        # real, dispatch-capable control (faders, knobs, mutes, solos,
        # transport), not just inert stubs.
        self._diagnostic_checkbox.blockSignals(True)
        self._diagnostic_checkbox.setChecked(True)
        self._diagnostic_checkbox.blockSignals(False)
        self._enter_diagnostic()
        self._monitor.on_record = self._verify_session.offer
        self._verify_log.clear()
        self._update_verify_ui()

    def _on_verify_retry_clicked(self) -> None:
        """@spec MON-VERIFY-007"""
        if self._verify_session is None:
            return
        self._verify_session.retry()
        self._update_verify_ui()

    def _on_verify_next_clicked(self) -> None:
        """@spec MON-VERIFY-006: accepts the current (failing) pending result
        and advances anyway - the explicit override for a mismatch the user
        has decided not to chase further right now."""
        session = self._verify_session
        if session is None or session.pending is None:
            return
        self._log_verify_result(session.current_step, session.pending)
        session.advance()
        self._update_verify_ui()

    def _on_verify_save_clicked(self) -> None:
        """@spec MON-VERIFY-009"""
        session = self._verify_session
        if session is None or not session.finished:
            return
        path = save_verify_session(self._capture_sessions_dir, session.profile_name, session.results)
        self._verify_status_label.setText(f"Saved to {path}")
        self._end_verify_session()

    def _on_verify_cancel_clicked(self) -> None:
        """@spec MON-VERIFY-adjacent: discards without saving, mirroring
        Guided Capture's Cancel."""
        self._end_verify_session()

    def _end_verify_session(self) -> None:
        self._verify_session = None
        self._monitor.on_record = None
        self._update_verify_ui()

    def _log_verify_result(self, step, entry) -> None:
        """Appends one line to the running log for a just-resolved step -
        shared by the auto-pass path in `_update_verify_ui()` and the
        explicit Next-after-failure path above."""
        raw = entry.raw
        actual = actual_key(entry)
        passed = actual == step.expected_key
        mark = "✓" if passed else "✗"
        detail = f"{format_event_type(raw)} {format_channel(raw.channel)} #{format_number(raw.number)}"
        if passed:
            self._verify_log.appendPlainText(f"{mark} {step.label} — {detail}")
        else:
            self._verify_log.appendPlainText(f"{mark} {step.label} — expected {step.expected_key}, got {format_resolved(actual)} ({detail})")

    def _update_verify_ui(self) -> None:
        session = self._verify_session

        # Auto-advance every passing pending candidate immediately - at most
        # one iteration in practice (advancing clears `pending`, and the new
        # current step starts with nothing pending), but loop defensively.
        while session is not None and session.pending_passed is True:
            step = session.current_step
            self._log_verify_result(step, session.pending)
            session.advance()

        self._diagnostic_checkbox.setEnabled(session is None and self._guided_session is None)  # @spec MON-VERIFY-010

        if session is None:
            if self._guided_session is not None:
                self._verify_start_button.setEnabled(False)
                self._verify_status_label.setText("Guided Capture is running.")
            else:
                descriptors = self._build_descriptors()
                has_steps = len(descriptors) > 0
                self._verify_start_button.setEnabled(has_steps)
                self._verify_status_label.setText("" if has_steps else "No known controls for this profile.")
            self._verify_pending_label.setText("")
            self._verify_retry_button.setEnabled(False)
            self._verify_next_button.setEnabled(False)
            self._verify_save_button.setEnabled(False)
            self._verify_cancel_button.setEnabled(False)
            return

        self._verify_start_button.setEnabled(False)
        self._verify_cancel_button.setEnabled(True)

        if session.finished:
            passed = sum(1 for r in session.results if r.passed)
            failed = sum(1 for r in session.results if not r.passed)
            self._verify_status_label.setText(f"Finished: {passed} passed, {failed} failed.")
            self._verify_pending_label.setText("")
            self._verify_retry_button.setEnabled(False)
            self._verify_next_button.setEnabled(False)
            self._verify_save_button.setEnabled(True)
            return

        step = session.current_step
        self._verify_status_label.setText(f"Step {len(session.results) + 1} of {session.total_steps}: press/move “{step.label}”")
        pending = session.pending
        if pending is None:
            self._verify_pending_label.setText("Waiting for input…")
            self._verify_retry_button.setEnabled(False)
            self._verify_next_button.setEnabled(False)
        else:
            # Only the failing case ever reaches this branch live - a passing
            # pending candidate was already consumed by the auto-advance loop
            # above, on this same call.
            raw = pending.raw
            self._verify_pending_label.setText(
                f"✗ Mismatch — expected {step.expected_key}, got {format_event_type(raw)} {format_channel(raw.channel)} #{format_number(raw.number)}"
            )
            self._verify_retry_button.setEnabled(True)
            self._verify_next_button.setEnabled(True)
        self._verify_save_button.setEnabled(False)

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

        # A running session's `pending` is set by `on_record` (app.py's
        # dispatch thread, via MidiMonitor.record()), not by a button click -
        # re-render it here, on the same version-gated cadence as the table
        # above, so a background capture/verify becomes visible without a
        # click, and a passing Guided Verify step auto-advances immediately
        # rather than waiting for the user to do anything (@spec MON-VERIFY-005).
        if self._guided_session is not None:
            self._update_guided_ui()
        if self._verify_session is not None:
            self._update_verify_ui()
