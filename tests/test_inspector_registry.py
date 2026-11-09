"""Tests for the Inspector Editor Registry (docs/specs/app-ui.md § Inspector
Editor Registry).

@spec UI-INSPREG-001, UI-INSPREG-002
"""

from __future__ import annotations

from dragonmidi.inspector_registry import has_editor


# @spec UI-INSPREG-001
def test_fader_has_an_editor() -> None:
    assert has_editor("fader") is True


# @spec UI-INSPREG-001, UI-INSPREG-002 (Phase 1.2)
def test_rotary_has_an_editor_regardless_of_bank_derived() -> None:
    assert has_editor("rotary") is True
    assert has_editor("rotary", bank_derived=False) is True


# @spec UI-INSPREG-002 (Phase 1.2)
def test_bank_derived_button_has_an_editor() -> None:
    assert has_editor("button", bank_derived=True) is True


# @spec UI-INSPREG-002 (Phase 1.2)
def test_non_bank_derived_button_has_no_editor() -> None:
    assert has_editor("button") is False
    assert has_editor("button", bank_derived=False) is False


# @spec UI-INSPREG-001
def test_jog_has_no_editor() -> None:
    assert has_editor("jog") is False


# @spec UI-INSPREG-001
def test_unknown_control_type_has_no_editor() -> None:
    assert has_editor("jog_wheel") is False
    assert has_editor("") is False
