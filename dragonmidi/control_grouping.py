"""Groups `ControlDescriptor`s for navigation (`docs/llds/app-ui.md
§ Control Grouping`, Phase 1.1) - a presentation layer over the existing
descriptor list, not a new mapping model. A control's `ControlGroup`
membership is derived entirely from data the active controller already
exposes (`bank_fader_keys`, `knob_to_fader`, `mute_to_fader`,
`websocket_keys`, and, for Intech Grid specifically, its own per-channel key
tags) - never from parsing a display-name string, and never from checking
the controller's own name/type.

@spec UI-CTRLGROUP-001 through UI-CTRLGROUP-005
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .active_controller import ActiveController
    from .control_descriptor import ControlDescriptor

    _Key = tuple[str, "int | None"]

GLOBAL_GROUP_ID = "global"
GLOBAL_GROUP_LABEL = "Transport & Global"
FALLBACK_GROUP_ID = "controls"
FALLBACK_GROUP_LABEL = "Controls"

# Intech Grid's own per-module-type key tags (`grid_controller.py`'s
# `_PBF4_ROLE_TAGS`/`_VSN1_ROLE_TAGS`) are the one place this module needs
# controller-family-specific knowledge, mirroring `control_descriptor.py`'s
# own precedent of reading real Grid key shapes rather than inventing a
# zero-knowledge universal rule. PBF4's pot/button share their fader's own
# numeric index within one module (`grid_controller.py`'s per-tag counters
# increment in lockstep across one module's pot/fader/button elements), so
# matching on that shared index is enough - no reverse map needed, unlike
# Korg's Knob/Mute (which route through `bank_fader_key()` below instead).
_PBF4_CHANNEL_TAGS = frozenset({"grid_pbf4_pot", "grid_pbf4_button"})
_VSN1_BUTTON_TAG = "grid_vsn1_button"
_VSN1_JOG_TAGS = frozenset({"grid_vsn1_jog", "grid_vsn1_jog_button"})


@dataclass(frozen=True)
class ControlGroup:
    id: str
    label: str
    controls: tuple["ControlDescriptor", ...]
    kind: str  # "channel" | "global" | "fallback" | "vsn1_buttons" | "vsn1_jog"


def _bank_index_for(key: "_Key", active_controller: "ActiveController") -> int | None:
    """Which Bank (1-based) `key` belongs to, or `None` if it isn't a member
    of any Bank's channel strip. Faders are members of their own Bank;
    Knob/Mute resolve via the existing `bank_fader_key()` method every
    `ActiveController` already provides; Solo resolves via its position in
    `websocket_keys.solos` (the same tuple `MappingEngine.process_websocket`
    already indexes into for its `N + bank_count*(g-1)` formula)."""
    bank_fader_keys = active_controller.bank_fader_keys
    fader_key = key if key in active_controller.fader_keys else active_controller.bank_fader_key(key)
    if fader_key is not None:
        try:
            return bank_fader_keys.index(fader_key) + 1
        except ValueError:
            return None
    ws_keys = active_controller.websocket_keys
    if ws_keys is not None and key in ws_keys.solos:
        return ws_keys.solos.index(key) + 1
    kind, number = key
    if kind in _PBF4_CHANNEL_TAGS and isinstance(number, int) and 1 <= number <= active_controller.bank_count:
        return number
    return None


def build_control_groups(
    descriptors: "list[ControlDescriptor]", active_controller: "ActiveController"
) -> list[ControlGroup]:
    """Channel groups 1..bank_count first (each only created if it ends up
    with at least one member - a Bank with only a Fader and no Knob/Mute/
    Solo still gets a one-member Channel group), in Bank order; then any
    VSN1-specific Buttons/Jog Wheel groups; then one catch-all group for
    whatever is left (`Transport & Global` for Korg/PBF4's genuinely
    transport-and-global leftovers, `Controls` for a controller with no
    recognized channel structure at all - `UI-CTRLGROUP-004`'s fallback).
    Every descriptor ends up in exactly one group - none are dropped.
    """
    channel_members: dict[int, list[ControlDescriptor]] = {}
    vsn1_buttons: list[ControlDescriptor] = []
    vsn1_jog: list[ControlDescriptor] = []
    leftover: list[ControlDescriptor] = []

    for descriptor in descriptors:
        bank = _bank_index_for(descriptor.key, active_controller)
        if bank is not None:
            channel_members.setdefault(bank, []).append(descriptor)
            continue
        kind = descriptor.key[0]
        if kind == _VSN1_BUTTON_TAG:
            vsn1_buttons.append(descriptor)
        elif kind in _VSN1_JOG_TAGS:
            vsn1_jog.append(descriptor)
        else:
            leftover.append(descriptor)

    groups: list[ControlGroup] = []
    for bank in sorted(channel_members):
        groups.append(
            ControlGroup(
                id=f"channel-{bank}",
                label=f"Channel {bank}",
                controls=tuple(channel_members[bank]),
                kind="channel",
            )
        )
    if vsn1_buttons:
        groups.append(ControlGroup(id="vsn1-buttons", label="Buttons", controls=tuple(vsn1_buttons), kind="vsn1_buttons"))
    if vsn1_jog:
        groups.append(ControlGroup(id="vsn1-jog", label="Jog Wheel", controls=tuple(vsn1_jog), kind="vsn1_jog"))
    if leftover:
        if groups:
            # A controller with real channel/VSN1 structure: its leftovers
            # are genuinely transport/global controls (Play, Stop, Scene,
            # Cycle, Markers, Track, the Korg jog wheel's two rows, ...).
            groups.append(ControlGroup(id=GLOBAL_GROUP_ID, label=GLOBAL_GROUP_LABEL, controls=tuple(leftover), kind="global"))
        else:
            # No channel/VSN1 structure recognized at all (UI-CTRLGROUP-004's
            # fallback) - everything lands in one generically-named group
            # rather than being dropped.
            groups.append(ControlGroup(id=FALLBACK_GROUP_ID, label=FALLBACK_GROUP_LABEL, controls=tuple(leftover), kind="fallback"))
    return groups
