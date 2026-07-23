"""Tests for the Controller Profile-driven behavior of the Static Mapping Engine
(docs/specs/static-mapping.md § Controller Profile Behavior).

@spec MAP-PROFILE-001, MAP-PROFILE-002, MAP-PROFILE-003, MAP-PROFILE-004
@spec MAP-TABLE-001, MAP-JOG-000, MAP-JOGKEY-000, MAP-WS-001, MAP-WS-002
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.events import MidiEvent
from dragonmidi.mapping import (
    NANOKONTROL2_CHANNEL,
    NANOKONTROL2_PROFILE,
    OPINIONATED_MAP_NANOKONTROL2,
    OPINIONATED_MAP_STUDIO,
    STUDIO_CHANNEL,
    STUDIO_PROFILE,
    MappingEngine,
)

FADER_CCS = list(range(8))
KNOB_CCS = list(range(16, 24))
MUTE_CCS = list(range(48, 56))
BUTTON_CCS_TO_ADDRESS = {
    45: "/dragonframe/shoot",
    41: "/dragonframe/play",
    43: "/dragonframe/stepBackward",
    44: "/dragonframe/stepForward",
}
# Previous/Next Track (CC58/59) are Group-switch-targeted as of Phase 6 (MAP-GROUP-003),
# no longer OSC entries in either profile's opinionated map - excluded from this dict;
# see test_mapping.py's Group Switching section for their coverage (profile-agnostic,
# so not duplicated per-profile here).
UNMAPPED_NANOKONTROL2_CCS = [60, 64, 65, 70, 71]  # Set Marker, Record 1-8 (R buttons)


def cc_event(number: int, value: int, channel: int) -> MidiEvent:
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


# --- MIDI-PROFILE-002/003 shape ---


# @spec MIDI-PROFILE-002
def test_studio_profile_shape() -> None:
    assert STUDIO_PROFILE.name == "nanoKONTROL Studio"
    assert STUDIO_PROFILE.has_native_mode is True
    assert STUDIO_PROFILE.default_channel == STUDIO_CHANNEL == 15
    assert STUDIO_PROFILE.has_jog_wheel is True
    assert STUDIO_PROFILE.has_scene_button is True
    assert STUDIO_PROFILE.opinionated_map is OPINIONATED_MAP_STUDIO


# @spec MIDI-PROFILE-003
def test_nanokontrol2_profile_shape() -> None:
    assert NANOKONTROL2_PROFILE.name == "nanoKONTROL2"
    assert NANOKONTROL2_PROFILE.has_native_mode is False
    assert NANOKONTROL2_PROFILE.default_channel == NANOKONTROL2_CHANNEL == 0
    assert NANOKONTROL2_PROFILE.has_jog_wheel is False
    assert NANOKONTROL2_PROFILE.has_scene_button is False
    assert NANOKONTROL2_PROFILE.opinionated_map is OPINIONATED_MAP_NANOKONTROL2


# @spec MAP-PROFILE-001
def test_engine_defaults_to_studio_profile() -> None:
    assert MappingEngine().profile is STUDIO_PROFILE


# --- MAP-PROFILE-002: nanoKONTROL2's map matches the Studio's for shared controls ---


# @spec MAP-PROFILE-002
def test_nanokontrol2_map_matches_studio_map_for_every_shared_key() -> None:
    shared_keys = set(OPINIONATED_MAP_STUDIO) & set(OPINIONATED_MAP_NANOKONTROL2)
    assert shared_keys == set(OPINIONATED_MAP_NANOKONTROL2)  # nanoKONTROL2 has no keys the Studio lacks
    for key in shared_keys:
        assert OPINIONATED_MAP_STUDIO[key] == OPINIONATED_MAP_NANOKONTROL2[key]


# --- MAP-PROFILE-003: nanoKONTROL2's map omits the Scene button entry ---


# @spec MAP-PROFILE-003
def test_nanokontrol2_map_has_no_scene_button_entry() -> None:
    assert ("korg_scene", None) not in OPINIONATED_MAP_NANOKONTROL2
    assert ("korg_scene", None) in OPINIONATED_MAP_STUDIO


# @spec MAP-GROUP-003
def test_previous_next_track_are_absent_from_both_opinionated_maps() -> None:
    # Group-switch-targeted as of Phase 6, the same "removed from OPINIONATED_MAP
    # entirely" treatment MAP-WS-009 already gives Stop/Cycle/Solo/Marker, for a
    # different reason (internal-state-targeted instead of WebSocket-targeted).
    for cc in (58, 59):
        assert ("cc", cc) not in OPINIONATED_MAP_STUDIO
        assert ("cc", cc) not in OPINIONATED_MAP_NANOKONTROL2


@given(number=st.sampled_from(KNOB_CCS + MUTE_CCS + list(BUTTON_CCS_TO_ADDRESS)), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-001, MAP-PROFILE-002
def test_nanokontrol2_shared_controls_match_on_its_own_default_channel(number: int, value: int) -> None:
    # Knobs/Mute here have no bank axis assigned, so they fall back to their opinionated
    # encoder/encoderReset targets (MAP-BANK-004) - still a real match, unlike faders
    # (which default to axis mode with no name and produce nothing - MAP-AXIS-009,
    # covered separately below).
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    result = engine.process(cc_event(number, value, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is not None


@given(number=st.sampled_from(FADER_CCS), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-001, MAP-PROFILE-002, MAP-AXIS-008
def test_nanokontrol2_faders_default_to_axis_mode_like_studios(number: int, value: int) -> None:
    # Faders start in OSC axis (direct) mode with no name selected on every profile
    # (MAP-AXIS-008); this is engine-level default behavior, not profile-specific, so
    # a fresh nanoKONTROL2 engine produces nothing until a name is picked - same as
    # the Studio.
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    assert engine.process(cc_event(number, value, channel=NANOKONTROL2_CHANNEL), now=0.0) is None
    engine.set_axis_target(("cc", number), 1, "PAN", 0.0, 100.0)
    result = engine.process(cc_event(number, value, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/axis/PAN/gotoPosition"


@given(
    number=st.sampled_from(FADER_CCS + KNOB_CCS + MUTE_CCS + list(BUTTON_CCS_TO_ADDRESS)),
    channel=st.integers(min_value=0, max_value=15).filter(lambda c: c != NANOKONTROL2_CHANNEL),
    value=st.integers(min_value=1, max_value=127),
)
# @spec MAP-TABLE-001
def test_nanokontrol2_shared_controls_never_match_on_studio_channel_or_others(number: int, channel: int, value: int) -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    assert engine.process(cc_event(number, value, channel=channel), now=0.0) is None


@given(number=st.sampled_from(UNMAPPED_NANOKONTROL2_CCS), value=st.integers(min_value=1, max_value=127))
# @spec MAP-PROFILE-003, MAP-TABLE-005
def test_nanokontrol2_unmapped_controls_produce_nothing(number: int, value: int) -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    assert engine.process(cc_event(number, value, channel=NANOKONTROL2_CHANNEL), now=0.0) is None


# --- MAP-JOG-000: jog wheel dispatch is gated on has_jog_wheel ---


@given(raw=st.integers(min_value=1, max_value=127))
# @spec MAP-JOG-000
def test_nanokontrol2_never_dispatches_cc110_as_jog_wheel(raw: int) -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    # CC110 isn't in the nanoKONTROL2's opinionated map, so this exercises both the
    # has_jog_wheel gate and the fallback "no match" path landing on the same result.
    result = engine.process(cc_event(110, raw, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is None


# --- MAP-JOGKEY-000: keystroke output is gated on has_jog_wheel ---


@given(raw=st.integers(min_value=0, max_value=127))
# @spec MAP-JOGKEY-000
def test_nanokontrol2_process_keystroke_always_returns_none(raw: int) -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    event = cc_event(110, raw, channel=NANOKONTROL2_CHANNEL)
    assert engine.process_keystroke(event) is None


# --- Scene button dispatch is gated on has_scene_button ---


@given(channel=st.integers(min_value=0, max_value=15), value=st.integers(min_value=1, max_value=127))
# @spec MAP-TABLE-001, MAP-PROFILE-003
def test_nanokontrol2_never_dispatches_scene_button(channel: int, value: int) -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    assert engine.process(scene_event(channel, value), now=0.0) is None


# --- WebSocket-targeted controls: identical mechanism, profile's own channel ---


# @spec MAP-WS-001
def test_nanokontrol2_stop_produces_e_stop_on_its_own_channel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    result = engine.process_websocket(cc_event(42, 127, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is not None
    assert result.input == "E-Stop"


# @spec MAP-WS-001
def test_nanokontrol2_stop_does_not_match_on_studio_channel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    assert engine.process_websocket(cc_event(42, 127, channel=STUDIO_CHANNEL), now=0.0) is None


# @spec MAP-WS-002
def test_nanokontrol2_solo_produces_select_axn_on_its_own_channel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    result = engine.process_websocket(cc_event(35, 127, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is not None
    assert result.input == "select-AX4"  # CC32 + 3 -> Solo 4


# --- MAP-PROFILE-004: set_profile() swaps map/channel and wipes all state ---


# @spec MAP-PROFILE-004
def test_set_profile_switches_active_map_and_channel() -> None:
    engine = MappingEngine()  # starts on Studio
    assert engine.profile is STUDIO_PROFILE
    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.profile is NANOKONTROL2_PROFILE
    # A Studio-channel CC no longer matches; the same control now only matches on
    # the nanoKONTROL2's own channel.
    assert engine.process(cc_event(41, 127, channel=STUDIO_CHANNEL), now=0.0) is None
    result = engine.process(cc_event(41, 127, channel=NANOKONTROL2_CHANNEL), now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/play"


# @spec MAP-PROFILE-004
def test_set_profile_wipes_axis_assignment() -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    assert engine.axis_target(("cc", 0), 1) is not None

    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.axis_target(("cc", 0), 1) is None


# @spec MAP-PROFILE-004, MAP-AXIS-010
def test_set_profile_resets_the_engine_wide_fader_mode_to_axis() -> None:
    # The engine-wide fader mode (2026-07-23 reversal) is reset by a profile switch the
    # same way the per-fader flag it replaced was - no lingering encoder-mode override
    # survives into the newly-selected profile.
    engine = MappingEngine()
    engine.set_fader_mode(axis=False)
    assert engine.is_axis_mode() is False

    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.is_axis_mode() is True


# @spec MAP-PROFILE-004
def test_set_profile_wipes_previous_value_and_pressed_state() -> None:
    engine = MappingEngine()
    engine.process(cc_event(41, 127, channel=STUDIO_CHANNEL), now=0.0)  # Play, pressed
    assert engine.tracked_controls()

    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.tracked_controls() == set()


# @spec MAP-PROFILE-004
def test_set_profile_resets_cycle_index() -> None:
    engine = MappingEngine()
    engine.process_websocket(cc_event(46, 127, channel=STUDIO_CHANNEL), now=0.0, axis_positions={"PAN": 0.0})
    engine.set_profile(NANOKONTROL2_PROFILE)
    # After the switch, the very next Cycle press starts again from index 0 (AX1),
    # not continuing from wherever it left off under the old profile.
    result = engine.process_websocket(cc_event(46, 127, channel=NANOKONTROL2_CHANNEL), now=1.0, axis_positions={"PAN": 0.0})
    assert result is not None
    assert result.input == "select-AX1"


# @spec MAP-PROFILE-004
def test_set_profile_is_independent_of_device_being_found() -> None:
    # set_profile() is a pure MappingEngine operation - it doesn't require or wait
    # on any MIDI connection to exist; the switch takes effect immediately.
    engine = MappingEngine()
    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.profile is NANOKONTROL2_PROFILE


# @spec MAP-PROFILE-004, MAP-GROUP-007
def test_set_profile_resets_active_group() -> None:
    engine = MappingEngine()
    engine.process(cc_event(59, 0, channel=STUDIO_CHANNEL), now=0.0)
    engine.process(cc_event(59, 127, channel=STUDIO_CHANNEL), now=0.0)  # Next Track: Group 1 -> 2
    assert engine.active_group == 2

    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.active_group == 1


# @spec MAP-PROFILE-004, MAP-GROUP-008
def test_set_profile_wipes_group_axis_targets_for_every_group() -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    engine.set_axis_target(("cc", 0), 3, "TILT", 0.0, 100.0)
    assert engine.axis_target(("cc", 0), 1) is not None
    assert engine.axis_target(("cc", 0), 3) is not None

    engine.set_profile(NANOKONTROL2_PROFILE)
    assert engine.axis_target(("cc", 0), 1) is None
    assert engine.axis_target(("cc", 0), 3) is None
