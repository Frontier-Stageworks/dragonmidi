from __future__ import annotations

import os
import queue
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import ConfigController, EndpointConfig
from .controller_profile import ControllerProfile
from .controller_profile_loader import load_controller_profiles
from .events import MidiEvent
from .keystroke_output import KeystrokeOutputAdapter, PynputBackend
from .mapping import MappingEngine
from .mapping_widgets import ConfigurationDialog, MappingView
from .midi_input import MidiInputAdapter, MidoBackend
from .osc_io import AxisDiscovery, OscClient, OscListener
from .preset_store import load_group_axis_targets, save_group_axis_targets
from .queue_drain import drain_queue
from .shutdown import run_shutdown_sequence
from .signal_monitor import SignalMonitor
from .status_presenter import compute_status_snapshot, config_load_failure_label, show_setup_hint
from .status_widgets import IndicatorRow
from .websocket_output import WebSocketOutputAdapter

APP_TITLE = "DragonMIDI"
DISCOVERY_POLL_MS = 2000
UI_TICK_MS = 30
DEFAULT_PROFILE_NAME = "nanoKONTROL Studio"
# Fixed maximum widths for the host/port fields (2026-07-23, user's explicit
# choice) - sized to their longest realistic content (an IPv4 address/short
# hostname, and a 5-digit port number) rather than stretching to fill the row.
_HOST_FIELD_MAX_WIDTH = 110
_PORT_FIELD_MAX_WIDTH = 55
# Bounded the same way as the host/port fields - a controller name has no
# reason to claim more than this much width (2026-07-23, user's explicit choice).
_CONTROLLER_COMBO_MAX_WIDTH = 250

# Evokes the app icon's own light/dark grey palette (2026-07-23, user's explicit
# choice, superseding the initial cream/mustard pass) - colors sampled directly
# from assets/dragonmidi.png (the icon's background and fader-icon fill), plus a
# monospace, technical-blueprint typography family applied to Qt's native widgets.
# The mustard accent from that initial pass is kept for every button - user's
# explicit choice.
_INK = "#363B40"
_PAPER = "#C7D3DE"
_ACCENT = "#E8B923"
_APP_STYLESHEET = f"""
QWidget {{
    background-color: {_PAPER};
    color: {_INK};
    font-family: Menlo, Monaco, "Courier New", monospace;
}}
QGroupBox {{
    border: 2px solid {_INK};
    border-radius: 0px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    background-color: {_PAPER};
}}
QPushButton {{
    background-color: {_ACCENT};
    border: 2px solid {_INK};
    border-radius: 0px;
    padding: 5px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #f0c53d;
}}
QPushButton:pressed {{
    background-color: #cfa61c;
}}
QLineEdit, QComboBox {{
    border: 1px solid {_INK};
    border-radius: 0px;
    padding: 3px 6px;
    background-color: white;
}}
QTableWidget {{
    border: 2px solid {_INK};
    gridline-color: {_INK};
    background-color: white;
}}
QHeaderView::section {{
    background-color: {_INK};
    color: {_PAPER};
    padding: 4px;
    border: none;
    font-weight: bold;
}}
"""


def _asset_path(filename: str) -> str | None:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.join(os.path.dirname(__file__), "..", "assets")
    path = os.path.normpath(os.path.join(base, filename))
    return path if os.path.exists(path) else None


def _bundled_controllers_dir() -> Path:
    """@spec PROFILE-LOAD-001 (bundled-folder resolution, same frozen-vs-dev branch
    as `_asset_path`)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "dragonmidi" / "controllers"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "controllers"


def _user_controllers_dir() -> Path:
    """@spec PROFILE-LOAD-001"""
    return Path.home() / "Documents" / "DragonMIDI" / "controllers"


def _configurations_dir() -> Path:
    """@spec MAP-STORE-001"""
    return Path.home() / "Documents" / "DragonMIDI" / "configurations"


def _default_profile(profiles: tuple[ControllerProfile, ...]) -> ControllerProfile:
    """@spec MIDI-PROFILE-004"""
    for profile in profiles:
        if profile.name == DEFAULT_PROFILE_NAME:
            return profile
    return profiles[0]  # accepted fallback if even the bundled Studio profile failed to load


class DragonMidiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)

        # Discovered once per launch, before anything else - @spec PROFILE-LOAD-001.
        # Deliberately not module-level: a bare `import dragonmidi.app` (e.g. from a
        # test or tool) must not have the side effect of touching the real filesystem
        # (creating/seeding the user-local controllers folder, @spec PROFILE-LOAD-007).
        self._load_result = load_controller_profiles(bundled_dir=_bundled_controllers_dir(), user_dir=_user_controllers_dir())
        self._controller_profiles: tuple[ControllerProfile, ...] = self._load_result.profiles
        self._default_profile = _default_profile(self._controller_profiles)

        self._activity_queue: queue.Queue[str] = queue.Queue()
        self._midi_queue: queue.Queue[MidiEvent] = queue.Queue()

        self._mapping = MappingEngine(profile=self._default_profile)
        # @spec MAP-STORE-002: load the default profile's persisted (Bank, Group)
        # axis table before the Mapping View is built, so the initial render
        # (UI-MAP-011) already reflects it.
        self._mapping.load_group_axis_targets(load_group_axis_targets(_configurations_dir(), self._default_profile.name))
        self._keystroke_output = KeystrokeOutputAdapter(PynputBackend())
        self._websocket_output = WebSocketOutputAdapter()
        self._monitor = SignalMonitor()
        self._config = ConfigController(EndpointConfig(), on_apply=self._on_config_applied)

        self._osc_client = OscClient(host=self._config.applied.host, port=self._config.applied.dragonframe_port)
        self._axis_discovery = AxisDiscovery()
        self._osc_listener = OscListener(
            port=self._config.applied.listen_port,
            on_activity=lambda: self._activity_queue.put("dragonframe"),
            on_bind_result=lambda ok: self._monitor.set_error("dragonframe", not ok),
            axis_discovery=self._axis_discovery,
            dragonframe_host=self._config.applied.host,
            dragonframe_port=self._config.applied.dragonframe_port,
        )
        self._midi_connected = False
        self._midi_device_name: str | None = None
        self._midi = MidiInputAdapter(
            backend=MidoBackend(),
            on_activity=lambda: self._activity_queue.put("midi"),
            on_event=self._midi_queue.put,
            on_connection_change=self._on_midi_connection_change,
            on_error=lambda active: self._monitor.set_error("midi", active),
            on_reset_mapping=self._mapping.reset,
            profile=self._default_profile,
        )

        self._build_ui()

        self._osc_listener.start()
        self._websocket_output.start()

        self._discovery_timer = QTimer(self)
        self._discovery_timer.timeout.connect(self._midi.poll_discovery)
        self._discovery_timer.start(DISCOVERY_POLL_MS)

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._on_tick)
        self._ui_timer.start(UI_TICK_MS)

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        title_label = QLabel(APP_TITLE)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(title_label)

        top_row = QHBoxLayout()
        top_row.addWidget(self._build_status_group())
        top_row.addWidget(self._build_configuration_group())
        layout.addLayout(top_row)

        layout.addWidget(QLabel("Mapping"))
        self._mapping_view = MappingView(
            self._mapping,
            self._axis_discovery,
            on_rescan=self._osc_listener.rescan,
            on_group_axis_changed=self._save_group_axis_targets,
        )
        layout.addWidget(self._mapping_view, 1)

        self.setCentralWidget(central)
        self.resize(self._mapping_view.table_width_hint() + 60, 700)

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("Status")
        layout = QVBoxLayout(group)
        self._midi_row = IndicatorRow("MIDI signal")
        self._dragonframe_row = IndicatorRow("Dragonframe signal")
        layout.addWidget(self._midi_row)
        layout.addWidget(self._dragonframe_row)
        layout.addStretch(1)
        return group

    def _build_configuration_group(self) -> QGroupBox:
        """Controller selection and network settings share one "Configuration"
        panel, side-by-side with Status (2026-07-23, user's explicit choice) -
        both are settings a user sets and rarely revisits, unlike Status's
        continuously-live indicators."""
        group = QGroupBox("Configuration")
        layout = QVBoxLayout(group)

        combo_row = QHBoxLayout()
        combo_row.addWidget(QLabel("Controller"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([profile.name for profile in self._controller_profiles])
        self._profile_combo.setMaximumWidth(_CONTROLLER_COMBO_MAX_WIDTH)
        default_index = next(i for i, p in enumerate(self._controller_profiles) if p is self._default_profile)
        # setCurrentIndex() before connecting the signal, so selecting the default
        # profile (which may not be index 0 - the dropdown lists user-local profiles
        # first, @spec PROFILE-LOAD-004) doesn't itself fire a redundant initial
        # profile switch - the engine/adapter already start on self._default_profile
        # from their constructors.
        self._profile_combo.setCurrentIndex(default_index)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        combo_row.addWidget(self._profile_combo)
        combo_row.addStretch(1)
        layout.addLayout(combo_row)

        self._configuration_dialog = ConfigurationDialog(self._mapping)
        configuration_button = QPushButton("Configuration…")
        configuration_button.clicked.connect(self._on_configuration_clicked)
        configuration_row = QHBoxLayout()
        configuration_row.addWidget(configuration_button)
        configuration_row.addStretch(1)
        layout.addLayout(configuration_row)

        self._profile_hint_label = QLabel(self._default_profile.setup_hint or "")
        self._profile_hint_label.setVisible(show_setup_hint(self._default_profile.setup_hint))
        layout.addWidget(self._profile_hint_label)

        load_failure_text = config_load_failure_label(len(self._load_result.failures))
        if load_failure_text is not None:
            layout.addWidget(QLabel(load_failure_text))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        sending_to_container = QWidget()
        sending_to_row = QHBoxLayout(sending_to_container)
        sending_to_row.setContentsMargins(0, 0, 0, 0)
        self._host_edit = QLineEdit(self._config.applied.host)
        self._host_edit.setMaximumWidth(_HOST_FIELD_MAX_WIDTH)
        self._df_port_edit = QLineEdit(str(self._config.applied.dragonframe_port))
        self._df_port_edit.setMaximumWidth(_PORT_FIELD_MAX_WIDTH)
        sending_to_row.addWidget(self._host_edit)
        sending_to_row.addWidget(self._df_port_edit)
        form.addRow("Sending to", sending_to_container)

        self._listen_port_edit = QLineEdit(str(self._config.applied.listen_port))
        self._listen_port_edit.setMaximumWidth(_PORT_FIELD_MAX_WIDTH)
        form.addRow("Listen port", self._listen_port_edit)
        layout.addLayout(form)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._on_apply_clicked)
        apply_row = QHBoxLayout()
        apply_row.addWidget(apply_button)
        apply_row.addStretch(1)
        layout.addLayout(apply_row)

        return group

    def _on_midi_connection_change(self, connected: bool, device_name: str | None) -> None:
        self._midi_connected = connected
        self._midi_device_name = device_name

    def _on_configuration_clicked(self) -> None:
        """@spec UI-CFGDLG-001: opened modally; the underlying QTimer keeps
        ticking during exec()'s nested event loop, so the dialog's own content
        (and the main window's, if later revealed) stays live-refreshed.
        """
        self._configuration_dialog.exec()

    def _on_profile_changed(self, index: int) -> None:
        """Applies immediately, no Apply step (@spec UI-PROFILE-002): resets the
        Mapping Engine to the newly-selected profile's map right away, independent
        of whether a matching device has yet been found, then tells the MIDI Input
        Adapter to disconnect (if connected) and start matching the new pattern
        (@spec MIDI-PROFILE-005, MIDI-PROFILE-006).
        """
        profile = self._controller_profiles[index]
        self._mapping.set_profile(profile)
        # @spec MAP-STORE-002, MAP-STORE-007: loaded synchronously, in the same
        # handler as set_profile() above and before the Mapping View refreshes -
        # no caller can observe _group_axis_targets cleared-but-not-yet-reloaded.
        self._mapping.load_group_axis_targets(load_group_axis_targets(_configurations_dir(), profile.name))
        self._midi.set_profile(profile)
        self._profile_hint_label.setText(profile.setup_hint or "")
        self._profile_hint_label.setVisible(show_setup_hint(profile.setup_hint))  # @spec UI-PROFILE-003
        self._mapping_view.refresh()
        self._configuration_dialog.rebuild_for_profile_change()  # @spec UI-CFGDLG-010

    def _save_group_axis_targets(self) -> None:
        """@spec MAP-STORE-004"""
        save_group_axis_targets(_configurations_dir(), self._mapping.profile.name, self._mapping.dump_group_axis_targets())

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

    def _on_config_applied(self, config: EndpointConfig, listen_port_changed: bool) -> None:
        self._osc_client.configure(config.host, config.dragonframe_port)
        self._osc_listener.update_dragonframe_target(config.host, config.dragonframe_port)
        if listen_port_changed:
            self._osc_listener.rebind(config.listen_port)

    def _on_tick(self) -> None:
        drain_queue(self._activity_queue, self._monitor.mark_activity)
        drain_queue(self._midi_queue, self._process_midi_event)
        self._axis_discovery.check_timeout()
        self._mapping_view.refresh()
        self._configuration_dialog.refresh()

        snapshot = compute_status_snapshot(
            self._monitor,
            midi_connected=self._midi_connected,
            midi_device_name=self._midi_device_name,
            listen_port=self._config.applied.listen_port,
            midi_profile_name=self._midi.profile.name,
        )
        self._midi_row.set_state(snapshot.midi.state, snapshot.midi.label)
        self._dragonframe_row.set_state(snapshot.dragonframe.state, snapshot.dragonframe.label)

    def _process_midi_event(self, event: MidiEvent) -> None:
        now = time.monotonic()
        axis_positions = self._axis_discovery.axes
        message = self._mapping.process(event, now=now, axis_positions=axis_positions)
        if message is not None:
            self._osc_client.send(message.address, *message.args)
        combo = self._mapping.process_keystroke(event)
        if combo is not None:
            self._keystroke_output.send(combo)
        command = self._mapping.process_websocket(event, now=now, axis_positions=axis_positions)
        if command is not None:
            self._websocket_output.send(command)

    def closeEvent(self, event) -> None:
        run_shutdown_sequence(
            [
                self._midi.disconnect,
                self._osc_listener.stop,
                self._osc_client.close,
                self._websocket_output.stop,
            ]
        )
        super().closeEvent(event)


def run() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(_APP_STYLESHEET)
    icon_path = _asset_path("dragonmidi.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    window = DragonMidiWindow()
    window.show()
    sys.exit(app.exec())
