"""Tests for the Inspector Editor Registry (docs/specs/app-ui.md § Inspector
Editor Registry).

@spec UI-INSPREG-001
"""

from __future__ import annotations

from dragonmidi.inspector_registry import has_editor


# @spec UI-INSPREG-001
def test_fader_has_an_editor() -> None:
    assert has_editor("fader") is True


# @spec UI-INSPREG-001
def test_knob_and_button_have_no_editor() -> None:
    assert has_editor("knob") is False
    assert has_editor("button") is False


# @spec UI-INSPREG-001
def test_unknown_control_type_has_no_editor() -> None:
    assert has_editor("jog_wheel") is False
    assert has_editor("") is False
