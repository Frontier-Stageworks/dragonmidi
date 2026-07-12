"""Tests for the Static Mapping Engine (docs/specs/static-mapping.md).

@spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-004, MAP-TABLE-005
@spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.events import MidiEvent
from dragonmidi.mapping import CHANNEL, MappingEngine, decode_sign_magnitude

FADER_CCS = list(range(0, 8))  # CC 0-7 -> encoder 1-8
KNOB_CCS = list(range(16, 24))  # CC 16-23 -> encoder 9-16
MUTE_CCS = list(range(48, 56))  # CC 48-55 -> encoderReset 1-8
SOLO_CCS = list(range(32, 40))  # CC 32-39 -> encoderReset 9-16
BUTTON_CCS_TO_ADDRESS = {
    47: "/dragonframe/encoderReset/17",  # Return to Zero
    45: "/dragonframe/shoot",  # Transport Record
    41: "/dragonframe/play",
    42: "/dragonframe/live",
    44: "/dragonframe/shootVideoAssist",
    46: "/dragonframe/mute",
    60: "/dragonframe/delete",
}
JOG_CC = 110
UNMAPPED_CCS = [64, 65, 70, 71, 80, 87, 43, 61, 62, 58, 59]  # Record/Select/Rewind/markers/tracks


def cc_event(number: int, value: int, channel: int = CHANNEL) -> MidiEvent:
    return MidiEvent(
        type="cc",
        channel=channel,
        number=number,
        raw_value=value,
        normalized=value / 127.0,
        is_press=value > 0,
        is_release=value == 0,
    )


def scene_event(channel: int, value: int) -> MidiEvent:
    return MidiEvent(
        type="korg_scene",
        channel=channel,
        number=None,
        raw_value=value,
        normalized=value / 127.0,
        is_press=value > 0,
        is_release=value == 0,
    )


# --- MAP-TABLE-001: channel invariant for CC-sourced controls, korg_scene exempt ---

@given(
    number=st.sampled_from(FADER_CCS + KNOB_CCS + MUTE_CCS + SOLO_CCS + list(BUTTON_CCS_TO_ADDRESS)),
    channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != CHANNEL),
    value=st.integers(min_value=0, max_value=127),
)
# @spec MAP-TABLE-001
def test_cc_on_wrong_channel_never_matches(number: int, channel: int, value: int) -> None:
    engine = MappingEngine()
    assert engine.process(cc_event(number, value, channel=channel), now=0.0) is None


@given(channel=st.integers(min_value=0, max_value=15), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-001
def test_scene_button_matches_regardless_of_channel(channel: int, value: int) -> None:
    # The Scene button's channel is the controller's own configured global-channel ID,
    # not a stand-in for MIDI channel 16 - it must match on every channel value 0-15.
    engine = MappingEngine()
    result = engine.process(scene_event(channel, value), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/black"


# --- MAP-TABLE-002: fader/knob absolute encoders, distinct-value-only, no debounce ---

@given(number=st.sampled_from(FADER_CCS), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-002
def test_fader_sends_absolute_encoder_value(number: int, value: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(number, value), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/encoder/{number + 1}"
    assert result.args == (value / 127.0,)


@given(number=st.sampled_from(KNOB_CCS), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-002
def test_knob_sends_absolute_encoder_value(number: int, value: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(number, value), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/encoder/{number - 16 + 9}"
    assert result.args == (value / 127.0,)


@given(number=st.sampled_from(FADER_CCS + KNOB_CCS), value=st.integers(min_value=0, max_value=127))
# @spec MAP-TABLE-002
def test_absolute_control_repeating_identical_value_sends_only_once(number: int, value: int) -> None:
    engine = MappingEngine()
    first = engine.process(cc_event(number, value), now=0.0)
    second = engine.process(cc_event(number, value), now=0.001)  # identical value again
    assert first is not None
    assert second is None  # "every distinct value" - a repeat of the same value is not distinct


@given(
    number=st.sampled_from(FADER_CCS + KNOB_CCS),
    values=st.lists(st.integers(min_value=0, max_value=127), min_size=2, max_size=10, unique=True),
)
# @spec MAP-TABLE-002
def test_absolute_control_sends_every_distinct_value_with_no_debounce(number: int, values: list[int]) -> None:
    engine = MappingEngine()
    # Fire all distinct values back-to-back at the same instant (now never advances):
    # MAP-TABLE-002 requires no debounce for absolute controls, unlike button press-edges.
    results = [engine.process(cc_event(number, v), now=0.0) for v in values]
    assert all(r is not None for r in results)


# --- MAP-TABLE-003: button press-edge, one-shot per transition ---

@given(cc=st.sampled_from(list(BUTTON_CCS_TO_ADDRESS)), press_value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-003
def test_button_press_edge_fires_expected_address(cc: int, press_value: int) -> None:
    engine = MappingEngine()
    # Release-then-press so the transition crosses the threshold from a known "not pressed" state.
    engine.process(cc_event(cc, 0), now=0.0)
    result = engine.process(cc_event(cc, press_value), now=0.0)
    assert result is not None
    assert result.address == BUTTON_CCS_TO_ADDRESS[cc]


# @spec MAP-TABLE-003
def test_transport_record_sends_shoot_with_frame_count_one() -> None:
    engine = MappingEngine()
    engine.process(cc_event(45, 0), now=0.0)
    result = engine.process(cc_event(45, 127), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/shoot"
    assert result.args == (1,)


@given(cc=st.sampled_from(MUTE_CCS))
# @spec MAP-TABLE-003
def test_mute_resets_matching_encoder(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    result = engine.process(cc_event(cc, 127), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/encoderReset/{cc - 48 + 1}"


@given(cc=st.sampled_from(SOLO_CCS))
# @spec MAP-TABLE-003
def test_solo_resets_matching_encoder(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    result = engine.process(cc_event(cc, 127), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/encoderReset/{cc - 32 + 9}"


# @spec MAP-TABLE-003
def test_button_holding_at_max_only_fires_once_not_on_every_message() -> None:
    engine = MappingEngine()
    engine.process(cc_event(41, 0), now=0.0)
    first = engine.process(cc_event(41, 127), now=0.0)
    second = engine.process(cc_event(41, 127), now=1.0)  # same value repeated, well past debounce
    assert first is not None
    assert second is None  # no new transition occurred; previous was already >= threshold


# --- MAP-TABLE-004: jog wheel sign-magnitude decode (full-domain property) ---

@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-TABLE-004
def test_decode_sign_magnitude_matches_reference_definition(raw: int) -> None:
    if raw in (0, 64):
        expected = 0
    elif 1 <= raw <= 63:
        expected = raw
    else:
        expected = -(raw - 64)
    assert decode_sign_magnitude(raw) == expected


@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-TABLE-004
def test_decode_sign_magnitude_is_bounded_and_zero_only_at_rest_values(raw: int) -> None:
    delta = decode_sign_magnitude(raw)
    assert -63 <= delta <= 63
    assert (delta == 0) == (raw in (0, 64))


@given(raw=st.integers(min_value=65, max_value=127))
# @spec MAP-TABLE-004
def test_decode_sign_magnitude_symmetry(raw: int) -> None:
    # 65..127 mirrors 1..63 in magnitude, opposite sign - a real cross-check, not
    # a re-statement of the formula, since it relates two disjoint input ranges.
    mirrored = raw - 64
    assert decode_sign_magnitude(raw) == -decode_sign_magnitude(mirrored)


@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-TABLE-004
def test_jog_wheel_event_produces_matching_encoder17_delta(raw: int) -> None:
    engine = MappingEngine()
    event = cc_event(JOG_CC, raw)
    result = engine.process(event, now=0.0)
    delta = decode_sign_magnitude(raw)
    if delta == 0:
        assert result is None
    else:
        assert result is not None
        assert result.address == "/dragonframe/encoder/17"
        assert result.args == (float(delta),)


# --- MAP-TABLE-005 / MAP-STATE-001: unmapped controls produce nothing and hold no state ---

@given(cc=st.sampled_from(UNMAPPED_CCS), value=st.integers(min_value=0, max_value=127))
# @spec MAP-TABLE-005
def test_unmapped_control_produces_no_message(cc: int, value: int) -> None:
    engine = MappingEngine()
    assert engine.process(cc_event(cc, value), now=0.0) is None


@given(cc=st.sampled_from(UNMAPPED_CCS))
# @spec MAP-STATE-001
def test_unmapped_control_allocates_no_tracked_state(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 127), now=0.0)
    assert ("cc", cc) not in engine.tracked_controls()


@given(number=st.sampled_from(FADER_CCS + MUTE_CCS))
# @spec MAP-STATE-001
def test_mapped_control_does_allocate_tracked_state(number: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(number, 64), now=0.0)
    assert ("cc", number) in engine.tracked_controls()


# --- MAP-DEBOUNCE-001: dropped inside window, allowed after ---

@given(cc=st.sampled_from(list(BUTTON_CCS_TO_ADDRESS)), gap=st.floats(min_value=0.0, max_value=0.079))
# @spec MAP-DEBOUNCE-001
def test_second_press_inside_debounce_window_is_dropped(cc: int, gap: float) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    engine.process(cc_event(cc, 127), now=0.0)  # first press-edge, fires
    engine.process(cc_event(cc, 0), now=0.0 + gap / 2)  # release
    result = engine.process(cc_event(cc, 127), now=gap)  # re-press inside 80ms window
    assert result is None


@given(cc=st.sampled_from(list(BUTTON_CCS_TO_ADDRESS)), gap=st.floats(min_value=0.081, max_value=5.0))
# @spec MAP-DEBOUNCE-001
def test_second_press_after_debounce_window_fires(cc: int, gap: float) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    engine.process(cc_event(cc, 127), now=0.0)  # first press-edge, fires
    engine.process(cc_event(cc, 0), now=gap / 2)  # release
    result = engine.process(cc_event(cc, 127), now=gap)  # re-press after window
    assert result is not None


# --- MAP-STATE-002: control already held before first message behaves as documented ---

# @spec MAP-STATE-002
def test_first_ever_message_being_a_release_shape_fires_nothing() -> None:
    # Simulates a control already held down before the app started: the app never saw
    # the original press, so its first observed message for that control is the release.
    engine = MappingEngine()
    assert ("cc", 41) not in engine.tracked_controls()
    result = engine.process(cc_event(41, 0), now=0.0)  # release-shaped value, first ever message
    assert result is None


# @spec MIDI-EVT-004
def test_reset_clears_tracked_state_so_a_prior_press_no_longer_blocks_debounce() -> None:
    engine = MappingEngine()
    engine.process(cc_event(41, 0), now=0.0)
    engine.process(cc_event(41, 127), now=0.0)
    engine.reset()
    assert engine.tracked_controls() == set()
    # After reset, the very next press-edge must fire again without being treated as a repeat.
    engine.process(cc_event(41, 0), now=100.0)
    result = engine.process(cc_event(41, 127), now=100.0)
    assert result is not None
