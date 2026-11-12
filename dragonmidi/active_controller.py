"""The structural shape `MappingEngine`, `mapping_view_model.py`'s row builders,
and `MidiInputAdapter` actually depend on, satisfied today by `ControllerProfile`
and now also by `GridRuntimeController` (docs/llds/intech-grid.md § Active Grid
Controller). Neither concrete class needs to know about this Protocol or about
the other - Python's structural typing (`@runtime_checkable` `Protocol`) makes
both conform without inheritance.

Every member below was checked against an actual read site (not sketched,
not aspirational) - see docs/llds/intech-grid.md § Active Grid Controller for
the per-member citation. `setup_hint` is deliberately absent: it's read only
by `app.py`'s UI wiring, not by any of the four consumers this Protocol
describes, so it stays an `app.py`-level duck-typed concern (`getattr(...,
"setup_hint", None)`) rather than a required member here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .mapping import GroupKeys, WebSocketKeys, _MapEntry

    _Key = tuple[str, "int | None"]


@runtime_checkable
class ActiveController(Protocol):
    name: str
    default_channel: int
    has_native_mode: bool
    has_jog_wheel: bool
    has_scene_button: bool
    bank_count: int
    bank_fader_keys: "tuple[_Key, ...]"
    fader_keys: "frozenset[_Key]"
    knob_to_fader: "Mapping[_Key, _Key]"
    mute_to_fader: "Mapping[_Key, _Key]"
    fader_to_knob: "Mapping[_Key, _Key]"
    # Phase 1.6.1, @spec MAP-BANK-011: naming/grouping only - read by
    # control_descriptor.py/control_grouping.py, never by bank_fader_key()
    # or MappingEngine's dispatch (see build_bank_membership()'s docstring).
    record_to_fader: "Mapping[_Key, _Key]"
    select_to_fader: "Mapping[_Key, _Key]"
    opinionated_map: "Mapping[_Key, _MapEntry]"
    control_names: "Mapping[_Key, str]"
    websocket_keys: "WebSocketKeys | None"
    group_keys: "GroupKeys | None"

    def bank_fader_key(self, key: "_Key") -> "_Key | None": ...

    def matches(self, port_name: str) -> bool: ...
