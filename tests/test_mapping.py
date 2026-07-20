"""Tests for the Static Mapping Engine (docs/specs/static-mapping.md).

@spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-005
@spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
@spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-004, MAP-AXIS-006, MAP-AXIS-007
@spec MAP-AXIS-008, MAP-AXIS-009, MAP-AXIS-010
@spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-004, MAP-BANK-005, MAP-BANK-006, MAP-BANK-007
@spec MAP-BANK-008, MAP-BANK-009
@spec MAP-JOG-001, MAP-JOG-002, MAP-JOG-003, MAP-JOG-004, MAP-JOG-005
@spec MAP-JOGKEY-001, MAP-JOGKEY-002, MAP-JOGKEY-003, MAP-JOGKEY-004, MAP-JOGKEY-005
@spec MAP-JOGKEY-006, MAP-JOGKEY-007
@spec MAP-WS-001, MAP-WS-002, MAP-WS-003, MAP-WS-004, MAP-WS-005, MAP-WS-006
@spec MAP-WS-007, MAP-WS-008, MAP-WS-009
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.events import KeyCombo, MidiEvent, WebSocketCommand
from dragonmidi.mapping import CHANNEL, OPINIONATED_MAP, MappingEngine

FADER_CCS = list(range(0, 8))  # CC 0-7 -> encoder 1-8
KNOB_CCS = list(range(16, 24))  # CC 16-23 -> encoder 9-16
MUTE_CCS = list(range(48, 56))  # CC 48-55 -> encoderReset 1-8
SOLO_CCS = list(range(32, 40))  # CC 32-39 -> WebSocket select-AX1..8 (MAP-WS-002), not OSC
BUTTON_CCS_TO_ADDRESS = {
    45: "/dragonframe/shoot",  # Transport Record
    41: "/dragonframe/play",
    43: "/dragonframe/stepBackward",  # Rewind (<<)
    44: "/dragonframe/stepForward",  # Fast Forward (>>)
    58: "/dragonframe/stepBackward",  # Previous Track
    59: "/dragonframe/stepForward",  # Next Track
}
# Stop/Cycle/Previous Marker/Next Marker are WebSocket-targeted (MAP-WS-001, 003, 006, 007),
# not OSC - tested separately below, not via BUTTON_CCS_TO_ADDRESS.
WEBSOCKET_BUTTON_CCS = [42, 46, 61, 62]
UNMAPPED_CCS = [64, 65, 70, 71, 80, 87, 60, 47]  # Record/Select/Set Marker/Return to Zero
JOG_CC = 110


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
    number=st.sampled_from(FADER_CCS + KNOB_CCS + MUTE_CCS + list(BUTTON_CCS_TO_ADDRESS)),
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
    engine.clear_axis_target(("cc", number))  # explicit OSC encoder mode (MAP-AXIS-008 default is now axis mode)
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
    if number in FADER_CCS:
        engine.clear_axis_target(("cc", number))  # explicit OSC encoder mode
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
    if number in FADER_CCS:
        engine.clear_axis_target(("cc", number))  # explicit OSC encoder mode
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


@given(cc=st.sampled_from(list(BUTTON_CCS_TO_ADDRESS)))
# @spec MAP-TABLE-003
def test_button_holding_at_max_only_fires_once_not_on_every_message(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    first = engine.process(cc_event(cc, 127), now=0.0)
    second = engine.process(cc_event(cc, 127), now=1.0)  # same value repeated, well past debounce
    assert first is not None
    assert second is None  # no new transition occurred; previous was already >= threshold


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
    if number in FADER_CCS:
        engine.clear_axis_target(("cc", number))  # explicit OSC encoder mode, so it actually dispatches
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


@given(cc=st.sampled_from(list(BUTTON_CCS_TO_ADDRESS)))
# @spec MAP-STATE-002
def test_first_ever_message_being_a_release_shape_fires_nothing(cc: int) -> None:
    # Simulates a control already held down before the app started: the app never saw
    # the original press, so its first observed message for that control is the release.
    engine = MappingEngine()
    assert ("cc", cc) not in engine.tracked_controls()
    result = engine.process(cc_event(cc, 0), now=0.0)  # release-shaped value, first ever message
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


# --- MAP-AXIS-001: gotoPosition scaling formula, continuous, no debounce ---


@given(
    number=st.sampled_from(FADER_CCS),
    axis_name=st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1, max_size=8),
    min_value=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    max_value=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    raw_value=st.integers(min_value=1, max_value=127),
)
# @spec MAP-AXIS-001
def test_axis_target_sends_gotoposition_scaled_into_min_max(number: int, axis_name: str, min_value: float, max_value: float, raw_value: int) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), axis_name, min_value, max_value)
    result = engine.process(cc_event(number, raw_value), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/axis/{axis_name}/gotoPosition"
    normalized = raw_value / 127.0
    expected_position = min_value + normalized * (max_value - min_value)
    assert result.args == (expected_position,)


@given(number=st.sampled_from(FADER_CCS), value=st.integers(min_value=0, max_value=127))
# @spec MAP-AXIS-001
def test_axis_target_repeating_identical_value_sends_only_once(number: int, value: int) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", 0.0, 100.0)
    first = engine.process(cc_event(number, value), now=0.0)
    second = engine.process(cc_event(number, value), now=0.001)
    assert first is not None
    assert second is None  # identical value is not "distinct" - no debounce needed to explain this


@given(
    number=st.sampled_from(FADER_CCS),
    values=st.lists(st.integers(min_value=0, max_value=127), min_size=2, max_size=8, unique=True),
)
# @spec MAP-AXIS-001
def test_axis_target_sends_every_distinct_value_with_no_debounce(number: int, values: list[int]) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", 0.0, 100.0)
    # Fire all distinct values at the same instant; a debounce window would drop some of these.
    results = [engine.process(cc_event(number, v), now=0.0) for v in values]
    assert all(r is not None for r in results)


@given(number=st.sampled_from(FADER_CCS), channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != CHANNEL))
# @spec MAP-AXIS-001
def test_axis_target_still_respects_the_channel_16_invariant(number: int, channel: int) -> None:
    # An axis-targeted fader is still a CC-sourced control; MAP-TABLE-001's channel
    # invariant must keep applying regardless of target type.
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", 0.0, 100.0)
    result = engine.process(cc_event(number, 100, channel=channel), now=0.0)
    assert result is None


# --- MAP-AXIS-002: no min/max validation, any real pair accepted ---


@given(
    number=st.sampled_from(FADER_CCS),
    min_value=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    max_value=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
)
# @spec MAP-AXIS-002
def test_set_axis_target_accepts_any_real_min_max_pair(number: int, min_value: float, max_value: float) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", min_value, max_value)  # must not raise, even if min > max


@given(number=st.sampled_from(FADER_CCS), constant=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
# @spec MAP-AXIS-002
def test_min_equal_max_produces_constant_output(number: int, constant: float) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", constant, constant)
    result_low = engine.process(cc_event(number, 0), now=0.0)
    result_high = engine.process(cc_event(number, 127), now=0.001)
    assert result_low is not None and result_low.args == (constant,)
    assert result_high is not None and result_high.args == (constant,)


@given(number=st.sampled_from(FADER_CCS), raw_value=st.integers(min_value=1, max_value=126))
# @spec MAP-AXIS-002
def test_inverted_min_max_produces_reversed_mapping(number: int, raw_value: int) -> None:
    # min > max is a legitimate "reversed" mapping: a higher fader value should
    # produce a *lower* position, not be rejected.
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", 100.0, 0.0)
    result = engine.process(cc_event(number, raw_value), now=0.0)
    assert result is not None
    normalized = raw_value / 127.0
    assert result.args == (100.0 + normalized * (0.0 - 100.0),)


# --- MAP-AXIS-003 / MAP-AXIS-006: picker-only at selection time, but no re-validation afterward ---


# @spec MAP-AXIS-006
def test_axis_target_fires_even_for_a_name_no_longer_considered_discovered() -> None:
    # The engine itself has no notion of a "discovered axes" list at all - that's the
    # OSC Listener's responsibility (docs/llds/osc-io.md). Restricting selection to
    # discovered names is a UI-level gate; the engine must keep sending regardless of
    # whether that name is still considered valid by anything else.
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), "NO_LONGER_DISCOVERED", 0.0, 100.0)
    result = engine.process(cc_event(0, 64), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/axis/NO_LONGER_DISCOVERED/gotoPosition"


# --- MAP-AXIS-004: fader-only restriction ---


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-004
def test_set_axis_target_succeeds_for_fader_keys(number: int) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", number), "PAN", 0.0, 100.0)  # must not raise


@given(number=st.sampled_from(KNOB_CCS + MUTE_CCS + SOLO_CCS + list(BUTTON_CCS_TO_ADDRESS)))
# @spec MAP-AXIS-004
def test_set_axis_target_rejects_non_fader_keys(number: int) -> None:
    engine = MappingEngine()
    try:
        engine.set_axis_target(("cc", number), "PAN", 0.0, 100.0)
    except ValueError:
        return
    raise AssertionError(f"expected ValueError for non-fader key ('cc', {number})")


# --- Target-switch behavior: switching discards prior dedup state for that key ---


def test_setting_an_axis_target_discards_prior_encoder_dedup_state() -> None:
    engine = MappingEngine()
    engine.clear_axis_target(("cc", 0))  # explicit OSC encoder mode
    # Establish previous-value state via the OSC-encoder target first.
    engine.process(cc_event(0, 64), now=0.0)
    assert ("cc", 0) in engine.tracked_controls()

    engine.set_axis_target(("cc", 0), "PAN", 0.0, 100.0)
    # The same raw value that would have been deduped under the old target must fire
    # again under the new target, proving the switch discarded the prior dedup state.
    result = engine.process(cc_event(0, 64), now=0.001)
    assert result is not None
    assert result.address == "/dragonframe/axis/PAN/gotoPosition"


# --- MAP-AXIS-007: clearing an axis target reverts to the opinionated encoder target ---


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-007
def test_clear_axis_target_reverts_to_opinionated_encoder(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    engine.clear_axis_target(key)

    result = engine.process(cc_event(number, 64), now=0.0)
    assert result is not None
    assert result.address == OPINIONATED_MAP[key].address
    assert not result.address.startswith("/dragonframe/axis/")


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-007
def test_clear_axis_target_discards_dedup_state_from_the_axis_target(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    engine.process(cc_event(number, 64), now=0.0)  # establish previous-value state under the axis target

    engine.clear_axis_target(key)
    # The same raw value that would have been deduped under the axis target must fire
    # again under the restored encoder target, proving the clear discarded prior state.
    result = engine.process(cc_event(number, 64), now=0.001)
    assert result is not None
    assert result.address == OPINIONATED_MAP[key].address


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-007
def test_clear_axis_target_on_a_key_with_no_axis_target_is_a_noop(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.clear_axis_target(key)  # must not raise

    result = engine.process(cc_event(number, 64), now=0.0)
    assert result is not None
    assert result.address == OPINIONATED_MAP[key].address


# --- MAP-AXIS-008 / MAP-AXIS-009: faders default to axis mode, no name, no output ---


@given(number=st.sampled_from(FADER_CCS), value=st.integers(min_value=1, max_value=127))
# @spec MAP-AXIS-008, MAP-AXIS-009
def test_fresh_fader_defaults_to_axis_mode_and_sends_nothing_until_named(number: int, value: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(number, value), now=0.0)
    assert result is None


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-008
def test_is_axis_mode_defaults_true_for_every_fader(number: int) -> None:
    engine = MappingEngine()
    assert engine.is_axis_mode(("cc", number)) is True


# --- MAP-AXIS-010: axis/encoder mode tracked independently of a chosen name ---


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-010
def test_clear_axis_target_enters_encoder_mode(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.clear_axis_target(key)
    assert engine.is_axis_mode(key) is False
    result = engine.process(cc_event(number, 100), now=0.0)
    assert result is not None
    assert result.address == OPINIONATED_MAP[key].address


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-010
def test_enter_axis_mode_without_a_name_sends_nothing_not_encoder_fallback(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.clear_axis_target(key)  # encoder mode
    engine.enter_axis_mode(key)  # back to axis mode, no name yet
    assert engine.is_axis_mode(key) is True
    result = engine.process(cc_event(number, 100), now=0.0)
    assert result is None


# --- Bank Derivation (MAP-BANK-001 through MAP-BANK-007) ---

_KNOB_BANK_OFFSET = 16
_MUTE_BANK_OFFSET = 48
_SOLO_BANK_OFFSET = 32
_KNOB_STEP_SCALE = 0.1


@given(fader_number=st.sampled_from(FADER_CCS), raw=st.integers(min_value=0, max_value=127))
# @spec MAP-BANK-001
def test_knob_first_reading_establishes_baseline_and_sends_nothing(fader_number: int, raw: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    result = engine.process(cc_event(knob_number, raw), now=0.0)
    assert result is None


@given(
    fader_number=st.sampled_from(FADER_CCS),
    first_raw=st.integers(min_value=0, max_value=127),
    second_raw=st.integers(min_value=0, max_value=127),
)
# @spec MAP-BANK-001
def test_knob_sends_step_position_as_the_change_since_its_own_last_reading(fader_number: int, first_raw: int, second_raw: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    # A wide range, with a real fader-established position safely in the middle of
    # it, so MAP-BANK-008's clamping never interferes - this test is only about the
    # delta formula; clamping (including the no-established-position default) has
    # its own dedicated tests below.
    engine.set_axis_target(fader_key, "PAN", -1000.0, 1000.0)
    engine.process(cc_event(fader_number, 64), now=-1.0)  # establishes a mid-range position
    engine.process(cc_event(knob_number, first_raw), now=0.0)  # establish baseline

    result = engine.process(cc_event(knob_number, second_raw), now=0.001)
    if second_raw == first_raw:
        assert result is None
    else:
        assert result is not None
        assert result.address == "/dragonframe/axis/PAN/stepPosition"
        assert result.args == (float(second_raw - first_raw) * _KNOB_STEP_SCALE,)


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-002
def test_mute_sends_setzero_when_bank_fader_has_axis(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    mute_number = fader_number + _MUTE_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine.process(cc_event(mute_number, 0), now=0.0)  # ensure a known not-pressed starting state
    result = engine.process(cc_event(mute_number, 127), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/axis/PAN/setZero"


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-004
def test_knob_mute_fall_back_to_static_targets_when_bank_has_no_axis(fader_number: int) -> None:
    knob_number = fader_number + _KNOB_BANK_OFFSET
    mute_number = fader_number + _MUTE_BANK_OFFSET
    engine = MappingEngine()  # fresh: bank's fader has no axis (default axis mode, no name)

    knob_result = engine.process(cc_event(knob_number, 100), now=0.0)
    engine.process(cc_event(mute_number, 0), now=0.0)
    mute_result = engine.process(cc_event(mute_number, 127), now=0.0)

    assert knob_result is not None and knob_result.address == OPINIONATED_MAP[("cc", knob_number)].address
    assert mute_result is not None and mute_result.address == OPINIONATED_MAP[("cc", mute_number)].address


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-WS-002
def test_solo_sends_select_ax_regardless_of_bank_fader_axis_state(fader_number: int) -> None:
    # Solo is unconditional on bank state (MAP-WS-002) - it behaves identically whether
    # or not Bank N's fader has an axis assigned, unlike Knob/Mute above.
    fader_key = ("cc", fader_number)
    solo_number = fader_number + _SOLO_BANK_OFFSET

    engine_with_axis = MappingEngine()
    engine_with_axis.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine_with_axis.process_websocket(cc_event(solo_number, 0), now=0.0)
    result_with_axis = engine_with_axis.process_websocket(cc_event(solo_number, 127), now=0.0)

    engine_without_axis = MappingEngine()
    engine_without_axis.process_websocket(cc_event(solo_number, 0), now=0.0)
    result_without_axis = engine_without_axis.process_websocket(cc_event(solo_number, 127), now=0.0)

    expected = WebSocketCommand(f"select-AX{fader_number + 1}")
    assert result_with_axis == expected
    assert result_without_axis == expected


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-005
def test_knob_derived_step_position_deduped_on_identical_raw_value(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine.process(cc_event(knob_number, 60), now=0.0)  # establish baseline
    first = engine.process(cc_event(knob_number, 90), now=0.001)
    second = engine.process(cc_event(knob_number, 90), now=0.002)  # identical raw value again
    assert first is not None
    assert first.address == "/dragonframe/axis/PAN/stepPosition"
    assert first.args == (30.0 * _KNOB_STEP_SCALE,)
    assert second is None


@given(fader_number=st.sampled_from(FADER_CCS), bank_base=st.sampled_from([64, 80]))
# @spec MAP-BANK-006
def test_record_and_select_stay_unmapped_regardless_of_bank_axis(fader_number: int, bank_base: int) -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", fader_number), "PAN", 0.0, 100.0)
    result = engine.process(cc_event(bank_base + fader_number, 127), now=0.0)
    assert result is None


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-007
def test_knob_dedup_discarded_on_encoder_to_axis_transition(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.clear_axis_target(fader_key)  # explicit encoder mode
    engine.process(cc_event(knob_number, 0), now=0.0)  # encoder-mode dedup stores normalized 0.0

    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)  # encoder -> axis transition
    # Without the MAP-BANK-007 discard, the stale normalized 0.0 would still be compared
    # against as if it were a raw baseline (0 - 0.0 == 0.0, a nonzero raw value like 50
    # would wrongly compute as a real delta of 50.0 instead of establishing a fresh baseline).
    first = engine.process(cc_event(knob_number, 50), now=1.0)
    assert first is None  # correctly treated as a fresh baseline, not a stale-comparison send

    second = engine.process(cc_event(knob_number, 55), now=1.001)
    assert second is not None
    assert second.address == "/dragonframe/axis/PAN/stepPosition"
    assert second.args == (5.0 * _KNOB_STEP_SCALE,)  # normal relative delta once a real baseline exists


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-007
def test_knob_dedup_not_discarded_by_a_same_mode_axis_name_change(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine.process(cc_event(knob_number, 60), now=0.0)  # establish baseline
    engine.process(cc_event(knob_number, 90), now=0.5)  # real reading, previous now = 90

    engine.set_axis_target(fader_key, "TILT", 0.0, 100.0)  # different name, still axis mode
    result = engine.process(cc_event(knob_number, 90), now=1.0)  # same raw value again
    assert result is None  # still deduped (delta=0) - no mode transition occurred


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-007
def test_enter_axis_mode_alone_discards_knob_dedup_on_transition(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.clear_axis_target(fader_key)  # encoder mode
    engine.process(cc_event(knob_number, 0), now=0.0)  # stale normalized 0.0 stored

    engine.enter_axis_mode(fader_key)  # transition back to axis mode, no name yet
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)  # already in axis mode - no further transition here
    # Proves the discard happened in enter_axis_mode itself, not (redundantly) in this set_axis_target call.
    first = engine.process(cc_event(knob_number, 50), now=1.0)
    assert first is None

    second = engine.process(cc_event(knob_number, 55), now=1.001)
    assert second is not None
    assert second.args == (5.0 * _KNOB_STEP_SCALE,)


# --- Knob position clamping (MAP-BANK-008, MAP-BANK-009) ---


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-008
def test_knob_nudge_reduced_to_reach_the_lower_bound_exactly(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 127.0)  # normalized*127 == raw_value, for easy math
    engine.process(cc_event(fader_number, 5), now=-1.0)  # establishes position 5.0
    engine.process(cc_event(knob_number, 100), now=0.0)  # establish knob baseline

    result = engine.process(cc_event(knob_number, 0), now=0.001)  # raw delta -100 -> requested delta -10.0
    assert result is not None
    assert result.address == "/dragonframe/axis/PAN/stepPosition"
    assert result.args == (-5.0,)  # reduced from -10.0 to land exactly on the 0.0 floor


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-008
def test_knob_nudge_already_at_lower_bound_sends_nothing(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 127.0)
    engine.process(cc_event(fader_number, 0), now=-1.0)  # establishes position 0.0, the floor itself
    engine.process(cc_event(knob_number, 100), now=0.0)  # establish knob baseline

    result = engine.process(cc_event(knob_number, 0), now=0.001)  # requests a further negative move
    assert result is None


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-008
def test_knob_nudge_reduced_to_reach_the_upper_bound_exactly(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 127.0)
    engine.process(cc_event(fader_number, 122), now=-1.0)  # establishes position 122.0
    engine.process(cc_event(knob_number, 0), now=0.0)  # establish knob baseline

    result = engine.process(cc_event(knob_number, 100), now=0.001)  # raw delta +100 -> requested delta +10.0
    assert result is not None
    assert result.args == (5.0,)  # reduced from +10.0 to land exactly on the 127.0 ceiling


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-008
def test_knob_clamp_bounds_are_order_independent(fader_number: int) -> None:
    """min > max (MAP-AXIS-002 permits it) still clamps against sorted(min, max)."""
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 127.0, 0.0)  # min > max
    engine.process(cc_event(fader_number, 5), now=-1.0)  # normalized*(0-127)+127 == 122.0
    engine.process(cc_event(knob_number, 0), now=0.0)  # establish knob baseline

    result = engine.process(cc_event(knob_number, 100), now=0.001)  # requested delta +10.0
    assert result is not None
    assert result.args == (5.0,)  # still clamped to the 127.0 ceiling, whichever field it came from


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-009
def test_knob_position_defaults_to_the_lower_bound_with_no_fader_send_and_no_live_reading(
    fader_number: int,
) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 127.0)  # fader never sends a gotoPosition
    engine.process(cc_event(knob_number, 100), now=0.0)  # establish knob baseline

    result = engine.process(cc_event(knob_number, 0), now=0.001)  # any negative delta
    assert result is None  # already assumed to be at the 0.0 floor


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-009
def test_knob_clamp_prefers_live_reported_position_over_internal_estimate(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)  # fader never sends -> internal estimate is 0.0 (the floor)
    engine.process(cc_event(knob_number, 50), now=0.0)  # establish knob baseline

    # Without the live reading, this delta (-5.0) would clamp against the internal
    # estimate's floor (0.0) and send nothing. With Dragonframe reporting 60.0 live,
    # it should be treated as comfortably mid-range instead.
    result = engine.process(cc_event(knob_number, 0), now=0.001, axis_positions={"PAN": 60.0})
    assert result is not None
    assert result.args == (-5.0,)


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-009
def test_knob_clamp_falls_back_to_internal_estimate_when_no_live_reading_for_this_axis(
    fader_number: int,
) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)  # internal estimate is 0.0 (the floor)
    engine.process(cc_event(knob_number, 50), now=0.0)  # establish knob baseline

    # axis_positions has no entry for "PAN" - must fall back to the internal estimate
    # (0.0), which is already at the floor, so the negative delta sends nothing.
    result = engine.process(cc_event(knob_number, 0), now=0.001, axis_positions={"OTHER_AXIS": 999.0})
    assert result is None


# --- Jog Wheel Frame Stepping (MAP-JOG-001 through MAP-JOG-005) ---


@given(raw=st.integers(min_value=1, max_value=63))
# @spec MAP-JOG-001
def test_jog_clockwise_sends_step_forward(raw: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(JOG_CC, raw), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/stepForward"


@given(raw=st.integers(min_value=65, max_value=127))
# @spec MAP-JOG-002
def test_jog_counterclockwise_sends_step_backward(raw: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(JOG_CC, raw), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/stepBackward"


@given(raw=st.sampled_from([0, 64]))
# @spec MAP-JOG-003
def test_jog_zero_or_center_value_sends_nothing(raw: int) -> None:
    engine = MappingEngine()
    assert engine.process(cc_event(JOG_CC, raw), now=0.0) is None


@given(raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127))
# @spec MAP-JOG-004
def test_jog_repeated_identical_value_fires_every_time_no_dedup(raw: int) -> None:
    # Unlike a continuous-absolute control (MAP-TABLE-002), which dedupes a repeated
    # identical value, each jog wheel message is its own physical detent and must fire
    # independently even if the raw value happens to repeat.
    engine = MappingEngine()
    first = engine.process(cc_event(JOG_CC, raw), now=0.0)
    second = engine.process(cc_event(JOG_CC, raw), now=0.001)
    assert first is not None
    assert second is not None
    assert first.address == second.address


@given(raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127))
# @spec MAP-JOG-004
def test_jog_fires_regardless_of_elapsed_time_no_debounce(raw: int) -> None:
    # No 80ms debounce window applies, unlike button-type entries (MAP-DEBOUNCE-001):
    # two messages at the same instant both fire.
    engine = MappingEngine()
    first = engine.process(cc_event(JOG_CC, raw), now=0.0)
    second = engine.process(cc_event(JOG_CC, raw), now=0.0)
    assert first is not None
    assert second is not None


@given(
    raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127),
    channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != CHANNEL),
)
# @spec MAP-TABLE-001
def test_jog_respects_the_channel_16_invariant(raw: int, channel: int) -> None:
    engine = MappingEngine()
    result = engine.process(cc_event(JOG_CC, raw, channel=channel), now=0.0)
    assert result is None


@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-JOG-005
def test_jog_allocates_no_tracked_state(raw: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(JOG_CC, raw), now=0.0)
    assert ("cc", JOG_CC) not in engine.tracked_controls()


# --- Jog Wheel Keystroke Output for Arc Motion Control (MAP-JOGKEY-001 through 007) ---

STEP_MOCO_FORWARD = KeyCombo(frozenset({"alt", "shift"}), "right")
STEP_MOCO_BACKWARD = KeyCombo(frozenset({"alt", "shift"}), "left")


@given(raw=st.integers(min_value=1, max_value=63))
# @spec MAP-JOGKEY-001
def test_jog_keystroke_clockwise_returns_step_moco_forward(raw: int) -> None:
    engine = MappingEngine()
    assert engine.process_keystroke(cc_event(JOG_CC, raw)) == STEP_MOCO_FORWARD


@given(raw=st.integers(min_value=65, max_value=127))
# @spec MAP-JOGKEY-002
def test_jog_keystroke_counterclockwise_returns_step_moco_backward(raw: int) -> None:
    engine = MappingEngine()
    assert engine.process_keystroke(cc_event(JOG_CC, raw)) == STEP_MOCO_BACKWARD


@given(raw=st.sampled_from([0, 64]))
# @spec MAP-JOGKEY-003
def test_jog_keystroke_zero_or_center_value_returns_none(raw: int) -> None:
    engine = MappingEngine()
    assert engine.process_keystroke(cc_event(JOG_CC, raw)) is None


@given(
    number=st.sampled_from(FADER_CCS + KNOB_CCS + MUTE_CCS + SOLO_CCS + list(BUTTON_CCS_TO_ADDRESS)),
    value=st.integers(min_value=0, max_value=127),
)
# @spec MAP-JOGKEY-003
def test_jog_keystroke_non_jog_wheel_control_returns_none(number: int, value: int) -> None:
    engine = MappingEngine()
    assert engine.process_keystroke(cc_event(number, value)) is None


@given(raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127))
# @spec MAP-JOGKEY-004
def test_jog_keystroke_and_osc_both_produced_for_the_same_event(raw: int) -> None:
    engine = MappingEngine()
    event = cc_event(JOG_CC, raw)
    osc_result = engine.process(event, now=0.0)
    keystroke_result = engine.process_keystroke(event)
    assert osc_result is not None
    assert keystroke_result is not None


@given(raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127))
# @spec MAP-JOGKEY-005
def test_jog_keystroke_repeated_identical_value_fires_every_time_no_dedup(raw: int) -> None:
    engine = MappingEngine()
    first = engine.process_keystroke(cc_event(JOG_CC, raw))
    second = engine.process_keystroke(cc_event(JOG_CC, raw))
    assert first is not None
    assert second is not None
    assert first == second


@given(
    raw=st.integers(min_value=1, max_value=63) | st.integers(min_value=65, max_value=127),
    channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != CHANNEL),
)
# @spec MAP-JOGKEY-006
def test_jog_keystroke_respects_the_channel_16_invariant(raw: int, channel: int) -> None:
    engine = MappingEngine()
    assert engine.process_keystroke(cc_event(JOG_CC, raw, channel=channel)) is None


@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-JOGKEY-007
def test_jog_keystroke_allocates_no_tracked_state(raw: int) -> None:
    engine = MappingEngine()
    engine.process_keystroke(cc_event(JOG_CC, raw))
    assert ("cc", JOG_CC) not in engine.tracked_controls()


# --- WebSocket-Targeted Controls (MAP-WS-001 through MAP-WS-009) ---

STOP_CC = 42
CYCLE_CC = 46
PREV_MARKER_CC = 61
NEXT_MARKER_CC = 62


# @spec MAP-WS-001
def test_stop_sends_e_stop_on_press_edge() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(STOP_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(STOP_CC, 127), now=0.0)
    assert result == WebSocketCommand("E-Stop")


# @spec MAP-WS-001, MAP-WS-009
def test_stop_produces_no_osc_output() -> None:
    engine = MappingEngine()
    engine.process(cc_event(STOP_CC, 0), now=0.0)
    assert engine.process(cc_event(STOP_CC, 127), now=0.0) is None


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-WS-002
def test_solo_n_sends_select_ax_n(fader_number: int) -> None:
    solo_number = fader_number + _SOLO_BANK_OFFSET
    engine = MappingEngine()
    engine.process_websocket(cc_event(solo_number, 0), now=0.0)
    result = engine.process_websocket(cc_event(solo_number, 127), now=0.0)
    assert result == WebSocketCommand(f"select-AX{fader_number + 1}")


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-WS-002, MAP-WS-009
def test_solo_produces_no_osc_output(fader_number: int) -> None:
    solo_number = fader_number + _SOLO_BANK_OFFSET
    engine = MappingEngine()
    engine.process(cc_event(solo_number, 0), now=0.0)
    assert engine.process(cc_event(solo_number, 127), now=0.0) is None


# @spec MAP-WS-003
def test_cycle_advances_through_axes_and_wraps() -> None:
    engine = MappingEngine()
    axes = {"PAN": 0.0, "TILT": 0.0, "ZOOM": 0.0}
    clock = [0.0]

    def press() -> "WebSocketCommand | None":
        clock[0] += 1.0  # each press well outside the 80ms debounce window
        engine.process_websocket(cc_event(CYCLE_CC, 0), now=clock[0])
        return engine.process_websocket(cc_event(CYCLE_CC, 127), now=clock[0], axis_positions=axes)

    assert press() == WebSocketCommand("select-AX1")
    assert press() == WebSocketCommand("select-AX2")
    assert press() == WebSocketCommand("select-AX3")
    assert press() == WebSocketCommand("select-AX1")  # wraps back around


# @spec MAP-WS-003
def test_cycle_reuses_axis_positions_snapshot_passed_to_process() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(CYCLE_CC, 127), now=0.0, axis_positions={"PAN": 1.0})
    assert result == WebSocketCommand("select-AX1")


# @spec MAP-WS-004
def test_cycle_with_zero_axes_produces_nothing_and_does_not_advance() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(CYCLE_CC, 127), now=0.0, axis_positions={})
    assert result is None

    # Once axes exist, the very first successful cycle still starts at AX1 - proving
    # the zero-axis press above never advanced _cycle_index.
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=1.0)
    next_result = engine.process_websocket(cc_event(CYCLE_CC, 127), now=1.0, axis_positions={"PAN": 0.0})
    assert next_result == WebSocketCommand("select-AX1")


# @spec MAP-WS-004
def test_cycle_with_none_axis_positions_treated_as_zero_axes() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(CYCLE_CC, 127), now=0.0, axis_positions=None)
    assert result is None


# @spec MAP-WS-005
def test_cycle_index_resets_on_engine_reset() -> None:
    engine = MappingEngine()
    axis_positions = {"PAN": 0.0, "TILT": 0.0}
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=0.0)
    first = engine.process_websocket(cc_event(CYCLE_CC, 127), now=0.0, axis_positions=axis_positions)
    engine.process_websocket(cc_event(CYCLE_CC, 0), now=1.0)
    engine.process_websocket(cc_event(CYCLE_CC, 127), now=1.0, axis_positions=axis_positions)  # advances to AX2

    engine.reset()

    engine.process_websocket(cc_event(CYCLE_CC, 0), now=2.0)
    after_reset = engine.process_websocket(cc_event(CYCLE_CC, 127), now=2.0, axis_positions=axis_positions)
    assert first == WebSocketCommand("select-AX1")
    assert after_reset == WebSocketCommand("select-AX1")  # back to the start, not continuing from AX2


# @spec MAP-WS-003, MAP-WS-009
def test_cycle_produces_no_osc_output() -> None:
    engine = MappingEngine()
    engine.process(cc_event(CYCLE_CC, 0), now=0.0)
    assert engine.process(cc_event(CYCLE_CC, 127), now=0.0) is None


# @spec MAP-WS-006
def test_previous_marker_sends_jog_all_backward() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(PREV_MARKER_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(PREV_MARKER_CC, 127), now=0.0)
    assert result == WebSocketCommand("Jog All", operation="+", params=(-1,))


# @spec MAP-WS-007
def test_next_marker_sends_jog_all_forward() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(NEXT_MARKER_CC, 0), now=0.0)
    result = engine.process_websocket(cc_event(NEXT_MARKER_CC, 127), now=0.0)
    assert result == WebSocketCommand("Jog All", operation="+", params=(1,))


@given(cc=st.sampled_from([PREV_MARKER_CC, NEXT_MARKER_CC]))
# @spec MAP-WS-006, MAP-WS-007, MAP-WS-009
def test_marker_produces_no_osc_output(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    assert engine.process(cc_event(cc, 127), now=0.0) is None


# --- MAP-WS-008: shared press-edge/debounce state with process()'s button entries ---


@given(
    cc=st.sampled_from([STOP_CC, CYCLE_CC, PREV_MARKER_CC, NEXT_MARKER_CC] + SOLO_CCS),
    gap=st.floats(min_value=0.0, max_value=0.079),
)
# @spec MAP-WS-008
def test_websocket_control_second_press_inside_debounce_window_is_dropped(cc: int, gap: float) -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(cc, 0), now=0.0)
    engine.process_websocket(cc_event(cc, 127), now=0.0, axis_positions={"PAN": 0.0})  # first press, fires
    engine.process_websocket(cc_event(cc, 0), now=gap / 2)  # release
    result = engine.process_websocket(cc_event(cc, 127), now=gap, axis_positions={"PAN": 0.0})
    assert result is None


@given(
    cc=st.sampled_from([STOP_CC, CYCLE_CC, PREV_MARKER_CC, NEXT_MARKER_CC] + SOLO_CCS),
    gap=st.floats(min_value=0.081, max_value=5.0),
)
# @spec MAP-WS-008
def test_websocket_control_second_press_after_debounce_window_fires(cc: int, gap: float) -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(cc, 0), now=0.0)
    engine.process_websocket(cc_event(cc, 127), now=0.0, axis_positions={"PAN": 0.0})  # first press, fires
    engine.process_websocket(cc_event(cc, 0), now=gap / 2)  # release
    result = engine.process_websocket(cc_event(cc, 127), now=gap, axis_positions={"PAN": 0.0})
    assert result is not None


@given(cc=st.sampled_from([STOP_CC, CYCLE_CC, PREV_MARKER_CC, NEXT_MARKER_CC] + SOLO_CCS))
# @spec MAP-WS-008
def test_websocket_control_holding_at_max_only_fires_once(cc: int) -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(cc, 0), now=0.0)
    first = engine.process_websocket(cc_event(cc, 127), now=0.0, axis_positions={"PAN": 0.0})
    second = engine.process_websocket(cc_event(cc, 127), now=1.0, axis_positions={"PAN": 0.0})
    assert first is not None
    assert second is None


# --- Channel-16 invariant for WebSocket-targeted controls ---


@given(
    cc=st.sampled_from([STOP_CC, CYCLE_CC, PREV_MARKER_CC, NEXT_MARKER_CC] + SOLO_CCS),
    channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != CHANNEL),
    value=st.integers(min_value=0, max_value=127),
)
# @spec MAP-WS-001 (channel invariant, mirroring MAP-TABLE-001 for the OSC path)
def test_websocket_control_on_wrong_channel_never_matches(cc: int, channel: int, value: int) -> None:
    engine = MappingEngine()
    result = engine.process_websocket(cc_event(cc, value, channel=channel), now=0.0, axis_positions={"PAN": 0.0})
    assert result is None
