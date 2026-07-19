"""Tests for the Mapping View's pure-Python logic (docs/specs/app-ui.md § Mapping View).

@spec UI-MAP-001, UI-MAP-002, UI-MAP-004, UI-MAP-005, UI-MAP-007, UI-MAP-008
"""
from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.mapping import FADER_KEYS, OPINIONATED_MAP, MappingEngine
from dragonmidi.mapping_view_model import (
    AxisPickerState,
    axis_picker_state,
    build_rows,
    midi_source_label,
    parse_axis_field,
)

FADER_CCS = list(range(0, 8))


# --- UI-MAP-001: one row per opinionated entry, in table order ---

def test_build_rows_returns_one_row_per_opinionated_entry_in_table_order() -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    assert [row.key for row in rows] == list(OPINIONATED_MAP.keys())


# --- UI-MAP-002: only fader rows are editable ---

def test_only_fader_rows_are_marked_editable() -> None:
    engine = MappingEngine()
    rows = build_rows(engine)
    for row in rows:
        assert row.editable == (row.key in FADER_KEYS)


# --- Fader row target rendering: default vs. axis-targeted vs. reverted ---

@given(number=st.sampled_from(FADER_CCS))
def test_fader_row_defaults_to_its_opinionated_osc_encoder_target(number: int) -> None:
    key = ("cc", number)
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC encoder"
    assert row.target == f"Encoder {number + 1}"


def test_fader_row_shows_osc_axis_target_once_set() -> None:
    key = ("cc", 0)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC axis"
    assert row.target == "PAN (0-100)"


def test_fader_row_target_formatting_handles_non_integer_and_negative_bounds() -> None:
    key = ("cc", 1)
    engine = MappingEngine()
    engine.set_axis_target(key, "TILT", -5.5, 12.25)
    rows = {row.key: row for row in build_rows(engine)}
    assert rows[key].target == "TILT (-5.5-12.25)"


def test_fader_row_reverts_to_osc_encoder_after_clear_axis_target() -> None:
    key = ("cc", 2)
    engine = MappingEngine()
    engine.set_axis_target(key, "PAN", 0.0, 100.0)
    engine.clear_axis_target(key)
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[key]
    assert row.target_type == "OSC encoder"
    assert row.target == "Encoder 3"


# --- Non-fader row target rendering: OSC action / OSC encoder (reset) ---

def test_knob_row_shows_osc_encoder_target() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("cc", 16)]  # Knob 1 -> encoder 9
    assert row.target_type == "OSC encoder"
    assert row.target == "Encoder 9"


def test_mute_row_shows_encoder_reset_target() -> None:
    engine = MappingEngine()
    rows = {row.key: row for row in build_rows(engine)}
    row = rows[("cc", 48)]  # Mute 1 -> reset encoder 1
    assert row.target_type == "OSC encoder"
    assert row.target == "Reset encoder 1"


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


# --- MIDI source labels ---

@given(number=st.integers(min_value=0, max_value=127))
def test_midi_source_label_for_cc_controls(number: int) -> None:
    assert midi_source_label(("cc", number)) == f"CC{number}, ch16"


def test_midi_source_label_for_scene_button() -> None:
    assert midi_source_label(("korg_scene", None)) == "Native Mode Scene"


# --- UI-MAP-004 / UI-MAP-005: axis picker's three discovery-state renderings ---

def test_axis_picker_state_disabled_with_discovering_placeholder_when_never_queried() -> None:
    state = axis_picker_state(configured_name=None, axes=None)
    assert state == AxisPickerState(enabled=False, placeholder="Discovering…", candidates=(), current=None)


def test_axis_picker_state_disabled_with_no_axes_placeholder_when_queried_empty() -> None:
    state = axis_picker_state(configured_name=None, axes={})
    assert state == AxisPickerState(enabled=False, placeholder="No axes found", candidates=(), current=None)


def test_axis_picker_state_enabled_with_sorted_candidates_when_axes_present() -> None:
    state = axis_picker_state(configured_name=None, axes={"PAN": 1.0, "ARM": 2.0, "TILT": 3.0})
    assert state.enabled is True
    assert state.placeholder is None
    assert state.candidates == ("ARM", "PAN", "TILT")


# --- UI-MAP-008: configured name is always carried through as `current`, even if stale ---

@given(
    configured_name=st.one_of(st.none(), st.text(min_size=1, max_size=10)),
    axes=st.one_of(
        st.none(),
        st.dictionaries(st.text(min_size=1, max_size=10), st.floats(allow_nan=False, allow_infinity=False)),
    ),
)
def test_axis_picker_state_always_carries_the_configured_name_through_as_current(
    configured_name: str | None, axes: dict[str, float] | None
) -> None:
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


@given(text=st.sampled_from(["", "abc", "1.2.3", "--5", "PAN", "12,5"]))
def test_parse_axis_field_rejects_unparseable_text(text: str) -> None:
    assert parse_axis_field(text) is None
