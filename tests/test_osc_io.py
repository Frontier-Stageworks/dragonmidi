"""Tests for the OSC Transport (docs/specs/osc-io.md).

@spec OSC-CLIENT-001, OSC-CLIENT-002
@spec OSC-LISTEN-001, OSC-LISTEN-002, OSC-LISTEN-003, OSC-LISTEN-005, OSC-LISTEN-006
@spec OSC-CONFIG-001, OSC-CONFIG-002
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
    OscClient,
    OscListener,
    encode_osc_message,
    validate_ports,
)

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
