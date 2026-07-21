from __future__ import annotations

import os
import queue
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import ConfigController, EndpointConfig
from .controller_profile import ControllerProfile
from .events import MidiEvent
from .keystroke_output import KeystrokeOutputAdapter, PynputBackend
from .mapping import NANOKONTROL2_PROFILE, STUDIO_PROFILE, MappingEngine
from .mapping_widgets import MappingView
from .midi_input import MidiInputAdapter, MidoBackend
from .osc_io import AxisDiscovery, OscClient, OscListener
from .queue_drain import drain_queue
from .shutdown import run_shutdown_sequence
from .signal_monitor import SignalMonitor
from .status_presenter import compute_status_snapshot, show_nanokontrol2_setup_hint
from .status_widgets import IndicatorRow
from .websocket_output import WebSocketOutputAdapter

APP_TITLE = "DragonMIDI"
DISCOVERY_POLL_MS = 2000
UI_TICK_MS = 30

# @spec MIDI-PROFILE-001, MIDI-PROFILE-004, UI-PROFILE-001
CONTROLLER_PROFILES: tuple[ControllerProfile, ...] = (STUDIO_PROFILE, NANOKONTROL2_PROFILE)
NANOKONTROL2_SETUP_HINT = "Hold SET MARKER + CYCLE while powering on for CC mode"


def _asset_path(filename: str) -> str | None:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.join(os.path.dirname(__file__), "..", "assets")
    path = os.path.normpath(os.path.join(base, filename))
    return path if os.path.exists(path) else None


class DragonMidiWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)

        self._activity_queue: "queue.Queue[str]" = queue.Queue()
        self._midi_queue: "queue.Queue[MidiEvent]" = queue.Queue()

        self._mapping = MappingEngine(profile=STUDIO_PROFILE)
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
            profile=STUDIO_PROFILE,
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

        profile_form = QGridLayout()
        profile_form.addWidget(QLabel("Controller"), 0, 0)
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([profile.name for profile in CONTROLLER_PROFILES])
        # Connected after addItems() so populating the combo (index -1 -> 0) doesn't
        # itself fire a redundant initial profile switch - the engine/adapter already
        # start on CONTROLLER_PROFILES[0] (nanoKONTROL Studio) from their constructors.
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        profile_form.addWidget(self._profile_combo, 0, 1)
        layout.addLayout(profile_form)

        self._profile_hint_label = QLabel(NANOKONTROL2_SETUP_HINT)
        self._profile_hint_label.setVisible(False)
        layout.addWidget(self._profile_hint_label)

        self._midi_row = IndicatorRow("MIDI signal")
        self._dragonframe_row = IndicatorRow("Dragonframe signal")
        layout.addWidget(self._midi_row)
        layout.addWidget(self._dragonframe_row)

        form = QGridLayout()
        form.addWidget(QLabel("Sending to"), 0, 0)
        self._host_edit = QLineEdit(self._config.applied.host)
        self._df_port_edit = QLineEdit(str(self._config.applied.dragonframe_port))
        form.addWidget(self._host_edit, 0, 1)
        form.addWidget(self._df_port_edit, 0, 2)
        form.addWidget(QLabel("Listen port"), 1, 0)
        self._listen_port_edit = QLineEdit(str(self._config.applied.listen_port))
        form.addWidget(self._listen_port_edit, 1, 1)
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self._on_apply_clicked)
        form.addWidget(apply_button, 1, 2)
        layout.addLayout(form)

        layout.addWidget(QLabel("Mapping"))
        self._mapping_view = MappingView(self._mapping, self._axis_discovery, on_rescan=self._osc_listener.rescan)
        layout.addWidget(self._mapping_view, 1)

        self.setCentralWidget(central)
        self.resize(self._mapping_view.table_width_hint() + 60, 700)

    def _on_midi_connection_change(self, connected: bool, device_name: str | None) -> None:
        self._midi_connected = connected
        self._midi_device_name = device_name

    def _on_profile_changed(self, index: int) -> None:
        """Applies immediately, no Apply step (@spec UI-PROFILE-002): resets the
        Mapping Engine to the newly-selected profile's map right away, independent
        of whether a matching device has yet been found, then tells the MIDI Input
        Adapter to disconnect (if connected) and start matching the new pattern
        (@spec MIDI-PROFILE-005, MIDI-PROFILE-006).
        """
        profile = CONTROLLER_PROFILES[index]
        self._mapping.set_profile(profile)
        self._midi.set_profile(profile)
        self._profile_hint_label.setVisible(show_nanokontrol2_setup_hint(profile.name))  # @spec UI-PROFILE-003
        self._mapping_view.refresh()

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

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override signature
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
    icon_path = _asset_path("dragonmidi.png")
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))
    window = DragonMidiWindow()
    window.show()
    sys.exit(app.exec())
