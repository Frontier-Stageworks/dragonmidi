"""Tests for the Static Mapping Engine (docs/specs/static-mapping.md).

@spec MAP-TABLE-001, MAP-TABLE-002, MAP-TABLE-003, MAP-TABLE-005
@spec MAP-DEBOUNCE-001, MAP-STATE-001, MAP-STATE-002
@spec MAP-AXIS-001, MAP-AXIS-002, MAP-AXIS-004, MAP-AXIS-006, MAP-AXIS-007
@spec MAP-AXIS-008, MAP-AXIS-009, MAP-AXIS-010
@spec MAP-BANK-001, MAP-BANK-002, MAP-BANK-003, MAP-BANK-004, MAP-BANK-005, MAP-BANK-006, MAP-BANK-007
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.events import MidiEvent
from dragonmidi.mapping import CHANNEL, OPINIONATED_MAP, MappingEngine

FADER_CCS = list(range(0, 8))  # CC 0-7 -> encoder 1-8
KNOB_CCS = list(range(16, 24))  # CC 16-23 -> encoder 9-16
MUTE_CCS = list(range(48, 56))  # CC 48-55 -> encoderReset 1-8
SOLO_CCS = list(range(32, 40))  # CC 32-39 -> encoderReset 9-16
BUTTON_CCS_TO_ADDRESS = {
    45: "/dragonframe/shoot",  # Transport Record
    41: "/dragonframe/play",
    42: "/dragonframe/live",  # Stop
    46: "/dragonframe/loop",  # Cycle
    43: "/dragonframe/stepBackward",  # Rewind (<<)
    44: "/dragonframe/stepForward",  # Fast Forward (>>)
    61: "/dragonframe/stepBackward",  # Previous Marker
    62: "/dragonframe/stepForward",  # Next Marker
    58: "/dragonframe/stepBackward",  # Previous Track
    59: "/dragonframe/stepForward",  # Next Track
}
UNMAPPED_CCS = [64, 65, 70, 71, 80, 87, 60, 47, 110]  # Record/Select/Set Marker/Return to Zero/Jog wheel


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


@given(cc=st.sampled_from(SOLO_CCS))
# @spec MAP-TABLE-003
def test_solo_resets_matching_encoder(cc: int) -> None:
    engine = MappingEngine()
    engine.process(cc_event(cc, 0), now=0.0)
    result = engine.process(cc_event(cc, 127), now=0.0)
    assert result is not None
    assert result.address == f"/dragonframe/encoderReset/{cc - 32 + 9}"


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
def test_axis_target_sends_gotoposition_scaled_into_min_max(
    number: int, axis_name: str, min_value: float, max_value: float, raw_value: int
) -> None:
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
def test_knob_sends_step_position_as_the_change_since_its_own_last_reading(
    fader_number: int, first_raw: int, second_raw: int
) -> None:
    fader_key = ("cc", fader_number)
    knob_number = fader_number + _KNOB_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine.process(cc_event(knob_number, first_raw), now=0.0)  # establish baseline

    result = engine.process(cc_event(knob_number, second_raw), now=0.001)
    if second_raw == first_raw:
        assert result is None
    else:
        assert result is not None
        assert result.address == "/dragonframe/axis/PAN/stepPosition"
        assert result.args == (float(second_raw - first_raw),)


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
# @spec MAP-BANK-003
def test_solo_sends_sethome_when_bank_fader_has_axis(fader_number: int) -> None:
    fader_key = ("cc", fader_number)
    solo_number = fader_number + _SOLO_BANK_OFFSET
    engine = MappingEngine()
    engine.set_axis_target(fader_key, "PAN", 0.0, 100.0)
    engine.process(cc_event(solo_number, 0), now=0.0)
    result = engine.process(cc_event(solo_number, 127), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/axis/PAN/setHome"


@given(fader_number=st.sampled_from(FADER_CCS))
# @spec MAP-BANK-004
def test_knob_mute_solo_fall_back_to_static_targets_when_bank_has_no_axis(fader_number: int) -> None:
    knob_number = fader_number + _KNOB_BANK_OFFSET
    mute_number = fader_number + _MUTE_BANK_OFFSET
    solo_number = fader_number + _SOLO_BANK_OFFSET
    engine = MappingEngine()  # fresh: bank's fader has no axis (default axis mode, no name)

    knob_result = engine.process(cc_event(knob_number, 100), now=0.0)
    engine.process(cc_event(mute_number, 0), now=0.0)
    mute_result = engine.process(cc_event(mute_number, 127), now=0.0)
    engine.process(cc_event(solo_number, 0), now=0.0)
    solo_result = engine.process(cc_event(solo_number, 127), now=0.0)

    assert knob_result is not None and knob_result.address == OPINIONATED_MAP[("cc", knob_number)].address
    assert mute_result is not None and mute_result.address == OPINIONATED_MAP[("cc", mute_number)].address
    assert solo_result is not None and solo_result.address == OPINIONATED_MAP[("cc", solo_number)].address


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
    assert first.args == (30.0,)
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
    assert second.args == (5.0,)  # normal relative delta once a real baseline exists


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
    assert second.args == (5.0,)
