from __future__ import annotations

from dataclasses import dataclass

from .signal_monitor import ChannelState, SignalMonitor


@dataclass(frozen=True)
class IndicatorViewModel:
    state: ChannelState
    label: str


@dataclass(frozen=True)
class StatusSnapshot:
    midi: IndicatorViewModel
    dragonframe: IndicatorViewModel


def midi_indicator(state: ChannelState, connected: bool, device_name: str | None, profile_name: str) -> IndicatorViewModel:
    """`profile_name` is the currently-selected Controller Profile's display name
    (e.g. "nanoKONTROL Studio", "nanoKONTROL2"), used only for the not-yet-connected
    waiting text - once connected, the label always shows the actual device name.

    @spec UI-STATUS-002, UI-STATUS-004
    """
    label = device_name if connected and device_name else f"Waiting for {profile_name}…"
    return IndicatorViewModel(state=state, label=label)


def dragonframe_indicator(state: ChannelState, listen_port: int) -> IndicatorViewModel:
    """@spec UI-STATUS-003"""
    return IndicatorViewModel(state=state, label=f"127.0.0.1:{listen_port} (listen)")


def show_setup_hint(setup_hint: str | None) -> bool:
    """Whether the Controller Profile dropdown's one-line setup hint
    (docs/llds/app-ui.md § Status UI) should be visible, given the active profile's
    `setup_hint` field. Generalizes the prior nanoKONTROL2-only name check - any
    profile with non-empty `setup_hint` shows its own hint text verbatim.

    @spec UI-PROFILE-003
    """
    return bool(setup_hint)


def config_load_failure_label(failure_count: int) -> str | None:
    """Count-only Status UI indicator for Controller Profile config files that
    failed to load (`PROFILE-LOAD-011`, see docs/specs/midi-input.md) - deliberately
    not a log viewer or per-file detail, per the HLD's "no log pane" Non-Goal.

    @spec UI-PROFILE-004
    """
    if failure_count <= 0:
        return None
    noun = "file" if failure_count == 1 else "files"
    return f"{failure_count} controller config {noun} failed to load"


def compute_status_snapshot(
    monitor: SignalMonitor,
    midi_connected: bool,
    midi_device_name: str | None,
    listen_port: int,
    midi_profile_name: str,
) -> StatusSnapshot:
    """Reads each channel's Signal Monitor state exactly once per call.

    @spec UI-STATUS-001
    """
    midi_state = monitor.state("midi")
    dragonframe_state = monitor.state("dragonframe")
    return StatusSnapshot(
        midi=midi_indicator(midi_state, midi_connected, midi_device_name, midi_profile_name),
        dragonframe=dragonframe_indicator(dragonframe_state, listen_port),
    )
