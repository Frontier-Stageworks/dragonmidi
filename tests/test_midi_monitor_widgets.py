"""Tests for the MIDI Input Monitor dialog (docs/specs/midi-monitor.md § Monitor Dialog).

Uses PySide6's offscreen platform plugin, matching every other Qt-level test
file's convention. Uses `.show()`, never `.exec()`, since `.exec()` blocks on
its own nested event loop - `showEvent()`/`closeEvent()` fire the same way
either entry point is used, so this exercises the real override without
hanging the test.

@spec MON-DIAG-004, MON-DIAG-005, MON-DIAG-006, MON-DIAG-007, MON-DIAG-008
@spec MON-UI-001, MON-UI-002, MON-UI-003, MON-UI-004, MON-UI-005, MON-UI-007, MON-UI-008
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dragonmidi.events import MidiEvent  # noqa: E402
from dragonmidi.mapping import NANOKONTROL2_PROFILE, MappingEngine  # noqa: E402
from dragonmidi.midi_monitor import MidiMonitor  # noqa: E402
from dragonmidi.midi_monitor_widgets import MidiMonitorDialog  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _cc(number: int = 36) -> MidiEvent:
    return MidiEvent(type="cc", channel=0, number=number, raw_value=64, normalized=64 / 127, is_press=False, is_release=False)


def _dialog(
    monitor: MidiMonitor | None = None,
    engine: MappingEngine | None = None,
    capture_sessions_dir: Path | None = None,
) -> tuple[MidiMonitorDialog, MidiMonitor, list[int]]:
    """Defaults to a real `MappingEngine(profile=NANOKONTROL2_PROFILE)` -
    Guided Verify's step list is built from real `build_fader_rows()`/
    `build_configuration_rows()` output, which need a genuine engine, not a
    duck-typed stand-in. nanoKONTROL2 (not the Studio) specifically because
    it still has real unconfirmed controls (Record, Set Marker), useful for
    any test here that wants to exercise Guided Capture's "has steps" path."""
    _qapp()
    monitor = monitor or MidiMonitor()
    engine = engine if engine is not None else MappingEngine(profile=NANOKONTROL2_PROFILE)
    capture_sessions_dir = capture_sessions_dir or Path(tempfile.mkdtemp())
    calls: list[int] = []
    dialog = MidiMonitorDialog(
        monitor,
        on_enter_diagnostic=lambda: calls.append(1),
        get_mapping_engine=lambda: engine,
        capture_sessions_dir=capture_sessions_dir,
    )
    return dialog, monitor, calls


# --- Opening defaults diagnostic mode on and fires the entry callback (MON-DIAG-004, 005) ---


def test_showing_the_dialog_turns_diagnostic_mode_on_and_checks_the_box() -> None:
    dialog, monitor, calls = _dialog()
    assert monitor.diagnostic_active is False

    dialog.show()

    assert monitor.diagnostic_active is True
    assert dialog._diagnostic_checkbox.isChecked() is True
    assert calls == [1]


def test_reopening_the_dialog_fires_the_entry_callback_again() -> None:
    dialog, monitor, calls = _dialog()
    dialog.show()
    dialog.close()
    assert calls == [1]

    dialog.show()

    assert calls == [1, 1]  # fires again on every open, not only the first
    assert monitor.diagnostic_active is True


# --- Checkbox toggling (MON-DIAG-005, 007) ---


def test_unchecking_the_checkbox_turns_diagnostic_mode_off_with_no_extra_send() -> None:
    dialog, monitor, calls = _dialog()
    dialog.show()
    assert calls == [1]

    dialog._diagnostic_checkbox.setChecked(False)

    assert monitor.diagnostic_active is False
    assert calls == [1]  # exiting never sends anything


def test_rechecking_the_checkbox_fires_the_entry_callback_again() -> None:
    dialog, monitor, calls = _dialog()
    dialog.show()
    dialog._diagnostic_checkbox.setChecked(False)

    dialog._diagnostic_checkbox.setChecked(True)

    assert monitor.diagnostic_active is True
    assert len(calls) == 2


# --- Closing always forces diagnostic mode off (MON-DIAG-008) ---


def test_closing_forces_diagnostic_mode_off_even_if_checkbox_was_left_checked() -> None:
    dialog, monitor, _ = _dialog()
    dialog.show()
    assert dialog._diagnostic_checkbox.isChecked() is True

    dialog.close()

    assert monitor.diagnostic_active is False


def test_closing_forces_diagnostic_mode_off_even_if_checkbox_was_unchecked() -> None:
    dialog, monitor, _ = _dialog()
    dialog.show()
    dialog._diagnostic_checkbox.setChecked(False)
    assert monitor.diagnostic_active is False

    dialog.close()

    assert monitor.diagnostic_active is False  # already false; still an explicit, safe no-op


# --- Clear (MON-UI-004) ---


def test_clear_empties_the_table_and_resets_the_captured_label() -> None:
    dialog, monitor, _ = _dialog()
    monitor.record(_cc(), device_name="nanoKONTROL2", resolved=None, module=None)
    dialog.refresh()
    assert dialog._table.rowCount() == 1

    dialog._on_clear_clicked()

    assert dialog._table.rowCount() == 0
    assert dialog._captured_label.text() == "No input captured yet."
    assert monitor.events == ()


def test_clear_while_a_capture_is_pending_keeps_the_waiting_label() -> None:
    dialog, monitor, _ = _dialog()
    dialog._on_capture_clicked()

    dialog._on_clear_clicked()

    assert monitor.capture_pending is True  # Clear never cancels a pending request
    assert dialog._captured_label.text() == "Waiting for next input…"


# --- Capture Next Input + refresh (MON-UI-005) ---


def test_capture_next_input_then_an_event_arriving_updates_the_captured_label() -> None:
    dialog, monitor, _ = _dialog()
    dialog._on_capture_clicked()
    assert dialog._captured_label.text() == "Waiting for next input…"

    monitor.record(_cc(number=41), device_name="nanoKONTROL2", resolved=None, module=None)
    dialog.refresh()

    assert "CC" in dialog._captured_label.text()
    assert "41" in dialog._captured_label.text()


# --- Batched refresh: no Qt work when nothing changed (MON-UI-007, 008) ---


def test_refresh_is_a_no_op_when_the_monitor_has_not_changed() -> None:
    dialog, monitor, _ = _dialog()
    monitor.record(_cc(), device_name=None, resolved=None, module=None)
    dialog.refresh()
    rendered_version = dialog._last_rendered_version

    dialog.refresh()  # nothing new recorded in between

    assert dialog._last_rendered_version == rendered_version
    assert dialog._table.rowCount() == 1


def test_refresh_batches_many_events_recorded_between_ticks_into_one_rebuild() -> None:
    """Simulates a burst of fast CC traffic (e.g. a jog wheel) arriving within
    one UI tick before refresh() is next called - the table must reflect all
    of it after a single refresh() call, not require one call per event."""
    dialog, monitor, _ = _dialog()
    for n in range(50):
        monitor.record(_cc(number=n), device_name="VSN1", resolved=None, module=None)

    dialog.refresh()

    assert dialog._table.rowCount() == 50


# --- Settings entry point exists and is reachable (MON-UI-001) ---


def test_dialog_exposes_a_close_button_and_stays_compact() -> None:
    dialog, _, _ = _dialog()
    assert dialog.windowTitle() == "MIDI Input Monitor"
    assert dialog._clear_button.text() == "Clear"
    assert dialog._capture_button.text() == "Capture Next Input"


# @spec MON-UI-009
def test_dialog_has_no_controller_selection_or_network_configuration_widgets() -> None:
    """Keeps the dialog scoped to exactly Clear / Capture Next Input /
    diagnostic checkbox / the event table - no QComboBox (controller
    selection) and no QLineEdit (host/port, like SettingsDialog has)."""
    from PySide6.QtWidgets import QComboBox, QLineEdit

    dialog, _, _ = _dialog()
    assert dialog.findChildren(QComboBox) == []
    assert dialog.findChildren(QLineEdit) == []


# ============================================================
# Guided Verify (docs/specs/midi-monitor.md § Guided Verify)
# ============================================================


def _studio_fader_cc(number: int, raw_value: int = 64) -> MidiEvent:
    return MidiEvent(type="cc", channel=15, number=number, raw_value=raw_value, normalized=raw_value / 127, is_press=False, is_release=False)


def _studio_dialog():
    from dragonmidi.mapping import STUDIO_PROFILE

    return _dialog(engine=MappingEngine(profile=STUDIO_PROFILE))


# @spec MON-VERIFY-001, MON-VERIFY-002
def test_verify_start_builds_steps_from_the_real_descriptor_list() -> None:
    dialog, _, _ = _studio_dialog()
    dialog._on_verify_start_clicked()
    assert dialog._verify_session is not None
    assert dialog._verify_session.total_steps > 0
    assert dialog._verify_session.current_step.label == "Fader Channel 1"
    assert dialog._verify_session.current_step.expected_key == ("cc", 0)


# @spec MON-VERIFY-009, MON-VERIFY-010
def test_verify_start_forces_diagnostic_on_and_disables_its_checkbox() -> None:
    dialog, monitor, calls = _studio_dialog()
    dialog._diagnostic_checkbox.setChecked(False)
    assert monitor.diagnostic_active is False

    dialog._on_verify_start_clicked()

    assert monitor.diagnostic_active is True
    assert calls == [1]
    assert dialog._diagnostic_checkbox.isEnabled() is False


# @spec MON-VERIFY-003, MON-VERIFY-004, MON-VERIFY-005
def test_verify_auto_advances_and_logs_on_a_correct_move() -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._on_verify_start_clicked()
    first_step = dialog._verify_session.current_step

    monitor.record(_studio_fader_cc(0), device_name="Studio", resolved=None, module=None)  # correct: Fader 1 is CC 0
    dialog.refresh()  # next UI tick

    assert dialog._verify_session.current_step != first_step
    assert len(dialog._verify_session.results) == 1
    assert dialog._verify_session.results[0].passed is True
    assert "✓" in dialog._verify_log.toPlainText()


# @spec MON-VERIFY-004, MON-VERIFY-006, MON-VERIFY-007
def test_verify_reports_a_mismatch_and_requires_retry_or_next() -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._on_verify_start_clicked()  # expects Fader Channel 1, CC 0

    monitor.record(_studio_fader_cc(5), device_name="Studio", resolved=None, module=None)  # wrong control
    dialog.refresh()

    assert dialog._verify_session.pending_passed is False
    assert len(dialog._verify_session.results) == 0  # not auto-advanced
    assert dialog._verify_retry_button.isEnabled() is True
    assert dialog._verify_next_button.isEnabled() is True
    assert "Mismatch" in dialog._verify_pending_label.text()


def test_verify_retry_clears_pending_and_keeps_the_same_step() -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._on_verify_start_clicked()
    step_before = dialog._verify_session.current_step
    monitor.record(_studio_fader_cc(5), device_name=None, resolved=None, module=None)
    dialog.refresh()

    dialog._on_verify_retry_clicked()

    assert dialog._verify_session.pending is None
    assert dialog._verify_session.current_step == step_before
    assert dialog._verify_session.results == ()


def test_verify_next_accepts_the_failure_and_advances() -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._on_verify_start_clicked()
    step_before = dialog._verify_session.current_step
    monitor.record(_studio_fader_cc(5), device_name=None, resolved=None, module=None)
    dialog.refresh()

    dialog._on_verify_next_clicked()

    assert len(dialog._verify_session.results) == 1
    assert dialog._verify_session.results[0].passed is False
    assert dialog._verify_session.current_step != step_before
    assert "✗" in dialog._verify_log.toPlainText()


def test_verify_cancel_discards_without_saving(tmp_path) -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._capture_sessions_dir = tmp_path
    dialog._on_verify_start_clicked()
    monitor.record(_studio_fader_cc(0), device_name=None, resolved=None, module=None)
    dialog.refresh()

    dialog._on_verify_cancel_clicked()

    assert dialog._verify_session is None
    assert dialog._diagnostic_checkbox.isEnabled() is True
    assert not list(tmp_path.glob("*.json"))


# @spec MON-VERIFY-008
def test_verify_finishing_shows_a_summary_and_enables_save_then_save_ends_the_session(tmp_path) -> None:
    dialog, monitor, _ = _studio_dialog()
    dialog._capture_sessions_dir = tmp_path
    dialog._on_verify_start_clicked()
    total = dialog._verify_session.total_steps

    # Pass every step by always offering an event that resolves (via the raw
    # fallback) to whatever the current step's expected key already is -
    # this test only needs "finished", not a mix of pass/fail.
    for _ in range(total):
        key = dialog._verify_session.current_step.expected_key
        raw = MidiEvent(type=key[0], channel=15, number=key[1], raw_value=64, normalized=64 / 127, is_press=False, is_release=False)
        monitor.record(raw, device_name=None, resolved=None, module=None)
        dialog.refresh()

    assert dialog._verify_session.finished is True
    assert dialog._verify_retry_button.isEnabled() is False
    assert dialog._verify_next_button.isEnabled() is False
    assert dialog._verify_save_button.isEnabled() is True
    assert f"{total} passed, 0 failed" in dialog._verify_status_label.text()

    dialog._on_verify_save_clicked()

    assert dialog._verify_session is None  # Save ends the session, mirroring Guided Capture
    saved = list(tmp_path.glob("*-verify-*.json"))
    assert len(saved) == 1


# --- Mutual exclusion between Guided Capture and Guided Verify ---


def test_guided_capture_and_guided_verify_are_mutually_exclusive() -> None:
    dialog, _, _ = _studio_dialog()  # STUDIO_PROFILE has no unconfirmed controls - force the engine's profile for Capture's own steps too
    from dragonmidi.mapping import NANOKONTROL2_PROFILE

    dialog._get_mapping_engine = lambda: MappingEngine(profile=NANOKONTROL2_PROFILE)

    dialog._on_guided_start_clicked()
    assert dialog._guided_session is not None
    dialog._update_verify_ui()
    assert dialog._verify_start_button.isEnabled() is False

    dialog._end_guided_session()
    dialog._on_verify_start_clicked()
    assert dialog._verify_session is not None
    dialog._update_guided_ui()
    assert dialog._guided_start_button.isEnabled() is False
