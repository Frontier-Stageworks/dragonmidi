"""Tests for the Active Grid Controller: logical-control enumeration, bank_count,
address-table construction, collision/multi-row/multi-VSN1 rejection, and the
`ActiveController` shape (docs/llds/intech-grid.md § Active Grid Controller,
§ MIDI -> Module/Element Resolution).

@spec GRID-CTRL-001, GRID-CTRL-002, GRID-CTRL-003, GRID-CTRL-004, GRID-CTRL-005
@spec GRID-CTRL-006, GRID-CTRL-007, GRID-CTRL-008, GRID-CTRL-009
@spec GRID-MIDI-001, GRID-MIDI-002, GRID-MIDI-003, GRID-MAP-002
"""

from __future__ import annotations

from dragonmidi.grid_controller import AddressCollision, GridRuntimeController, Ready, UnsupportedTopology, build_grid_controller
from dragonmidi.grid_topology import GridModule, GridTopology
from dragonmidi.grid_modules import ModuleType
from dragonmidi.mapping import ControlsConfig, MappingEngine, build_profile


def _pbf4(x: int, y: int = 0) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=y, rotation=0)


def _vsn1(x: int, y: int = 0) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=49, module_type=ModuleType.VSN1, x=x, y=y, rotation=0)


def _unsupported(x: int, y: int = 0, hwcfg: int = 1) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=hwcfg, module_type=None, x=x, y=y, rotation=0)


def _topology(modules: list[GridModule], page: int = 0) -> GridTopology:
    return GridTopology(modules=tuple(modules), current_page=page)


# --- bank_count vs logical_control_count (GRID-CTRL-001) ---


def test_single_pbf4_has_bank_count_4() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    assert isinstance(outcome, Ready)
    assert outcome.controller.bank_count == 4


def test_pbf4_vsn1_pbf4_has_bank_count_8() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)]))
    assert isinstance(outcome, Ready)
    controller = outcome.controller
    assert controller.bank_count == 8
    assert len(controller.bank_fader_keys) == 8
    # logical_control_count exceeds bank_count: 8 faders + 8 pots + 8 buttons + 12 vsn1 buttons + 1 jog + 1 jog push-button
    assert len(controller.control_names) == 8 + 8 + 8 + 12 + 1 + 1


def test_three_pbf4_has_bank_count_12() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _pbf4(1), _pbf4(2)]))
    assert isinstance(outcome, Ready)
    assert outcome.controller.bank_count == 12


# --- PBF4 numbering: VSN1/unsupported modules never reset or interrupt it (GRID-CTRL-002) ---


def test_pbf4_fader_numbering_ignores_an_interposed_vsn1() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)]))
    controller = outcome.controller
    assert set(controller.fader_keys) == {("grid_fader", n) for n in range(1, 9)}
    # left PBF4 (x=0) -> faders 1-4, right PBF4 (x=2) -> faders 5-8.
    assert controller.address_table[("cc", (32 + 0 * 16 + 4) % 128)] == ("grid_fader", 1)  # left module, fader element idx4
    assert controller.address_table[("cc", (32 + 2 * 16 + 4) % 128)] == ("grid_fader", 5)  # right module, fader element idx4


def test_pbf4_pots_and_buttons_number_independently_left_to_right() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _unsupported(1), _pbf4(2)]))
    controller = outcome.controller
    pot_keys = {k for k in controller.control_names if k[0] == "grid_pbf4_pot"}
    button_keys = {k for k in controller.control_names if k[0] == "grid_pbf4_button"}
    assert pot_keys == {("grid_pbf4_pot", n) for n in range(1, 9)}
    assert button_keys == {("grid_pbf4_button", n) for n in range(1, 9)}


def test_unsupported_module_between_two_pbf4_does_not_reset_numbering() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _unsupported(1), _pbf4(2)]))
    assert isinstance(outcome, Ready)
    assert outcome.controller.bank_count == 8


# --- Phase 1.2: PBF4's Rotary/Button are bank-derived, like Korg's Knob/Mute ---


def test_single_pbf4_wires_pot_and_button_to_their_own_channels_fader() -> None:
    controller = build_grid_controller(_topology([_pbf4(0)])).controller
    for channel in range(1, 5):
        assert controller.knob_to_fader[("grid_pbf4_pot", channel)] == ("grid_fader", channel)
        assert controller.mute_to_fader[("grid_pbf4_button", channel)] == ("grid_fader", channel)
        assert controller.bank_fader_key(("grid_pbf4_pot", channel)) == ("grid_fader", channel)
        assert controller.bank_fader_key(("grid_pbf4_button", channel)) == ("grid_fader", channel)
    assert controller.fader_to_knob[("grid_fader", 1)] == ("grid_pbf4_pot", 1)


def test_pbf4_vsn1_pbf4_chain_keeps_pot_button_fader_alignment_across_modules() -> None:
    """The VSN1 sandwiched in the middle must not shift the second PBF4
    module's pot/button indices out of alignment with its own fader's."""
    controller = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    assert controller.bank_count == 8
    for channel in range(1, 9):
        assert controller.knob_to_fader[("grid_pbf4_pot", channel)] == ("grid_fader", channel)
        assert controller.mute_to_fader[("grid_pbf4_button", channel)] == ("grid_fader", channel)


def test_vsn1_only_topology_has_no_knob_or_mute_wiring() -> None:
    controller = build_grid_controller(_topology([_vsn1(0)])).controller
    assert controller.knob_to_fader == {}
    assert controller.mute_to_fader == {}
    assert controller.fader_to_knob == {}


# --- VSN1 identity independent of position (GRID-CTRL-003) ---


def test_vsn1_logical_identities_independent_of_position() -> None:
    # @spec GRID-CTRL-003 - with exactly one recognized VSN1, its ordinal is
    # always 1 regardless of where it sits in the row.
    left = build_grid_controller(_topology([_vsn1(0), _pbf4(1), _pbf4(2)])).controller
    middle = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    right = build_grid_controller(_topology([_pbf4(0), _pbf4(1), _vsn1(2)])).controller
    expected_keys = {("grid_vsn1_button", n) for n in range(1, 13)} | {("grid_vsn1_jog", 1)}
    for controller in (left, middle, right):
        present = {k for k in controller.control_names if k[0] in ("grid_vsn1_button", "grid_vsn1_jog")}
        assert present == expected_keys


def test_vsn1_button_count_is_12() -> None:
    outcome = build_grid_controller(_topology([_vsn1(0)]))
    controller = outcome.controller
    button_keys = {k for k in controller.control_names if k[0] == "grid_vsn1_button"}
    assert button_keys == {("grid_vsn1_button", n) for n in range(1, 13)}
    assert ("grid_vsn1_jog", 1) in controller.control_names
    assert controller.control_names[("grid_vsn1_button", 1)] == "VSN1 Button 1"
    assert controller.control_names[("grid_vsn1_jog", 1)] == "VSN1 Jog"


# --- Multi-row rejection (GRID-CTRL / GRID-TOPO-010) ---


def test_multi_row_topology_is_rejected() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0, y=0), _pbf4(1, y=1)]))
    assert isinstance(outcome, UnsupportedTopology)


# --- Multiple VSN1 modules supported, globally numbered (GRID-CTRL-003/004, Phase 1.3) ---


def test_two_vsn1_modules_are_supported_and_numbered_globally() -> None:
    outcome = build_grid_controller(_topology([_vsn1(0), _pbf4(1), _vsn1(2)]))
    assert isinstance(outcome, Ready)
    controller = outcome.controller
    button_keys = {k for k in controller.control_names if k[0] == "grid_vsn1_button"}
    # Module 1's (left VSN1's) 12 buttons are keys 1-12; module 2's (right
    # VSN1's) are 13-24 - a global sequence, same pattern PBF4 already used.
    assert button_keys == {("grid_vsn1_button", n) for n in range(1, 25)}
    # Jog/jog-button carry a VSN1-instance ordinal (1 for the left VSN1, 2 for
    # the right), not the raw-address-based module position.
    assert ("grid_vsn1_jog", 1) in controller.control_names
    assert ("grid_vsn1_jog", 2) in controller.control_names
    assert controller.control_names[("grid_vsn1_jog", 1)] == "VSN1 #1 Jog"
    assert controller.control_names[("grid_vsn1_jog", 2)] == "VSN1 #2 Jog"
    # Display text for the globally-numbered buttons shows the per-module
    # local number (1-12), prefixed by VSN1 instance, not the global index.
    assert controller.control_names[("grid_vsn1_button", 1)] == "VSN1 #1 Button 1"
    assert controller.control_names[("grid_vsn1_button", 13)] == "VSN1 #2 Button 1"
    assert controller.control_names[("grid_vsn1_button", 24)] == "VSN1 #2 Button 12"


def test_two_vsn1_modules_raw_addresses_do_not_collide() -> None:
    # The two VSN1s sit at different x positions, so their raw addresses
    # differ even though both contribute 12 buttons each - no AddressCollision.
    outcome = build_grid_controller(_topology([_vsn1(0), _pbf4(1), _vsn1(2)]))
    assert isinstance(outcome, Ready)


def test_one_vsn1_is_fine() -> None:
    outcome = build_grid_controller(_topology([_vsn1(0)]))
    assert isinstance(outcome, Ready)


# --- Address-table uniqueness / collision rejection, fail closed (GRID-CTRL-005/006) ---


def test_densely_packed_8_pbf4_modules_build_successfully() -> None:
    outcome = build_grid_controller(_topology([_pbf4(x) for x in range(8)]))
    assert isinstance(outcome, Ready)
    assert outcome.controller.bank_count == 32


def test_a_9th_adjacent_pbf4_collides_and_is_rejected() -> None:
    outcome = build_grid_controller(_topology([_pbf4(x) for x in range(9)]))
    assert isinstance(outcome, AddressCollision)


def test_no_partial_controller_on_collision() -> None:
    outcome = build_grid_controller(_topology([_pbf4(x) for x in range(9)]))
    assert not hasattr(outcome, "controller")


# --- Current-page-derived default_channel (GRID-CTRL-009) ---


def test_default_channel_is_page_modulo_16() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)], page=3))
    assert outcome.controller.default_channel == 3


def test_default_channel_zero_for_default_page() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)], page=0))
    assert outcome.controller.default_channel == 0


# --- has_jog_wheel is False; VSN1 jog is its own logical control (GRID-CTRL-008) ---


def test_has_jog_wheel_is_false() -> None:
    outcome = build_grid_controller(_topology([_vsn1(0)]))
    assert outcome.controller.has_jog_wheel is False
    assert outcome.controller.has_native_mode is False
    assert outcome.controller.has_scene_button is False


# --- PBF4/VSN1 identity has no opinionated_map entry yet except grid_fader (§19) ---


def test_only_grid_fader_has_an_opinionated_map_entry() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0), _vsn1(1)]))
    controller = outcome.controller
    assert all(k[0] == "grid_fader" for k in controller.opinionated_map)
    assert ("grid_fader", 1) in controller.opinionated_map
    assert controller.opinionated_map[("grid_fader", 1)].address == "/dragonframe/encoder/1"


# --- ActiveController shape conformance driving the real MappingEngine (GRID-CTRL-007, GRID-MAP-002) ---


def test_grid_runtime_controller_drives_the_real_mapping_engine_end_to_end() -> None:
    # Proves genuine ActiveController substitution: the *existing, unmodified*
    # MappingEngine, constructed with a GridRuntimeController as its profile,
    # dispatches a grid_fader event through the exact same opinionated_map
    # lookup path a Korg CC event goes through.
    from dragonmidi.events import MidiEvent

    outcome = build_grid_controller(_topology([_pbf4(x) for x in range(3)]))  # 12 faders
    assert isinstance(outcome, Ready)
    controller = outcome.controller
    assert controller.bank_count == 12

    engine = MappingEngine(profile=controller)
    engine.set_fader_mode(axis=False)  # OSC encoder mode - exercises the opinionated_map path
    event = MidiEvent(type="grid_fader", channel=controller.default_channel, number=1, raw_value=64, normalized=0.5, is_press=False, is_release=False)
    result = engine.process(event, now=0.0)
    assert result is not None
    assert result.address == "/dragonframe/encoder/1"


def test_grid_bank_count_12_matches_a_synthetic_12_bank_korg_profiles_solo_formula() -> None:
    # bank_count is the only thing MAP-WS-002's Solo formula depends on; confirms
    # a Grid-sourced bank_count=12 is arithmetically identical to a static
    # profile's, even though Grid itself has no Solo-equivalent control to fire.
    outcome = build_grid_controller(_topology([_pbf4(x) for x in range(3)]))
    controls = ControlsConfig(faders=tuple(range(12)), knobs=(), mutes=(), solos=tuple(range(100, 112)), transport={}, jog_wheel=None)
    korg_profile = build_profile(
        name="Synthetic 12-Bank",
        match_substring="synthetic12bank",
        has_native_mode=False,
        default_channel=0,
        has_jog_wheel=False,
        has_scene_button=False,
        controls=controls,
    )
    assert outcome.controller.bank_count == korg_profile.bank_count == 12


# --- VSN1 jog push-button: confirmed real-hardware behavior (2026-11-04) ---
# the endless encoder's push function sends Note On/Off on the SAME raw
# index the encoder's own CC uses, distinguished only by message type - not
# modeled before this validation pass; see grid_modules.py/grid_controller.py.


# @spec GRID-CTRL-010
def test_vsn1_jog_push_button_gets_its_own_logical_identity_sharing_the_jogs_raw_index() -> None:
    outcome = build_grid_controller(_topology([_vsn1(0)]))
    assert isinstance(outcome, Ready)
    controller = outcome.controller
    assert controller.address_table[("cc", 40)] == ("grid_vsn1_jog", 1)
    assert controller.address_table[("note", 40)] == ("grid_vsn1_jog_button", 1)
    assert controller.control_names[("grid_vsn1_jog_button", 1)] == "VSN1 Jog Push"


def test_grid_runtime_controller_matches_the_confirmed_midi_interface_name() -> None:
    # Real-hardware correction (2026-11-04): a real Grid's CoreMIDI port name
    # is simply "Grid" (confirmed via mido against physical PBF4/VSN1
    # hardware) - not the "Intech Grid MIDI" per-interface descriptor string
    # source research had assumed would be exposed. The match substring must
    # recognize the real bare name; it still also recognizes the originally
    # assumed fuller name, should some future platform/firmware expose it.
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    controller = outcome.controller
    assert controller.matches("Grid")
    assert controller.matches("Intech Grid MIDI")
    assert controller.matches("intech grid midi 1")  # fuzzy-normalized, same as ControllerProfile.matches()
    assert not controller.matches("nanoKONTROL Studio")


def test_grid_runtime_controller_satisfies_active_controller_protocol() -> None:
    from dragonmidi.active_controller import ActiveController

    outcome = build_grid_controller(_topology([_pbf4(0)]))
    controller: GridRuntimeController = outcome.controller
    assert isinstance(controller, ActiveController)


# --- GRID-DISCOVER-001: MidiInputAdapter auto-connects to Grid's MIDI port using
# --- GridRuntimeController.matches(), with zero Grid-specific code in MidiInputAdapter ---


def test_midi_input_adapter_auto_connects_using_grid_runtime_controller_matches() -> None:
    from dragonmidi.midi_input import MidiInputAdapter

    class _FakeBackend:
        def __init__(self, inputs):
            self.inputs = inputs

        def list_inputs(self):
            return list(self.inputs)

        def list_outputs(self):
            return []

        def open_input(self, name, callback):
            return type("P", (), {"close": lambda self: None})()

    outcome = build_grid_controller(_topology([_pbf4(0)]))
    controller = outcome.controller
    backend = _FakeBackend(inputs=["Intech Grid MIDI", "Some Other Device"])
    adapter = MidiInputAdapter(
        backend,
        on_activity=lambda: None,
        on_event=lambda event: None,
        on_connection_change=lambda connected, name: None,
        on_error=lambda active: None,
        on_reset_mapping=lambda: None,
        profile=controller,
    )
    adapter.poll_discovery()
    assert adapter.connected is True
    assert adapter.device_name == "Intech Grid MIDI"


# --- module_shape / control_module / module_count (GRID-CTRL-012, GRID-CTRL-013, Phase 1.3) ---


def test_module_shape_reflects_recognized_modules_in_normalized_order() -> None:
    controller = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    assert controller.module_shape == ("PBF4", "VSN1", "PBF4")
    assert controller.module_count == 3


def test_module_shape_excludes_unrecognized_modules() -> None:
    controller = build_grid_controller(_topology([_pbf4(0), _unsupported(1), _pbf4(2)])).controller
    assert controller.module_shape == ("PBF4", "PBF4")
    assert controller.module_count == 2


def test_single_module_has_module_count_1() -> None:
    assert build_grid_controller(_topology([_pbf4(0)])).controller.module_count == 1
    assert build_grid_controller(_topology([_vsn1(0)])).controller.module_count == 1


def test_module_shape_is_invariant_to_usb_root_offset() -> None:
    # A USB-root change shifts every module's absolute x by a constant offset
    # without changing left-to-right order - module_shape must not change.
    a = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    b = build_grid_controller(_topology([_pbf4(10), _vsn1(11), _pbf4(12)])).controller
    assert a.module_shape == b.module_shape


def test_control_module_assigns_each_logical_key_its_owning_module_ordinal_and_type() -> None:
    controller = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    # Module 1 (first PBF4): faders/pots/buttons 1-4.
    assert controller.control_module[("grid_fader", 1)].ordinal == 1
    assert controller.control_module[("grid_fader", 1)].module_type == "PBF4"
    assert controller.control_module[("grid_pbf4_pot", 4)].ordinal == 1
    # Module 2 (the VSN1): all its buttons/jog.
    assert controller.control_module[("grid_vsn1_button", 1)].ordinal == 2
    assert controller.control_module[("grid_vsn1_button", 1)].module_type == "VSN1"
    assert controller.control_module[("grid_vsn1_jog", 1)].ordinal == 2
    # Module 3 (second PBF4): faders 5-8, still ordinal 3, unaffected by the
    # interposed VSN1 (same non-interruption guarantee GRID-CTRL-002 states).
    assert controller.control_module[("grid_fader", 5)].ordinal == 3
    assert controller.control_module[("grid_fader", 5)].module_type == "PBF4"


def test_control_module_every_recognized_logical_key_has_an_entry() -> None:
    controller = build_grid_controller(_topology([_pbf4(0), _vsn1(1), _pbf4(2)])).controller
    assert set(controller.control_module.keys()) == set(controller.control_names.keys())
