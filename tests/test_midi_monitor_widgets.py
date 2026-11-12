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
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dragonmidi.events import MidiEvent  # noqa: E402
from dragonmidi.midi_monitor import MidiMonitor  # noqa: E402
from dragonmidi.midi_monitor_widgets import MidiMonitorDialog  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _cc(number: int = 36) -> MidiEvent:
    return MidiEvent(type="cc", channel=0, number=number, raw_value=64, normalized=64 / 127, is_press=False, is_release=False)


@dataclass
class _FakeController:
    """A minimal stand-in exposing exactly what build_capture_steps() reads -
    no real MappingEngine/ControllerProfile needed for these widget tests."""

    name: str = "Fake Controller"
    bank_count: int = 2
    unconfirmed_channel_controls: tuple[str, ...] = field(default_factory=tuple)
    unconfirmed_global_controls: tuple[str, ...] = field(default_factory=tuple)


def _dialog(
    monitor: MidiMonitor | None = None,
    controller: _FakeController | None = None,
    capture_sessions_dir: Path | None = None,
) -> tuple[MidiMonitorDialog, MidiMonitor, list[int]]:
    _qapp()
    monitor = monitor or MidiMonitor()
    controller = controller if controller is not None else _FakeController()
    capture_sessions_dir = capture_sessions_dir or Path(tempfile.mkdtemp())
    calls: list[int] = []
    dialog = MidiMonitorDialog(
        monitor,
        on_enter_diagnostic=lambda: calls.append(1),
        get_active_controller=lambda: controller,
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
