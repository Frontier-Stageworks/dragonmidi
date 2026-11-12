"""Tests for Control Grouping (docs/specs/app-ui.md § Control Grouping).

@spec UI-CTRLGROUP-001, UI-CTRLGROUP-002, UI-CTRLGROUP-003, UI-CTRLGROUP-004, UI-CTRLGROUP-005
"""

from __future__ import annotations

from dragonmidi.control_descriptor import build_control_descriptors
from dragonmidi.control_grouping import FALLBACK_GROUP_LABEL, GLOBAL_GROUP_LABEL, build_control_groups
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


# @spec UI-CTRLGROUP-001
def test_studio_has_eight_channel_groups_in_order() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert [g.label for g in channel_groups] == [f"Channel {i}" for i in range(1, 9)]


# @spec UI-CTRLGROUP-001, UI-CTRLGROUP-009
def test_channel_1_contains_fader_knob_mute_solo_record_and_select() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    channel_1 = next(g for g in groups if g.label == "Channel 1")
    fader_key = STUDIO_PROFILE.bank_fader_keys[0]
    knob_key = next(k for k, f in STUDIO_PROFILE.knob_to_fader.items() if f == fader_key)
    mute_key = next(k for k, f in STUDIO_PROFILE.mute_to_fader.items() if f == fader_key)
    solo_key = STUDIO_PROFILE.websocket_keys.solos[0]
    # Record/Select (Phase 1.6.1): now a real, confirmed CC identity - grouped
    # via record_to_fader/select_to_fader, same positional pairing as Mute above.
    record_key = next(k for k, f in STUDIO_PROFILE.record_to_fader.items() if f == fader_key)
    select_key = next(k for k, f in STUDIO_PROFILE.select_to_fader.items() if f == fader_key)
    member_keys = {c.key for c in channel_1.controls}
    member_labels = {c.label for c in channel_1.controls}
    assert fader_key in member_keys
    assert knob_key in member_keys
    assert mute_key in member_keys
    assert solo_key in member_keys
    assert record_key in member_keys
    assert select_key in member_keys
    assert "Record 1" in member_labels
    assert "Select 1" in member_labels
    assert len(channel_1.controls) == 6


# @spec UI-CTRLGROUP-002
def test_leftover_controls_land_in_transport_and_global_group() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    global_group = next(g for g in groups if g.label == GLOBAL_GROUP_LABEL)
    labels = {c.label for c in global_group.controls}
    assert "Play" in labels
    assert "Jog Wheel" in labels
    assert "Scene" in labels


# @spec UI-CTRLGROUP-005
def test_every_descriptor_appears_in_exactly_one_group() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    descriptors = _descriptors(engine)
    groups = build_control_groups(descriptors, engine.profile)
    grouped_keys = [c.key for g in groups for c in g.controls]
    assert sorted(grouped_keys) == sorted(d.key for d in descriptors)
    assert len(grouped_keys) == len(set(grouped_keys))  # no duplicates - each key in exactly one group


# @spec UI-CTRLGROUP-001
def test_nanokontrol2_has_eight_channels_and_no_jog_wheel_leftover() -> None:
    engine = MappingEngine(profile=NANOKONTROL2_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert len(channel_groups) == 8
    global_group = next(g for g in groups if g.label == GLOBAL_GROUP_LABEL)
    assert all("Jog" not in c.label for c in global_group.controls)


# @spec UI-CTRLGROUP-003
def test_single_pbf4_has_four_channels_with_fader_pot_button() -> None:
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert [g.label for g in channel_groups] == [f"Channel {i}" for i in range(1, 5)]
    channel_1 = channel_groups[0]
    kinds = {c.key[0] for c in channel_1.controls}
    assert kinds == {"grid_fader", "grid_pbf4_pot", "grid_pbf4_button"}


# @spec UI-CTRLGROUP-003
def test_pbf4_vsn1_pbf4_chain_channel_numbering_ignores_the_interposed_vsn1() -> None:
    """VSN1 contributes its own tags (grid_vsn1_*), which don't share the
    PBF4 per-channel counters - the second PBF4 module's channels must pick
    up numbering 5-8, not restart or collide.

    This is a 3-module topology (Phase 1.3: module_count > 1), so channel
    groups are nested under the module tier (UI-CTRLGROUP-007) rather than
    appearing at the top level - see test_multi_module_grid_nests_under_a_
    module_tier for the module-tier structure itself; this test's own focus
    (channel *numbering* ignoring the interposed VSN1) still holds, just
    reached by flattening the two PBF4 modules' children."""
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)
    channel_groups = [child for g in groups if g.kind == "module" for child in g.children if child.kind == "channel"]
    assert [g.label for g in channel_groups] == [f"Channel {i}" for i in range(1, 9)]
    for group in channel_groups:
        kinds = {c.key[0] for c in group.controls}
        assert kinds == {"grid_fader", "grid_pbf4_pot", "grid_pbf4_button"}


# @spec UI-CTRLGROUP-004
def test_vsn1_only_has_buttons_and_jog_groups_no_channels() -> None:
    controller = _grid_controller(_vsn1(0))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)
    assert not any(g.kind == "channel" for g in groups)
    buttons = next(g for g in groups if g.kind == "vsn1_buttons")
    jog = next(g for g in groups if g.kind == "vsn1_jog")
    assert len(buttons.controls) == 12  # VSN1_DEFINITION's 12 button elements
    jog_labels = {c.label for c in jog.controls}
    assert jog_labels == {"VSN1 Jog", "VSN1 Jog Push"}


# @spec UI-CTRLGROUP-004
def test_vsn1_only_every_control_still_represented() -> None:
    """Explicit acceptance criterion: VSN1 has no channel structure, but no
    control should disappear - every descriptor must land in some group."""
    controller = _grid_controller(_vsn1(0))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    groups = build_control_groups(descriptors, controller)
    grouped_keys = {c.key for g in groups for c in g.controls}
    assert grouped_keys == {d.key for d in descriptors}


# @spec UI-CTRLGROUP-004
def test_controller_with_no_recognized_structure_falls_back_to_one_group() -> None:
    from dataclasses import dataclass, field

    @dataclass(frozen=True)
    class _FakeActiveController:
        control_names: dict = field(default_factory=dict)
        fader_keys: frozenset = frozenset()
        knob_to_fader: dict = field(default_factory=dict)
        mute_to_fader: dict = field(default_factory=dict)
        record_to_fader: dict = field(default_factory=dict)
        select_to_fader: dict = field(default_factory=dict)
        websocket_keys: object = None
        bank_fader_keys: tuple = ()
        bank_count: int = 0

        def bank_fader_key(self, key):
            return None

    fake = _FakeActiveController(control_names={("cc", 1): "Mystery Button"})
    descriptors = build_control_descriptors([], [], fake)
    groups = build_control_groups(descriptors, fake)
    assert len(groups) == 1
    assert groups[0].label == FALLBACK_GROUP_LABEL
    assert groups[0].controls[0].key == ("cc", 1)


# --- Module-tier grouping for multi-module Grid (UI-CTRLGROUP-006/007/008, Phase 1.3) ---


# @spec UI-CTRLGROUP-006
def test_single_module_grid_is_unchanged_no_module_tier() -> None:
    """A lone PBF4/VSN1 must render exactly as before Phase 1.3 - no
    "module" group at all, same flat groups as every existing test above."""
    controller = _grid_controller(_pbf4(0))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)
    assert not any(g.kind == "module" for g in groups)
    channel_groups = [g for g in groups if g.kind == "channel"]
    assert [g.label for g in channel_groups] == [f"Channel {i}" for i in range(1, 5)]


# @spec UI-CTRLGROUP-006
def test_korg_profiles_are_unaffected_no_module_tier() -> None:
    engine = MappingEngine(profile=STUDIO_PROFILE)
    groups = build_control_groups(_descriptors(engine), engine.profile)
    assert not any(g.kind == "module" for g in groups)


# @spec UI-CTRLGROUP-007
def test_multi_module_grid_nests_under_a_module_tier() -> None:
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)

    module_groups = [g for g in groups if g.kind == "module"]
    assert [g.label for g in module_groups] == ["Module 1 (PBF4)", "Module 2 (VSN1)", "Module 3 (PBF4)"]
    for g in module_groups:
        assert g.controls == ()  # a "module" group never holds leaves directly

    module1, module2, module3 = module_groups
    assert [c.label for c in module1.children] == ["Channel 1", "Channel 2", "Channel 3", "Channel 4"]
    assert {c.kind for c in module2.children} == {"vsn1_buttons", "vsn1_jog"}
    assert [c.label for c in module3.children] == ["Channel 5", "Channel 6", "Channel 7", "Channel 8"]


# @spec UI-CTRLGROUP-007
def test_multi_module_grid_every_descriptor_still_represented_once() -> None:
    controller = _grid_controller(_pbf4(0), _vsn1(1), _pbf4(2))
    engine = MappingEngine(profile=controller)
    descriptors = _descriptors(engine)
    groups = build_control_groups(descriptors, controller)

    seen = []
    for group in groups:
        if group.kind == "module":
            for child in group.children:
                seen.extend(child.controls)
        else:
            seen.extend(group.controls)
    assert sorted(d.key for d in seen) == sorted(d.key for d in descriptors)
    assert len(seen) == len(descriptors)  # none duplicated across module groups


# @spec UI-CTRLGROUP-008
def test_descriptor_missing_from_control_module_is_not_dropped() -> None:
    """Defensive branch: every Grid logical key has a `control_module` entry
    today (GRID-CTRL-012), so this never fires in practice - but a
    descriptor somehow missing one must still be represented, not silently
    dropped, under the module-tier wrapping."""
    from dragonmidi.control_descriptor import ControlDescriptor
    from dragonmidi.grid_controller import ModuleRef

    class _FakeMultiModuleController:
        control_names: dict = {}
        fader_keys: frozenset = frozenset({("grid_fader", 1)})
        knob_to_fader: dict = {}
        mute_to_fader: dict = {}
        record_to_fader: dict = {}
        select_to_fader: dict = {}
        websocket_keys: object = None
        bank_fader_keys: tuple = (("grid_fader", 1),)
        bank_count: int = 1
        module_count: int = 2
        module_shape: tuple = ("PBF4", "PBF4")
        control_module: dict = {("grid_fader", 1): ModuleRef(ordinal=1, module_type="PBF4")}

        def bank_fader_key(self, key):
            return None

    fake = _FakeMultiModuleController()
    orphan = ControlDescriptor(key=("mystery", 1), label="Mystery", control_type="button")
    descriptors = build_control_descriptors([], [], fake) + [orphan]
    groups = build_control_groups(descriptors, fake)

    all_controls = []
    for group in groups:
        if group.kind == "module":
            for child in group.children:
                all_controls.extend(child.controls)
        else:
            all_controls.extend(group.controls)
    assert orphan in all_controls
    assert any(g.kind == "global" for g in groups)  # the unassigned fallback group


# @spec UI-CTRLGROUP-007
def test_three_vsn1_modules_each_get_their_own_module_group() -> None:
    controller = _grid_controller(_vsn1(0), _vsn1(1), _vsn1(2))
    engine = MappingEngine(profile=controller)
    groups = build_control_groups(_descriptors(engine), controller)
    module_groups = [g for g in groups if g.kind == "module"]
    assert [g.label for g in module_groups] == ["Module 1 (VSN1)", "Module 2 (VSN1)", "Module 3 (VSN1)"]
    for g in module_groups:
        kinds = {c.kind for c in g.children}
        assert kinds == {"vsn1_buttons", "vsn1_jog"}
