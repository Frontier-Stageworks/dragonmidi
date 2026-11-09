"""Which `ControlDescriptor.control_type` values have a registered Inspector
editor (`docs/llds/app-ui.md § Control Descriptor and Inspector Editor
Registry`). Deliberately a membership test, not a widget factory - the actual
editor widget lives in `controller_view_widgets.py`, which is allowed to
import Qt; this module stays Qt-free so it's unit-testable without a
`QApplication`.

@spec UI-INSPREG-001, UI-INSPREG-002
"""

from __future__ import annotations

# "jog" is deliberately absent (Phase 1.2): no new Shuttle/Jog functionality
# is in scope yet, so a jog wheel/VSN1 jog gets accurate physical labeling
# (control_descriptor.py) but no editor.
_TYPES_WITH_EDITOR: frozenset[str] = frozenset({"fader", "rotary"})


def has_editor(control_type: str, *, bank_derived: bool = False) -> bool:
    """`bank_derived` is only consulted for `"button"` (@spec UI-INSPREG-002):
    a Mute-role control (Korg's Mute, PBF4's channel Button) has a
    configurable action, but a Solo/transport/Scene/VSN1 button does not -
    "only expose actions the current DragonMIDI/Dragonframe integration
    actually supports," not every physical button. A `"fader"`/`"rotary"`
    always has an editor regardless of `bank_derived`."""
    if control_type == "button":
        return bank_derived
    return control_type in _TYPES_WITH_EDITOR
