# Static Mapping Engine — EARS Specs

Traces to `docs/llds/static-mapping.md`.

## Opinionated Table

- [ ] **MAP-TABLE-001**: For every table entry whose MIDI source is a CC message, the system shall map it to its corresponding Dragonframe OSC message only when the event's MIDI channel is 16 (zero-indexed 15); an otherwise-matching CC control on any other channel shall not match any table entry. This invariant does not apply to the Scene button (`korg_scene` type), which matches on type alone — its `channel` field is the controller's own configured Native Mode global-channel ID (see `MIDI-NATIVE-001`), not a stand-in for MIDI channel 16, and may legitimately be any value 0–15.
- [ ] **MAP-TABLE-002**: While a fader (CC 0–7) or knob (CC 16–23) control changes value, the system shall send its mapped `/dragonframe/encoder/<n>` OSC message (float 0.0–1.0) on every distinct value received, with no debounce.
- [ ] **MAP-TABLE-003**: When a mapped button-type control (Mute 1–8, Solo 1–8, Return to Zero, Transport Record, Play, Stop, Fast Forward, Cycle, Set Marker, or the Native Mode Scene button) transitions to pressed, the system shall send that control's mapped one-shot Dragonframe OSC message exactly once per transition.
- [ ] **MAP-TABLE-004**: When the jog wheel (CC 110) sends a KORG sign-magnitude relative value, the system shall decode it to a signed delta (`0` or `64` → `0`; `1`–`63` → positive; `65`–`127` → negative via `raw − 64`) and send it as `/dragonframe/encoder/17`.
- [ ] **MAP-TABLE-005**: If a MIDI event does not correspond to any entry in the opinionated table (including Record 1–8, Select 1–8, Rewind, Previous/Next Marker, and Previous/Next Track), then the system shall produce no OSC output and no log entry for it.

## Debounce and State

- [ ] **MAP-DEBOUNCE-001**: If a second press-edge for the same button-type control arrives within 80ms of its previous press-edge, then the system shall drop the second press-edge rather than queueing it or re-firing it after the window closes.
- [ ] **MAP-STATE-001**: The system shall allocate previous-value state only for controls present in the opinionated table; controls not in the table shall never have state allocated for them.
- [ ] **MAP-STATE-002**: While a mapped button-type control has produced no MIDI message since app start (or since the last reconnect clear per `MIDI-EVT-004`, `docs/specs/midi-input.md`), the system shall treat it as not-pressed, such that a control already held down at that time requires one release-then-press cycle before its first press-edge fires.

## References

- `docs/llds/static-mapping.md`
- `~/github/DragonMIDI-vibed/mappings.md` — source table this LLD's map mirrors.
