"""Integration tests for the MIDI Input Monitor's wiring into `app.py`'s real
MIDI dispatch path (docs/llds/midi-monitor.md), mirroring
`test_app_named_controller_wiring.py`'s approach: a real `DragonMidiWindow`
with its persistence directories redirected to a temp path, driving
`_process_midi_event` directly rather than through a real MIDI port.

Where the task asks to test against the real controller profiles and Grid
runtime rather than mocks alone, this file installs an actual
`GridRuntimeController` built by `build_grid_controller()` from a real
`GridTopology` - the same seam `test_app_named_controller_wiring.py` already
uses - rather than a fake/stub controller.

@spec MON-CAPTURE-001 through MON-CAPTURE-006, MON-CAPTURE-008
@spec MON-DIAG-001 through MON-DIAG-009
@spec MON-GUIDE-001 through MON-GUIDE-013

Note on scope: MON-CAPTURE-007 ("no second MIDI backend connection, Grid
topology link, or MIDI router") is exercised structurally by inspection -
`midi_monitor.py`/`midi_monitor_widgets.py` construct no `MidiBackend`,
`GridLifecycle`, or router of their own, and every test below drives events
through the app's one existing `MidiInputAdapter`/`GridAppCoordinator` - not
by an automated assertion, matching `test_websocket_output.py`'s identical
treatment of its own structural, no-new-resource specs.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import dragonmidi.app as appmod  # noqa: E402
from dragonmidi.events import MidiEvent, WebSocketCommand  # noqa: E402
from dragonmidi.grid_controller import Ready, build_grid_controller  # noqa: E402
from dragonmidi.grid_modules import ModuleType  # noqa: E402
from dragonmidi.grid_topology import GridModule, GridTopology  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _FakePynputBackend:
    """Matches `test_app_named_controller_wiring.py`'s own fixture - the real
    backend refuses to initialize on a headless CI runner."""

    def press(self, key: str) -> None:
        pass

    def release(self, key: str) -> None:
        pass


@pytest.fixture
def window(tmp_path, monkeypatch):
    _qapp()
    monkeypatch.setattr(appmod, "_user_controllers_dir", lambda: tmp_path / "controllers")
    monkeypatch.setattr(appmod, "_configurations_dir", lambda: tmp_path / "configurations")
    monkeypatch.setattr(appmod, "_named_controllers_dir", lambda: tmp_path / "named_controllers")
    monkeypatch.setattr(appmod, "_capture_sessions_dir", lambda: tmp_path / "capture_sessions")
    monkeypatch.setattr(appmod, "PynputBackend", _FakePynputBackend)
    win = appmod.DragonMidiWindow()
    yield win


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


def _fader_cc_event(number: int, raw_value: int = 80, channel: int = 0) -> MidiEvent:
    return MidiEvent(type="cc", channel=channel, number=number, raw_value=raw_value, normalized=raw_value / 127, is_press=False, is_release=False)


def _install_real_grid_controller(window, *modules: GridModule):
    outcome = build_grid_controller(GridTopology(modules=tuple(modules), current_page=0))
    assert isinstance(outcome, Ready)
    controller = outcome.controller
    window._resolve_and_install_grid_controller(controller)
    window._grid_coordinator.grid_active = True
    # The real settle path (GridLifecycle.poll()) is what normally stores
    # the settled controller here; this test harness bypasses that path
    # entirely (as test_app_named_controller_wiring.py's own fixtures already
    # do), so it must be set directly for route_event()'s internal lookup
    # (self._grid_lifecycle.controller) to see this controller at all.
    window._grid_coordinator.lifecycle._controller = controller
    return controller


# --- Recording happens regardless of diagnostic mode (MON-CAPTURE-002) ---


def test_every_event_is_recorded_whether_or_not_diagnostic_mode_is_on(window) -> None:
    window._midi.profile  # sanity: default Korg profile is active
    event = _fader_cc_event(0)

    window._process_midi_event(event)
    assert len(window._midi_monitor.events) == 1

    window._midi_monitor.diagnostic_active = True
    window._process_midi_event(event)
    assert len(window._midi_monitor.events) == 2


# --- Diagnostic mode suppresses every output path (MON-DIAG-002) ---


def test_diagnostic_mode_suppresses_osc_output_for_a_fader_event(window, monkeypatch) -> None:
    channel = window._default_profile.default_channel
    sent = []
    monkeypatch.setattr(window._osc_client, "send", lambda *a, **k: sent.append(a))
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._midi_monitor.diagnostic_active = True

    window._process_midi_event(_fader_cc_event(0, channel=channel))

    assert sent == []


def test_diagnostic_mode_off_dispatches_exactly_as_before(window, monkeypatch) -> None:
    """Regression guard: with diagnostic mode off, behavior is unchanged from
    before this feature existed."""
    channel = window._default_profile.default_channel
    sent = []
    monkeypatch.setattr(window._osc_client, "send", lambda *a, **k: sent.append(a))
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)

    window._process_midi_event(_fader_cc_event(0, raw_value=64, channel=channel))

    assert len(sent) == 1
    assert sent[0][0] == "/dragonframe/axis/PAN/gotoPosition"


def test_diagnostic_mode_suppresses_websocket_output(window, monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(window._websocket_output, "send", lambda cmd: sent.append(cmd))
    window._midi_monitor.diagnostic_active = True

    # Solo always sends a WebSocket select-AXn command, unconditional on
    # Bank/axis state (MAP-WS-002) - a convenient always-on WebSocket target.
    profile = window._mapping.profile
    solo_key = profile.websocket_keys.solos[0]
    event = MidiEvent(
        type=solo_key[0], channel=profile.default_channel, number=solo_key[1], raw_value=127, normalized=1.0, is_press=True, is_release=False
    )

    window._process_midi_event(event)

    assert sent == []


# --- Opening the Monitor dialog sends E-Stop and suppresses dispatch end-to-end (MON-DIAG-004) ---


def test_opening_the_monitor_dialog_sends_e_stop_and_then_suppresses_dispatch(window, monkeypatch) -> None:
    channel = window._default_profile.default_channel
    ws_sent = []
    osc_sent = []
    monkeypatch.setattr(window._websocket_output, "send", lambda cmd: ws_sent.append(cmd))
    monkeypatch.setattr(window._osc_client, "send", lambda *a, **k: osc_sent.append(a))
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)

    window._midi_monitor_dialog.show()  # showEvent() -> diagnostic on + E-Stop, matching .exec()

    assert ws_sent == [WebSocketCommand("E-Stop")]

    window._process_midi_event(_fader_cc_event(0, channel=channel))
    assert osc_sent == []  # the fader's gotoPosition never fires while diagnostic mode is on

    window._midi_monitor_dialog.close()
    window._process_midi_event(_fader_cc_event(0, channel=channel))
    assert len(osc_sent) == 1  # normal processing resumed after closing


# --- Raw identity is preserved even when Grid resolves the event (real Grid runtime) ---


def test_raw_cc_is_preserved_alongside_the_resolved_grid_identity(window) -> None:
    _install_real_grid_controller(window, _pbf4(0))
    # Fader element index 4 at x=0 -> cc number (32+0*16+4)%128 = 36 (matches
    # test_grid_resolution.py's own derivation).
    raw_number = 36

    window._process_midi_event(_fader_cc_event(raw_number, raw_value=77))

    recorded = window._midi_monitor.events[-1]
    assert recorded.raw.number == raw_number  # the wire-level CC, never overwritten
    assert recorded.raw.raw_value == 77
    assert recorded.resolved == ("grid_fader", 1)
    assert recorded.module is not None
    assert recorded.module.module_type == "PBF4"


def test_unresolved_grid_event_shows_no_module_or_resolved_identity(window) -> None:
    _install_real_grid_controller(window, _pbf4(0))

    window._process_midi_event(_fader_cc_event(99))  # not any recognized element's address

    recorded = window._midi_monitor.events[-1]
    assert recorded.resolved is None
    assert recorded.module is None


def test_non_grid_controller_never_populates_resolved_or_module(window) -> None:
    """A Korg profile has no Grid-style resolution layer at all - resolved/
    module stay None by construction, not because nothing matched."""
    window._process_midi_event(_fader_cc_event(0))
    recorded = window._midi_monitor.events[-1]
    assert recorded.resolved is None
    assert recorded.module is None


def test_switching_from_grid_to_korg_mid_session_does_not_retroactively_change_earlier_rows(window) -> None:
    _install_real_grid_controller(window, _pbf4(0))
    window._process_midi_event(_fader_cc_event(36, raw_value=50))
    grid_row = window._midi_monitor.events[-1]
    assert grid_row.module is not None

    window._grid_coordinator.grid_active = False
    window._midi.set_profile(window._default_profile)
    window._mapping.set_profile(window._default_profile)
    window._process_midi_event(_fader_cc_event(0, raw_value=50))

    assert window._midi_monitor.events[0] is grid_row  # unchanged
    assert window._midi_monitor.events[-1].resolved is None  # the new, post-switch row


# --- Device/port is read from the one currently connected device (MON-CAPTURE-003) ---


def test_device_name_reflects_the_currently_tracked_midi_device(window) -> None:
    window._midi_device_name = "nanoKONTROL2 SOUND"
    window._process_midi_event(_fader_cc_event(0))
    assert window._midi_monitor.events[-1].device_name == "nanoKONTROL2 SOUND"


# --- Existing behavior is unaffected by this feature (compatibility) ---


def test_grid_dropped_unresolved_events_are_still_dropped_when_diagnostic_is_off(window, monkeypatch) -> None:
    """Matches the pre-existing GRID-MAP-001 behavior exactly - an event Grid
    can't resolve still produces no output, with or without this feature."""
    sent = []
    monkeypatch.setattr(window._osc_client, "send", lambda *a, **k: sent.append(a))
    _install_real_grid_controller(window, _pbf4(0))

    window._process_midi_event(_fader_cc_event(99))

    assert sent == []


# --- Guided Capture, end-to-end against the real nanoKONTROL Studio profile ---
# @spec MON-GUIDE-001 through MON-GUIDE-013


def test_guided_capture_end_to_end_against_the_real_nanokontrol2_profile_and_saves_a_report(window, tmp_path) -> None:
    """Drives the exact path a real user follows: open the Monitor, switch
    to nanoKONTROL2 (a real ControllerProfile loaded from the bundled YAML,
    not a fake - still has genuinely unconfirmed controls, unlike the
    Studio, whose Record/Select/Set Marker/Return to Zero were confirmed via
    Guided Capture itself in Phase 1.6.1), start Guided Capture, send
    real-shaped raw MIDI for the first two steps, confirm one and skip one,
    then save and read back the written JSON."""
    nk2_index = next(i for i, c in enumerate(window._controller_choices) if c.name == "nanoKONTROL2")
    window._profile_combo.setCurrentIndex(nk2_index)
    channel = window._mapping.profile.default_channel
    dialog = window._midi_monitor_dialog
    dialog.show()  # diagnostic mode on, same as a real Settings-launched open

    dialog._on_guided_start_clicked()
    assert dialog._guided_session is not None
    assert dialog._guided_session.current_step.label == "Record 1"
    assert dialog._guided_session.total_steps == 9  # 8 Record + Set Marker
    assert dialog._guided_confirm_button.isEnabled() is False  # nothing pending yet
    assert dialog._diagnostic_checkbox.isEnabled() is False  # @spec MON-GUIDE-009

    # "Press Record 1" - any raw CC on this channel flows through the real
    # dispatch path (_process_midi_event), gets recorded, and - because
    # diagnostic mode is on - reaches the session via MidiMonitor.on_record.
    window._process_midi_event(_fader_cc_event(34, raw_value=127, channel=channel))
    assert dialog._guided_session.pending is not None
    dialog.refresh()  # the next UI tick - button enablement is refresh-driven, not synchronous
    assert dialog._guided_confirm_button.isEnabled() is True

    dialog._on_guided_confirm_clicked()
    assert dialog._guided_session.current_step.label == "Record 2"

    dialog._on_guided_skip_clicked()
    assert dialog._guided_session.current_step.label == "Record 3"

    # Skip through the remaining 7 steps (Record 3-8, Set Marker) to reach Save Session.
    for _ in range(7):
        dialog._on_guided_skip_clicked()
    assert dialog._guided_session.finished is True
    assert dialog._guided_save_button.isEnabled() is True

    dialog._on_guided_save_clicked()

    assert dialog._guided_session is None  # session ended after Save
    assert dialog._diagnostic_checkbox.isEnabled() is True  # re-enabled

    saved_files = list((tmp_path / "capture_sessions").glob("nanoKONTROL2-*.json"))
    assert len(saved_files) == 1
    report = json.loads(saved_files[0].read_text())
    assert report["profile_name"] == "nanoKONTROL2"
    assert len(report["results"]) == 9  # 8 Record + Set Marker
    assert report["results"][0] == {
        "label": "Record 1",
        "skipped": False,
        "raw": {"type": "cc", "channel": channel, "number": 34, "raw_value": 127},
        "device_name": None,
    }
    assert report["results"][1]["skipped"] is True


def test_guided_capture_cancel_discards_without_writing_a_file(window, tmp_path) -> None:
    """@spec MON-GUIDE-011"""
    dialog = window._midi_monitor_dialog
    dialog.show()
    dialog._on_guided_start_clicked()
    window._process_midi_event(_fader_cc_event(34, channel=window._default_profile.default_channel))

    dialog._on_guided_cancel_clicked()

    assert dialog._guided_session is None
    assert dialog._diagnostic_checkbox.isEnabled() is True
    assert not (tmp_path / "capture_sessions").exists()


def test_guided_capture_disabled_for_a_controller_with_no_unconfirmed_controls(window) -> None:
    """A profile whose unconfirmed_channel_controls/unconfirmed_global_controls
    are both empty (hypothetically fully confirmed) must disable Start with
    an explanatory label, never open an empty session."""
    from dataclasses import replace

    fully_confirmed = replace(window._default_profile, unconfirmed_channel_controls=(), unconfirmed_global_controls=())
    window._mapping.set_profile(fully_confirmed)
    dialog = window._midi_monitor_dialog
    dialog.show()

    dialog._update_guided_ui()  # re-derive from the now-different active controller

    assert dialog._guided_start_button.isEnabled() is False
    assert "No unconfirmed controls" in dialog._guided_status_label.text()
