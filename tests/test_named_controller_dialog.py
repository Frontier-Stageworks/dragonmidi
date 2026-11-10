"""Tests for the Named Controller Ambiguous dialog (docs/llds/app-ui.md
§ Named Controller UI).

Uses PySide6's offscreen platform plugin, matching `test_controller_view_
widgets.py`'s existing convention - no real display, safe for CI.

@spec NAMEDCTRL-AMBIG-002, UI-NAMEDCTRL-002, UI-NAMEDCTRL-003
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from dragonmidi.named_controller_dialog import ConfigurationLoadDialog, NamedControllerAmbiguousDialog  # noqa: E402
from dragonmidi.named_controller_registry import NamedController  # noqa: E402


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _candidates() -> tuple[NamedController, ...]:
    shape = ("PBF4", "VSN1", "PBF4")
    return (
        NamedController(id="grid-1", display_name="Stewart Platform Controller", kind="grid", module_shape=shape, created_at="2026-01-01"),
        NamedController(id="grid-2", display_name="Focus Puller Rig", kind="grid", module_shape=shape, created_at="2026-02-01"),
    )


def test_lists_every_candidate_plus_a_create_new_option() -> None:
    _qapp()
    dialog = NamedControllerAmbiguousDialog(_candidates(), ("PBF4", "VSN1", "PBF4"))
    labels = [dialog._list.item(i).text() for i in range(dialog._list.count())]
    assert any("Stewart Platform Controller" in label for label in labels)
    assert any("Focus Puller Rig" in label for label in labels)
    assert any("Create new configuration" in label for label in labels)


def test_selecting_an_existing_candidate_and_accepting_returns_it() -> None:
    _qapp()
    candidates = _candidates()
    dialog = NamedControllerAmbiguousDialog(candidates, ("PBF4", "VSN1", "PBF4"))
    dialog._list.setCurrentRow(1)  # "Focus Puller Rig"
    dialog._on_accept()
    assert dialog.chosen_candidate() is candidates[1]


def test_create_new_prompts_for_a_name_and_returns_it_as_a_plain_string(monkeypatch) -> None:
    _qapp()
    candidates = _candidates()
    dialog = NamedControllerAmbiguousDialog(candidates, ("PBF4", "VSN1", "PBF4"))
    dialog._list.setCurrentRow(len(candidates))  # the "Create new configuration" row
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("My New Rig", True)))
    dialog._on_accept()
    assert dialog.chosen_candidate() == "My New Rig"


def test_create_new_cancelled_leaves_dialog_unresolved(monkeypatch) -> None:
    _qapp()
    candidates = _candidates()
    dialog = NamedControllerAmbiguousDialog(candidates, ("PBF4", "VSN1", "PBF4"))
    dialog._list.setCurrentRow(len(candidates))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    dialog._on_accept()
    assert dialog.chosen_candidate() is None


def test_no_selection_and_cancel_returns_none() -> None:
    _qapp()
    dialog = NamedControllerAmbiguousDialog(_candidates(), ("PBF4", "VSN1", "PBF4"))
    dialog.reject()
    assert dialog.chosen_candidate() is None


# --- ConfigurationLoadDialog (Phase 1.4, @spec UI-SAVELOAD-006/007/008) ---


def test_load_dialog_lists_builtin_and_siblings_with_created_at() -> None:
    _qapp()
    builtin = NamedController(
        id="nanoKONTROL2", display_name="nanoKONTROL2", kind="static", profile_name="nanoKONTROL2", created_at="2026-01-01", is_builtin=True
    )
    sibling = NamedController(
        id="nanoKONTROL2 (2)", display_name="Studio Setup A", kind="static", profile_name="nanoKONTROL2", created_at="2026-02-01"
    )
    dialog = ConfigurationLoadDialog(None, (builtin, sibling))
    labels = [dialog._list.item(i).text() for i in range(dialog._list.count())]
    assert any("nanoKONTROL2" in label and "(built-in)" in label and "2026-01-01" in label for label in labels)
    assert any("Studio Setup A" in label and "(built-in)" not in label and "2026-02-01" in label for label in labels)


def test_load_dialog_selecting_and_accepting_returns_the_chosen_configuration() -> None:
    _qapp()
    a = NamedController(id="nanoKONTROL2", display_name="nanoKONTROL2", kind="static", profile_name="nanoKONTROL2", is_builtin=True)
    b = NamedController(id="nanoKONTROL2 (2)", display_name="Studio Setup A", kind="static", profile_name="nanoKONTROL2")
    dialog = ConfigurationLoadDialog(None, (a, b))
    dialog._list.setCurrentRow(1)
    dialog._on_accept()
    assert dialog.chosen_configuration() is b


def test_load_dialog_disables_a_grid_candidate_whose_shape_does_not_match_connected_hardware() -> None:
    _qapp()
    matching = NamedController(id="grid-1", display_name="Stewart Platform Controller", kind="grid", module_shape=("PBF4", "VSN1"))
    mismatched = NamedController(id="grid-2", display_name="Slider Rig", kind="grid", module_shape=("PBF4", "PBF4"))
    dialog = ConfigurationLoadDialog(None, (matching, mismatched), connected_shape=("PBF4", "VSN1"))

    matching_item = dialog._list.item(0)
    mismatched_item = dialog._list.item(1)
    assert bool(matching_item.flags() & Qt.ItemFlag.ItemIsEnabled) is True
    assert bool(mismatched_item.flags() & Qt.ItemFlag.ItemIsEnabled) is False
    assert "PBF4+PBF4" in mismatched_item.toolTip()
    assert "PBF4+VSN1" in mismatched_item.toolTip()

    # Accepting a disabled row is refused - nothing is chosen.
    dialog._list.setCurrentRow(1)
    dialog._on_accept()
    assert dialog.chosen_configuration() is None

    dialog._list.setCurrentRow(0)
    dialog._on_accept()
    assert dialog.chosen_configuration() is matching


def test_load_dialog_rename_updates_the_row_without_closing(tmp_path, monkeypatch) -> None:
    _qapp()
    from dragonmidi.named_controller_registry import save_named_controller

    sibling = NamedController(id="nanoKONTROL2 (2)", display_name="Old Name", kind="static", profile_name="nanoKONTROL2")
    save_named_controller(tmp_path, sibling)
    dialog = ConfigurationLoadDialog(tmp_path, (sibling,))
    dialog._list.setCurrentRow(0)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("New Name", True)))
    dialog._on_rename_clicked()

    assert "New Name" in dialog._list.item(0).text()
    assert dialog._list.count() == 1  # no duplicate row added
    assert dialog.chosen_configuration() is None  # renaming alone never resolves/accepts the dialog


def test_load_dialog_rename_disabled_for_a_builtin_row() -> None:
    _qapp()
    builtin = NamedController(id="nanoKONTROL2", display_name="nanoKONTROL2", kind="static", profile_name="nanoKONTROL2", is_builtin=True)
    dialog = ConfigurationLoadDialog(None, (builtin,))
    dialog._list.setCurrentRow(0)
    assert dialog._rename_button.isEnabled() is False
