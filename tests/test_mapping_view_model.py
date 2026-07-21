"""Tests for the Mapping View's pure-Python logic (docs/specs/app-ui.md § Mapping View).

@spec UI-MAP-001, UI-MAP-002, UI-MAP-004, UI-MAP-005, UI-MAP-007, UI-MAP-008
@spec UI-MAP-011, UI-MAP-012, UI-MAP-013
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.mapping import FADER_KEYS, NANOKONTROL2_PROFILE, OPINIONATED_MAP, OPINIONATED_MAP_NANOKONTROL2, MappingEngine, bank_fader_key
from dragonmidi.mapping_view_model import (
    JOG_WHEEL_ARC_ROW_KEY,
    JOG_WHEEL_ROW_KEY,
    AxisPickerState,
    axis_picker_state,
    build_rows,
    midi_source_label,
    parse_axis_field,
)

FADER_CCS = list(range(0, 8))
SOLO_CCS = list(range(32, 40))
WEBSOCKET_ROW_KEYS = [
    ("cc", 42),  # Stop
    ("cc", 46),  # Cycle
    ("solo_websocket", None),  # Solo 1-8 summary row
    ("cc", 61),  # Previous Marker
    ("cc", 62),  # Next Marker
]


# --- UI-MAP-001: one row per opinionated entry, in table order, except bank members ---


def test_build_rows_returns_one_row_per_non_bank_member_entry_in_table_order() -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    expected_keys = [key for key in OPINIONATED_MAP if bank_fader_key(key) is None]
    row_keys = [row.key for row in rows]
    # The WebSocket-targeted rows (UI-MAP-013) and the two jog wheel rows
    # (UI-MAP-012) are appended after every opinionated-map row, since none of
    # them are themselves OPINIONATED_MAP entries.
    assert row_keys[: len(expected_keys)] == expected_keys
    assert row_keys[len(expected_keys) :] == [*WEBSOCKET_ROW_KEYS, JOG_WHEEL_ROW_KEY, JOG_WHEEL_ARC_ROW_KEY]


def test_build_rows_excludes_knob_mute_rows() -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    row_keys = {row.key for row in rows}
    for key in OPINIONATED_MAP:
        if bank_fader_key(key) is not None:
            assert key not in row_keys


@given(cc=st.sampled_from(SOLO_CCS))
# @spec UI-MAP-013
def test_build_rows_excludes_individual_solo_cc_keys(cc: int) -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    row_keys = {row.key for row in rows}
    assert ("cc", cc) not in row_keys


# --- UI-MAP-002: only fader rows are editable ---


def test_only_fader_rows_are_marked_editable() -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    for row in rows:
        assert row.editable == (row.key in FADER_KEYS)


# --- Fader row target rendering: default vs. axis-targeted vs. reverted ---


@given(number=st.sampled_from(FADER_CCS))
# @spec UI-MAP-011
def test_fader_row_defaults_to_osc_axis_with_no_name_selected(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC axis"
    assert row.target == ""


@given(number=st.sampled_from(FADER_CCS))
# @spec MAP-AXIS-010
def test_fader_row_shows_osc_encoder_once_explicitly_switched(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.clear_axis_target(key)
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC encoder"
    assert row.target == f"Encoder {number + 1}"


@given(number=st.sampled_from(FADER_CCS))
def test_fader_row_shows_osc_axis_target_once_set(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC axis"
    assert row.target == "PAN (0-100)"


@given(
    number=st.sampled_from(FADER_CCS),
    axis_name=st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1, max_size=6),
    min_value=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    max_value=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
def test_fader_row_target_formatting(number: int, axis_name: str, min_value: float, max_value: float) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.set_axis_target(key, axis_name, min_value, max_value)
    rows = {row.key: row for row in build_rows(engine)}
    assert rows[key].target == f"{axis_name} ({min_value:g}-{max_value:g})"


@given(number=st.sampled_from(FADER_CCS))
def test_fader_row_reverts_to_osc_encoder_after_clear_axis_target(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    engine.clear_axis_target(key)
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC encoder"
    assert row.target == f"Encoder {number + 1}"


def test_play_row_shows_osc_action_target() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("cc", 41)]
    assert row.target_type == "OSC action"
    assert row.target == "/dragonframe/play"


def test_scene_row_shows_osc_action_target_with_no_cc_number() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("korg_scene", None)]
    assert row.target_type == "OSC action"
    assert row.target == "/dragonframe/black"
    assert row.midi_source == "Native Mode Scene"


# --- UI-MAP-013: WebSocket-targeted rows (Stop, Cycle, Solo 1-8, Marker) ---


def test_build_rows_includes_all_websocket_target_rows() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    for key in WEBSOCKET_ROW_KEYS:
        assert key in rows
        assert rows[key].target_type == "WebSocket"
        assert rows[key].editable is False


def test_stop_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("cc", 42)]
    assert row.name == "Stop"
    assert row.midi_source == "CC42, ch16"
    assert row.trigger == "Press"
    assert row.target == "E-Stop"


def test_cycle_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("cc", 46)]
    assert row.name == "Cycle"
    assert row.midi_source == "CC46, ch16"
    assert row.target == "select-AXn (cycling)"


def test_solo_summary_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("solo_websocket", None)]
    assert row.name == "Solo 1-8"
    assert row.midi_source == "CC32-39, ch16"
    assert row.target == "select-AX1 – select-AX8 (button N → AXN)"


def test_marker_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    prev_row = rows[("cc", 61)]
    next_row = rows[("cc", 62)]
    assert prev_row.name == "Previous Marker"
    assert prev_row.midi_source == "CC61, ch16"
    assert prev_row.target == "Jog All (backward)"
    assert next_row.name == "Next Marker"
    assert next_row.midi_source == "CC62, ch16"
    assert next_row.target == "Jog All (forward)"


# --- UI-MAP-012: jog wheel's two additional, non-editable rows ---


def test_build_rows_includes_both_jog_wheel_rows() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    assert JOG_WHEEL_ROW_KEY in rows
    assert JOG_WHEEL_ARC_ROW_KEY in rows


def test_jog_wheel_osc_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[JOG_WHEEL_ROW_KEY]
    assert row.name == "Jog Wheel"
    assert row.midi_source == "CC110, ch16"
    assert row.trigger == "Directional"
    assert row.target_type == "OSC action"
    assert row.target == "stepForward / stepBackward"
    assert row.editable is False


def test_jog_wheel_arc_keystroke_row_content() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[JOG_WHEEL_ARC_ROW_KEY]
    assert row.name == "Jog Wheel (Arc)"
    assert row.midi_source == "CC110, ch16"
    assert row.trigger == "Directional"
    assert row.target_type == "Keystroke"
    assert row.target == "Option+Shift+Right / Option+Shift+Left"
    assert row.editable is False


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


def test_build_rows_for_nanokontrol2_omits_jog_wheel_rows() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_rows(engine)}
    assert JOG_WHEEL_ROW_KEY not in rows
    assert JOG_WHEEL_ARC_ROW_KEY not in rows


def test_build_rows_for_nanokontrol2_omits_scene_row() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_rows(engine)}
    assert ("korg_scene", None) not in rows


def test_build_rows_for_nanokontrol2_includes_only_its_own_map_entries() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = build_rows(engine)
    expected_keys = [key for key in OPINIONATED_MAP_NANOKONTROL2 if bank_fader_key(key) is None]
    row_keys = [row.key for row in rows]
    # Same WebSocket rows as the Studio (both profiles have Stop/Cycle/Solo/Marker),
    # but no jog wheel rows appended - has_jog_wheel is false for this profile.
    assert row_keys == [*expected_keys, *WEBSOCKET_ROW_KEYS]


def test_build_rows_for_nanokontrol2_shows_its_own_channel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    rows = {row.key: row for row in build_rows(engine)}
    assert rows[("cc", 41)].midi_source == "CC41, ch1"  # Play, channel 0 zero-indexed -> "ch1"
    assert rows[("cc", 42)].midi_source == "CC42, ch1"  # Stop (WebSocket row)
    assert rows[("solo_websocket", None)].midi_source == "CC32-39, ch1"
