"""Which `ControlDescriptor.control_type` values have a registered Inspector
editor (`docs/llds/app-ui.md § Control Descriptor and Inspector Editor
Registry`). Deliberately a membership test, not a widget factory - the actual
editor widget lives in `controller_view_widgets.py`, which is allowed to
import Qt; this module stays Qt-free so it's unit-testable without a
`QApplication`.

@spec UI-INSPREG-001
"""

from __future__ import annotations

_TYPES_WITH_EDITOR: frozenset[str] = frozenset({"fader"})


def has_editor(control_type: str) -> bool:
    return control_type in _TYPES_WITH_EDITOR
