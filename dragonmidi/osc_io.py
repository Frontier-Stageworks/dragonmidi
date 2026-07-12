from __future__ import annotations

import socket
import struct
import threading
from typing import Any, Callable

# @spec OSC-CONFIG-001
DEFAULT_DRAGONFRAME_HOST = "127.0.0.1"
DEFAULT_DRAGONFRAME_PORT = 7010
DEFAULT_LISTEN_PORT = 7011


def _pad4(data: bytes) -> bytes:
    return data + b"\x00" * ((-len(data)) % 4)


def _osc_string(value: str) -> bytes:
    return _pad4(value.encode("utf-8") + b"\x00")


def encode_osc_message(address: str, *args: Any) -> bytes:
    """Encode one OSC 1.0 message.

    @spec OSC-CLIENT-001
    """
    if not address.startswith("/"):
        raise ValueError("OSC address must start with '/'")

    tags = [","]
    payload = bytearray()
    for value in args:
        if isinstance(value, bool):
            tags.append("T" if value else "F")
        elif isinstance(value, int):
            tags.append("i")
            payload += struct.pack(">i", value)
        elif isinstance(value, float):
            tags.append("f")
            payload += struct.pack(">f", value)
        elif isinstance(value, str):
            tags.append("s")
            payload += _osc_string(value)
        else:
            raise TypeError(f"unsupported OSC argument type: {type(value).__name__}")

    return _osc_string(address) + _osc_string("".join(tags)) + bytes(payload)


def validate_ports(dragonframe_port: int, listen_port: int) -> None:
    """@spec OSC-CONFIG-002"""
    if dragonframe_port == listen_port:
        raise ValueError("Dragonframe port and local listen port must differ")


class OscClient:
    """@spec OSC-CLIENT-001, OSC-CLIENT-002"""

    def __init__(
        self,
        host: str = DEFAULT_DRAGONFRAME_HOST,
        port: int = DEFAULT_DRAGONFRAME_PORT,
        sock: Any | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._socket = sock if sock is not None else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._on_error = on_error

    def configure(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def send(self, address: str, *args: Any) -> None:
        packet = encode_osc_message(address, *args)
        try:
            self._socket.sendto(packet, (self.host, self.port))
        except OSError as exc:
            if self._on_error is not None:
                self._on_error(exc)

    def close(self) -> None:
        self._socket.close()


class OscListener:
    """Binds a local UDP port and reports any incoming datagram as liveness signal.

    @spec OSC-LISTEN-001, OSC-LISTEN-002, OSC-LISTEN-003, OSC-LISTEN-005, OSC-LISTEN-006
    """

    def __init__(
        self,
        port: int,
        on_activity: Callable[[], None],
        on_bind_result: Callable[[bool], None] | None = None,
    ) -> None:
        self.port = port
        self._on_activity = on_activity
        self._on_bind_result = on_bind_result
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("0.0.0.0", self.port))
        except OSError:
            if self._on_bind_result is not None:
                self._on_bind_result(False)
            return

        self._socket = sock
        self._running = True
        if self._on_bind_result is not None:
            self._on_bind_result(True)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            try:
                assert self._socket is not None
                self._socket.recvfrom(65536)
            except OSError:
                break
            self._on_activity()

    def rebind(self, new_port: int) -> None:
        self.stop()
        self.port = new_port
        self.start()

    def stop(self) -> None:
        self._running = False
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
