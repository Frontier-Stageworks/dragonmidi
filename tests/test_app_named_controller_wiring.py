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
@spec UI-NAMEDCTRL-001
@spec NAMEDCTRL-DATA-005, NAMEDCTRL-CONFIG-004
@spec UI-SAVELOAD-001 through UI-SAVELOAD-012
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox  # noqa: E402

import dragonmidi.app as appmod  # noqa: E402
from dragonmidi.controller_selection import StaticChoice  # noqa: E402
from dragonmidi.grid_controller import Ready, build_grid_controller  # noqa: E402
from dragonmidi.grid_lifecycle import GridStatus  # noqa: E402
from dragonmidi.grid_modules import ModuleType  # noqa: E402
from dragonmidi.grid_topology import GridModule, GridTopology  # noqa: E402
from dragonmidi.named_controller_registry import NamedController, save_named_controller  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _pbf4(x: int) -> GridModule:
    return GridModule(heartbeat_type=0, hwcfg=64, module_type=ModuleType.PBF4, x=x, y=0, rotation=0)


class _FakePynputBackend:
    """Stands in for `dragonmidi.keystroke_output.PynputBackend` - the real
    one eagerly imports and constructs `pynput.keyboard.Controller()`, which
    refuses to initialize on a headless Linux CI runner with no X11 display
    at all, regardless of Qt's own `QT_QPA_PLATFORM=offscreen` setting (a
    separate concern). This module's tests only exercise `app.py`'s
    composition/wiring, never actual keystroke output, so a real backend is
    never needed - matching `test_keystroke_output.py`'s own
    `FakeKeystrokeBackend` convention (@spec KEY-BACKEND-001)."""

    def press(self, key: str) -> None:
        pass

    def release(self, key: str) -> None:
        pass


@pytest.fixture
def window(tmp_path, monkeypatch):
    _qapp()
    monkeypatch.setattr(appmod, "_user_controllers_dir", lambda: tmp_path / "controllers")
    monkeypatch.setattr(appmod, "_configurations_dir", lambda: tmp_path / "configurations")
    monkeypatch.setattr(appmod, "_named_controllers_dir", lambda: tmp_path / "named_controllers")
    monkeypatch.setattr(appmod, "PynputBackend", _FakePynputBackend)
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


def test_preset_store_key_for_static_profile_is_unchanged_by_this_feature(window, tmp_path, monkeypatch) -> None:
    # The default profile's Named Controller is a builtin as of Phase 1.4
    # (NAMEDCTRL-DATA-005), so an ordinary edit no longer live-writes to it
    # directly (UI-SAVELOAD-012) - force it non-builtin here to isolate this
    # test's actual subject (the Preset Store key is unchanged), which is
    # orthogonal to builtin protection (covered separately below).
    profile_name = window._default_profile.name
    non_builtin = NamedController(id=profile_name, display_name=profile_name, kind="static", profile_name=profile_name, is_builtin=False)
    monkeypatch.setattr(window, "_active_named_controller", non_builtin)
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    assert (tmp_path / "configurations" / f"{window._default_profile.name}.json").is_file()


# --- Grid: zero/one/many matching, installed via the real composition root ---


def test_grid_zero_match_creates_and_installs_a_named_controller(window) -> None:
    controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(controller)
    assert window._active_named_controller.kind == "grid"
    assert window._active_named_controller.id == "grid-1"
    assert window._active_named_controller.module_shape == ("PBF4",)
    assert window._mapping.profile is controller
    assert window._save_button.isEnabled() is True
    assert window._save_as_button.isEnabled() is True
    assert window._load_button.isEnabled() is True


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


# --- Grid Save As / Load, including shape-mismatch refusal (Phase 1.4) ---


def test_grid_save_as_then_load_round_trips_through_a_different_shape(window, monkeypatch) -> None:
    """Save As a configuration for one connected shape, then connect a
    *different* shape, then Load's defense-in-depth re-check refuses to
    install the mismatched saved configuration (@spec UI-SAVELOAD-009,
    NAMEDCTRL-CONFIG-006) - installing it would apply a (Bank, Group) axis
    table built for different physical hardware onto what's actually
    connected."""
    first_shape_controller = _grid_ready_controller(_pbf4(0))
    window._resolve_and_install_grid_controller(first_shape_controller)
    window._mapping.set_axis_target(first_shape_controller.bank_fader_keys[0], 1, "PAN", 0.0, 100.0)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Single PBF4 Rig", True)))
    window._on_save_as_clicked()
    saved = window._active_named_controller
    assert saved.module_shape == ("PBF4",)

    # A different, two-module shape settles and gets installed instead.
    second_shape_controller = _grid_ready_controller(_pbf4(0), _pbf4(1))
    window._resolve_and_install_grid_controller(second_shape_controller)
    assert window._active_named_controller.id != saved.id

    class FakeLoadDialogReturningMismatchedSave:
        def __init__(self, *a, **k) -> None:
            pass

        def exec(self) -> None:
            pass

        def chosen_configuration(self):
            return saved  # shape ("PBF4",) - does not match the now-connected two-module shape

    monkeypatch.setattr(appmod, "ConfigurationLoadDialog", FakeLoadDialogReturningMismatchedSave)
    before = window._active_named_controller
    window._on_load_clicked()

    assert window._active_named_controller is before  # refused - nothing installed
    assert window._mapping.profile is second_shape_controller


# --- Save/Save As/Load (UI-SAVELOAD-*, Phase 1.4) ---


def test_default_launch_is_builtin_and_dirty_starts_false(window) -> None:
    assert window._active_named_controller.is_builtin is True
    assert window._dirty is False


def test_editing_a_builtin_sets_dirty_and_does_not_write_its_file(window, tmp_path) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    assert window._dirty is True
    assert not (tmp_path / "configurations" / f"{window._default_profile.name}.json").exists()
    assert "•" in window._active_config_label.text()


def test_save_on_a_builtin_routes_into_save_as(window, tmp_path, monkeypatch) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Studio Setup A", True)))

    window._on_save_clicked()

    assert window._active_named_controller.display_name == "Studio Setup A"
    assert window._active_named_controller.is_builtin is False
    assert window._dirty is False
    builtin_path = tmp_path / "configurations" / f"{window._default_profile.name}.json"
    assert not builtin_path.exists()  # the builtin's own file is still untouched
    sibling_path = tmp_path / "configurations" / f"{window._active_named_controller.id}.json"
    assert sibling_path.is_file()


def test_save_as_seeds_the_sibling_with_current_in_memory_state_not_a_disk_reload(window, tmp_path, monkeypatch) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()  # held in memory only - builtin active
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Studio Setup A", True)))

    window._on_save_as_clicked()

    from dragonmidi.preset_store import load_group_axis_targets

    saved = load_group_axis_targets(tmp_path / "configurations", window._active_named_controller.id, window._default_profile.bank_count)
    assert saved[1][1]["axis_name"] == "PAN"


def test_save_on_a_non_builtin_is_idempotent_and_clears_dirty(window, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Studio Setup A", True)))
    window._on_save_as_clicked()  # now active, non-builtin, not dirty
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()  # non-builtin: live-writes immediately, never dirty
    assert window._dirty is False

    window._on_save_clicked()
    assert window._dirty is False
    assert "•" not in window._active_config_label.text()


def test_switching_profile_while_dirty_prompts_and_cancel_keeps_edits(window, monkeypatch) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    assert window._dirty is True
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))

    other_index = next(i for i, c in enumerate(window._controller_choices) if c.name != window._default_profile.name)
    window._profile_combo.setCurrentIndex(other_index)

    assert window._dirty is True  # declined - nothing discarded
    assert window._active_named_controller.id == window._default_profile.name


def test_switching_profile_while_dirty_confirmed_discards_and_installs_the_new_profile(window, monkeypatch) -> None:
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard))

    other_choice = next(c for c in window._controller_choices if c.name != window._default_profile.name and isinstance(c, StaticChoice))
    other_index = window._controller_choices.index(other_choice)
    window._profile_combo.setCurrentIndex(other_index)

    assert window._dirty is False
    assert window._active_named_controller.id == other_choice.profile.name


def test_selecting_grid_while_a_korg_builtin_is_dirty_is_also_gated(window, monkeypatch) -> None:
    """@spec UI-SAVELOAD-010: the discard check runs before either branch -
    not just the static-profile branch."""
    window._mapping.set_axis_target(("cc", 0), 1, "PAN", 0.0, 100.0)
    window._on_mapping_changed()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel))

    grid_index = next(i for i, c in enumerate(window._controller_choices) if c.name == "Intech Grid")
    window._profile_combo.setCurrentIndex(grid_index)

    assert window._dirty is True  # declined - Grid was never actually selected
    assert window._active_named_controller.kind == "static"


def test_load_installs_the_chosen_configuration_via_the_existing_install_path(window, monkeypatch) -> None:
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Studio Setup A", True)))
    window._on_save_as_clicked()
    sibling = window._active_named_controller
    profile_name = window._default_profile.name
    builtin = NamedController(id=profile_name, display_name=profile_name, kind="static", profile_name=profile_name, is_builtin=True)

    class FakeLoadDialogToBuiltin:
        def __init__(self, *a, **k) -> None:
            pass

        def exec(self) -> None:
            pass

        def chosen_configuration(self):
            return builtin

    monkeypatch.setattr(appmod, "ConfigurationLoadDialog", FakeLoadDialogToBuiltin)
    window._on_load_clicked()  # active is now `sibling` (non-builtin, never dirty) -> Load back to builtin needs no discard prompt
    assert window._active_named_controller.id == builtin.id

    class FakeLoadDialogToSibling:
        def __init__(self, *a, **k) -> None:
            pass

        def exec(self) -> None:
            pass

        def chosen_configuration(self):
            return sibling

    monkeypatch.setattr(appmod, "ConfigurationLoadDialog", FakeLoadDialogToSibling)
    window._on_load_clicked()
    assert window._active_named_controller.id == sibling.id


def test_save_load_buttons_disabled_while_grid_selected_but_not_yet_settled(window) -> None:
    grid_index = next(i for i, c in enumerate(window._controller_choices) if c.name == "Intech Grid")
    window._profile_combo.setCurrentIndex(grid_index)
    assert window._save_button.isEnabled() is False
    assert window._save_as_button.isEnabled() is False
    assert window._load_button.isEnabled() is False


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
