from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Any, Callable, Protocol

# @spec OSC-CONFIG-001
DEFAULT_DRAGONFRAME_HOST = "127.0.0.1"
DEFAULT_DRAGONFRAME_PORT = 7010
DEFAULT_LISTEN_PORT = 7011
DISCOVERY_TIMEOUT_SECONDS = 2.0
AXIS_ADDRESS_PREFIX = "/dragonframe/axis/"
GET_ALL_POSITION_ADDRESS = "/dragonframe/axis/getAllPosition"


class UdpSocket(Protocol):
    """The subset of `socket.socket`'s interface `OscClient`/`OscListener` depend
    on - lets tests inject a fake instead of a real OS socket, matching the
    `MidiBackend`/`KeystrokeBackend` pattern used elsewhere in this app.

    @spec OSC-BACKEND-001
    """

    def bind(self, address: tuple[str, int]) -> None: ...
    def settimeout(self, value: "float | None") -> None: ...
    def sendto(self, data: bytes, address: tuple[str, int]) -> int: ...
    def recvfrom(self, bufsize: int) -> tuple[bytes, Any]: ...
    def close(self) -> None: ...


def _real_udp_socket() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


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


def _read_padded_string(buf: bytes, offset: int) -> tuple[str, int]:
    end = buf.index(b"\x00", offset)
    raw = buf[offset:end]
    total_len = end - offset + 1
    padded_len = total_len + ((-total_len) % 4)
    return raw.decode("utf-8", errors="replace"), offset + padded_len


def decode_osc_message(data: bytes) -> tuple[str, tuple]:
    """Decode a single (non-bundle) OSC 1.0 message."""
    address, offset = _read_padded_string(data, 0)
    type_tags, offset = _read_padded_string(data, offset)
    args: list = []
    for tag in type_tags[1:]:
        if tag == "i":
            (value,) = struct.unpack_from(">i", data, offset)
            args.append(value)
            offset += 4
        elif tag == "f":
            (value,) = struct.unpack_from(">f", data, offset)
            args.append(value)
            offset += 4
        elif tag == "s":
            value, offset = _read_padded_string(data, offset)
            args.append(value)
        else:
            raise ValueError(f"unsupported OSC type tag: {tag!r}")
    return address, tuple(args)


def decode_osc_packet(data: bytes) -> list[tuple[str, tuple]]:
    """Decode a top-level OSC packet, which may be a single message or a
    #bundle wrapping multiple (possibly nested) messages. Always returns a
    flat list of (address, args) tuples.

    No recursion-depth or size-consistency bound is imposed - Dragonframe is
    a trusted local peer, not untrusted input.

    @spec OSC-DISCOVER-004
    """
    if data.startswith(b"#bundle\x00"):
        offset = 8  # "#bundle\0" is exactly 8 bytes, no padding needed
        offset += 8  # 8-byte OSC time tag, ignored here
        messages: list[tuple[str, tuple]] = []
        while offset < len(data):
            (element_size,) = struct.unpack_from(">i", data, offset)
            offset += 4
            element = data[offset : offset + element_size]
            offset += element_size
            messages.extend(decode_osc_packet(element))
        return messages
    return [decode_osc_message(data)]


class AxisDiscovery:
    """Tracks Dragonframe axis names discovered via getAllPosition responses.

    @spec OSC-DISCOVER-005, OSC-DISCOVER-006, OSC-DISCOVER-007, OSC-DISCOVER-008
    """

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = DISCOVERY_TIMEOUT_SECONDS,
    ) -> None:
        self._clock = clock
        self._timeout = timeout
        self._axes: dict[str, float] | None = None
        self._query_sent_at: float | None = None

    @property
    def axes(self) -> dict[str, float] | None:
        return self._axes

    def mark_query_sent(self) -> None:
        self._query_sent_at = self._clock()

    def handle_datagram(self, data: bytes) -> None:
        try:
            messages = decode_osc_packet(data)
        except Exception:
            return  # malformed/truncated framing is tolerated, not raised
        for address, args in messages:
            if address == GET_ALL_POSITION_ADDRESS:
                continue  # the query's own echo, not an axis response
            if address.startswith(AXIS_ADDRESS_PREFIX):
                axis_name = address[len(AXIS_ADDRESS_PREFIX) :]
                if self._axes is None:
                    self._axes = {}
                self._axes[axis_name] = args[0] if args else None

    def check_timeout(self) -> None:
        if self._axes is not None or self._query_sent_at is None:
            return
        if (self._clock() - self._query_sent_at) >= self._timeout:
            self._axes = {}


class OscClient:
    """@spec OSC-CLIENT-001, OSC-CLIENT-002, OSC-BACKEND-001"""

    def __init__(
        self,
        host: str = DEFAULT_DRAGONFRAME_HOST,
        port: int = DEFAULT_DRAGONFRAME_PORT,
        sock: "UdpSocket | None" = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._socket: UdpSocket = sock if sock is not None else _real_udp_socket()
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

    Optionally performs axis discovery: sending getAllPosition from this same
    socket (not a separate one) whenever it successfully binds, and routing
    every received datagram through the given AxisDiscovery.

    @spec OSC-LISTEN-001, OSC-LISTEN-002, OSC-LISTEN-003, OSC-LISTEN-005, OSC-LISTEN-006
    @spec OSC-LISTEN-007, OSC-BACKEND-001
    @spec OSC-DISCOVER-001, OSC-DISCOVER-002, OSC-DISCOVER-003, OSC-DISCOVER-009
    """

    def __init__(
        self,
        port: int,
        on_activity: Callable[[], None],
        on_bind_result: Callable[[bool], None] | None = None,
        axis_discovery: "AxisDiscovery | None" = None,
        dragonframe_host: str | None = None,
        dragonframe_port: int | None = None,
        socket_factory: Callable[[], UdpSocket] = _real_udp_socket,
    ) -> None:
        self.port = port
        self._on_activity = on_activity
        self._on_bind_result = on_bind_result
        self._axis_discovery = axis_discovery
        self._dragonframe_host = dragonframe_host
        self._dragonframe_port = dragonframe_port
        self._socket_factory = socket_factory
        self._socket: "UdpSocket | None" = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        try:
            sock = self._socket_factory()
            sock.bind(("0.0.0.0", self.port))
            # A bounded timeout, not an indefinite block, so `_run()` re-checks
            # `self._running` on a steady cadence instead of depending solely on
            # `stop()`'s `socket.close()` to unblock a concurrent `recvfrom()` -
            # closing a socket from another thread while a blocking recv is in
            # flight isn't reliably prompt cross-platform (observed: fine on
            # macOS, but on Linux CI the old thread could outlive `stop()`'s
            # `join()` and still process one more in-flight datagram on the
            # port `rebind()` was meant to have already vacated).
            sock.settimeout(0.5)
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
        self._send_discovery_query()

    def rescan(self) -> None:
        """Explicit, user-triggered re-query, independent of the automatic one.

        @spec OSC-DISCOVER-003
        """
        self._send_discovery_query()

    def update_dragonframe_target(self, host: str, port: int) -> None:
        """Update the Dragonframe host/port the discovery query is sent to, and
        immediately re-query against the new target. Without this, a Dragonframe
        host/port change applied via the Status UI would leave discovery silently
        querying the old target indefinitely.

        @spec OSC-DISCOVER-009
        """
        self._dragonframe_host = host
        self._dragonframe_port = port
        self._send_discovery_query()

    def _send_discovery_query(self) -> None:
        if self._axis_discovery is None or self._socket is None or self._dragonframe_host is None:
            return
        packet = encode_osc_message(GET_ALL_POSITION_ADDRESS)
        self._socket.sendto(packet, (self._dragonframe_host, self._dragonframe_port))
        self._axis_discovery.mark_query_sent()

    def _run(self) -> None:
        while self._running:
            try:
                assert self._socket is not None
                data, _addr = self._socket.recvfrom(65536)
            except TimeoutError:
                continue  # just a poll interval, not a real error - re-check self._running
            except OSError:
                break
            if not self._running:
                break  # stop() ran while this recvfrom() was already in flight - drop it
            self._on_activity()
            if self._axis_discovery is not None:
                self._axis_discovery.handle_datagram(data)

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
