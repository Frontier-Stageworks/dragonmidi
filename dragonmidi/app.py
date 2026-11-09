from __future__ import annotations

import os
import queue
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .active_controller import ActiveController
from .config import ConfigController, EndpointConfig
from .controller_profile import ControllerProfile
from .controller_profile_loader import load_controller_profiles
from .controller_selection import ControllerChoice, GridChoice, StaticChoice, build_controller_choices
from .controller_view_widgets import ControllerView, GroupSelectorRow
from .events import MidiEvent
from .grid_controller import GridRuntimeController
from .grid_lifecycle import GridAppCoordinator, GridLifecycle
from .grid_transport import SerialGridTransport
from .keystroke_output import KeystrokeOutputAdapter, PynputBackend
from .mapping import MappingEngine
from .mapping_widgets import ConfigurationDialog, MappingView
from .midi_input import MidiInputAdapter, MidoBackend
from .named_controller_dialog import NamedControllerAmbiguousDialog
from .named_controller_registry import (
    Activated,
    Ambiguous,
    NamedController,
    create_grid_named_controller,
    ensure_static_named_controller,
    rename_named_controller,
    resolve_grid_named_controller,
)
from .osc_io import AxisDiscovery, OscClient, OscListener
from .preset_store import load_bank_actions, load_group_axis_targets, save_group_axis_targets
from .queue_drain import drain_queue
from .settings_dialog import SettingsDialog
from .shutdown import run_shutdown_sequence
from .signal_monitor import ChannelState, SignalMonitor
from .status_presenter import compute_status_snapshot, config_load_failure_label
from .status_widgets import IndicatorRow
from .websocket_output import WebSocketOutputAdapter

APP_TITLE = "DragonMIDI"
DISCOVERY_POLL_MS = 2000
UI_TICK_MS = 30
DEFAULT_PROFILE_NAME = "nanoKONTROL Studio"
_REPO_URL = "https://github.com/Frontier-Stageworks/dragonmidi"
# Bounded the same way host/port fields are (now in settings_dialog.py) - a
# controller name has no reason to claim more than this much width
# (2026-07-23, user's explicit choice).
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


def _named_controllers_dir() -> Path:
    """@spec NAMEDCTRL-DATA-002"""
    return Path.home() / "Documents" / "DragonMIDI" / "named_controllers"


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
        # "Intech Grid" sits alongside the loaded profiles in the dropdown without
        # being one itself - @spec GRID-APP-001. The coordinator is the Qt-independent
        # state machine deciding when Grid's CDC lifecycle starts/stops and when a
        # just-settled GridRuntimeController should be installed (docs/llds/intech-grid.md
        # § Application Integration); it never touches a widget directly.
        self._controller_choices: tuple[ControllerChoice, ...] = build_controller_choices(self._controller_profiles)
        self._grid_coordinator = GridAppCoordinator(GridLifecycle(SerialGridTransport()))

        self._activity_queue: queue.Queue[str] = queue.Queue()
        self._midi_queue: queue.Queue[MidiEvent] = queue.Queue()

        self._mapping = MappingEngine(profile=self._default_profile)
        # @spec NAMEDCTRL-STATIC-001, NAMEDCTRL-STATIC-002: a transparent 1:1
        # wrapper for a static profile - id == profile.name always, so the
        # Preset Store key below is byte-identical to the bare name used
        # before this feature existed.
        self._active_named_controller: NamedController = ensure_static_named_controller(_named_controllers_dir(), self._default_profile.name)
        # @spec MAP-STORE-002: load the default profile's persisted (Bank, Group)
        # axis table before the Mapping View is built, so the initial render
        # (UI-MAP-011) already reflects it.
        self._mapping.load_group_axis_targets(
            load_group_axis_targets(_configurations_dir(), self._active_named_controller.id, self._default_profile.bank_count)
        )
        # @spec MAP-BTNACT-005: loaded the same way, before the Mapping View is built.
        self._mapping.load_bank_control_actions(
            load_bank_actions(_configurations_dir(), self._active_named_controller.id, self._default_profile.bank_count)
        )
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
        self._discovery_timer.timeout.connect(self._on_discovery_tick)
        self._discovery_timer.start(DISCOVERY_POLL_MS)

        self._ui_timer = QTimer(self)
        self._ui_timer.timeout.connect(self._on_tick)
        self._ui_timer.start(UI_TICK_MS)

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_header())

        self._body_stack = QStackedWidget()
        self._controller_view = ControllerView(
            self._mapping,
            self._axis_discovery,
            on_group_axis_changed=self._save_group_axis_targets,
        )
        self._body_stack.addWidget(self._controller_view)  # page 0, default (@spec UI-SHELL-005)
        self._body_stack.addWidget(self._build_table_view_page())  # page 1
        layout.addWidget(self._body_stack, 1)

        layout.addLayout(self._build_footer())

        footer_label = QLabel(f'Developed by Frontier Stageworks · GPL-3.0-or-later · <a href="{_REPO_URL}">{_REPO_URL}</a>')
        footer_label.setOpenExternalLinks(True)
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(footer_label)

        self.setCentralWidget(central)
        self.resize(900, 560)

    def _build_header(self) -> QVBoxLayout:
        """The shared header (`docs/llds/app-ui.md § Main Window Shell`):
        renders identically and stays interactive regardless of which body
        page (`_body_stack`) is currently showing.

        @spec UI-SHELL-001, UI-SHELL-002
        """
        header = QVBoxLayout()

        title_row = QHBoxLayout()
        title_label = QLabel(APP_TITLE)
        title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        self._midi_row = IndicatorRow("MIDI signal")
        self._dragonframe_row = IndicatorRow("Dragonframe signal")
        title_row.addWidget(self._midi_row)
        title_row.addWidget(self._dragonframe_row)
        settings_button = QPushButton("⚙")
        settings_button.clicked.connect(self._on_settings_clicked)
        title_row.addWidget(settings_button)
        header.addLayout(title_row)

        controller_row = QHBoxLayout()
        controller_row.addWidget(QLabel("Controller"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems([choice.name for choice in self._controller_choices])
        self._profile_combo.setMaximumWidth(_CONTROLLER_COMBO_MAX_WIDTH)
        default_index = next(
            i for i, choice in enumerate(self._controller_choices) if isinstance(choice, StaticChoice) and choice.profile is self._default_profile
        )
        # setCurrentIndex() before connecting the signal, so selecting the default
        # profile (which may not be index 0 - the dropdown lists user-local profiles
        # first, @spec PROFILE-LOAD-004) doesn't itself fire a redundant initial
        # profile switch - the engine/adapter already start on self._default_profile
        # from their constructors.
        self._profile_combo.setCurrentIndex(default_index)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        controller_row.addWidget(self._profile_combo)
        # @spec UI-NAMEDCTRL-004: renames the active Named Controller's
        # display_name only - enabled whenever one is active, which is
        # always true after __init__ (the default profile's wrapper is
        # created there) and briefly false only while Grid is selected but
        # not yet settled.
        self._rename_button = QPushButton("✎")
        self._rename_button.setToolTip("Rename this controller configuration")
        self._rename_button.setMaximumWidth(28)
        self._rename_button.clicked.connect(self._on_rename_named_controller_clicked)
        controller_row.addWidget(self._rename_button)
        controller_row.addStretch(1)
        self._group_selector = GroupSelectorRow(self._mapping)  # @spec UI-GROUPSEL-001
        controller_row.addWidget(self._group_selector)
        header.addLayout(controller_row)

        load_failure_text = config_load_failure_label(len(self._load_result.failures))
        self._settings_dialog = SettingsDialog(self._config, load_failure_text)
        self._settings_dialog.set_profile_hint(self._default_profile.setup_hint)

        return header

    def _build_table_view_page(self) -> QWidget:
        """Table View's body page: the prior Mapping View, unchanged, plus a
        button opening the existing modal Configuration Dialog (also
        unchanged) - the per-control mapping summaries that used to live
        beside the Controller dropdown now live here instead, distinct from
        the network-settings Settings Dialog opened from the shared header.

        @spec UI-SHELL-003
        """
        page = QWidget()
        layout = QVBoxLayout(page)

        self._mapping_view = MappingView(
            self._mapping,
            self._axis_discovery,
            on_rescan=self._osc_listener.rescan,
            on_group_axis_changed=self._save_group_axis_targets,
        )
        layout.addWidget(self._mapping_view, 1)

        self._configuration_dialog = ConfigurationDialog(self._mapping)
        configuration_row = QHBoxLayout()
        configuration_row.addStretch(1)
        configuration_button = QPushButton("Configuration…")
        configuration_button.clicked.connect(self._on_configuration_clicked)
        configuration_row.addWidget(configuration_button)
        layout.addLayout(configuration_row)

        return page

    def _build_footer(self) -> QHBoxLayout:
        """@spec UI-SHELL-004: one shared toggle button switches `_body_stack`;
        its text names the page switching *to*, not the page currently shown."""
        footer = QHBoxLayout()
        self._dragonframe_footer_label = QLabel("")
        footer.addWidget(self._dragonframe_footer_label)
        footer.addStretch(1)
        self._view_toggle_button = QPushButton("Table View")
        self._view_toggle_button.clicked.connect(self._on_view_toggle_clicked)
        footer.addWidget(self._view_toggle_button)
        return footer

    def _on_view_toggle_clicked(self) -> None:
        """@spec UI-SHELL-004"""
        if self._body_stack.currentIndex() == 0:
            self._body_stack.setCurrentIndex(1)
            self._view_toggle_button.setText("Controller View")
        else:
            self._body_stack.setCurrentIndex(0)
            self._view_toggle_button.setText("Table View")

    def _on_settings_clicked(self) -> None:
        """@spec UI-SETTINGS-001: opened modally, same `exec()` pattern as the
        Configuration Dialog - the UI tick timer keeps running during it."""
        self._settings_dialog.exec()

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
        """Applies immediately, no Apply step (@spec UI-PROFILE-002). A static
        (YAML) profile installs right away, independent of whether a matching
        device has yet been found, then tells the MIDI Input Adapter to
        disconnect (if connected) and start matching the new pattern
        (@spec MIDI-PROFILE-005, MIDI-PROFILE-006).

        "Intech Grid" is a distinct selection, not a `ControllerProfile` -
        there is no static object to install yet. Selecting it only
        disconnects whatever device the previous controller had and starts a
        fresh CDC discovery/settle cycle; it becomes the active controller
        later, from `_on_tick()`, the instant its `GridRuntimeController`
        settles (@spec GRID-APP-002, GRID-APP-003).
        """
        choice = self._controller_choices[index]
        if isinstance(choice, GridChoice):
            self._grid_coordinator.select_grid()
            self._midi.disconnect()
            # Disabled until a Named Controller resolves for whatever settles
            # (`_resolve_and_install_grid_controller`) - the previously-active
            # controller's Named Controller is still referenced by
            # `self._active_named_controller` at this point, and renaming it
            # now would silently rename the wrong (outgoing) configuration.
            self._rename_button.setEnabled(False)
            return
        self._grid_coordinator.select_static()  # no-op unless Grid was active; closes its CDC connection if so
        # @spec NAMEDCTRL-STATIC-001: a transparent 1:1 wrapper - id == profile.name
        # always, so this never prompts and never changes the Preset Store key a
        # Korg installation already used before this feature existed.
        named_controller = ensure_static_named_controller(_named_controllers_dir(), choice.profile.name)
        self._install_active_controller(choice.profile, named_controller)

    def _install_active_controller(self, controller: ActiveController, named_controller: NamedController) -> None:
        """Shared by the static-profile switch path above and the Grid-ready
        transition in `_on_tick()`: installs `controller` as the active
        Mapping Engine/MIDI Input Adapter target, loads its persisted (Bank,
        Group) axis table under the resolved Named Controller's `id` - never
        `controller.name` directly as of Phase 1.3 (@spec GRID-MAP-003) - and
        rebuilds - not merely refreshes - the Mapping View and Configuration
        dialog for its actual structure (@spec MAP-STORE-002, MAP-STORE-007,
        UI-PROFILE-003, UI-CFGDLG-010, GRID-MAP-002).
        """
        self._active_named_controller = named_controller
        self._rename_button.setEnabled(True)
        self._mapping.set_profile(controller)
        # @spec MAP-STORE-002, MAP-STORE-007: loaded synchronously, in the same
        # call as set_profile() above and before the Mapping View rebuilds - no
        # caller can observe _group_axis_targets cleared-but-not-yet-reloaded.
        self._mapping.load_group_axis_targets(load_group_axis_targets(_configurations_dir(), named_controller.id, controller.bank_count))
        self._mapping.load_bank_control_actions(load_bank_actions(_configurations_dir(), named_controller.id, controller.bank_count))
        self._midi.set_profile(controller)
        # `setup_hint` is a `ControllerProfile`-only field, not part of the
        # `ActiveController` shape `GridRuntimeController` also satisfies -
        # absent there, so the hint label is simply hidden for Grid.
        setup_hint = getattr(controller, "setup_hint", None)
        self._settings_dialog.set_profile_hint(setup_hint)  # @spec UI-PROFILE-003
        self._mapping_view.rebuild()  # @spec GRID-MAP-002: structural rebuild, not refresh() - bank_count may differ
        self._configuration_dialog.rebuild_for_profile_change()  # @spec UI-CFGDLG-010
        self._controller_view.rebuild()  # @spec UI-CTRLVIEW-004

    def _resolve_and_install_grid_controller(self, ready_controller: GridRuntimeController) -> None:
        """@spec GRID-APP-003 (revised Phase 1.3), NAMEDCTRL-MATCH-001 through
        NAMEDCTRL-MATCH-004. Resolves a Named Controller for `ready_controller`'s
        settled `module_shape` before installing anything. `Activated` installs
        immediately with no prompt (the common case, same zero-friction feel as
        before this feature existed). `Ambiguous` shows a blocking dialog; the
        UI timer is stopped first, not because any output path is actually
        unsafe while it's open (a Grid-tagged key never matches whatever
        profile/controller is still installed, the same harmless no-op every
        other profile switch already relies on), but to avoid the `QTimer`
        re-entering `_on_tick()` - and this method - while the modal's own
        nested event loop is running, which every other `exec()` call in this
        file (Configuration/Settings dialogs) deliberately allows since their
        content is live-refreshed; this dialog's isn't, so there's nothing to
        lose by pausing it. Cancelling the dialog installs nothing - Grid
        stays selected but un-activated until the user reselects it from the
        dropdown (@spec GRID-APP-002), which always restarts discovery fresh.
        """
        outcome = resolve_grid_named_controller(_named_controllers_dir(), _configurations_dir(), ready_controller.module_shape)
        if isinstance(outcome, Activated):
            self._install_active_controller(ready_controller, outcome.controller)
            return

        assert isinstance(outcome, Ambiguous)
        # @spec NAMEDCTRL-AMBIG-001, UI-NAMEDCTRL-005: a one-time direct widget
        # update, not a status computed by the next `_on_tick()` (the timer is
        # about to stop) - distinct wording from the pre-existing Grid CDC
        # "multiple devices found" text (`_STATUS_TEXT[GridStatus.AMBIGUOUS]`,
        # grid_lifecycle.py), since the two are different kinds of ambiguity.
        self._midi_row.set_state(ChannelState.ERROR, "Intech Grid: multiple saved configurations match — choose one")
        self._ui_timer.stop()
        try:
            dialog = NamedControllerAmbiguousDialog(outcome.candidates, ready_controller.module_shape)
            dialog.exec()
            chosen = dialog.chosen_candidate()
        finally:
            self._ui_timer.start(UI_TICK_MS)

        if chosen is None:
            return  # @spec UI-NAMEDCTRL-003: no dismissal leaves Grid silently active
        if isinstance(chosen, str):
            chosen = create_grid_named_controller(_named_controllers_dir(), ready_controller.module_shape, chosen)
        self._install_active_controller(ready_controller, chosen)

    def _on_rename_named_controller_clicked(self) -> None:
        """@spec UI-NAMEDCTRL-004: renames only `display_name` - no
        reconnect, no Mapping View rebuild, no Preset Store write. Enabled
        only while a Named Controller is active (see `_build_header`)."""
        name, ok = QInputDialog.getText(self, "Rename controller", "Name:", text=self._active_named_controller.display_name)
        if not ok or not name.strip():
            return
        self._active_named_controller = rename_named_controller(_named_controllers_dir(), self._active_named_controller.id, name.strip())

    def _on_discovery_tick(self) -> None:
        """Skips the ordinary MIDI discovery poll while Grid is selected but
        not yet settled (@spec GRID-APP-004) - there is no profile pattern to
        match a port against yet, and polling would otherwise try to
        reconnect against whichever static profile was previously active."""
        if self._grid_coordinator.should_poll_midi_discovery():
            self._midi.poll_discovery()

    def _save_group_axis_targets(self) -> None:
        """@spec MAP-STORE-004, MAP-BTNACT-005: saves both the (Bank, Group) axis
        table and the per-Bank Rotary/Button action overrides together, always
        re-dumped fresh from the engine - the one callback both `ControllerView`'s
        axis-target edits and its Phase 1.2 Rotary/Button action edits invoke
        (`on_group_axis_changed`), so neither piece is ever written stale."""
        save_group_axis_targets(
            _configurations_dir(),
            self._active_named_controller.id,
            self._mapping.dump_group_axis_targets(),
            self._mapping.dump_bank_control_actions(),
        )

    def _on_config_applied(self, config: EndpointConfig, listen_port_changed: bool) -> None:
        self._osc_client.configure(config.host, config.dragonframe_port)
        self._osc_listener.update_dragonframe_target(config.host, config.dragonframe_port)
        if listen_port_changed:
            self._osc_listener.rebind(config.listen_port)

    def _on_tick(self) -> None:
        drain_queue(self._activity_queue, self._monitor.mark_activity)
        drain_queue(self._midi_queue, self._process_midi_event)
        self._axis_discovery.check_timeout()

        # @spec GRID-APP-003: a no-op unless Grid is the active selection; returns
        # the GridRuntimeController exactly once, on the tick it first settles.
        ready_controller = self._grid_coordinator.poll()
        if ready_controller is not None:
            self._resolve_and_install_grid_controller(ready_controller)

        self._mapping_view.refresh()
        self._configuration_dialog.refresh()
        self._controller_view.refresh()  # @spec UI-CTRLVIEW-002, UI-CTRLVIEW-008
        self._group_selector.sync()  # @spec UI-GROUPSEL-001

        # @spec GRID-APP-005: while Grid is selected, its own pending/stale/
        # unsupported/ambiguous text and error-dot state borrow the existing
        # MIDI indicator's free-text slot and error flag - no new widget.
        # Guarded by grid_active: MidiInputAdapter's own on_error callback
        # (Native Mode handshake failure) remains the error-flag's authority
        # whenever Grid isn't the active selection; only Grid ever touches it
        # while it is.
        if self._grid_coordinator.grid_active:
            self._monitor.set_error("midi", self._grid_coordinator.is_error())
        # @spec UI-NAMEDCTRL-001: `GridAppCoordinator.status_override()` is `None`
        # for GridStatus.ACTIVE specifically (grid_lifecycle.py's own `grid_status_
        # text()` deliberately leaves that case to the ordinary connected/waiting
        # logic) - this is where that gap is filled, in app.py rather than
        # grid_lifecycle.py, since Named Controller identity is a layer above Grid's
        # own lifecycle knowledge (docs/llds/named-controller.md). Korg's status text
        # is deliberately left untouched here - it still shows the real connected
        # device name, matching existing behavior; only Grid's bare "Intech Grid"/
        # raw-port-name text is replaced, since that's the one place a user actually
        # needs to tell two saved configurations apart.
        status_override = self._grid_coordinator.status_override()
        if status_override is None and self._grid_coordinator.grid_active and self._active_named_controller.kind == "grid":
            status_override = self._active_named_controller.display_name
        snapshot = compute_status_snapshot(
            self._monitor,
            midi_connected=self._midi_connected,
            midi_device_name=self._midi_device_name,
            listen_port=self._config.applied.listen_port,
            midi_profile_name=self._midi.profile.name,
            midi_status_override=status_override,
        )
        self._midi_row.set_state(snapshot.midi.state, snapshot.midi.label)
        self._dragonframe_row.set_state(snapshot.dragonframe.state, snapshot.dragonframe.label)
        self._dragonframe_footer_label.setText(f"Dragonframe: {snapshot.dragonframe.label}")  # @spec UI-SHELL-004

    def _process_midi_event(self, event: MidiEvent) -> None:
        # @spec GRID-MAP-001: the one Grid-specific branch in the MIDI dispatch
        # path, kept out of every output path below - pass-through unchanged
        # when Grid isn't active, dropped when pending/stale/unresolvable.
        event = self._grid_coordinator.route_event(event)
        if event is None:
            return
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
                self._grid_coordinator.select_static,  # closes Grid's CDC connection if it was active
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
