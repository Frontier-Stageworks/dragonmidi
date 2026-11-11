"""Tests for the Settings Dialog (docs/specs/app-ui.md § Settings Dialog).

Uses PySide6's offscreen platform plugin, matching `test_mapping_widgets.py`.

@spec UI-SETTINGS-001, UI-SETTINGS-002
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from dragonmidi.config import ConfigController, EndpointConfig  # noqa: E402
from dragonmidi.settings_dialog import SettingsDialog  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _config() -> ConfigController:
    applied: list[tuple] = []
    return ConfigController(EndpointConfig(), on_apply=lambda cfg, changed: applied.append((cfg, changed)))


# @spec UI-SETTINGS-001
def test_fields_initialize_from_the_config_controllers_applied_values() -> None:
    _qapp()
    config = ConfigController(EndpointConfig(host="10.0.0.5", dragonframe_port=7010, listen_port=7011), on_apply=lambda *a: None)
    dialog = SettingsDialog(config, load_failure_text=None)
    assert dialog._host_edit.text() == "10.0.0.5"
    assert dialog._df_port_edit.text() == "7010"
    assert dialog._listen_port_edit.text() == "7011"


# @spec UI-SETTINGS-001
def test_apply_edits_and_applies_the_config_controller() -> None:
    _qapp()
    applied = []
    config = ConfigController(EndpointConfig(), on_apply=lambda cfg, changed: applied.append((cfg, changed)))
    dialog = SettingsDialog(config, load_failure_text=None)

    dialog._host_edit.setText("192.168.1.50")
    dialog._df_port_edit.setText("8000")
    dialog._listen_port_edit.setText("8001")
    dialog._on_apply_clicked()

    assert config.applied.host == "192.168.1.50"
    assert config.applied.dragonframe_port == 8000
    assert config.applied.listen_port == 8001
    assert len(applied) == 1


# @spec UI-SETTINGS-001
def test_invalid_port_input_does_not_apply() -> None:
    _qapp()
    config = _config()
    dialog = SettingsDialog(config, load_failure_text=None)
    original = config.applied

    dialog._df_port_edit.setText("not a number")
    dialog._on_apply_clicked()

    assert config.applied == original


# @spec UI-SETTINGS-001
def test_setup_hint_visibility_follows_show_setup_hint() -> None:
    _qapp()
    dialog = SettingsDialog(_config(), load_failure_text=None)
    dialog.show()  # a widget inside an unshown top-level always reports isVisible() == False
    assert dialog._profile_hint_label.isVisible() is False

    dialog.set_profile_hint("Hold SET MARKER + CYCLE while powering on")
    assert dialog._profile_hint_label.isVisible() is True
    assert dialog._profile_hint_label.text() == "Hold SET MARKER + CYCLE while powering on"

    dialog.set_profile_hint(None)
    assert dialog._profile_hint_label.isVisible() is False


# @spec UI-SETTINGS-001
def test_load_failure_text_shown_when_given() -> None:
    _qapp()
    dialog = SettingsDialog(_config(), load_failure_text="2 controller config files failed to load")
    texts = [dialog.layout().itemAt(i).widget().text() for i in range(dialog.layout().count()) if dialog.layout().itemAt(i).widget() is not None]
    assert any("failed to load" in text for text in texts)


# @spec MON-UI-001
def test_monitor_button_invokes_the_injected_callback() -> None:
    _qapp()
    calls = []
    dialog = SettingsDialog(_config(), load_failure_text=None, on_open_monitor=lambda: calls.append(1))
    dialog._monitor_button.click()
    assert calls == [1]


# @spec MON-UI-001
def test_monitor_button_defaults_to_a_harmless_no_op() -> None:
    _qapp()
    dialog = SettingsDialog(_config(), load_failure_text=None)
    dialog._monitor_button.click()  # must not raise
