"""Integration tests for `app.py`'s Named Controller wiring - the composition
root that resolves a Named Controller before installing a static profile or a
settled Grid controller, keys the Preset Store by its `id`, and surfaces its
`display_name` through the existing status-text slot (docs/llds/named-
controller.md, docs/llds/app-ui.md § Named Controller UI).

Constructs a real `DragonMidiWindow`, with its three persistence directories
redirected to a temp path (monkeypatched module-level functions) so this never
touches the real `~/Documents/DragonMIDI/` tree or depends on filesystem
permissions outside the temp directory. Uses PySide6's offscreen platform
plugin, matching every other Qt-level test file's convention. Does not open
any real MIDI port or serial connection - `DragonMidiWindow.__init__` only
*constructs* `MidoBackend`/`SerialGridTransport` without opening anything
until a device/port is actually found by the discovery poll, which these
tests never trigger (no `_on_discovery_tick()`/real `GridLifecycle.poll()`
call is driven here - Grid's settle is simulated by handing a directly-built
`GridRuntimeController` to `_resolve_and_install_grid_controller()`,
bypassing the CDC transport/timing entirely, the same seam
`test_grid_app_coordinator.py` already exercises at one layer down).

@spec NAMEDCTRL-STATIC-001, NAMEDCTRL-STATIC-002
@spec GRID-APP-003 (revised Phase 1.3), NAMEDCTRL-MATCH-002, NAMEDCTRL-MATCH-004
@spec UI-NAMEDCTRL-001, UI-NAMEDCTRL-004
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

import dragonmidi.app as appmod  # noqa: E402
from dragonmidi.grid_controller import Ready, build_grid_controller  # noqa: E402
from dragonmidi.grid_lifecycle import GridStatus  # noqa: E402
from dragonmidi.grid_modules import ModuleType  # noqa: E402
from dragonmidi.grid_topology import GridModule, GridTopology  # noqa: E402
from dragonmidi.named_controller_registry import NamedController, save_named_controller  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


@pytest.fixture
def window(tmp_path, monkeypatch):
    _qapp()
    monkeypatch.setattr(appmod, "_user_controllers_dir", lambda: tmp_path / "controllers")
    monkeypatch.setattr(appmod, "_configurations_dir", lambda: tmp_path / "configurations")
    monkeypatch.setattr(appmod, "_named_controllers_dir", lambda: tmp_path / "named_controllers")
    win = appmod.DragonMidiWindow()
    yield win


def _grid_ready_controller(*modules: GridModule):
    outcome = build_grid_controller(GridTopology(modules=tuple(modules), current_page=0))
    assert isinstance(outcome, Ready)
    return outcome.controller


# --- Static profile: transparent 1:1 wrapper (NAMEDCTRL-STATIC-*) ---


def test_default_launch_wraps_the_default_profile_in_a_named_controller(window) -> None:
    assert window._active_named_controller.kind == "static"
    assert window._active_named_controller.id == window._default_profile.name
    assert window._active_named_controller.display_name == window._default_profile.name


def test_preset_store_key_for_static_profile_is_unchanged_by_this_feature(window, tmp_path) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._save_group_axis_targets()
    assert (tmp_path / "configurations" / f"{window._default_profile.name}.json").is_file()


# --- Grid: zero/one/many matching, installed via the real composition root ---


def test_grid_zero_match_creates_and_installs_a_named_controller(window) -> None:
    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)
    assert window._active_named_controller.kind == "grid"
    assert window._active_named_controller.id == "grid-1"
    assert window._active_named_controller.module_shape == ("PBF4",)
    assert window._mapping.profile is controller
    assert window._rename_button.isEnabled() is True


def test_grid_rebuild_with_the_same_shape_resolves_to_the_same_named_controller(window) -> None:
    first = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(first)
    first_id = window._active_named_controller.id

    second = _grid_ready_controller(_pbf4(0), _pbf4(1))  # different physical count -> different shape, sanity check first
    window._resolve_and_install_grid_controller(second)
    assert window._active_named_controller.id != first_id  # different shape, different (new) Named Controller

    third = _grid_ready_controller(_pbf4(0))  # back to the original shape
    window._resolve_and_install_grid_controller(third)
    assert window._active_named_controller.id == first_id  # same shape, same Named Controller - no duplicate


# @spec NAMEDCTRL-AMBIG-001, UI-NAMEDCTRL-005
def test_grid_ambiguous_match_blocks_until_the_dialog_resolves(window, tmp_path, monkeypatch) -> None:
    shape = ("PBF4",)
    named_controllers_dir = tmp_path / "named_controllers"
    stewart = NamedController(id="grid-a", display_name="Stewart Platform Controller", kind="grid", module_shape=shape)
    focus_puller = NamedController(id="grid-b", display_name="Focus Puller Rig", kind="grid", module_shape=shape)
    save_named_controller(named_controllers_dir, stewart)
    save_named_controller(named_controllers_dir, focus_puller)

    class FakeAmbiguousDialog:
        def __init__(self, candidates, module_shape):
            self._candidates = candidates

        def exec(self) -> None:
            pass

        def chosen_candidate(self):
            return next(c for c in self._candidates if c.id == "grid-b")

    monkeypatch.setattr(appmod, "NamedControllerAmbiguousDialog", FakeAmbiguousDialog)
    timer_running_before = window._ui_timer.isActive()

    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)

    assert window._active_named_controller.id == "grid-b"
    assert window._mapping.profile is controller
    assert window._ui_timer.isActive() == timer_running_before  # stopped-then-restarted, net unchanged
    # The status text set right before the dialog opened is still the last
    # thing _midi_row shows (nothing else touched it after); must read as a
    # named-controller ambiguity, never the pre-existing Grid CDC "multiple
    # devices found" wording (docs/specs/intech-grid.md § GRID-DISCOVER-004).
    from dragonmidi.grid_lifecycle import _STATUS_TEXT, GridStatus

    assert window._midi_row._detail.text() != _STATUS_TEXT[GridStatus.AMBIGUOUS]
    assert "saved configuration" in window._midi_row._detail.text()


def test_grid_ambiguous_match_cancelled_installs_nothing(window, tmp_path, monkeypatch) -> None:
    shape = ("PBF4",)
    save_named_controller(tmp_path / "named_controllers", NamedController(id="grid-a", display_name="A", kind="grid", module_shape=shape))
    save_named_controller(tmp_path / "named_controllers", NamedController(id="grid-b", display_name="B", kind="grid", module_shape=shape))

    class FakeCancelledDialog:
        def __init__(self, candidates, module_shape) -> None:
            pass

        def exec(self) -> None:
            pass

        def chosen_candidate(self):
            return None

    monkeypatch.setattr(appmod, "NamedControllerAmbiguousDialog", FakeCancelledDialog)
    previous_profile = window._mapping.profile
    previous_named_controller = window._active_named_controller

    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)

    assert window._mapping.profile is previous_profile  # not installed
    assert window._active_named_controller is previous_named_controller  # unchanged


def test_grid_ambiguous_match_create_new_persists_under_a_fresh_id(window, tmp_path, monkeypatch) -> None:
    shape = ("PBF4",)
    save_named_controller(tmp_path / "named_controllers", NamedController(id="grid-a", display_name="A", kind="grid", module_shape=shape))
    save_named_controller(tmp_path / "named_controllers", NamedController(id="grid-b", display_name="B", kind="grid", module_shape=shape))

    class FakeCreateNewDialog:
        def __init__(self, candidates, module_shape) -> None:
            pass

        def exec(self) -> None:
            pass

        def chosen_candidate(self):
            return "Brand New Rig"

    monkeypatch.setattr(appmod, "NamedControllerAmbiguousDialog", FakeCreateNewDialog)

    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)

    assert window._active_named_controller.display_name == "Brand New Rig"
    assert window._active_named_controller.id not in ("grid-a", "grid-b")
    assert window._mapping.profile is controller


# --- Rename (UI-NAMEDCTRL-004) ---


def test_rename_changes_display_name_without_touching_the_preset_store_key(window, tmp_path, monkeypatch) -> None:
    original_id = window._active_named_controller.id
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Camera Rig", True)))
    window._on_rename_named_controller_clicked()

    assert window._active_named_controller.display_name == "Camera Rig"
    assert window._active_named_controller.id == original_id

    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._save_group_axis_targets()
    assert (tmp_path / "configurations" / f"{original_id}.json").is_file()


def test_rename_button_disabled_while_grid_selected_but_not_yet_settled(window) -> None:
    grid_index = next(i for i, c in enumerate(window._controller_choices) if c.name == "Intech Grid")
    window._profile_combo.setCurrentIndex(grid_index)
    assert window._rename_button.isEnabled() is False


# --- Status text override (UI-NAMEDCTRL-001) ---


def test_status_text_shows_the_active_grid_named_controllers_display_name_once_active(window) -> None:
    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)
    window._active_named_controller = NamedController(id="grid-1", display_name="Stewart Platform Controller", kind="grid", module_shape=("PBF4",))
    window._grid_coordinator.grid_active = True
    window._grid_coordinator.lifecycle._status = GridStatus.ACTIVE
    window._grid_coordinator.poll = lambda: None  # no real hardware connected in this test; avoid the real poll() resetting status back to WAITING

    window._on_tick()

    assert window._midi_row._detail.text() == "Stewart Platform Controller"


def test_status_text_for_korg_is_unaffected_by_this_feature(window) -> None:
    # A static profile's live status text still shows the real connected
    # device name or the ordinary waiting text - never a Named Controller
    # display_name override, which would hide which actual port is connected.
    window._on_tick()
    assert "Stewart" not in window._midi_row._detail.text()
    assert window._midi_row._detail.text() == f"Waiting for {window._default_profile.name}…"
