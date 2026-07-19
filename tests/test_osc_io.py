"""Tests for the OSC Transport (docs/specs/osc-io.md).

@spec OSC-CLIENT-001, OSC-CLIENT-002
@spec OSC-LISTEN-001, OSC-LISTEN-002, OSC-LISTEN-003, OSC-LISTEN-005, OSC-LISTEN-006
@spec OSC-CONFIG-001, OSC-CONFIG-002
@spec OSC-DISCOVER-001, OSC-DISCOVER-002, OSC-DISCOVER-003, OSC-DISCOVER-004
@spec OSC-DISCOVER-005, OSC-DISCOVER-006, OSC-DISCOVER-007, OSC-DISCOVER-008
"""
from __future__ import annotations

import socket
import struct
import threading
import time

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.osc_io import (
    DEFAULT_DRAGONFRAME_HOST,
    DEFAULT_DRAGONFRAME_PORT,
    DEFAULT_LISTEN_PORT,
    AxisDiscovery,
    OscClient,
    OscListener,
    decode_osc_packet,
    encode_osc_message,
    validate_ports,
)
from tests.support import FakeClock

ADDRESS_ALPHABET = st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters="\x00")
address_strategy = st.text(alphabet=ADDRESS_ALPHABET, min_size=0, max_size=24).map(lambda s: "/" + s)
string_arg_strategy = st.text(alphabet=ADDRESS_ALPHABET, min_size=0, max_size=16)
int_arg_strategy = st.integers(min_value=-(2**31), max_value=2**31 - 1)
float_arg_strategy = st.floats(width=32, allow_nan=False, allow_infinity=False)
arg_strategy = st.one_of(int_arg_strategy, float_arg_strategy, string_arg_strategy)


def _decode_osc_message(data: bytes) -> tuple[str, tuple]:
    """Independent, test-only OSC 1.0 decoder used to cross-check the encoder.

    Deliberately not implemented in terms of the encoder's own internals, so a
    round-trip test here proves the wire format is actually correct, not just
    self-consistent.
    """

    def read_padded_string(buf: bytes, offset: int) -> tuple[str, int]:
        end = buf.index(b"\x00", offset)
        raw = buf[offset:end]
        total_len = end - offset + 1
        padded_len = total_len + ((-total_len) % 4)
        return raw.decode("utf-8"), offset + padded_len

    address, offset = read_padded_string(data, 0)
    type_tags, offset = read_padded_string(data, offset)
    assert type_tags.startswith(",")
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
            value, offset = read_padded_string(data, offset)
            args.append(value)
        else:
            raise AssertionError(f"unhandled type tag {tag!r} in test decoder")
    return address, tuple(args)


# --- OSC-CLIENT-001: encoding, verified via an independent round-trip decoder ---

# @spec OSC-CLIENT-001
@given(address=address_strategy, args=st.lists(arg_strategy, max_size=5))
def test_encode_round_trips_through_independent_decoder(address: str, args: list) -> None:
    packet = encode_osc_message(address, *args)
    decoded_address, decoded_args = _decode_osc_message(packet)
    assert decoded_address == address
    assert decoded_args == tuple(args)


@given(address=address_strategy, args=st.lists(arg_strategy, max_size=5))
# @spec OSC-CLIENT-001
def test_encoded_packet_is_always_4_byte_aligned(address: str, args: list) -> None:
    packet = encode_osc_message(address, *args)
    assert len(packet) % 4 == 0


@given(address=st.text(alphabet=ADDRESS_ALPHABET, min_size=1, max_size=20).filter(lambda s: not s.startswith("/")))
# @spec OSC-CLIENT-001
def test_encode_rejects_address_without_leading_slash(address: str) -> None:
    try:
        encode_osc_message(address)
    except ValueError:
        return
    raise AssertionError("expected ValueError for an address with no leading '/'")


# --- OSC-CLIENT-002: send failures are caught, logged, and do not propagate ---

class _RaisingSocket:
    def sendto(self, data: bytes, addr: tuple[str, int]) -> int:
        raise OSError("simulated network failure")


# @spec OSC-CLIENT-002
def test_client_send_failure_is_caught_and_reported_not_raised() -> None:
    errors: list[Exception] = []
    client = OscClient(host="127.0.0.1", port=7010, sock=_RaisingSocket(), on_error=errors.append)
    client.send("/dragonframe/live")  # must not raise
    assert len(errors) == 1
    assert isinstance(errors[0], OSError)


# @spec OSC-CLIENT-002
def test_client_send_success_does_not_report_error() -> None:
    errors: list[Exception] = []
    real_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client = OscClient(host="127.0.0.1", port=7010, sock=real_sock, on_error=errors.append)
    client.send("/dragonframe/live")
    assert errors == []
    real_sock.close()


# --- OSC-LISTEN-001 / 002: real loopback bind + receive, no mocks ---

# @spec OSC-LISTEN-001, OSC-LISTEN-002
def test_listener_reports_activity_on_real_datagram(free_udp_port: int) -> None:
    activity = threading.Event()
    listener = OscListener(port=free_udp_port, on_activity=activity.set)
    listener.start()
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(encode_osc_message("/dragonframe/axis/PAN/position", 0.5), ("127.0.0.1", free_udp_port))
        sender.close()
        assert activity.wait(timeout=2.0)
    finally:
        listener.stop()


# @spec OSC-LISTEN-002
def test_listener_does_not_report_activity_before_any_datagram(free_udp_port: int) -> None:
    activity = threading.Event()
    listener = OscListener(port=free_udp_port, on_activity=activity.set)
    listener.start()
    try:
        assert not activity.wait(timeout=0.2)
    finally:
        listener.stop()


# --- OSC-LISTEN-003 / 005: bind failure surfaced, fresh attempt gets its own result ---

# @spec OSC-LISTEN-003
def test_listener_bind_failure_is_reported_distinctly(free_udp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("127.0.0.1", free_udp_port))
    try:
        results: list[bool] = []
        listener = OscListener(port=free_udp_port, on_activity=lambda: None, on_bind_result=results.append)
        listener.start()
        assert results == [False]
    finally:
        blocker.close()


# @spec OSC-LISTEN-005
def test_listener_bind_succeeds_after_prior_failure_is_released(free_udp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(("127.0.0.1", free_udp_port))
    results: list[bool] = []
    listener = OscListener(port=free_udp_port, on_activity=lambda: None, on_bind_result=results.append)
    listener.start()
    assert results == [False]
    blocker.close()
    listener.start()  # a fresh attempt, independent of the earlier failure
    try:
        assert results == [False, True]
    finally:
        listener.stop()


# --- OSC-LISTEN-006: rebind closes the old socket and moves traffic to the new port ---

# @spec OSC-LISTEN-006
def test_rebind_moves_listening_to_the_new_port(free_udp_port: int) -> None:
    other_port = free_udp_port + 1 if free_udp_port < 65000 else free_udp_port - 1
    activity_count = {"n": 0}
    lock = threading.Lock()

    def on_activity() -> None:
        with lock:
            activity_count["n"] += 1

    listener = OscListener(port=free_udp_port, on_activity=on_activity)
    listener.start()
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(encode_osc_message("/dragonframe/live"), ("127.0.0.1", free_udp_port))
        time.sleep(0.2)
        assert activity_count["n"] == 1

        listener.rebind(other_port)

        # Old port should no longer be listened on.
        sender.sendto(encode_osc_message("/dragonframe/live"), ("127.0.0.1", free_udp_port))
        time.sleep(0.2)
        assert activity_count["n"] == 1  # unchanged

        sender.sendto(encode_osc_message("/dragonframe/live"), ("127.0.0.1", other_port))
        time.sleep(0.2)
        assert activity_count["n"] == 2
        sender.close()
    finally:
        listener.stop()


# --- OSC-CONFIG-001 / 002 ---

# @spec OSC-CONFIG-001
def test_documented_defaults() -> None:
    assert DEFAULT_DRAGONFRAME_HOST == "127.0.0.1"
    assert DEFAULT_DRAGONFRAME_PORT == 7010
    assert DEFAULT_LISTEN_PORT == 7011


@given(port=st.integers(min_value=1, max_value=65535))
# @spec OSC-CONFIG-002
def test_validate_ports_rejects_equal_ports(port: int) -> None:
    try:
        validate_ports(dragonframe_port=port, listen_port=port)
    except ValueError:
        return
    raise AssertionError("expected ValueError when both ports are equal")


@given(
    dragonframe_port=st.integers(min_value=1, max_value=65535),
    listen_port=st.integers(min_value=1, max_value=65535),
)
# @spec OSC-CONFIG-002
def test_validate_ports_allows_distinct_ports(dragonframe_port: int, listen_port: int) -> None:
    if dragonframe_port == listen_port:
        return
    validate_ports(dragonframe_port=dragonframe_port, listen_port=listen_port)  # must not raise


# ---------------------------------------------------------------------------
# Axis discovery: decode_osc_packet (bundle-aware decoding)
# ---------------------------------------------------------------------------

def _build_bundle(entries: list[bytes]) -> bytes:
    """Hand-build an OSC 1.0 #bundle wrapping already-encoded message bytes.

    Deliberately independent of decode_osc_packet's own implementation - this
    is a second, from-scratch encoder used only to construct test fixtures.
    """
    body = bytearray(b"#bundle\x00")
    body += b"\x00" * 8  # arbitrary time tag, ignored by the decoder
    for message in entries:
        body += struct.pack(">i", len(message))
        body += message
    return bytes(body)


@given(address=address_strategy, args=st.lists(arg_strategy, max_size=3))
# @spec OSC-DISCOVER-004
def test_decode_osc_packet_handles_a_bare_single_message(address: str, args: list) -> None:
    packet = encode_osc_message(address, *args)
    messages = decode_osc_packet(packet)
    assert messages == [(address, tuple(args))]


def test_decode_osc_packet_unwraps_a_bundle_with_one_message() -> None:
    inner = encode_osc_message("/dragonframe/axis/PAN", 12.5)
    bundle = _build_bundle([inner])
    messages = decode_osc_packet(bundle)
    assert messages == [("/dragonframe/axis/PAN", (12.5,))]


@given(
    names=st.lists(
        st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1, max_size=6),
        min_size=2,
        max_size=6,
    )
)
# @spec OSC-DISCOVER-004
def test_decode_osc_packet_unwraps_a_bundle_with_multiple_messages_in_order(names: list[str]) -> None:
    inner_messages = [encode_osc_message(f"/dragonframe/axis/{name}", 0.0) for name in names]
    bundle = _build_bundle(inner_messages)
    messages = decode_osc_packet(bundle)
    assert messages == [(f"/dragonframe/axis/{name}", (0.0,)) for name in names]


def test_decode_osc_packet_recurses_into_a_nested_bundle() -> None:
    inner_message = encode_osc_message("/dragonframe/axis/PAN", 1.0)
    inner_bundle = _build_bundle([inner_message])
    outer_bundle = _build_bundle([inner_bundle])
    messages = decode_osc_packet(outer_bundle)
    assert messages == [("/dragonframe/axis/PAN", (1.0,))]


# ---------------------------------------------------------------------------
# Axis discovery: AxisDiscovery state machine
# ---------------------------------------------------------------------------

def _axis_response_datagram(name: str, position: float) -> bytes:
    return _build_bundle([encode_osc_message(f"/dragonframe/axis/{name}", position)])


# @spec OSC-DISCOVER-006
def test_axis_discovery_starts_never_queried() -> None:
    discovery = AxisDiscovery()
    assert discovery.axes is None


# @spec OSC-DISCOVER-005
def test_axis_discovery_records_axis_from_a_bundled_response() -> None:
    discovery = AxisDiscovery()
    discovery.handle_datagram(_axis_response_datagram("PAN", 42.0))
    assert discovery.axes == {"PAN": 42.0}


# @spec OSC-DISCOVER-005
def test_axis_discovery_overwrites_duplicate_entries_for_the_same_name() -> None:
    discovery = AxisDiscovery()
    discovery.handle_datagram(_axis_response_datagram("PAN", 1.0))
    discovery.handle_datagram(_axis_response_datagram("PAN", 2.0))
    assert discovery.axes == {"PAN": 2.0}


# @spec OSC-DISCOVER-005
def test_axis_discovery_tracks_multiple_distinct_axes() -> None:
    discovery = AxisDiscovery()
    discovery.handle_datagram(_axis_response_datagram("PAN", 1.0))
    discovery.handle_datagram(_axis_response_datagram("TILT", 2.0))
    assert discovery.axes == {"PAN": 1.0, "TILT": 2.0}


# @spec OSC-DISCOVER-005
def test_axis_discovery_ignores_the_getallposition_query_echo() -> None:
    discovery = AxisDiscovery()
    query_echo = encode_osc_message("/dragonframe/axis/getAllPosition")
    discovery.handle_datagram(query_echo)
    assert discovery.axes is None  # not recorded as an axis literally named "getAllPosition"


# @spec OSC-DISCOVER-007
def test_axis_discovery_malformed_datagram_does_not_raise() -> None:
    discovery = AxisDiscovery()
    discovery.handle_datagram(b"\xff\xfe not a valid osc packet at all")  # must not raise
    assert discovery.axes is None  # state unchanged by the failed decode


# @spec OSC-DISCOVER-008
def test_axis_discovery_timeout_transitions_never_queried_to_empty(fake_clock: FakeClock) -> None:
    discovery = AxisDiscovery(clock=fake_clock, timeout=2.0)
    discovery.mark_query_sent()
    fake_clock.advance(1.999)
    discovery.check_timeout()
    assert discovery.axes is None  # not yet timed out

    fake_clock.advance(0.002)  # now past 2.0s total
    discovery.check_timeout()
    assert discovery.axes == {}  # timed out with nothing reported -> "queried, zero axes"


# @spec OSC-DISCOVER-008
def test_axis_discovery_response_before_timeout_prevents_the_empty_transition(fake_clock: FakeClock) -> None:
    discovery = AxisDiscovery(clock=fake_clock, timeout=2.0)
    discovery.mark_query_sent()
    fake_clock.advance(1.0)
    discovery.handle_datagram(_axis_response_datagram("PAN", 0.0))
    fake_clock.advance(2.0)  # well past the original timeout
    discovery.check_timeout()
    assert discovery.axes == {"PAN": 0.0}  # never got overwritten to {}


# @spec OSC-DISCOVER-008
def test_axis_discovery_response_after_timeout_is_still_recorded(fake_clock: FakeClock) -> None:
    discovery = AxisDiscovery(clock=fake_clock, timeout=2.0)
    discovery.mark_query_sent()
    fake_clock.advance(3.0)
    discovery.check_timeout()
    assert discovery.axes == {}
    discovery.handle_datagram(_axis_response_datagram("PAN", 5.0))
    assert discovery.axes == {"PAN": 5.0}  # a late response still updates the store normally


# ---------------------------------------------------------------------------
# Axis discovery: OscListener integration (real loopback sockets)
# ---------------------------------------------------------------------------

class _FakeDragonframe:
    """A real UDP socket that replies to whatever address sent it a datagram -
    mirroring Dragonframe's own observed getAllPosition reply behavior."""

    def __init__(self, port: int, axis_name: str = "PAN", position: float = 7.0) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", port))
        self._axis_name = axis_name
        self._position = position
        self._running = True
        self.query_count = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            self._socket.settimeout(0.2)
            try:
                data, addr = self._socket.recvfrom(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            self.query_count += 1
            reply = _axis_response_datagram(self._axis_name, self._position)
            self._socket.sendto(reply, addr)

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=1.0)
        self._socket.close()


# @spec OSC-DISCOVER-001, OSC-DISCOVER-002
def test_listener_sends_discovery_query_from_its_own_socket_on_start(free_udp_port: int) -> None:
    dragonframe_port = free_udp_port + 1 if free_udp_port < 65000 else free_udp_port - 1
    fake_df = _FakeDragonframe(dragonframe_port)
    discovery = AxisDiscovery()
    listener = OscListener(
        port=free_udp_port,
        on_activity=lambda: None,
        axis_discovery=discovery,
        dragonframe_host="127.0.0.1",
        dragonframe_port=dragonframe_port,
    )
    listener.start()
    try:
        deadline = time.monotonic() + 2.0
        while discovery.axes is None and time.monotonic() < deadline:
            time.sleep(0.05)
        # The fake only replies to the sender's address - receiving anything here
        # proves the query was sent from the same socket this listener is bound to.
        assert discovery.axes == {"PAN": 7.0}
    finally:
        listener.stop()
        fake_df.stop()


# @spec OSC-DISCOVER-002
def test_listener_resends_discovery_query_on_rebind(free_udp_port: int) -> None:
    dragonframe_port = free_udp_port + 1 if free_udp_port < 65000 else free_udp_port - 1
    other_port = free_udp_port + 2 if free_udp_port < 65000 else free_udp_port - 2
    fake_df = _FakeDragonframe(dragonframe_port)
    discovery = AxisDiscovery()
    listener = OscListener(
        port=free_udp_port,
        on_activity=lambda: None,
        axis_discovery=discovery,
        dragonframe_host="127.0.0.1",
        dragonframe_port=dragonframe_port,
    )
    listener.start()
    try:
        deadline = time.monotonic() + 2.0
        while fake_df.query_count < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake_df.query_count == 1

        listener.rebind(other_port)
        deadline = time.monotonic() + 2.0
        while fake_df.query_count < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake_df.query_count == 2  # rebind triggered a second automatic query
    finally:
        listener.stop()
        fake_df.stop()


# @spec OSC-DISCOVER-003
def test_rescan_sends_an_independent_query(free_udp_port: int) -> None:
    dragonframe_port = free_udp_port + 1 if free_udp_port < 65000 else free_udp_port - 1
    fake_df = _FakeDragonframe(dragonframe_port)
    discovery = AxisDiscovery()
    listener = OscListener(
        port=free_udp_port,
        on_activity=lambda: None,
        axis_discovery=discovery,
        dragonframe_host="127.0.0.1",
        dragonframe_port=dragonframe_port,
    )
    listener.start()
    try:
        deadline = time.monotonic() + 2.0
        while fake_df.query_count < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake_df.query_count == 1

        listener.rescan()
        deadline = time.monotonic() + 2.0
        while fake_df.query_count < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake_df.query_count == 2
    finally:
        listener.stop()
        fake_df.stop()
