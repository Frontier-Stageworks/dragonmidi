"""Grid CDC frame/heartbeat parser (docs/llds/intech-grid.md § Grid Frame / Heartbeat Parser).

Grid's own wire protocol (Intech Studio `grid-fw`/`grid-protocol`, GPL-3.0-only)
frames messages with SOH (0x01) / EOB (0x17) control bytes and carries a
HEARTBEAT chunk (module type/position) plus, only for the USB-connected
"gridmaster" module, a piggybacked PAGEACTIVE chunk (the active page number) -
these are protocol *facts*, independently reimplemented here, not ported code
(docs/llds/intech-grid.md § Licensing / Provenance).

**Corrected against real hardware (2026-11-04)**: an earlier draft of this
module assumed a single flat `SOH 'H' TYPE(2) HWCFG(2) SX(4) SY(4) ROT(1)
PORTROT(1) EOB` record. Capturing and decoding real CDC traffic from a
physical PBF4/VSN1 chain (see the hardware-validation completion report)
showed the real wire format is a two-level "BRC" packet instead - confirmed
against Intech Studio's own `grid-protocol` TypeScript source
(`src/grid-protocol.ts`'s `decode_packet_frame`, GPL-3.0-only, independently
reimplemented here as a protocol *fact*, not ported code):

    SOH BRC(0x0F) <20 ASCII-hex header fields> EOB <class blocks>+ EOT <checksum(2)> LF

Header field offsets below are counted from this packet's own `SOH` (index
0); `SX`/`SY` are the module's own position, ASCII-hex, 1 byte (2 hex
digits) each, biased by +127 (not the 4-hex-digit two's-complement 16-bit
field the earlier draft assumed) - `ROT`/`PORTROT` are 1 hex digit each.
`EOB` always falls at index 22.

Each `<class block>` is `STX <3-hex class code> <1 reserved byte> <fields> ETX`;
field offsets below are counted from that block's own `STX` (index 0). Only
two class codes matter for Phase 1: `HEARTBEAT` (`0x010`: `TYPE`, `HWCFG`,
plus firmware version/port-state/GC-count fields this module reads but
ignores) and `PAGEACTIVE` (`0x030`: `PAGENUMBER`), present only alongside a
`TYPE == 1` ("gridmaster") heartbeat. A packet's checksum is the XOR of
every byte except its own trailing 2 checksum hex digits; this module
verifies it (real hardware's own noise-rejection) but does not verify the
header's `LEN` field, unlike Intech's own decoder - `LEN` is redundant with
the checksum for this module's purposes and, like `VMAJOR`/`PORTSTATE`/etc.,
not load-bearing for anything Phase 1 does with a decoded heartbeat.

The accumulator's contract (never raise, discard anything malformed, resync
on the next `SOH`) is unchanged by this correction and is what the EARS
requirements (GRID-TOPO-001..003) actually pin down - a byte-level mismatch
here does not imply any of §§3-11 of the LLD were wrong, and none were.
"""

from __future__ import annotations

from dataclasses import dataclass

SOH = 0x01
STX = 0x02
ETX = 0x03
EOB = 0x17
EOT = 0x04
LF = 0x0A
_BRC_MARKER = 0x0F

# BRC header field offsets/lengths, counted from this packet's own SOH (index 0).
# LEN/ID/SESSION/DX/DY/MSGAGE exist on the wire but are not read - not load-bearing
# for anything this module's consumers do with a decoded heartbeat.
_BRC_SX = (10, 2)
_BRC_SY = (12, 2)
_BRC_ROT = (18, 1)
_BRC_PORTROT = (19, 1)
_BRC_HEADER_LENGTH = 23  # SOH..EOB inclusive; EOB always falls at index 22
_BRC_POSITION_BIAS = 127  # SX/SY are transmitted unsigned, biased by this

# Class-block field offsets/lengths, counted from that block's own STX (index 0).
_CLASS_CODE = (1, 3)
_HEARTBEAT_CLASS_CODE = 0x010
_HEARTBEAT_TYPE = (5, 2)
_HEARTBEAT_HWCFG = (7, 2)
# VMAJOR/VMINOR/VPATCH/PORTSTATE/GCCOUNT also exist in this class block (offsets
# 9, 11, 13, 15, 17, each length 2) but are not read for the same reason as above.
_PAGEACTIVE_CLASS_CODE = 0x030
_PAGEACTIVE_PAGENUMBER = (5, 2)

# A well-formed packet (header + up to a couple of class blocks + footer) never
# exceeds this many bytes; anything longer with no LF in sight is not a packet
# this parser will ever recognize, so there is no reason to keep buffering it.
_MAX_PACKET_LENGTH = 160


@dataclass(frozen=True)
class GridHeartbeat:
    """One decoded Grid heartbeat. `heartbeat_type`: 0 ("grid"), 1 ("gridmaster"),
    or 255 ("editor") - only 0/1 are ever produced by `GridFrameAccumulator`,
    per GRID-TOPO-002/003 (docs/specs/intech-grid.md)."""

    heartbeat_type: int
    hwcfg: int
    x: int
    y: int
    rotation: int
    port_rotation: int
    page: int | None  # only populated for heartbeat_type == 1


def _parse_hex(data: bytes, offset: int, length: int) -> int | None:
    if offset + length > len(data):
        return None
    chunk = data[offset : offset + length]
    try:
        return int(chunk.decode("ascii"), 16)
    except (UnicodeDecodeError, ValueError):
        return None


def _to_signed_position(value: int) -> int:
    return value - _BRC_POSITION_BIAS


def _checksum_ok(packet: bytes) -> bool:
    if len(packet) < 2:
        return False
    calculated = 0
    for byte in packet[:-2]:
        calculated ^= byte
    received = _parse_hex(packet, len(packet) - 2, 2)
    return received is not None and calculated % 256 == received


def _split_class_blocks(region: bytes) -> dict[int, bytes]:
    """Splits a byte span into STX..ETX class blocks, keyed by class code.
    Returns `{}` - never raises - for any malformed span."""
    blocks: dict[int, bytes] = {}
    index = 0
    while index < len(region):
        if region[index] != STX:
            return {}
        etx_index = region.find(bytes([ETX]), index)
        if etx_index == -1:
            return {}
        block = region[index : etx_index + 1]
        code = _parse_hex(block, *_CLASS_CODE)
        if code is not None:
            blocks[code] = block
        index = etx_index + 1
    return blocks


def _decode_packet(packet: bytes) -> GridHeartbeat | None:
    """`packet` is one full `SOH`..checksum span (the accumulator strips the
    trailing `LF` terminator before calling this). Returns a `GridHeartbeat`
    only for a well-formed packet carrying a `HEARTBEAT` class block whose
    `heartbeat_type` is 0 or 1 (GRID-TOPO-002); anything else - a bad
    checksum, malformed field, missing/editor (255) heartbeat, or a
    heartbeat-less packet (e.g. a MIDI class block riding the same CDC
    stream) - returns `None` rather than raising (GRID-TOPO-001, GRID-TOPO-003)."""
    if len(packet) < _BRC_HEADER_LENGTH + 3:
        return None
    if packet[0] != SOH or packet[1] != _BRC_MARKER or packet[_BRC_HEADER_LENGTH - 1] != EOB:
        return None
    if not _checksum_ok(packet):
        return None
    if packet[-3] != EOT:
        return None

    sx = _parse_hex(packet, *_BRC_SX)
    sy = _parse_hex(packet, *_BRC_SY)
    rotation = _parse_hex(packet, *_BRC_ROT)
    port_rotation = _parse_hex(packet, *_BRC_PORTROT)
    if None in (sx, sy, rotation, port_rotation):
        return None

    class_blocks = _split_class_blocks(packet[_BRC_HEADER_LENGTH:-3])
    heartbeat_block = class_blocks.get(_HEARTBEAT_CLASS_CODE)
    if heartbeat_block is None:
        return None

    heartbeat_type = _parse_hex(heartbeat_block, *_HEARTBEAT_TYPE)
    hwcfg = _parse_hex(heartbeat_block, *_HEARTBEAT_HWCFG)
    if heartbeat_type is None or hwcfg is None or heartbeat_type not in (0, 1):
        return None  # 255 (editor), an undefined value, or a malformed field - not a module

    page = None
    if heartbeat_type == 1:
        pageactive_block = class_blocks.get(_PAGEACTIVE_CLASS_CODE)
        if pageactive_block is None:
            return None  # a gridmaster heartbeat with no PAGEACTIVE is malformed, not partially valid
        page = _parse_hex(pageactive_block, *_PAGEACTIVE_PAGENUMBER)
        if page is None:
            return None

    return GridHeartbeat(
        heartbeat_type=heartbeat_type,
        hwcfg=hwcfg,
        x=_to_signed_position(sx),
        y=_to_signed_position(sy),
        rotation=rotation,
        port_rotation=port_rotation,
        page=page,
    )


class GridFrameAccumulator:
    """Byte-stream framer: `feed(chunk) -> list[GridHeartbeat]`. Never raises.
    Handles a packet split across multiple `feed()` calls, multiple packets in
    one call, and garbage bytes between packets - matching `normalize_raw()`'s
    "normalize what we recognize, ignore the rest, never crash" posture.

    @spec GRID-TOPO-001, GRID-TOPO-002, GRID-TOPO-003
    """

    def __init__(self) -> None:
        self._buffer: bytearray | None = None  # None = not currently inside a packet

    def feed(self, data: bytes) -> list[GridHeartbeat]:
        results: list[GridHeartbeat] = []
        for byte in data:
            if byte == SOH:
                # A new packet starting - including before a previous one
                # closed, whose incomplete buffer is simply abandoned.
                self._buffer = bytearray([byte])
                continue

            if self._buffer is None:
                continue  # waiting for SOH; anything else between packets is ignored

            self._buffer.append(byte)
            if byte == LF:
                heartbeat = _decode_packet(bytes(self._buffer[:-1]))  # drop the LF terminator itself
                if heartbeat is not None:
                    results.append(heartbeat)
                self._buffer = None
                continue

            if len(self._buffer) > _MAX_PACKET_LENGTH:
                # No LF in sight after a sane maximum length - discard and
                # resync, rather than buffering unboundedly.
                self._buffer = None

        return results


def encode_heartbeat_frame(
    *,
    heartbeat_type: int,
    hwcfg: int,
    x: int,
    y: int,
    rotation: int,
    port_rotation: int,
    page: int | None = None,
) -> bytes:
    """Test-fixture helper: encodes a heartbeat into this module's own wire
    format, the inverse of `GridFrameAccumulator`. Not a production entry
    point - real Grid hardware is the only real-world producer of this wire
    format; this exists so tests can round-trip without hardware. Fields this
    module doesn't read (`LEN`, `ID`, `SESSION`, `DX`, `DY`, `MSGAGE`,
    `VMAJOR`/`VMINOR`/`VPATCH`, `PORTSTATE`, `GCCOUNT`, each class block's
    reserved byte at offset 4) are filled with harmless placeholder values -
    `LEN` alone is computed for wire-realism even though `_decode_packet`
    doesn't check it."""

    def _hex(value: int, width: int) -> bytes:
        return format(value & ((1 << (4 * width)) - 1), f"0{width}X").encode("ascii")

    def _class_block(code: int, fields: bytes) -> bytes:
        return bytes([STX]) + _hex(code, 3) + b"_" + fields + bytes([ETX])

    class_region = _class_block(
        _HEARTBEAT_CLASS_CODE,
        _hex(heartbeat_type, 2) + _hex(hwcfg, 2) + _hex(0, 2) + _hex(0, 2) + _hex(0, 2) + _hex(0, 2) + _hex(0, 2),
    )
    if heartbeat_type == 1:
        class_region += _class_block(_PAGEACTIVE_CLASS_CODE, _hex(page if page is not None else 0, 2))

    header_fields = (
        _hex(0, 2)  # ID
        + _hex(0, 2)  # SESSION
        + _hex(x + _BRC_POSITION_BIAS, 2)  # SX
        + _hex(y + _BRC_POSITION_BIAS, 2)  # SY
        + _hex(_BRC_POSITION_BIAS, 2)  # DX (unused by Phase 1, biased "zero")
        + _hex(_BRC_POSITION_BIAS, 2)  # DY (unused by Phase 1, biased "zero")
        + _hex(rotation, 1)
        + _hex(port_rotation, 1)
        + _hex(0, 2)  # MSGAGE
    )
    body_without_checksum = bytes([SOH, _BRC_MARKER]) + _hex(0, 4) + header_fields + bytes([EOB]) + class_region + bytes([EOT])
    # LEN is wire-realism only (see docstring); matches Intech's own convention
    # (packet length minus the 2 trailing checksum digits), not read on decode.
    length_field = _hex(len(body_without_checksum) + 2, 4)
    body_without_checksum = body_without_checksum[:2] + length_field + body_without_checksum[6:]

    checksum = 0
    for byte in body_without_checksum:
        checksum ^= byte
    checksum %= 256

    return body_without_checksum + _hex(checksum, 2) + bytes([LF])
