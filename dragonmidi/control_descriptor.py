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

from .mapping_view_model import JOG_WHEEL_ARC_ROW_KEY, JOG_WHEEL_ROW_KEY, KNOB_ROW_KEY, MUTE_ROW_KEY, SOLO_ROW_KEY

# JOG_WHEEL_ARC_ROW_KEY is deliberately included here too (Phase 1.5.1): it is
# not a second physical control, just `process_keystroke()`'s independent
# second output for the one physical jog wheel `JOG_WHEEL_ROW_KEY` already
# represents (`MappingEngine.process()`/`process_keystroke()` both run against
# the very same incoming MIDI event - docs/llds/app-ui.md's Phase 1.5.1 audit).
# Table View's Configuration Dialog still shows both as separate rows
# (`mapping_view_model.build_configuration_rows()`, unchanged) - that dense
# table is a different presentation with its own, already-correct precedent
# for one-row-per-output; only the Controller View's *physical inventory* is
# wrong if it shows two jog wheels.
_COLLAPSED_SUMMARY_ROW_KEYS = {KNOB_ROW_KEY, MUTE_ROW_KEY, SOLO_ROW_KEY, JOG_WHEEL_ARC_ROW_KEY}

# Synthetic key tags for a physically-present, MIDI-identity-unconfirmed
# control (Phase 1.5.1, @spec UI-CTRLDESC-005) - never a real MIDI type, never
# looked up in any `opinionated_map`/`address_table`, so these can never be
# interactive or light up on MIDI activity. See `ControllerProfile`'s
# `unconfirmed_channel_controls`/`unconfirmed_global_controls` docstring.
_UNCONFIRMED_CHANNEL_TAG = "unconfirmed_channel"
_UNCONFIRMED_GLOBAL_TAG = "unconfirmed_global"

# Physical hardware identity only - never the control's assigned function
# (Phase 1.2). A jog wheel/VSN1 jog is its own physical shape, distinct from
# an ordinary button, even though neither gets an Inspector editor yet
# (`inspector_registry.py`) - no new jog functionality in this phase, just
# accurate labeling.
_JOG_KEYS = {JOG_WHEEL_ROW_KEY, JOG_WHEEL_ARC_ROW_KEY}
_JOG_TAGS = {"grid_vsn1_jog", "grid_vsn1_jog_button"}

if TYPE_CHECKING:
    from .active_controller import ActiveController
    from .mapping_view_model import RowView

    _Key = tuple[str, "int | None"]


@dataclass(frozen=True)
class ControlDescriptor:
    key: "_Key"
    label: str
    control_type: str  # "fader" | "rotary" | "button" | "jog"


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

    # A Knob-role control is physically a Rotary (Korg's Knob, PBF4's potentiometer) -
    # distinct from the generic Button shape, so it gets its own Inspector editor
    # (@spec UI-CTRLDESC-002, Phase 1.2).
    for knob_key in active_controller.knob_to_fader:
        label = active_controller.control_names.get(knob_key, "Knob")
        descriptors.append(ControlDescriptor(key=knob_key, label=label, control_type="rotary"))
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
        control_type = "jog" if row.key in _JOG_KEYS else "button"
        descriptors.append(ControlDescriptor(key=row.key, label=row.name, control_type=control_type))
        seen.add(row.key)

    for key, label in active_controller.control_names.items():
        if key in seen:
            continue
        if key in active_controller.fader_keys:
            control_type = "fader"
        elif key[0] in _JOG_TAGS:
            control_type = "jog"
        else:
            control_type = "button"
        descriptors.append(ControlDescriptor(key=key, label=label, control_type=control_type))

    # Physically-present, MIDI-identity-unconfirmed controls (Phase 1.5.1) -
    # appended last, after every real-MIDI-backed control, so they read as an
    # explicit addendum rather than being interleaved with confirmed controls.
    # `getattr` defaults keep this a no-op for any `ActiveController` that
    # doesn't declare either field (Grid's `GridRuntimeController`, and any
    # third-party-config-loaded profile - see `build_profile()`'s docstring).
    for label_index, label in enumerate(getattr(active_controller, "unconfirmed_global_controls", ())):
        key = (f"{_UNCONFIRMED_GLOBAL_TAG}_{label_index}", None)
        descriptors.append(ControlDescriptor(key=key, label=label, control_type="button"))
    bank_count = getattr(active_controller, "bank_count", 0)
    for label_index, label in enumerate(getattr(active_controller, "unconfirmed_channel_controls", ())):
        for bank in range(1, bank_count + 1):
            # `label_index` keeps keys unique across multiple unconfirmed labels
            # (e.g. two different unconfirmed per-channel buttons); `bank` keeps
            # them unique across channels - `_bank_index_for` (control_grouping.py)
            # matches on the tag prefix, independent of `label_index`.
            key = (f"{_UNCONFIRMED_CHANNEL_TAG}_{label_index}", bank)
            descriptors.append(ControlDescriptor(key=key, label=label, control_type="button"))
    return descriptors
