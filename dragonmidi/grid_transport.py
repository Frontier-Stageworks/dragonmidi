"""Grid CDC transport (docs/llds/intech-grid.md § Grid CDC Transport).

`SerialGridTransport`'s actual port-opening/background-reading behavior
requires `pyserial` and a real (or OS-level virtual) serial port - it is not
exercised by the automated test suite, which drives `GridLifecycle`
(`grid_lifecycle.py`) through the `GridTransport` Protocol via a fake instead.
See the completion report's "remaining hardware-validation items".

VID/PID pairs are source-confirmed (Intech Studio `grid-editor`'s own
`configuration.json`, GPL-3.0-only) - the same allowlist Grid Editor itself
uses to find the device via the Web Serial API.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

BAUD_RATE = 2_000_000

# (VID, PID) pairs - source: grid-editor/configuration.json.
GRID_VID_PID_PAIRS: tuple[tuple[int, int], ...] = (
    (0x03EB, 0xECAC),
    (0x303A, 0x8123),
    (0x2E8A, 0x1145),
)

# A secondary, corroborating signal only; VID/PID is the primary filter and
# is never substituted by this. Corrected against real hardware (2026-11-04):
# a real Grid's CDC port description/product string is simply "Grid" (the
# device's bare USB product string, confirmed via pyserial's list_ports), not
# the "Intech Grid CDC" per-interface descriptor string source research had
# assumed - that assumed string never actually mattered functionally (VID/PID
# already succeeded without it), but "grid" at least gives this corroboration
# a chance to actually corroborate.
GRID_CDC_MATCH_SUBSTRING = "grid"


class GridConnection(Protocol):
    def close(self) -> None: ...


class GridTransport(Protocol):
    """Parallel to `midi_input.py`'s `MidiBackend` - a second transport for
    Grid's topology channel, independent of the ordinary MIDI backend."""

    def list_candidate_ports(self) -> list[tuple[str, int, int]]:
        """Returns `(port_name, vid, pid)` for every serial port whose
        VID/PID matches `GRID_VID_PID_PAIRS` - callers filter/disambiguate
        further (name corroboration, the ambiguous-chains rule) themselves."""
        ...

    def open(self, port_name: str, callback: Callable[[bytes], None]) -> GridConnection:
        """`callback` is invoked with raw byte chunks as they arrive, on
        whatever thread the real implementation reads on - mirroring
        `MidiBackend.open_input()`'s per-message callback shape."""
        ...


def is_candidate_cdc_port(vid: int, pid: int) -> bool:
    """VID/PID is the required, primary signal - a port's OS-surfaced name
    (checked separately by callers against `GRID_CDC_MATCH_SUBSTRING` via
    `name_matching.fuzzy_contains`, if they want the secondary corroborating
    signal) is never sufficient by itself, and its absence never disqualifies
    an otherwise-matching VID/PID (not every platform surfaces the interface
    string in the port name)."""
    return (vid, pid) in GRID_VID_PID_PAIRS


class SerialGridTransport:
    """The real implementation, backed by `pyserial`. Not exercised by the
    automated test suite (see module docstring)."""

    def list_candidate_ports(self) -> list[tuple[str, int, int]]:
        import serial.tools.list_ports  # imported lazily - pyserial is only needed when this real backend is used

        candidates = []
        for port_info in serial.tools.list_ports.comports():
            if port_info.vid is None or port_info.pid is None:
                continue
            if is_candidate_cdc_port(port_info.vid, port_info.pid):
                candidates.append((port_info.device, port_info.vid, port_info.pid))
        return candidates

    def open(self, port_name: str, callback: Callable[[bytes], None]) -> "_SerialGridConnection":
        import serial

        ser = serial.Serial(port_name, baudrate=BAUD_RATE, timeout=0.1)
        return _SerialGridConnection(ser, callback)


class _SerialGridConnection:
    def __init__(self, serial_port, callback: Callable[[bytes], None]) -> None:
        self._port = serial_port
        self._callback = callback
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                chunk = self._port.read(4096)
            except Exception:
                break
            if chunk:
                self._callback(chunk)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._port.close()


__all__ = [
    "BAUD_RATE",
    "GRID_VID_PID_PAIRS",
    "GRID_CDC_MATCH_SUBSTRING",
    "GridConnection",
    "GridTransport",
    "SerialGridTransport",
    "is_candidate_cdc_port",
]
