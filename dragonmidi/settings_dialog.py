"""A new, thin modal dialog (Phase 8) holding the host/Dragonframe-port/
listen-port fields, the per-profile setup hint, and the config-load-failure
count - fields that previously lived inline in the main window's body, moved
behind the shared header's ⚙ button (`docs/llds/app-ui.md § Settings
Dialog`). No new validation, persistence, or Apply logic: `ConfigController`'s
existing pending/applied/Apply-validate behavior is reused unchanged.

Distinct from `ConfigurationDialog` (`mapping_widgets.py`), which holds
per-control mapping summaries and lives in Table View instead - the two are
easy to conflate by name, so this module calls them Settings dialog and
Configuration dialog throughout.

@spec UI-SETTINGS-001, UI-SETTINGS-002
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from .config import ConfigController
from .status_presenter import show_setup_hint

# Same bounded widths the pre-Phase-8 Status UI already applied to these
# fields (2026-07-23) - unchanged by moving them into this dialog.
_HOST_FIELD_MAX_WIDTH = 110
_PORT_FIELD_MAX_WIDTH = 55
_NETWORK_LABEL_WIDTH = 90


class SettingsDialog(QDialog):
    """@spec UI-SETTINGS-001, UI-SETTINGS-002"""

    def __init__(self, config: ConfigController, load_failure_text: str | None, on_open_monitor: Callable[[], None] = lambda: None) -> None:
        super().__init__()
        self.setWindowTitle("Settings")
        self._config = config

        layout = QVBoxLayout(self)

        self._profile_hint_label = QLabel("")
        self._profile_hint_label.setVisible(False)
        layout.addWidget(self._profile_hint_label)

        if load_failure_text is not None:
            layout.addWidget(QLabel(load_failure_text))

        sending_to_label = QLabel("Sending to")
        sending_to_label.setFixedWidth(_NETWORK_LABEL_WIDTH)
        listen_port_label = QLabel("Listen port")
        listen_port_label.setFixedWidth(_NETWORK_LABEL_WIDTH)

        sending_to_row = QHBoxLayout()
        sending_to_row.addWidget(sending_to_label)
        self._host_edit = QLineEdit(config.applied.host)
        self._host_edit.setMaximumWidth(_HOST_FIELD_MAX_WIDTH)
        self._df_port_edit = QLineEdit(str(config.applied.dragonframe_port))
        self._df_port_edit.setMaximumWidth(_PORT_FIELD_MAX_WIDTH)
        sending_to_row.addWidget(self._host_edit)
        sending_to_row.addWidget(self._df_port_edit)
        sending_to_row.addStretch(1)
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._on_apply_clicked)
        sending_to_row.addWidget(apply_button)
        layout.addLayout(sending_to_row)

        listen_port_row = QHBoxLayout()
        listen_port_row.addWidget(listen_port_label)
        self._listen_port_edit = QLineEdit(str(config.applied.listen_port))
        self._listen_port_edit.setMaximumWidth(_PORT_FIELD_MAX_WIDTH)
        listen_port_row.addWidget(self._listen_port_edit)
        listen_port_row.addStretch(1)
        layout.addLayout(listen_port_row)

        # Added Phase 1.6 (docs/llds/midi-monitor.md) - a hardware-diagnostic
        # tool, not network configuration, but reachable from here per the
        # task that introduced it rather than a second top-level header button.
        monitor_row = QHBoxLayout()
        self._monitor_button = QPushButton("MIDI Input Monitor…")
        self._monitor_button.clicked.connect(on_open_monitor)
        monitor_row.addWidget(self._monitor_button)
        monitor_row.addStretch(1)
        layout.addLayout(monitor_row)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def set_profile_hint(self, setup_hint: str | None) -> None:
        """@spec UI-SETTINGS-001 (carries UI-PROFILE-003's existing behavior)"""
        self._profile_hint_label.setText(setup_hint or "")
        self._profile_hint_label.setVisible(show_setup_hint(setup_hint))

    def _on_apply_clicked(self) -> None:
        try:
            self._config.edit(
                host=self._host_edit.text().strip(),
                dragonframe_port=int(self._df_port_edit.text()),
                listen_port=int(self._listen_port_edit.text()),
            )
            self._config.apply()
        except ValueError:
            pass  # invalid input (bad int, or equal ports): edits stay pending, nothing applied
