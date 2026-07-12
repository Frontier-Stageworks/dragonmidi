# Static Mapping Engine

## Context and Design Philosophy

This component is the one place MIDI meaning becomes Dragonframe meaning. It is deliberately a pure, stateless-as-possible translation: normalized MIDI event in, zero-or-one Dragonframe OSC message out. It holds the "opinionated, hard-coded" map decided in the HLD — no editor, no MIDI-learn, no JSON preset format. The map mirrors the prototype's validated default table (`DragonMIDI-vibed/mappings.md`) because that table is the one part of the prototype the user has actually exercised, not an unconstrained guess.

Isolating this behind a single `event -> Optional[OscMessage]` interface is what lets a future configuration/editor phase replace the table without touching MIDI I/O, OSC I/O, or the UI (per HLD's forward-compatibility discipline).

## The Opinionated Map

All controls are on MIDI channel 16 (zero-indexed 15), matching the nanoKONTROL Studio's Native Mode output.

| Control(s) | MIDI source | Behavior | OSC output |
|---|---|---|---|
| Faders 1–8 | CC 0–7 | Continuous absolute | `/dragonframe/encoder/1`–`8`, float 0.0–1.0 |
| Knobs 1–8 | CC 16–23 | Continuous absolute | `/dragonframe/encoder/9`–`16`, float 0.0–1.0 |
| Mute 1–8 | CC 48–55 | Press edge | `/dragonframe/encoderReset/1`–`8` |
| Solo 1–8 | CC 32–39 | Press edge | `/dragonframe/encoderReset/9`–`16` |
| Jog wheel | CC 110, sign-magnitude relative | Relative delta | `/dragonframe/encoder/17`, signed float delta |
| Return to Zero | CC 47 | Press edge | `/dragonframe/encoderReset/17` |
| Transport Record | CC 45 | Press edge | `/dragonframe/shoot`, int `1` |
| Play | CC 41 | Press edge | `/dragonframe/play` |
| Stop | CC 42 | Press edge | `/dragonframe/live` |
| Fast Forward | CC 44 | Press edge | `/dragonframe/shootVideoAssist` |
| Cycle | CC 46 | Press edge | `/dragonframe/mute` |
| Set Marker | CC 60 | Press edge | `/dragonframe/delete` |
| Scene button | Native Mode SysEx (`korg_scene`) | Press edge | `/dragonframe/black` |
| Record 1–8, Select 1–8, Rewind, Prev/Next Marker, Prev/Next Track | various CCs | — | Not mapped; silently produce no OSC |

This is the same set the prototype ships enabled by default; everything the prototype leaves as a "disabled placeholder" stays unmapped here too, since there is no editor to ever enable it in this phase.

## Trigger Semantics

- **Continuous absolute** (faders, knobs): every distinct MIDI value produces an OSC send. No debounce — Dragonframe needs frequent updates to drive smooth axis motion.
- **Press edge** (buttons, resets, transport, Scene): fires once when the source transitions into "pressed" (velocity/value crossing above 0, or note-on) — reused edge-detection logic from the prototype's `_evaluate`. Debounced at 80ms to absorb switch bounce, matching the prototype's default.
- **Relative delta** (jog wheel): decodes KORG sign-magnitude relative values into a signed delta, scaled by a fixed constant, and forwarded as `/dragonframe/encoder/17` — reused decode logic from the prototype's `relative_sign_magnitude` handling.

## State

The engine keeps a small per-control "previous normalized value" map, needed only for press-edge detection (was it below threshold last time, is it at/above threshold now). This is the only state it holds; it does not know about MIDI connection status or OSC delivery success.

- **Match invariant (CC-sourced controls only):** for every table entry whose MIDI source is a CC message (faders, knobs, Mute, Solo, transport, Return to Zero, jog wheel), channel is part of the match condition exactly like the CC number — a message on any channel other than 16 fails to match and is dropped through the same "no match" path as any other non-matching event. **This invariant explicitly excludes the Scene button.** The Scene button's event carries a `channel` field decoded from its Native Mode SysEx payload (the controller's own configured global-channel ID, set during the Native Mode handshake — see `midi-input.md`), which is unrelated to "MIDI channel 16" and may legitimately be any value 0–15. The Scene button entry matches on event `type == "korg_scene"` alone, with no channel check — applying the channel-16 filter to it would silently break the Scene→Black mapping on any controller not configured to global channel 16. (This correction was caught while designing the Phase 5 test suite — the original spec text generalized the channel invariant to "every table entry," which was wrong for this one entry.)
- **State scope:** the previous-value map only has entries for controls that appear in the static table. Unmapped controls (Record 1–8, Select 1–8, etc.) never reach stateful evaluation at all, so no state is ever allocated for them.
- **Initial state:** every mapped control starts as "not pressed" / below threshold. A physical control already held down at app launch will not fire its first press-edge until it is released and pressed again — an accepted limitation, not specially handled.
- **Debounce semantics:** a second press-edge arriving inside the 80ms debounce window is dropped, not queued or deferred, matching the prototype's `last_sent`-gate behavior.
- **Reconnect hygiene:** the entire previous-value map is cleared whenever the MIDI Input Adapter completes a fresh connect (see `midi-input.md`), so no state survives a disconnect/reconnect cycle.
- **Jog wheel decode totality:** the sign-magnitude decode (`0`/`64` → delta 0, `1–63` → positive, `65–127` → negative via `raw − 64`) is already total over the full 0–127 input range — there is no invalid byte value to handle as a special case.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Map storage | Static in-code data structure (module-level constant) | JSON preset file (prototype's approach) | No editor/persistence needed this phase; removes an entire subsystem (preset load/save, blank-preset state) the HLD marks as a non-goal |
| Unmapped controls | Silently produce no OSC | Log "unmapped control pressed" | Keeps behavior identical to the prototype's default (disabled = no OSC); avoids noise for controls with no assigned meaning yet |
| Fader/knob update rate | Send on every distinct value, no debounce | Fixed-rate throttling (e.g. max 30/sec) | Matches prototype behavior; Dragonframe's own OSC encoder handling is the throttle point if one is ever needed |
| Engine statefulness | Minimal (previous-value map only) | Fully stateless (push edge-detection into MIDI-IN) | Keeps MIDI-IN a pure protocol adapter; edge-detection is inherently a mapping-semantics concern, not a MIDI-parsing concern |
| Channel matching | Channel is one field of the match condition, same mechanism as CC number | Separate explicit channel-filter step | No new mechanism needed; a channel-16-only invariant falls out of the existing per-control match |
| Unmapped-control diagnostics | Completely silent, no log | Log "unmapped control pressed" | Matches "simple UI" goal — there's no log pane to show it in, and it adds no user-facing value in phase 1 |
| Debounce collision handling | Drop the second press-edge inside the window | Queue and re-fire after the window closes | Matches standard debounce semantics and the prototype's existing gate behavior |
| Stuck-control initial state | Assume "not pressed" at launch; accept the one-cycle detection gap | Query controller for current state at connect | nanoKONTROL Studio has no simple state-dump facility; gap is rare and self-correcting |

## Open Questions & Future Decisions

### Resolved
1. ✅ Channel matching, unmapped-control diagnostics (silent), debounce-collision handling (drop), stuck-control initial state (accepted gap), previous-value map scope (mapped controls only), reconnect state hygiene (cleared on connect), and jog-wheel decode totality are all resolved above (decided together with the user during the Phase 2 LLD edge-case review).

### Deferred
1. The jog wheel's relative-delta scale constant needs a concrete default value; the prototype leaves this to per-mapping configuration. A fixed default should be chosen empirically once hardware is available to test against, and does not block the LLD.

## References

- `~/github/DragonMIDI-vibed/mappings.md` — the validated default control-by-control table this LLD's map mirrors.
- `~/github/DragonMIDI-vibed/dragonmidi/engine.py` — source of the trigger-evaluation logic (`_evaluate`) and action-building logic (`_build_action`) this LLD scopes down to a fixed set.
