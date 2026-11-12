"""Physical control inventory regression tests (Phase 1.5,
docs/roadmap.md § Supported hardware and control inventory).

These tests pin down, per supported controller, exactly which physical
controls `build_control_descriptors()`/`build_control_groups()` expose and
what `ControlDescriptor.control_type` each gets - independent of which
Dragonframe action a control is currently assigned. They exist to catch a
regression where a controller's *physical inventory* becomes wrong or
generic (e.g. every controller showing the same control list), as distinct
from the already-shared, intentionally-generic `ROTARY_ACTIONS`/
`BUTTON_ACTIONS` catalog a control's Inspector offers.
"""

from __future__ import annotations

from collections import Counter

from dragonmidi.control_descriptor import build_control_descriptors
from dragonmidi.control_grouping import build_control_groups
from dragonmidi.grid_controller import Ready, build_grid_controller
from dragonmidi.grid_modules import ModuleType
from dragonmidi.grid_topology import GridModule, GridTopology
from dragonmidi.mapping import NANOKONTROL2_PROFILE, STUDIO_PROFILE, MappingEngine
from dragonmidi.mapping_view_model import build_configuration_rows, build_fader_rows


def _descriptors(engine: MappingEngine) -> list:
    return build_control_descriptors(build_fader_rows(engine), build_configuration_rows(engine), engine.profile)


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


def _vsn1(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=49, module_type=ModuleType.VSN1, x=x, y=0, rotation=0)


def _grid_controller(*modules: GridModule):
    outcome = build_grid_controller(GridTopology(modules=tuple(modules), current_page=0))
    assert isinstance(outcome, Ready)
    return outcome.controller


def _type_counts(descriptors) -> Counter:
    return Counter(d.control_type for d in descriptors)


# --- nanoKONTROL Studio: 8 channels (fader+rotary+button), transport, jog wheel ---


def test_studio_has_eight_fader_eight_rotary_eight_button_channels() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    assert counts["fader"] == 8
    assert counts["rotary"] == 8
    # 8 Mute + 8 Solo + Scene + 4 wired transport (Record/Play/Rewind/Fast
    # Forward) + 4 WebSocket transport (Stop/Cycle/Prev/Next Marker) + 2 Group
    # switch (Prev/Next Track) + 8 Record + 8 Select (Phase 1.5.1, unconfirmed
    # MIDI identity) + Set Marker + Return to Zero (also unconfirmed) = 45.
    assert counts["button"] == 45


def test_studio_has_exactly_one_jog_wheel() -> None:
    """Phase 1.5.1: there is only one physical jog wheel - `process()`'s OSC
    step output and `process_keystroke()`'s Arc Motion Control keystroke are
    two independent outputs from the *same* incoming MIDI event, not two
    physical controls, so this must not render as two tree entries."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors)["jog"] == 1
    jog_labels = [d.label for d in descriptors if d.control_type == "jog"]
    assert jog_labels == ["Jog Wheel"]


# @spec UI-CTRLDESC-007, MAP-BANK-006, MAP-BANK-011
def test_studio_has_record_and_select_as_confirmed_per_channel_controls() -> None:
    """Record 1-8/Select 1-8's real CC identity was confirmed via a Guided
    Capture session against physical hardware (Phase 1.6.1, 2026-11-12,
    docs/roadmap.md § Hardware verification tasks) - channel 16, CC 64-71/
    80-87. They appear in the Controller View with their real per-channel
    labels, but are still never a real MIDI-backed, bank-derived *action*:
    `record_to_fader`/`select_to_fader` exist only for naming/grouping, never
    consulted by `bank_fader_key()` (reusing `rec_to_fader`-style wiring for
    actual dispatch here was tried and reverted once already: it broke
    `test_record_and_select_stay_unmapped_regardless_of_bank_axis`,
    `MAP-BANK-006`'s own regression guard - unaffected by this phase)."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    labels = Counter(d.label for d in descriptors)
    for n in range(1, 9):
        assert labels[f"Record {n}"] == 1
        assert labels[f"Select {n}"] == 1
    # The safety invariant MAP-BANK-006 protects: confirmed identity does not
    # mean dispatch-eligible.
    for cc in range(64, 72):
        assert STUDIO_PROFILE.bank_fader_key(("cc", cc)) is None
    for cc in range(80, 88):
        assert STUDIO_PROFILE.bank_fader_key(("cc", cc)) is None


def test_studio_has_set_marker_and_return_to_zero_as_confirmed_globals() -> None:
    """Phase 1.6.1: real CC identity confirmed (channel 16, CC 60/47) -
    named, but still produces no OSC/WebSocket output (not in
    opinionated_map, build_websocket_keys(), or build_group_keys())."""
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    labels = Counter(d.label for d in descriptors)
    assert labels["Set Marker"] == 1
    assert labels["Return to Zero"] == 1
    assert ("cc", 60) not in STUDIO_PROFILE.opinionated_map
    assert ("cc", 47) not in STUDIO_PROFILE.opinionated_map


def test_studio_channel_groups_each_have_fader_rotary_button() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert len(channel_groups) == 8
    for group in channel_groups:
        types = {d.control_type for d in group.controls}
        assert {"fader", "rotary", "button"} <= types


# --- nanoKONTROL2: same 8-channel fader+rotary+button shape, no jog wheel ---


def test_nanokontrol2_has_eight_fader_eight_rotary_eight_button_channels() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    assert counts["fader"] == 8
    assert counts["rotary"] == 8
    # Studio's 45 minus the Scene button (1) and Select (8, confirmed absent
    # on this model per `MAP-PROFILE-003`) it lacks, minus Return to Zero (1,
    # also confirmed absent) = 35.
    assert counts["button"] == 35


def test_nanokontrol2_has_record_but_not_select() -> None:
    """Per `MAP-PROFILE-003`: nanoKONTROL2's per-channel buttons are
    Solo/Mute/Record only - no separate Select, unlike the Studio."""
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    descriptors = _descriptors(engine)
    labels = Counter(d.label for d in descriptors)
    assert labels["Record"] == 8
    assert labels["Select"] == 0


def test_nanokontrol2_has_set_marker_but_not_return_to_zero() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    descriptors = _descriptors(engine)
    labels = Counter(d.label for d in descriptors)
    assert labels["Set Marker"] == 1
    assert labels["Return to Zero"] == 0


def test_nanokontrol2_has_no_jog_wheel() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors)["jog"] == 0


# --- Intech PBF4: 4 channels, each exactly one Fader + one Rotary + one Button ---


def test_single_pbf4_has_four_channels_each_with_one_fader_one_rotary_one_button() -> None:
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    assert counts == Counter({"fader": 4, "rotary": 4, "button": 4})

    groups = build_control_groups(descriptors, controller)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert len(channel_groups) == 4
    for group in channel_groups:
        assert sorted(d.control_type for d in group.controls) == ["button", "fader", "rotary"]


def test_pbf4_has_no_jog_wheel_and_no_transport_leftovers() -> None:
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors)["jog"] == 0
    groups = build_control_groups(descriptors, controller)
    assert all(g.kind == "channel" for g in groups)  # no global/fallback leftovers at all


def test_two_pbf4_modules_each_contribute_four_complete_channels() -> None:
    """Repeated modules of the same type: two PBF4s give 8 channels, each
    still exactly one Fader + one Rotary + one Button - not a shared/
    collapsed inventory."""
    controller = _grid_controller(_pbf4(0), _pbf4(1))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors) == Counter({"fader": 8, "rotary": 8, "button": 8})


# --- Intech VSN1: 12 buttons (8 primary + 4 additional), jog wheel + jog push ---


def _vsn1_controller():
    return _grid_controller(_vsn1(0))


def test_vsn1_has_twelve_buttons_not_just_eight() -> None:
    """The roadmap's hardware table lists VSN1 as '8 primary buttons; verify
    any additional controls' - the existing module definition
    (`grid_modules.VSN1_DEFINITION`) already confirms 4 more (indices 9-12),
    for 12 total. This pins that confirmed count down as a regression test."""
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors)["button"] == 12


def test_vsn1_has_a_jog_wheel_and_jog_push_button() -> None:
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    assert _type_counts(descriptors)["jog"] == 2
    labels = {d.label for d in descriptors if d.control_type == "jog"}
    assert labels == {"VSN1 Jog", "VSN1 Jog Push"}


def test_vsn1_display_buttons_are_labeled_generically_not_by_assigned_function() -> None:
    """Phase 1.5.1: VSN1's 4 buttons below the LCD (indices 9-12) must read
    as plain physical buttons ('VSN1 Button 9'-'12'), never a borrowed
    function name like 'Play'/'Record' - they have no assigned action at
    all today (`docs/llds/intech-grid.md § Open Questions` Deferred item 3),
    and no code path invents one for display purposes."""
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    labels = {d.label for d in descriptors if d.control_type == "button"}
    assert {"VSN1 Button 9", "VSN1 Button 10", "VSN1 Button 11", "VSN1 Button 12"} <= labels
    assert not any(label in labels for label in ("Play", "Record", "Mute", "Solo"))


def test_vsn1_jog_rotation_and_push_are_two_distinct_physical_inputs() -> None:
    """Unlike the Korg jog wheel's single-input/two-output collapse (Phase
    1.5.1, above), VSN1's rotation and push are two genuinely separate
    physical elements that happen to share one raw MIDI index, disambiguated
    by message type (`grid_controller.py`'s `_raw_key_for`) - confirmed
    against real hardware (`grid_modules.py`'s VSN1_DEFINITION docstring,
    2026-11-04 validation). Both must keep their own descriptor, not collapse
    into one the way the Korg jog wheel's two outputs did."""
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    jog_descriptors = [d for d in descriptors if d.control_type == "jog"]
    assert len(jog_descriptors) == 2
    assert {d.key[0] for d in jog_descriptors} == {"grid_vsn1_jog", "grid_vsn1_jog_button"}
    assert {d.label for d in jog_descriptors} == {"VSN1 Jog", "VSN1 Jog Push"}


def test_vsn1_has_no_fader_or_rotary() -> None:
    controller = _vsn1_controller()
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    assert counts["fader"] == 0
    assert counts["rotary"] == 0


# --- Mixed/repeated Intech layouts: every module keeps its own correct shape ---


def test_pbf4_vsn1_pbf4_mix_keeps_each_modules_physical_shape_independent() -> None:
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    # Two PBF4 modules: 8 fader + 8 rotary + 8 PBF4-button; one VSN1: 12 button + 2 jog.
    assert counts["fader"] == 8
    assert counts["rotary"] == 8
    assert counts["button"] == 8 + 12
    assert counts["jog"] == 2


def test_three_vsn1_modules_each_keep_their_own_twelve_buttons_and_jog() -> None:
    controller = _grid_controller(_vsn1(0), _vsn1(1), _vsn1(2))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    counts = _type_counts(descriptors)
    assert counts["button"] == 12 * 3
    assert counts["jog"] == 2 * 3
    assert counts["fader"] == 0
    assert counts["rotary"] == 0
