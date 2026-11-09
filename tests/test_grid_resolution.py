"""Tests for MIDI -> logical-control resolution (docs/llds/intech-grid.md
§ MIDI -> Module/Element Resolution), including the stale/pre-settle
fail-closed behavior from § Topology Change Policy.

@spec GRID-MIDI-003, GRID-MIDI-004, GRID-MIDI-005, GRID-MIDI-006, GRID-MIDI-007
"""

from __future__ import annotations

from dragonmidi.events import MidiEvent
from dragonmidi.grid_controller import build_grid_controller, resolve_grid_event, route_midi_event
from dragonmidi.grid_modules import ModuleType
from dragonmidi.grid_topology import GridModule, GridTopology


def _pbf4(x: int, y: int = 0) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=y, rotation=0)


def _topology(modules, page=0):
    return GridTopology(modules=tuple(modules), current_page=page)


def _raw_cc_event(number: int, channel: int = 0, raw_value: int = 64) -> MidiEvent:
    return MidiEvent(type="cc", channel=channel, number=number, raw_value=raw_value, normalized=raw_value / 127, is_press=False, is_release=False)


# --- Successful resolution, fields pass through unchanged (GRID-MIDI-006, 007) ---


def test_resolves_a_matching_raw_event_to_its_logical_key() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    controller = outcome.controller
    # fader element index 4 at x=0 -> cc number (32+0*16+4)%128 = 36
    event = _raw_cc_event(36, channel=0, raw_value=100)
    result = resolve_grid_event(event, controller)
    assert result is not None
    assert (result.type, result.number) == ("grid_fader", 1)
    # Physical-gesture fields pass through unchanged.
    assert result.raw_value == 100
    assert result.normalized == event.normalized
    assert result.is_press == event.is_press
    assert result.is_release == event.is_release
    assert result.channel == event.channel


# --- Same physical control resolves identically before/after rearrangement ---


def test_same_physical_fader_resolves_to_the_same_logical_key_after_usb_root_change() -> None:
    before = build_grid_controller(_topology([_pbf4(-1), _pbf4(1)])).controller  # host plugged in from one end
    after = build_grid_controller(_topology([_pbf4(0), _pbf4(2)])).controller  # host plugged in from the other end

    # The physical left-hand module's fader-element-4 is at x=-1 before, x=0 after.
    event_before = _raw_cc_event((32 + -1 * 16 + 4) % 128)
    event_after = _raw_cc_event((32 + 0 * 16 + 4) % 128)
    result_before = resolve_grid_event(event_before, before)
    result_after = resolve_grid_event(event_after, after)
    assert (result_before.type, result_before.number) == (result_after.type, result_after.number) == ("grid_fader", 1)


# --- Unmatched event resolves to nothing, never guessed (GRID-MIDI-006) ---


def test_unmatched_event_resolves_to_nothing() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    event = _raw_cc_event(99)  # not any recognized element's address
    assert resolve_grid_event(event, outcome.controller) is None


# --- Stale controller resolves nothing (GRID-MIDI-005) ---


def test_stale_controller_resolves_nothing_even_for_a_previously_valid_address() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    controller = outcome.controller
    event = _raw_cc_event(36)
    assert resolve_grid_event(event, controller) is not None  # valid while fresh
    controller.mark_stale()
    assert resolve_grid_event(event, controller) is None


# --- Page-derived channel feeds resolution correctly ---


def test_a_non_default_page_is_reflected_in_default_channel_and_does_not_break_resolution() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)], page=5))
    controller = outcome.controller
    assert controller.default_channel == 5
    event = _raw_cc_event(36, channel=5)
    result = resolve_grid_event(event, controller)
    assert result is not None
    assert (result.type, result.number) == ("grid_fader", 1)


# --- route_midi_event(): the one Grid-specific branch app.py's MIDI input
# --- dispatch needs, kept out of every output path (GRID-MAP-001) ---


def test_route_midi_event_passes_through_unchanged_when_grid_is_not_active() -> None:
    event = _raw_cc_event(36)
    assert route_midi_event(event, grid_active=False, controller=None) is event


def test_route_midi_event_drops_everything_when_grid_active_but_no_controller_yet() -> None:
    event = _raw_cc_event(36)
    assert route_midi_event(event, grid_active=True, controller=None) is None


def test_route_midi_event_resolves_through_the_controller_when_grid_is_active() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    event = _raw_cc_event(36)
    result = route_midi_event(event, grid_active=True, controller=outcome.controller)
    assert result is not None
    assert (result.type, result.number) == ("grid_fader", 1)


def test_route_midi_event_drops_unresolvable_events_when_grid_is_active() -> None:
    outcome = build_grid_controller(_topology([_pbf4(0)]))
    event = _raw_cc_event(99)  # no recognized element at this address
    assert route_midi_event(event, grid_active=True, controller=outcome.controller) is None
