"""Tests for the Named Controller Ambiguous dialog (docs/llds/app-ui.md
§ Named Controller UI).

Uses PySide6's offscreen platform plugin, matching `test_controller_view_
widgets.py`'s existing convention - no real display, safe for CI.

@spec NAMEDCTRL-AMBIG-002, UI-NAMEDCTRL-002, UI-NAMEDCTRL-003
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

from dragonmidi.named_controller_dialog import NamedControllerAmbiguousDialog  # noqa: E402
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
