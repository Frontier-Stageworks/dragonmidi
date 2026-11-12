"""Tests for the Control Descriptor (docs/specs/app-ui.md § Control Descriptor).

@spec UI-CTRLDESC-001, UI-CTRLDESC-002, UI-CTRLDESC-003, UI-CTRLDESC-004
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dragonmidi.control_descriptor import ControlDescriptor, build_control_descriptors
from dragonmidi.grid_controller import Ready, build_grid_controller
from dragonmidi.grid_modules import ModuleType
from dragonmidi.grid_topology import GridModule, GridTopology
from dragonmidi.mapping import NANOKONTROL2_PROFILE, STUDIO_PROFILE, MappingEngine
from dragonmidi.mapping_view_model import (
    JOG_WHEEL_ARC_ROW_KEY,
    JOG_WHEEL_ROW_KEY,
    KNOB_ROW_KEY,
    MUTE_ROW_KEY,
    SOLO_ROW_KEY,
    build_configuration_rows,
    build_fader_rows,
)


def _descriptors(engine: MappingEngine) -> list[ControlDescriptor]:
    return build_control_descriptors(build_fader_rows(engine), build_configuration_rows(engine), engine.profile)


def _vsn1_controller(x: int = 0):
    module = GridModule(heartbeat_type=0, hwcfg=49, module_type=ModuleType.VSN1, x=x, y=0, rotation=0)
    outcome = build_grid_controller(GridTopology(modules=(module,), current_page=0))
    assert isinstance(outcome, Ready)
    return outcome.controller


# @spec UI-CTRLDESC-001
def test_fader_rows_come_first_in_their_own_order() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    fader_rows = build_fader_rows(engine)
    assert descriptors[: len(fader_rows)] == [ControlDescriptor(key=row.key, label=row.name, control_type="fader") for row in fader_rows]


# @spec UI-CTRLDESC-002
def test_every_fader_row_descriptor_is_fader_type() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    fader_keys = {row.key for row in build_fader_rows(engine)}
    assert all(d.control_type == "fader" for d in descriptors if d.key in fader_keys)


# @spec UI-CTRLDESC-004
def test_knob_mute_solo_are_expanded_per_real_key_not_collapsed() -> None:
    """Phase 1.1: per-channel grouping needs to know *which bank* each
    Knob/Mute/Solo belongs to, which the single collapsed summary row can't
    express - so each real key gets its own descriptor instead."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptor_keys = {d.key for d in _descriptors(engine)}
    assert KNOB_ROW_KEY not in descriptor_keys  # the collapsed sentinel - gone
    assert MUTE_ROW_KEY not in descriptor_keys
    assert SOLO_ROW_KEY not in descriptor_keys
    for knob_key in STUDIO_PROFILE.knob_to_fader:
        assert knob_key in descriptor_keys
    for mute_key in STUDIO_PROFILE.mute_to_fader:
        assert mute_key in descriptor_keys
    for solo_key in STUDIO_PROFILE.websocket_keys.solos:
        assert solo_key in descriptor_keys


# @spec UI-CTRLDESC-002, UI-CTRLDESC-004
def test_knob_mute_solo_labels_and_types() -> None:
    """Phase 1.2: a Knob-role control is physically a Rotary, distinct from
    the generic Button shape Mute/Solo remain."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = {d.key: d for d in _descriptors(engine)}
    first_knob_key = next(iter(STUDIO_PROFILE.knob_to_fader))
    first_mute_key = next(iter(STUDIO_PROFILE.mute_to_fader))
    first_solo_key = STUDIO_PROFILE.websocket_keys.solos[0]
    assert descriptors[first_knob_key].label == STUDIO_PROFILE.control_names[first_knob_key]
    assert descriptors[first_mute_key].label == STUDIO_PROFILE.control_names[first_mute_key]
    assert descriptors[first_solo_key].label == "Solo"
    assert descriptors[first_knob_key].control_type == "rotary"
    assert descriptors[first_mute_key].control_type == "button"
    assert descriptors[first_solo_key].control_type == "button"


# @spec UI-CTRLDESC-002
def test_jog_wheel_row_classifies_as_jog() -> None:
    """Phase 1.2: the jog wheel's own physical shape, distinct from an
    ordinary button, even though it gets no Inspector editor yet."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = {d.key: d for d in _descriptors(engine)}
    assert descriptors[JOG_WHEEL_ROW_KEY].control_type == "jog"


# @spec UI-CTRLDESC-002
def test_jog_wheel_arc_row_is_collapsed_into_the_same_jog_wheel_descriptor() -> None:
    """Phase 1.5.1: there is only one physical jog wheel.
    `JOG_WHEEL_ARC_ROW_KEY` is `process_keystroke()`'s independent *second
    output* for the same incoming MIDI event `JOG_WHEEL_ROW_KEY`'s OSC output
    already represents (docs/llds/app-ui.md's Phase 1.5.1 audit) - not a
    second physical control. It must never get its own descriptor, even
    though `build_configuration_rows()` (Table View's own, unaffected
    row-builder) still produces a `RowView` for it."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptor_keys = {d.key for d in _descriptors(engine)}
    assert JOG_WHEEL_ARC_ROW_KEY not in descriptor_keys
    assert any(row.key == JOG_WHEEL_ARC_ROW_KEY for row in build_configuration_rows(engine))


# @spec UI-CTRLDESC-002
def test_jog_wheel_row_is_present_though_absent_from_control_names() -> None:
    """Regression guard: a first draft built descriptors from
    `profile.control_names` directly, which silently omits the jog wheel
    entirely for a Korg profile."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptor_keys = {d.key for d in _descriptors(engine)}
    assert JOG_WHEEL_ROW_KEY in descriptor_keys
    assert ("cc", 110) not in STUDIO_PROFILE.control_names  # the jog wheel's raw key


# @spec UI-CTRLDESC-002
def test_nanokontrol2_has_no_jog_wheel_or_scene_descriptor() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    descriptor_keys = {d.key for d in _descriptors(engine)}
    assert JOG_WHEEL_ROW_KEY not in descriptor_keys
    assert ("korg_scene", None) not in descriptor_keys


# @spec UI-CTRLDESC-003
def test_empty_fader_rows_produce_no_fader_descriptor_and_do_not_raise() -> None:
    """Realistic empty-fader_rows input: a controller (VSN1) whose own
    `fader_keys` is also empty, matching how this function is actually
    called (`build_fader_rows(engine)` against `engine.profile`) - not an
    empty list paired with a profile that genuinely has faders."""
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = build_control_descriptors(
        fader_rows=build_fader_rows(engine),
        configuration_rows=build_configuration_rows(engine),
        active_controller=controller,
    )
    assert build_fader_rows(engine) == []
    assert all(d.control_type != "fader" for d in descriptors)


# @spec UI-CTRLDESC-001, UI-CTRLDESC-003
def test_vsn1_buttons_and_jog_are_present_though_absent_from_both_row_builders() -> None:
    """Regression guard for the real bug: VSN1's buttons/jog have
    `control_names` entries but no `opinionated_map` entry at all (not yet
    wired to a default action), so an earlier two-source version of this
    function (fader_rows + configuration_rows only) produced an *empty*
    descriptor list for a VSN1-only controller."""
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    assert build_fader_rows(engine) == []
    assert build_configuration_rows(engine) == []  # the gap this test guards against

    descriptors = _descriptors(engine)
    assert len(descriptors) == len(controller.control_names)
    assert all(d.control_type != "fader" for d in descriptors)
    labels = {d.label for d in descriptors}
    assert "VSN1 Jog" in labels
    assert "VSN1 Button 1" in labels


# @spec UI-CTRLDESC-002
def test_vsn1_jog_classifies_as_jog_and_buttons_as_button_via_the_fallback() -> None:
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = {d.key: d for d in _descriptors(engine)}
    assert descriptors[("grid_vsn1_jog", 1)].control_type == "jog"
    assert descriptors[("grid_vsn1_jog_button", 1)].control_type == "jog"
    assert descriptors[("grid_vsn1_button", 1)].control_type == "button"


@dataclass(frozen=True)
class _FakeActiveController:
    """Minimal duck-typed stand-in for a controller whose `control_names`
    includes a key classified purely via the fallback path (no RowView for
    it at all) - exercises the fallback's own `fader_keys` branch directly,
    which the real VSN1 fixture above doesn't (VSN1 has no faders)."""

    control_names: dict = field(default_factory=dict)
    fader_keys: frozenset = frozenset()
    knob_to_fader: dict = field(default_factory=dict)
    mute_to_fader: dict = field(default_factory=dict)
    record_to_fader: dict = field(default_factory=dict)
    select_to_fader: dict = field(default_factory=dict)
    websocket_keys: object = None


# @spec UI-CTRLDESC-002, UI-CTRLDESC-004
def test_fallback_classifies_fader_vs_button_and_knob_is_expanded_not_dropped() -> None:
    fake = _FakeActiveController(
        control_names={("cc", 0): "Fake Fader", ("cc", 1): "Fake Knob", ("cc", 2): "Fake Button"},
        fader_keys=frozenset({("cc", 0)}),
        knob_to_fader={("cc", 1): ("cc", 0)},
    )
    descriptors = {d.key: d for d in build_control_descriptors([], [], fake)}
    assert descriptors[("cc", 0)].control_type == "fader"
    assert descriptors[("cc", 1)].label == "Fake Knob"  # expanded via knob_to_fader, not dropped
    assert descriptors[("cc", 1)].control_type == "rotary"  # Phase 1.2: a Knob-role control is a Rotary
    assert descriptors[("cc", 2)].control_type == "button"


# @spec UI-CTRLDESC-001
def test_descriptor_is_a_frozen_dataclass_with_expected_fields() -> None:
    descriptor = ControlDescriptor(key=("cc", 0), label="Fader Channel 1", control_type="fader")
    assert descriptor.key == ("cc", 0)
    assert descriptor.label == "Fader Channel 1"
    assert descriptor.control_type == "fader"
