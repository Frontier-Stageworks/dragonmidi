"""Tests for the Mapping View's and Configuration Dialog's pure-Python logic
(docs/specs/app-ui.md § Mapping View, § Configuration Dialog).

@spec UI-MAP-001, UI-MAP-002, UI-MAP-004, UI-MAP-005, UI-MAP-007, UI-MAP-008
@spec UI-MAP-011, UI-MAP-014, UI-MAP-015, UI-MAP-017
@spec UI-CFGDLG-002, UI-CFGDLG-006, UI-CFGDLG-007, UI-CFGDLG-008, UI-CFGDLG-009
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.events import MidiEvent
from dragonmidi.mapping import CHANNEL, NANOKONTROL2_PROFILE, STUDIO_PROFILE, MappingEngine
from dragonmidi.mapping_view_model import (
    JOG_WHEEL_ARC_ROW_KEY,
    JOG_WHEEL_ROW_KEY,
    KNOB_ROW_KEY,
    MUTE_ROW_KEY,
    SOLO_ROW_KEY,
    AxisPickerState,
    active_group_lights,
    axis_picker_state,
    build_configuration_rows,
    build_fader_rows,
    group_axis_picker_states,
    midi_source_label,
    parse_axis_field,
)

FADER_CCS = list(range(0, 8))
PREV_TRACK_CC = 58
NEXT_TRACK_CC = 59
WEBSOCKET_ROW_KEYS = [
    ("cc", 42),  # Stop
    ("cc", 46),  # Cycle
    SOLO_ROW_KEY,
    ("cc", 61),  # Previous Marker
    ("cc", 62),  # Next Marker
]
GROUP_SWITCH_ROW_KEYS = [
    ("cc", PREV_TRACK_CC),  # Previous Track
    ("cc", NEXT_TRACK_CC),  # Next Track
]


def cc_event_for_track(number: int, value: int, channel: int = CHANNEL) -> MidiEvent:
    return MidiEvent(
        type="cc",
        channel=channel,
        number=number,
        raw_value=value,
        normalized=value / 127.0,
        is_press=value > 0,
        is_release=value == 0,
    )


# --- UI-MAP-001: Mapping View is fader rows only, one per Bank, in Bank order ---


def test_build_fader_rows_returns_exactly_the_eight_bank_fader_keys_in_order() -> None:
    engine = MappingEngine()
    rows = build_fader_rows(engine)
    assert [row.key for row in rows] == list(STUDIO_PROFILE.bank_fader_keys)


def test_build_fader_rows_are_all_editable() -> None:
    engine = MappingEngine()
    rows = build_fader_rows(engine)
    assert all(row.editable for row in rows)


def test_build_fader_rows_shows_name_and_midi_source() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_fader_rows(engine)}
    row = rows[("cc", 0)]
    assert row.name == STUDIO_PROFILE.control_names[("cc", 0)]
    assert row.midi_source == "CC0, ch16"


# --- UI-CFGDLG-002: Configuration Dialog excludes the Fader row entirely ---


def test_build_configuration_rows_excludes_every_fader_key() -> None:
    engine = MappingEngine()
    rows = build_configuration_rows(engine)
    row_keys = {row.key for row in rows}
    for key in STUDIO_PROFILE.fader_keys:
        assert key not in row_keys


@given(cc=st.sampled_from(list(range(32, 40))))
# @spec UI-CFGDLG-007
def test_build_configuration_rows_excludes_individual_solo_cc_keys(cc: int) -> None:
    engine = MappingEngine()
    rows = build_configuration_rows(engine)
    row_keys = {row.key for row in rows}
    assert ("cc", cc) not in row_keys


@given(cc=st.sampled_from(list(range(16, 24)) + list(range(48, 56))))
# @spec UI-CFGDLG-006
def test_build_configuration_rows_excludes_individual_knob_and_mute_cc_keys(cc: int) -> None:
    engine = MappingEngine()
    rows = build_configuration_rows(engine)
    row_keys = {row.key for row in rows}
    assert ("cc", cc) not in row_keys


def test_build_configuration_rows_are_never_editable() -> None:
    engine = MappingEngine()
    rows = build_configuration_rows(engine)
    assert all(row.editable is False for row in rows)


# --- UI-CFGDLG-006: Knob (pot) and Mute collapse to one static-text row each ---


def test_knob_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[KNOB_ROW_KEY]
    assert row.name == "Knob (pot)"
    assert row.midi_source == "CC16-23, ch16"
    assert "Encoder 9-16" in row.target
    assert "Bank-derived" in row.target


def test_mute_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[MUTE_ROW_KEY]
    assert row.name == "Mute"
    assert row.midi_source == "CC48-55, ch16"
    assert "Reset encoder 1-8" in row.target
    assert "Bank-derived" in row.target


def test_knob_row_content_is_not_recomputed_by_active_group() -> None:
    # Unlike Solo (below), Knob/Mute describe a shared rule, not a live per-Group
    # value - the active Group must not change their text.
    engine = MappingEngine()
    before = {row.key: row for row in build_configuration_rows(engine)}[KNOB_ROW_KEY].target
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 0), now=0.0)
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 127), now=0.0)  # Group 1 -> 2
    after = {row.key: row for row in build_configuration_rows(engine)}[KNOB_ROW_KEY].target
    assert before == after


# --- UI-CFGDLG-007: Solo summary row, Group-aware text ---


def test_solo_summary_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[SOLO_ROW_KEY]
    assert row.name == "Solo 1-8"
    assert row.midi_source == "CC32-39, ch16"
    assert row.target == "select-AX1 – select-AX8 (Group 1)"


def test_solo_summary_row_target_follows_the_active_group() -> None:
    engine = MappingEngine()
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 0), now=0.0)
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 127), now=0.0)  # Next Track: Group 1 -> 2
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[SOLO_ROW_KEY]
    assert row.target == "select-AX9 – select-AX16 (Group 2)"


# --- Single-instance rows: unchanged content, relocated ---


def test_play_row_shows_osc_action_target() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("cc", 41)]
    assert row.target == "/dragonframe/play"


def test_scene_row_shows_osc_action_target_with_no_cc_number() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("korg_scene", None)]
    assert row.target == "/dragonframe/black"
    assert row.midi_source == "Native Mode Scene"


def test_build_configuration_rows_includes_all_websocket_target_rows() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    for key in WEBSOCKET_ROW_KEYS:
        assert key in rows
        assert rows[key].editable is False


def test_stop_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("cc", 42)]
    assert row.name == "Stop"
    assert row.midi_source == "CC42, ch16"
    assert row.target == "E-Stop"


def test_cycle_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("cc", 46)]
    assert row.name == "Cycle"
    assert row.midi_source == "CC46, ch16"
    assert row.target == "select-AXn (cycling)"


def test_marker_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    prev_row = rows[("cc", 61)]
    next_row = rows[("cc", 62)]
    assert prev_row.name == "Previous Marker"
    assert prev_row.midi_source == "CC61, ch16"
    assert prev_row.target == "Jog All (backward)"
    assert next_row.name == "Next Marker"
    assert next_row.midi_source == "CC62, ch16"
    assert next_row.target == "Jog All (forward)"


# --- UI-CFGDLG-008: jog wheel's two additional, non-editable rows ---


def test_build_configuration_rows_includes_both_jog_wheel_rows() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    assert JOG_WHEEL_ROW_KEY in rows
    assert JOG_WHEEL_ARC_ROW_KEY in rows


def test_jog_wheel_osc_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[JOG_WHEEL_ROW_KEY]
    assert row.name == "Jog Wheel"
    assert row.midi_source == "CC110, ch16"
    assert row.target == "stepForward / stepBackward"
    assert row.editable is False


def test_jog_wheel_arc_keystroke_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[JOG_WHEEL_ARC_ROW_KEY]
    assert row.name == "Jog Wheel (Arc)"
    assert row.midi_source == "CC110, ch16"
    assert row.target == "Option+Shift+Right / Option+Shift+Left"
    assert row.editable is False


# --- UI-CFGDLG-009: Previous/Next Track's fixed rows ---


def test_previous_track_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("cc", PREV_TRACK_CC)]
    assert row.name == "Previous Track"
    assert row.midi_source == "CC58, ch16"
    assert row.target == "Previous (wraps 5→1)"
    assert row.editable is False


def test_next_track_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_configuration_rows(engine)}
    row = rows[("cc", NEXT_TRACK_CC)]
    assert row.name == "Next Track"
    assert row.midi_source == "CC59, ch16"
    assert row.target == "Next (wraps 5→1)"
    assert row.editable is False


# --- UI-MAP-014: 5 Group axis pickers per fader row ---


def test_group_axis_picker_states_returns_five_states() -> None:
    engine = MappingEngine()
    states = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0, "TILT": 0.0})
    assert len(states) == 5
    assert all(isinstance(s, AxisPickerState) for s in states)


def test_group_axis_picker_states_reflects_each_groups_own_assignment() -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    engine.set_axis_target(("cc", 0), 3, "TILT", 0.0, 100.0)
    states = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0, "TILT": 0.0})
    assert states[0].current == "PAN"  # Group 1
    assert states[1].current is None  # Group 2, unassigned
    assert states[2].current == "TILT"  # Group 3
    assert states[3].current is None  # Group 4
    assert states[4].current is None  # Group 5


def test_group_axis_picker_states_are_independent_of_editing_a_different_group() -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    before = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0})[0]
    engine.set_axis_target(("cc", 0), 3, "TILT", 0.0, 100.0)
    after = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0, "TILT": 0.0})[0]
    assert before.current == after.current == "PAN"  # Group 1's picker unaffected by Group 3's edit


def test_group_axis_picker_states_are_unaffected_by_the_engine_wide_fader_mode() -> None:
    # @spec UI-MAP-018: the Mapping View's picker grid displays regardless of mode.
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    engine.set_fader_mode(axis=False)
    states = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0})
    assert states[0].current == "PAN"


# --- UI-MAP-017: clearing one picker leaves other groups intact ---


def test_clearing_one_group_leaves_other_groups_intact() -> None:
    engine = MappingEngine()
    engine.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    engine.set_axis_target(("cc", 0), 2, "TILT", 0.0, 100.0)
    engine.clear_group_axis_target(("cc", 0), 1)
    states = group_axis_picker_states(engine, ("cc", 0), axes={"PAN": 0.0, "TILT": 0.0})
    assert states[0].current is None  # Group 1 cleared
    assert states[1].current == "TILT"  # Group 2 untouched


# --- UI-MAP-015: Group indicator lights ---


def test_active_group_lights_returns_five_booleans_with_group_1_lit_by_default() -> None:
    engine = MappingEngine()
    lights = active_group_lights(engine)
    assert lights == (True, False, False, False, False)


def test_active_group_lights_follows_track_presses() -> None:
    engine = MappingEngine()
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 0), now=0.0)
    engine.process(cc_event_for_track(NEXT_TRACK_CC, 127), now=0.0)
    lights = active_group_lights(engine)
    assert lights == (False, True, False, False, False)


# --- MIDI source labels ---


@given(number=st.integers(min_value=0, max_value=127), channel=st.integers(min_value=0, max_value=15))
def test_midi_source_label_for_cc_controls(number: int, channel: int) -> None:
    assert midi_source_label(("cc", number), channel) == f"CC{number}, ch{channel + 1}"


def test_midi_source_label_for_scene_button() -> None:
    assert midi_source_label(("korg_scene", None), channel=15) == "Native Mode Scene"


# --- UI-MAP-004 / UI-MAP-005: axis picker's three discovery-state renderings ---


def test_axis_picker_state_disabled_with_discovering_placeholder_when_never_queried() -> None:
    state = axis_picker_state(configured_name=None, axes=None)
    assert state == AxisPickerState(enabled=False, placeholder="Discovering…", candidates=(), current=None)


def test_axis_picker_state_disabled_with_no_axes_placeholder_when_queried_empty() -> None:
    state = axis_picker_state(configured_name=None, axes={})
    assert state == AxisPickerState(enabled=False, placeholder="No axes found", candidates=(), current=None)


@given(axes=st.dictionaries(st.text(min_size=1, max_size=8), st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=10))
def test_axis_picker_state_enabled_with_sorted_candidates_when_axes_present(axes: dict[str, float]) -> None:
    state = axis_picker_state(configured_name=None, axes=axes)
    assert state.enabled is True
    assert state.placeholder is None
    assert state.candidates == tuple(sorted(axes))


# --- UI-MAP-008: configured name is always carried through as `current`, even if stale ---


@given(
    configured_name=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    axes=st.one_of(
        st.none(),
        st.dictionaries(st.text(min_size=1, max_size=10), st.floats(allow_nan=False, allow_infinity=False)),
    ),
)
def test_axis_picker_state_always_carries_the_configured_name_through_as_current(configured_name: str | None, axes: dict[str, float] | None) -> None:
    state = axis_picker_state(configured_name=configured_name, axes=axes)
    assert state.current == configured_name


def test_axis_picker_state_current_can_be_absent_from_candidates_when_stale() -> None:
    # The picker must not drop or replace a configured name just because it no
    # longer appears in the live discovered list (MAP-AXIS-006's UI-side counterpart).
    state = axis_picker_state(configured_name="GONE", axes={"PAN": 1.0})
    assert state.current == "GONE"
    assert "GONE" not in state.candidates


# --- UI-MAP-007: min/max field parsing ---


@given(value=st.floats(allow_nan=False, allow_infinity=False))
def test_parse_axis_field_accepts_any_real_number(value: float) -> None:
    assert parse_axis_field(repr(value)) == value


def _not_a_float(text: str) -> bool:
    try:
        float(text)
        return False
    except ValueError:
        return True


@given(text=st.text(max_size=12).filter(_not_a_float))
def test_parse_axis_field_rejects_unparseable_text(text: str) -> None:
    assert parse_axis_field(text) is None


# --- Controller Profile-driven rows: nanoKONTROL2 omits jog wheel/Scene rows ---


def test_build_configuration_rows_for_nanokontrol2_omits_jog_wheel_rows() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_configuration_rows(engine)}
    assert JOG_WHEEL_ROW_KEY not in rows
    assert JOG_WHEEL_ARC_ROW_KEY not in rows


def test_build_configuration_rows_for_nanokontrol2_omits_scene_row() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_configuration_rows(engine)}
    assert ("korg_scene", None) not in rows


def test_build_configuration_rows_for_nanokontrol2_shows_its_own_channel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_configuration_rows(engine)}
    assert rows[("cc", 41)].midi_source == "CC41, ch1"  # Play, channel 0 zero-indexed -> "ch1"
    assert rows[("cc", 42)].midi_source == "CC42, ch1"  # Stop (WebSocket row)
    assert rows[SOLO_ROW_KEY].midi_source == "CC32-39, ch1"
    assert rows[KNOB_ROW_KEY].midi_source == "CC16-23, ch1"
    assert rows[MUTE_ROW_KEY].midi_source == "CC48-55, ch1"


def test_build_fader_rows_for_nanokontrol2_returns_its_own_eight_bank_fader_keys() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = build_fader_rows(engine)
    assert [row.key for row in rows] == list(NANOKONTROL2_PROFILE.bank_fader_keys)
