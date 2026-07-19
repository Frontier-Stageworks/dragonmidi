from __future__ import annotations

from dataclasses import dataclass

from .signal_monitor import ChannelState, SignalMonitor

_WAITING_LABEL = "Waiting for nanoKONTROL Studio…"


@dataclass(frozen=True)
class IndicatorViewModel:
    state: ChannelState
    label: str


@dataclass(frozen=True)
class StatusSnapshot:
    midi: IndicatorViewModel
    dragonframe: IndicatorViewModel


def midi_indicator(state: ChannelState, connected: bool, device_name: str | None) -> IndicatorViewModel:
    """@spec UI-STATUS-002, UI-STATUS-004"""
    label = device_name if connected and device_name else _WAITING_LABEL
    return IndicatorViewModel(state=state, label=label)


def dragonframe_indicator(state: ChannelState, listen_port: int) -> IndicatorViewModel:
    """@spec UI-STATUS-003"""
    return IndicatorViewModel(state=state, label=f"127.0.0.1:{listen_port} (listen)")


def compute_status_snapshot(
    monitor: SignalMonitor,
    midi_connected: bool,
    midi_device_name: str | None,
    listen_port: int,
) -> StatusSnapshot:
    """Reads each channel's Signal Monitor state exactly once per call.

    @spec UI-STATUS-001
    """
    midi_state = monitor.state("midi")
    dragonframe_state = monitor.state("dragonframe")
    return StatusSnapshot(
        midi=midi_indicator(midi_state, midi_connected, midi_device_name),
        dragonframe=dragonframe_indicator(dragonframe_state, listen_port),
    )
