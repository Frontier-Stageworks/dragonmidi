"""Tests for the Controller Profile Config Schema's `controls:` block and the
parameterized opinionated-map synthesis it drives
(docs/specs/static-mapping.md § Controller Profile Config Schema).

@spec MAP-CONFIG-001, MAP-CONFIG-002, MAP-CONFIG-003, MAP-CONFIG-004
@spec MAP-CONFIG-005, MAP-CONFIG-006, MAP-CONFIG-007, MAP-CONFIG-008
"""

from __future__ import annotations

import pytest

from dragonmidi.mapping import (
    OPINIONATED_MAP_NANOKONTROL2,
    OPINIONATED_MAP_STUDIO,
    ControlsConfig,
    ControlsConfigError,
    build_bank_membership,
    build_opinionated_map,
    build_websocket_keys,
    validate_controls_config,
)

_SHARED_TRANSPORT = {
    "record": 45,
    "play": 41,
    "stop": 42,
    "rewind": 43,
    "fast_forward": 44,
    "cycle": 46,
    "previous_marker": 61,
    "next_marker": 62,
    "previous_track": 58,
    "next_track": 59,
}

STUDIO_CONTROLS = ControlsConfig(
    faders=tuple(range(8)),
    knobs=tuple(range(16, 24)),
    mutes=tuple(range(48, 56)),
    solos=tuple(range(32, 40)),
    transport=dict(_SHARED_TRANSPORT),
    jog_wheel=110,
)

NANOKONTROL2_CONTROLS = ControlsConfig(
    faders=tuple(range(8)),
    knobs=tuple(range(16, 24)),
    mutes=tuple(range(48, 56)),
    solos=tuple(range(32, 40)),
    transport=dict(_SHARED_TRANSPORT),
    jog_wheel=None,
)


def _minimal_valid_controls(**overrides) -> ControlsConfig:
    # Distinct, non-overlapping CC blocks per field, so a test overriding one field
    # can safely assert the others' CCs are absent without accidental collisions.
    fields = dict(
        faders=tuple(range(8)),
        knobs=tuple(range(100, 108)),
        mutes=tuple(range(200, 208)),
        solos=tuple(range(300, 308)),
        transport={},
        jog_wheel=None,
    )
    fields.update(overrides)
    return ControlsConfig(**fields)


# --- MAP-CONFIG-003: migration invariant - bundled configs must reproduce the legacy maps ---


# @spec MAP-CONFIG-003, MAP-CONFIG-001
def test_studio_controls_synthesize_a_map_identical_to_the_legacy_constant() -> None:
    assert build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True) == OPINIONATED_MAP_STUDIO


# @spec MAP-CONFIG-003, MAP-CONFIG-001
def test_nanokontrol2_controls_synthesize_a_map_identical_to_the_legacy_constant() -> None:
    assert build_opinionated_map(NANOKONTROL2_CONTROLS, has_scene_button=False) == OPINIONATED_MAP_NANOKONTROL2


# --- MAP-CONFIG-001/002: the map is genuinely parameterized, not hardcoded ---


# @spec MAP-CONFIG-001, MAP-CONFIG-002
def test_build_opinionated_map_uses_the_configured_cc_numbers_not_the_real_devices() -> None:
    controls = _minimal_valid_controls(
        faders=(20, 21, 22, 23, 24, 25, 26, 27),
        transport={"play": 60},
    )
    result = build_opinionated_map(controls, has_scene_button=False)
    assert result[("cc", 20)].address == "/dragonframe/encoder/1"
    assert result[("cc", 60)].address == "/dragonframe/play"
    # The real Studio/nanoKONTROL2 CC numbers for these same controls must not leak in.
    assert ("cc", 0) not in result
    assert ("cc", 41) not in result


# @spec MAP-CONFIG-002
def test_build_opinionated_map_adds_scene_button_entry_only_when_flagged() -> None:
    controls = _minimal_valid_controls()
    with_scene = build_opinionated_map(controls, has_scene_button=True)
    without_scene = build_opinionated_map(controls, has_scene_button=False)
    assert with_scene[("korg_scene", None)].address == "/dragonframe/black"
    assert ("korg_scene", None) not in without_scene


# --- MAP-CONFIG-004: an omitted transport key produces no row, not a disabled one ---


# @spec MAP-CONFIG-004
def test_omitted_transport_key_produces_no_row() -> None:
    controls = _minimal_valid_controls(transport={"play": 41})
    result = build_opinionated_map(controls, has_scene_button=False)
    assert result[("cc", 41)].address == "/dragonframe/play"
    assert ("cc", 45) not in result  # record was never declared


# --- MAP-CONFIG-005: WebSocket-targeted keys are sourced from controls too ---


# @spec MAP-CONFIG-005
def test_build_websocket_keys_sources_solos_and_transport_entries() -> None:
    controls = _minimal_valid_controls(
        solos=(100, 101, 102, 103, 104, 105, 106, 107),
        transport={"stop": 200, "cycle": 201, "previous_marker": 202, "next_marker": 203},
    )
    keys = build_websocket_keys(controls)
    assert keys.stop == ("cc", 200)
    assert keys.cycle == ("cc", 201)
    assert keys.previous_marker == ("cc", 202)
    assert keys.next_marker == ("cc", 203)
    assert keys.solos == tuple(("cc", cc) for cc in (100, 101, 102, 103, 104, 105, 106, 107))


# @spec MAP-CONFIG-005
def test_build_websocket_keys_missing_transport_entries_are_none() -> None:
    controls = _minimal_valid_controls(transport={})
    keys = build_websocket_keys(controls)
    assert keys.stop is None
    assert keys.cycle is None
    assert keys.previous_marker is None
    assert keys.next_marker is None


# @spec MAP-CONFIG-005
def test_websocket_targeted_keys_are_absent_from_the_opinionated_map() -> None:
    # Solo/Stop/Cycle/Marker CC numbers must not also appear as OPINIONATED_MAP rows
    # (MAP-WS-009) - they're dispatched only via build_websocket_keys().
    controls = _minimal_valid_controls(
        solos=(400, 401, 402, 403, 404, 405, 406, 407),
        transport={"stop": 500, "cycle": 501, "previous_marker": 502, "next_marker": 503},
    )
    result = build_opinionated_map(controls, has_scene_button=False)
    for cc in (400, 500, 501, 502, 503):
        assert ("cc", cc) not in result


# --- MAP-CONFIG-006: faders/knobs/mutes/solos must each be exactly 8 entries ---


@pytest.mark.parametrize("field", ["faders", "knobs", "mutes", "solos"])
# @spec MAP-CONFIG-006
def test_wrong_length_control_list_fails_validation(field: str) -> None:
    controls = _minimal_valid_controls(**{field: tuple(range(7))})
    with pytest.raises(ControlsConfigError):
        validate_controls_config(controls, has_jog_wheel=False)


@pytest.mark.parametrize("field", ["faders", "knobs", "mutes", "solos"])
# @spec MAP-CONFIG-006
def test_exactly_8_entries_passes_validation(field: str) -> None:
    controls = _minimal_valid_controls(**{field: tuple(range(8))})
    validate_controls_config(controls, has_jog_wheel=False)  # must not raise


# --- MAP-CONFIG-007: jog_wheel is required when has_jog_wheel is true ---


# @spec MAP-CONFIG-007
def test_missing_jog_wheel_fails_validation_when_has_jog_wheel_true() -> None:
    controls = _minimal_valid_controls(jog_wheel=None)
    with pytest.raises(ControlsConfigError):
        validate_controls_config(controls, has_jog_wheel=True)


# @spec MAP-CONFIG-007
def test_present_jog_wheel_passes_validation_when_has_jog_wheel_true() -> None:
    controls = _minimal_valid_controls(jog_wheel=110)
    validate_controls_config(controls, has_jog_wheel=True)  # must not raise


# @spec MAP-CONFIG-007
def test_jog_wheel_absent_is_fine_when_has_jog_wheel_false() -> None:
    controls = _minimal_valid_controls(jog_wheel=None)
    validate_controls_config(controls, has_jog_wheel=False)  # must not raise


# --- MAP-CONFIG-008: bank membership is positional, not CC-arithmetic ---


# @spec MAP-CONFIG-008
def test_bank_membership_pairs_by_index_not_cc_offset() -> None:
    # Knobs/mutes deliberately NOT offset-aligned with faders (unlike every real
    # nanoKONTROL device) - a config-arithmetic approach would fail to associate
    # these with any fader at all. Index 0 of each list is Bank 1, etc.
    controls = _minimal_valid_controls(
        faders=(0, 1, 2, 3, 4, 5, 6, 7),
        knobs=(100, 101, 102, 103, 104, 105, 106, 107),
        mutes=(200, 201, 202, 203, 204, 205, 206, 207),
    )
    membership = build_bank_membership(controls)
    assert membership["knob_to_fader"][("cc", 100)] == ("cc", 0)
    assert membership["knob_to_fader"][("cc", 107)] == ("cc", 7)
    assert membership["mute_to_fader"][("cc", 200)] == ("cc", 0)
    assert membership["fader_to_knob"][("cc", 0)] == ("cc", 100)
    assert membership["fader_keys"] == frozenset(("cc", cc) for cc in range(8))


# @spec MAP-CONFIG-008
def test_bank_membership_matches_legacy_offsets_for_the_bundled_layout() -> None:
    # The two shipped controllers' CCs happen to be offset-aligned (knobs = faders
    # + 16, mutes = faders + 48) - confirms the positional mechanism reproduces the
    # same pairing the old CC-arithmetic approach gave for this specific layout.
    membership = build_bank_membership(STUDIO_CONTROLS)
    for fader_cc in range(8):
        assert membership["knob_to_fader"][("cc", fader_cc + 16)] == ("cc", fader_cc)
        assert membership["mute_to_fader"][("cc", fader_cc + 48)] == ("cc", fader_cc)
