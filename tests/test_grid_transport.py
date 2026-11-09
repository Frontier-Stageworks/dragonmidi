"""Tests for Grid CDC transport discovery (docs/llds/intech-grid.md § Grid CDC
Transport). `SerialGridTransport`'s real pyserial-backed port-opening was
exercised directly against physical hardware during the 2026-11-04 hardware
validation pass (see the completion report), not via this automated suite -
this file tests the pure VID/PID candidate-filtering and name-matching logic.

@spec GRID-DISCOVER-002, GRID-DISCOVER-003, GRID-DISCOVER-004
"""

from __future__ import annotations

from dragonmidi.grid_transport import GRID_CDC_MATCH_SUBSTRING, GRID_VID_PID_PAIRS, is_candidate_cdc_port
from dragonmidi.name_matching import fuzzy_contains


def test_every_documented_vid_pid_pair_is_a_candidate() -> None:
    for vid, pid in GRID_VID_PID_PAIRS:
        assert is_candidate_cdc_port(vid, pid)


def test_an_unrelated_vid_pid_pair_is_not_a_candidate() -> None:
    assert not is_candidate_cdc_port(0x1234, 0x5678)


def test_a_right_vid_wrong_pid_pair_is_not_a_candidate() -> None:
    real_vid, _ = GRID_VID_PID_PAIRS[0]
    assert not is_candidate_cdc_port(real_vid, 0xFFFF)


def test_real_hardware_observed_vid_pid_is_a_documented_pair() -> None:
    # Confirmed via ioreg/pyserial against a real PBF4+VSN1 chain
    # (2026-11-04): VID 0x303A / PID 0x8123, the ESP32-S3-based firmware
    # variant - already one of the three documented pairs, unmodified by
    # this validation pass.
    assert is_candidate_cdc_port(0x303A, 0x8123)


def test_cdc_match_substring_corroborates_the_real_bare_product_name() -> None:
    # Real-hardware correction (2026-11-04): the CDC port's description is
    # simply "Grid" (confirmed via pyserial's list_ports), not the "Intech
    # Grid CDC" per-interface descriptor string source research had assumed -
    # this corroboration is never required (VID/PID already succeeds without
    # it), but it should actually fire when given the chance to.
    assert fuzzy_contains(GRID_CDC_MATCH_SUBSTRING, "Grid")
