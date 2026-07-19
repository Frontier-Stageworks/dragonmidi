# Static Mapping Engine — EARS Specs

Traces to `docs/llds/static-mapping.md`.

## Opinionated Table

- [x] **MAP-TABLE-001**: For every table entry whose MIDI source is a CC message, the system shall map it to its corresponding Dragonframe OSC message only when the event's MIDI channel is 16 (zero-indexed 15); an otherwise-matching CC control on any other channel shall not match any table entry. This invariant does not apply to the Scene button (`korg_scene` type), which matches on type alone — its `channel` field is the controller's own configured Native Mode global-channel ID (see `MIDI-NATIVE-001`), not a stand-in for MIDI channel 16, and may legitimately be any value 0–15.
- [x] **MAP-TABLE-002**: While a fader (CC 0–7) or knob (CC 16–23) control **whose target is an OSC encoder channel** changes value, the system shall send its mapped `/dragonframe/encoder/<n>` OSC message (float 0.0–1.0) on every distinct value received, with no debounce. (A fader retargeted to an OSC axis (direct) instead follows `MAP-AXIS-001`, not this spec.)
- [x] **MAP-TABLE-003**: When a mapped button-type control (Mute 1–8, Solo 1–8, Return to Zero, Transport Record, Play, Stop, Rewind, Fast Forward, Cycle, Previous Marker, Next Marker, Previous Track, Next Track, or the Native Mode Scene button) transitions to pressed, the system shall send that control's mapped one-shot Dragonframe OSC message exactly once per transition.
- [x] **MAP-TABLE-004**: When the jog wheel (CC 110) sends a KORG sign-magnitude relative value, the system shall decode it to a signed delta (`0` or `64` → `0`; `1`–`63` → positive; `65`–`127` → negative via `raw − 64`) and send it as `/dragonframe/encoder/17`.
- [x] **MAP-TABLE-005**: If a MIDI event does not correspond to any entry in the opinionated table (including Record 1–8, Select 1–8, and Set Marker), then the system shall produce no OSC output and no log entry for it.

## OSC Axis (Direct) Target

- [x] **MAP-AXIS-001**: While a fader targeting an OSC axis (direct) changes value, the system shall send `/dragonframe/axis/{axisname}/gotoPosition,f (position)` on every distinct value, with no debounce, where `position = min + normalized_value * (max - min)` using that mapping entry's configured `min` and `max`.
- [x] **MAP-AXIS-002**: The system shall accept any real-valued `min`/`max` pair for an OSC axis (direct) target — including `min > max` and `min == max` — without validation or rejection.
- [x] **MAP-AXIS-003**: When the user configures an OSC axis (direct) target, the system shall restrict axis name selection to names present in the OSC Listener's discovered list at that moment (`OSC-DISCOVER-005`, `docs/specs/osc-io.md`) and shall not accept an arbitrary or free-text axis name; this restriction applies only at selection time and is not re-enforced afterward against a mapping entry already configured (see `MAP-AXIS-006` for what happens if the axis later disappears). Enforced by the Mapping View UI (picker), not the `MappingEngine` class — see `UI-MAP-004`, `docs/specs/app-ui.md`.
- [x] **MAP-AXIS-006**: If a mapping entry's configured axis name is absent from the OSC Listener's discovered list at the time a `gotoPosition` message would be sent for it, the system shall send the message anyway (targeting that name unconditionally); it shall not withhold the send, warn, or disable the mapping entry based on discovered-list membership.
- [x] **MAP-AXIS-004**: The system shall offer the OSC axis (direct) target type only for fader controls in this phase; knobs, buttons, and the jog wheel shall not be assignable to this target type.
- [x] **MAP-AXIS-007**: When a fader's OSC axis (direct) target is cleared, the system shall remove that fader's axis-target configuration and dedup state entirely, such that its next event is evaluated against the opinionated OSC encoder channel target as if an axis target had never been set.

## Debounce and State

- [x] **MAP-DEBOUNCE-001**: If a second press-edge for the same button-type control arrives within 80ms of its previous press-edge, then the system shall drop the second press-edge rather than queueing it or re-firing it after the window closes.
- [x] **MAP-STATE-001**: The system shall allocate previous-value state only for controls present in the opinionated table; controls not in the table shall never have state allocated for them.
- [x] **MAP-STATE-002**: While a mapped button-type control has produced no MIDI message since app start (or since the last reconnect clear per `MIDI-EVT-004`, `docs/specs/midi-input.md`), the system shall treat it as not-pressed, such that a control already held down at that time requires one release-then-press cycle before its first press-edge fires.

## References

- `docs/llds/static-mapping.md`
- `~/github/DragonMIDI-vibed/mappings.md` — source table this LLD's map mirrors.
- `docs/dragonframe-messages-research.md § Empirically validated: direct axis addressing` — the `gotoPosition` scaling and Manual-function findings behind the OSC Axis (Direct) Target specs.
