"""Unifies the Mapping View's and Configuration Dialog's existing row output,
plus the active controller's raw `control_names`/`knob_to_fader`/
`mute_to_fader`/`websocket_keys`, into one per-control list for the
Controller View (`docs/llds/app-ui.md § Control Descriptor and Inspector
Editor Registry`).

Four sources are combined, each catching what the others miss:

- `build_fader_rows()` - every fader.
- `build_configuration_rows()` - every control with an `opinionated_map`
  entry or a special-cased row (the jog wheel, transport/marker/Scene/Track)
  that isn't a fader, Knob, Mute, or Solo - those four are expanded per-bank
  below instead of taken from this source's collapsed summary rows.
- Per-bank Knob/Mute/Solo expansion, below - one descriptor per real
  `knob_to_fader`/`mute_to_fader` key and per `websocket_keys.solos` entry,
  not the single collapsed `KNOB_ROW_KEY`/`MUTE_ROW_KEY`/`SOLO_ROW_KEY`
  summary row `build_configuration_rows()` produces for Table View. Table
  View's one-row-per-type collapsing (`docs/llds/app-ui.md`'s 2026-07-23
  decision) is the right call for a flat table; it's the wrong shape for
  per-channel grouping (Phase 1.1), which needs to know *which bank* each
  Knob/Mute/Solo belongs to - something the collapsed row doesn't carry.
- `active_controller.control_names` directly, for any key none of the
  above produced a row for - caught while testing against a real Intech Grid
  VSN1 controller: its buttons and jog wheel have `control_names` entries
  (so Table View's `ConfigurationDialog` *could* name them) but no
  `opinionated_map` entry at all (`docs/high-level-design.md § Delivery
  Phasing`'s Phase 7 note: VSN1's controls aren't wired to a default action
  yet), so `build_configuration_rows()` produces no row for them and an
  earlier two-source version of this function silently omitted them
  entirely - the same "control present on the hardware, with a name, but
  unassigned" case a fader with no axis chosen already represents correctly.

@spec UI-CTRLDESC-001, UI-CTRLDESC-002, UI-CTRLDESC-003, UI-CTRLDESC-004
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .mapping_view_model import KNOB_ROW_KEY, MUTE_ROW_KEY, SOLO_ROW_KEY

_COLLAPSED_SUMMARY_ROW_KEYS = {KNOB_ROW_KEY, MUTE_ROW_KEY, SOLO_ROW_KEY}

if TYPE_CHECKING:
    from .active_controller import ActiveController
    from .mapping_view_model import RowView

    _Key = tuple[str, "int | None"]


@dataclass(frozen=True)
class ControlDescriptor:
    key: "_Key"
    label: str
    control_type: str  # "fader" | "button"


def build_control_descriptors(
    fader_rows: "list[RowView]",
    configuration_rows: "list[RowView]",
    active_controller: "ActiveController",
) -> list[ControlDescriptor]:
    """`fader_rows` (from `build_fader_rows()`) are each "fader" by
    construction. Knob/Mute/Solo are expanded one descriptor per real key
    (not the collapsed summary row) so each can later be grouped under its
    own bank/channel. Every other row in `configuration_rows` is "button".
    Any `control_names` key not already covered by any of the above (e.g.
    VSN1's unwired buttons/jog) is classified "fader" if it's in
    `fader_keys`, else "button"."""
    descriptors = [ControlDescriptor(key=row.key, label=row.name, control_type="fader") for row in fader_rows]
    seen = {row.key for row in fader_rows}

    for knob_key in active_controller.knob_to_fader:
        label = active_controller.control_names.get(knob_key, "Knob")
        descriptors.append(ControlDescriptor(key=knob_key, label=label, control_type="button"))
        seen.add(knob_key)
    for mute_key in active_controller.mute_to_fader:
        label = active_controller.control_names.get(mute_key, "Mute")
        descriptors.append(ControlDescriptor(key=mute_key, label=label, control_type="button"))
        seen.add(mute_key)
    ws_keys = active_controller.websocket_keys
    if ws_keys is not None:
        for solo_key in ws_keys.solos:
            descriptors.append(ControlDescriptor(key=solo_key, label="Solo", control_type="button"))
            seen.add(solo_key)

    seen |= _COLLAPSED_SUMMARY_ROW_KEYS
    for row in configuration_rows:
        if row.key in seen:
            continue  # the collapsed Knob/Mute/Solo summary rows - superseded by the per-bank expansion above
        descriptors.append(ControlDescriptor(key=row.key, label=row.name, control_type="button"))
        seen.add(row.key)

    for key, label in active_controller.control_names.items():
        if key in seen:
            continue
        control_type = "fader" if key in active_controller.fader_keys else "button"
        descriptors.append(ControlDescriptor(key=key, label=label, control_type=control_type))
    return descriptors
