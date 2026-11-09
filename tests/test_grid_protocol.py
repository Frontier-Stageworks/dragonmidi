"""Tests for the Grid CDC frame/heartbeat parser (docs/specs/intech-grid.md).

Wire format was corrected against a real captured CDC byte trace from a
physical PBF4/VSN1 chain (2026-11-04 hardware validation) - see
`grid_protocol.py`'s module docstring for the exact byte layout, its
provenance, and what changed from the earlier, unvalidated draft. A frozen
real-hardware fixture lives in `test_decodes_a_real_captured_trace` below.

@spec GRID-TOPO-001, GRID-TOPO-002, GRID-TOPO-003
"""

from __future__ import annotations

from dragonmidi.grid_protocol import SOH, EOB, GridFrameAccumulator, GridHeartbeat, encode_heartbeat_frame


# --- Round-trip encode/decode of well-formed frames ---


# @spec GRID-TOPO-002
def test_decodes_a_type0_heartbeat_with_no_page() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    results = acc.feed(frame)
    assert results == [GridHeartbeat(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0, page=None)]


# @spec GRID-TOPO-002
def test_decodes_a_type1_gridmaster_heartbeat_with_page() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=1, hwcfg=49, x=0, y=0, rotation=0, port_rotation=0, page=3)
    acc = GridFrameAccumulator()
    results = acc.feed(frame)
    assert results == [GridHeartbeat(heartbeat_type=1, hwcfg=49, x=0, y=0, rotation=0, port_rotation=0, page=3)]


# @spec GRID-TOPO-002
def test_negative_coordinates_round_trip() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=-1, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    [result] = acc.feed(frame)
    assert result.x == -1
    assert result.y == 0


# --- TYPE handling (GRID-TOPO-003) ---


# @spec GRID-TOPO-003
def test_type_255_editor_heartbeat_is_discarded_not_a_module() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=255, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    assert acc.feed(frame) == []


# @spec GRID-TOPO-003
def test_undefined_type_value_is_discarded_not_a_crash() -> None:
    # 2 is neither a known module type (0/1) nor the known editor type (255).
    frame = encode_heartbeat_frame(heartbeat_type=2, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    assert acc.feed(frame) == []


# --- Frame boundary / malformed input handling ---


# @spec GRID-TOPO-001
def test_truncated_frame_with_no_eob_is_discarded_and_does_not_raise() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    assert acc.feed(frame[:-1]) == []  # drop the trailing LF terminator - never finalizes, never raises


def _recompute_checksum(frame: bytearray) -> None:
    """Test helper: fixes up the trailing 2-hex-digit checksum after a test
    has deliberately corrupted some other byte, so a test can isolate "a
    malformed field the sender itself transmitted" from "wire-noise the
    checksum should catch" (the latter is its own test below)."""
    body = bytes(frame[:-3])  # excludes LF, and the 2 checksum chars before it
    checksum = 0
    for byte in body:
        checksum ^= byte
    checksum %= 256
    frame[-3:-1] = format(checksum, "02X").encode("ascii")


# @spec GRID-TOPO-001
def test_malformed_hex_fields_are_discarded_and_do_not_raise() -> None:
    frame = bytearray(encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0))
    # Corrupt a byte inside the HEARTBEAT class block's HWCFG hex field: "010_"
    # is the class code (0x010) plus its reserved byte, immediately followed by
    # TYPE's 2 hex digits, then HWCFG's first hex digit.
    hwcfg_field_index = frame.index(b"010_") + len(b"010_") + 2
    frame[hwcfg_field_index] = ord("?")
    _recompute_checksum(frame)  # isolates "malformed field" from "wire corruption" (see test below)
    acc = GridFrameAccumulator()
    assert acc.feed(bytes(frame)) == []


# @spec GRID-TOPO-001
def test_checksum_mismatch_is_discarded_and_does_not_raise() -> None:
    # A real-hardware-informed addition (2026-11-04): the real wire format
    # carries a checksum this parser verifies - noise that flips any single
    # byte without also fixing up the checksum must be rejected.
    frame = bytearray(encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0))
    frame[10] ^= 0xFF  # flip a byte inside the BRC header, leave the checksum as-is
    acc = GridFrameAccumulator()
    assert acc.feed(bytes(frame)) == []


# @spec GRID-TOPO-001
def test_eob_with_no_preceding_soh_is_ignored() -> None:
    acc = GridFrameAccumulator()
    assert acc.feed(bytes([EOB, EOB, EOB])) == []


# @spec GRID-TOPO-001
def test_an_overlong_frame_with_no_eob_is_discarded_and_parser_resyncs() -> None:
    acc = GridFrameAccumulator()
    garbage = bytes([SOH]) + b"x" * 5000  # far past any sane max frame length, no EOB
    assert acc.feed(garbage) == []
    # The accumulator must have recovered - a well-formed frame right after still decodes.
    good = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=1, y=0, rotation=0, port_rotation=0)
    [result] = acc.feed(good)
    assert result.hwcfg == 64


# @spec GRID-TOPO-001
def test_multiple_frames_in_one_feed_call() -> None:
    frame_a = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    frame_b = encode_heartbeat_frame(heartbeat_type=0, hwcfg=49, x=1, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    results = acc.feed(frame_a + frame_b)
    assert [r.hwcfg for r in results] == [64, 49]


# @spec GRID-TOPO-001
def test_a_single_frame_split_across_multiple_feed_calls() -> None:
    frame = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    midpoint = len(frame) // 2
    assert acc.feed(frame[:midpoint]) == []
    [result] = acc.feed(frame[midpoint:])
    assert result.hwcfg == 64


# @spec GRID-TOPO-001
def test_garbage_between_frames_does_not_prevent_the_next_good_frame() -> None:
    good = encode_heartbeat_frame(heartbeat_type=0, hwcfg=64, x=0, y=0, rotation=0, port_rotation=0)
    acc = GridFrameAccumulator()
    results = acc.feed(b"\x00\x02\x03" + good)
    assert [r.hwcfg for r in results] == [64]


# --- Real-hardware regression fixture (2026-11-04 validation pass) ---
# Two packets captured verbatim from a real PBF4 (TYPE 0) and a real VSN1
# gridmaster (TYPE 1) over USB CDC at 2,000,000 baud - frozen here so this
# exact real byte layout (BRC header + HEARTBEAT/PAGEACTIVE class blocks +
# checksum + LF) stays covered independently of `encode_heartbeat_frame`,
# which is this project's own encoder and could theoretically drift from the
# real format in lockstep with a parser bug.

_REAL_PBF4_PACKET = bytes.fromhex(
    "01 0f 30 30 32 63 61 66 62 37 37 65 37 66 30 30 30 30 30 30 30 31 17 "
    "02 30 31 30 65 30 30 34 33 30 31 30 35 30 34 30 32 33 65 03 "
    "04 31 61 0a".replace(" ", "")
)
_REAL_VSN1_GRIDMASTER_PACKET = bytes.fromhex(
    "01 0f 30 30 33 34 64 35 36 66 37 66 37 66 30 30 30 30 30 30 30 30 17 "
    "02 30 31 30 65 30 31 33 62 30 31 30 35 30 34 30 38 34 36 03 "
    "02 30 33 30 64 30 30 03 "
    "04 34 32 0a".replace(" ", "")
)


# @spec GRID-TOPO-001, GRID-TOPO-002
def test_decodes_a_real_captured_trace() -> None:
    acc = GridFrameAccumulator()
    pbf4 = acc.feed(_REAL_PBF4_PACKET)
    assert pbf4 == [GridHeartbeat(heartbeat_type=0, hwcfg=67, x=-1, y=0, rotation=0, port_rotation=0, page=None)]

    vsn1 = acc.feed(_REAL_VSN1_GRIDMASTER_PACKET)
    assert vsn1 == [GridHeartbeat(heartbeat_type=1, hwcfg=59, x=0, y=0, rotation=0, port_rotation=0, page=0)]


# @spec GRID-TOPO-001
def test_real_captured_trace_round_trips_byte_by_byte() -> None:
    # Matches the fragmentation a real background serial-reader thread
    # actually delivers - one byte per feed() call, not one clean chunk.
    acc = GridFrameAccumulator()
    results = []
    for byte in _REAL_PBF4_PACKET + _REAL_VSN1_GRIDMASTER_PACKET:
        results.extend(acc.feed(bytes([byte])))
    assert [(r.heartbeat_type, r.hwcfg) for r in results] == [(0, 67), (1, 59)]
