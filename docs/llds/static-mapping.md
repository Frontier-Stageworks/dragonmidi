# Mapping Engine

## Context and Design Philosophy

This component is the one place MIDI meaning becomes Dragonframe meaning. Each mapping entry translates a normalized MIDI event into zero-or-one Dragonframe OSC message, through a single interface (`event -> Optional[OscMessage]`) that keeps this component swappable without touching MIDI I/O, OSC I/O, or the UI.

Unlike the original static-table design, entries are now editable (add/edit/remove, enable/disable, MIDI-learn) and persisted through a Preset Store, per `docs/high-level-design.md`. The table ships pre-loaded with the nanoKONTROL Studio's opinionated default map (mirroring `DragonMIDI-vibed/mappings.md`), so a user who never opens the mapping view sees identical behavior to a fixed table.

**Phase scope** (per `docs/high-level-design.md § Delivery Phasing`): this LLD describes the target design. **App Delivery Phase 1** implements only the new "OSC axis (direct)" target type described below, and only for the 8 faders — knobs, buttons, and the jog wheel keep their existing default targets (OSC encoder channel / OSC action) unchanged in this phase, and the general editor (MIDI-learn, add/remove, presets) is **App Delivery Phase 2**.

## The Opinionated Default Map

All controls are on MIDI channel 16 (zero-indexed 15), matching the nanoKONTROL Studio's Native Mode output. This is the table's default *content*, not a fixed structure — every row is editable.

| Control(s) | MIDI source | Behavior | Default target |
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
| Record 1–8, Select 1–8, Rewind, Prev/Next Marker, Prev/Next Track | various CCs | — | Not mapped by default; silently produce no OSC |

## Target Types

Each entry has exactly one target, chosen by the user (or left at its default):

- **OSC action** — one of Dragonframe's fixed named commands (`shoot`, `play`, `live`, `mute`, `black`, `delete`, `shootVideoAssist`, and the further commands listed in `docs/dragonframe-messages-research.md` not yet defaulted to any control).
- **OSC encoder channel** — `/dragonframe/encoder/{n}` / `/dragonframe/encoderReset/{n}`, requiring the user to separately wire that channel to an axis inside Dragonframe's Arc workspace.
- **OSC axis (direct)** — addresses a discovered axis by name directly (see below). **This is the only new target type implemented in App Delivery Phase 1, and only for faders.**
- **Custom OSC path** — arbitrary address/argument, restoring the old prototype's escape hatch. Not implemented before App Delivery Phase 2.

## OSC Axis (Direct) Target

- The user picks an axis name from the list the OSC Listener has discovered via `getAllPosition` (see `docs/llds/osc-io.md`), plus a **min** and **max** position value.
- For a continuous-absolute MIDI source (a fader), the engine sends `/dragonframe/axis/{axisname}/gotoPosition,f (position)` on every distinct MIDI value, with no debounce — position is computed as `min + normalized_value * (max - min)`, matching the same "continuous, no debounce" handling already used for OSC encoder targets.
- Min/max are **entered by the user, not discovered** — Dragonframe has `setLimits` but no `getLimits` over OSC, so an axis's practical range cannot be read back (`docs/dragonframe-messages-research.md`).
- **Setup precondition, not a DragonMIDI-enforced invariant:** the target axis's Function must be `Manual` (or otherwise not require a real connected device) for `gotoPosition` to actually move it. Empirically confirmed: an axis with `Function: Normal` and a real hardware `Connect` type (e.g. ArcMoco) but no physical device attached accepts `gotoPosition` without error but never actually moves, even with Dragonframe's "Ready to Capture" mode enabled; switching to `Function: Manual` fixed this immediately (`docs/dragonframe-messages-research.md § Empirically validated`). DragonMIDI has no way to detect an axis's Function type over OSC, so this is documented user-facing guidance, not something the mapping view can validate or warn about.
- **Axis name selection is picker-only, not free text, and is gated only at selection time.** The user selects from the OSC Listener's currently-discovered axis list at the moment they configure the mapping; there is no way to type an arbitrary/undiscovered name into a direct-axis mapping, and there is no ongoing re-validation afterward (see the stale-reference bullet below — the restriction is a one-time UI gate, not a continuously-enforced invariant). A free-text field would let a typo produce a mapping that silently sends `gotoPosition` to a name Dragonframe doesn't recognize, with no way for DragonMIDI to detect the mistake.
- **Rescan to pick up newly added axes.** If the user adds an axis in Dragonframe after DragonMIDI has already discovered its axis list (or after switching to a different project), the on-demand "Rescan"/refresh action (`OSC-DISCOVER-003`, `docs/llds/osc-io.md`) re-queries `getAllPosition` and updates the discoverable list without requiring a DragonMIDI restart.
- **No validation on min/max ordering.** `min + normalized_value * (max - min)` is a well-defined linear interpolation for any real `min`/`max` pair, including `min > max` (a legitimate reversed/inverted mapping) or `min == max` (a constant output regardless of fader position, which can be a deliberate way to always send one fixed value). Neither is rejected.
- **Stale axis references are an accepted, undetected gap.** If the mapped axis name stops being reported by Dragonframe (the axis was deleted, or a different project with different axes was loaded), the engine keeps sending `gotoPosition` to that name regardless — Dragonframe presumably ignores it silently. DragonMIDI does not compare a mapping's target name against the current discovered list to warn about this, matching the project's general pattern of accepting rare, self-evident gaps rather than building detection machinery for them. Rescanning (above) helps a user find new axes; it does not retroactively validate mappings made against axes that have since disappeared.
- **Switching a mapping entry's target type discards the previous target's configuration.** Retargeting a fader from, say, an OSC encoder channel to an OSC axis (direct) replaces the entry's target-specific fields entirely — the old encoder channel number is not preserved for a later switch-back. This matches "one target per entry, not multiple" cleanly and avoids stale, hidden configuration silently persisting in a mapping entry (and potentially a saved preset). This is a decision for whoever implements the Mapping View UI (still a pending cascade into `docs/llds/app-ui.md`), recorded here so it's settled before that LLD is written.

## Trigger Semantics

- **Continuous absolute** (faders, knobs): every distinct MIDI value produces an OSC send, whether the target is an OSC encoder channel or a direct axis. No debounce — Dragonframe needs frequent updates to drive smooth axis motion.
- **Press edge** (buttons, resets, transport, Scene): fires once when the source transitions into "pressed" (velocity/value crossing above 0, or note-on) — reused edge-detection logic from the prototype's `_evaluate`. Debounced at 80ms to absorb switch bounce, matching the prototype's default.
- **Relative delta** (jog wheel): decodes KORG sign-magnitude relative values into a signed delta, scaled by a fixed constant, and forwarded as `/dragonframe/encoder/17` — reused decode logic from the prototype's `relative_sign_magnitude` handling. (Extending this trigger to also support a direct-axis `stepPosition` target is App Delivery Phase 2, not Phase 1.)

## State

The engine keeps a small per-control "previous normalized value" map, needed for both press-edge detection and continuous-value dedup (skip a resend of the identical value, regardless of whether the target is an OSC encoder channel or a direct axis). This is the only state it holds; it does not know about MIDI connection status or OSC delivery success.

- **Match invariant (CC-sourced controls only):** for every table entry whose MIDI source is a CC message (faders, knobs, Mute, Solo, transport, Return to Zero, jog wheel), channel is part of the match condition exactly like the CC number — a message on any channel other than 16 fails to match and is dropped through the same "no match" path as any other non-matching event. **This invariant explicitly excludes the Scene button.** The Scene button's event carries a `channel` field decoded from its Native Mode SysEx payload (the controller's own configured global-channel ID, set during the Native Mode handshake — see `midi-input.md`), which is unrelated to "MIDI channel 16" and may legitimately be any value 0–15. The Scene button entry matches on event `type == "korg_scene"` alone, with no channel check — applying the channel-16 filter to it would silently break the Scene→Black mapping on any controller not configured to global channel 16.
- **State scope:** the previous-value map only has entries for controls that appear in the table. Unmapped/disabled controls never reach stateful evaluation at all, so no state is ever allocated for them.
- **Initial state:** every mapped control starts as "not pressed" / below threshold. A physical control already held down at app launch will not fire its first press-edge until it is released and pressed again — an accepted limitation, not specially handled.
- **Debounce semantics:** a second press-edge arriving inside the 80ms debounce window is dropped, not queued or deferred, matching the prototype's `last_sent`-gate behavior.
- **Reconnect hygiene:** the entire previous-value map is cleared whenever the MIDI Input Adapter completes a fresh connect (see `midi-input.md`), so no state survives a disconnect/reconnect cycle.
- **Jog wheel decode totality:** the sign-magnitude decode (`0`/`64` → delta 0, `1–63` → positive, `65–127` → negative via `raw − 64`) is already total over the full 0–127 input range — there is no invalid byte value to handle as a special case.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Map storage | Editable table, persisted via Preset Store | Static in-code data structure (the original design) | Reversed per the HLD: confirming/correcting a control's assignment was a real, immediate need that a fixed table couldn't satisfy |
| Continuous axis addressing | Direct axis-name addressing (`gotoPosition`), scoped to faders in Phase 1 | A virtual gamepad (investigated and set aside, `docs/dragonframe-gamepad-research.md`) | Extends the already-working OSC path instead of adding a new OS-level dependency; empirically validated against a real Dragonframe instance |
| Axis scaling range | User-specified min/max | Attempt to discover the axis's real range | Dragonframe has no `getLimits` over OSC — the range genuinely cannot be read back |
| Manual-function requirement | Documented as user-facing setup guidance, not enforced by DragonMIDI | Attempt to detect/validate the axis's Function before sending | Function type isn't exposed over OSC in any response; nothing to check against |
| Axis name entry | Picker restricted to the discovered list, no free text | Allow typing an arbitrary axis name | A typo'd free-text name would silently fail with no detection possible; the discovery mechanism already exists |
| Min/max validation | None — any real min/max pair is accepted | Reject `min > max` or `min == max` | The linear interpolation formula is well-defined either way; both are legitimate (reversed mapping, constant output) |
| Stale axis reference handling | Accepted, undetected gap — engine keeps sending to a name Dragonframe may no longer recognize | Compare against the current discovered list and warn/disable | Matches the project's pattern of accepting rare, self-evident gaps over building detection machinery |
| Target-type switch behavior | Discard the previous target's configuration entirely | Preserve/hide it for a quick switch-back | Matches "one target per entry, not multiple"; avoids stale hidden state persisting in a mapping entry or a saved preset |
| Unmapped controls | Silently produce no OSC | Log "unmapped control pressed" | Keeps behavior identical to the prototype's default (disabled = no OSC); avoids noise for controls with no assigned meaning yet |
| Fader/knob update rate | Send on every distinct value, no debounce | Fixed-rate throttling (e.g. max 30/sec) | Matches prototype behavior; Dragonframe's own OSC handling is the throttle point if one is ever needed |
| Engine statefulness | Minimal (previous-value map only) | Fully stateless (push edge-detection into MIDI-IN) | Keeps MIDI-IN a pure protocol adapter; edge-detection is inherently a mapping-semantics concern, not a MIDI-parsing concern |
| Channel matching | Channel is one field of the match condition, same mechanism as CC number | Separate explicit channel-filter step | No new mechanism needed; a channel-16-only invariant falls out of the existing per-control match |
| Debounce collision handling | Drop the second press-edge inside the window | Queue and re-fire after the window closes | Matches standard debounce semantics and the prototype's existing gate behavior |
| Stuck-control initial state | Assume "not pressed" at launch; accept the one-cycle detection gap | Query controller for current state at connect | nanoKONTROL Studio has no simple state-dump facility; gap is rare and self-correcting |

## Open Questions & Future Decisions

### Resolved
1. Channel matching, unmapped-control diagnostics (silent), debounce-collision handling (drop), stuck-control initial state (accepted gap), previous-value map scope (mapped controls only), reconnect state hygiene (cleared on connect), and jog-wheel decode totality — see Decisions & Alternatives above.
2. Editable map storage, direct axis-name addressing as the continuous-jog mechanism, user-specified axis scaling, and the Manual-function precondition — see Decisions & Alternatives above.
3. Axis name entry (picker-only), min/max validation (none needed), and stale axis reference handling (accepted gap) — see Decisions & Alternatives above.
4. Cross-spec edge audit (Phase 4): the picker-only restriction is selection-time-only, not a continuously re-enforced invariant (clarified above, consistent with the accepted-gap decision); Rescan is the mechanism for picking up newly added axes; an empty picker during the startup discovery window is acceptable, not a bug; and target-type switching discards the previous target's configuration — see the bullets above and Decisions & Alternatives.

### Deferred
1. The jog wheel's relative-delta scale constant needs a concrete default value; the prototype leaves this to per-mapping configuration. A fixed default should be chosen empirically once hardware is available to test against, and does not block the LLD.
2. Extending direct-axis addressing to knobs (absolute) and the jog wheel (`stepPosition`, relative) — App Delivery Phase 2, not designed yet.
3. Whether DragonMIDI should ever detect a non-responsive axis (e.g., by comparing sent `gotoPosition` values against subsequent position broadcasts, to warn the user their axis might be `Function: Normal` with no hardware attached) — not in scope for Phase 1's minimal implementation.
4. Exact preset persistence format (JSON schema, file location) — a code-level decision, not yet made.
5. The picker-only axis-selection UI, how the mapping view surfaces "never discovered yet" vs. "discovered, zero axes" and an empty-during-startup picker, and the discard-on-target-switch behavior, all belong in `docs/llds/app-ui.md`'s Mapping View section, which has not yet been updated for this target type — a pending cascade, not a decision made here (the decisions themselves are settled above; only their UI implementation is pending).

## References

- `~/github/DragonMIDI-vibed/mappings.md` — the validated default control-by-control table this LLD's default map mirrors.
- `~/github/DragonMIDI-vibed/dragonmidi/engine.py` — source of the trigger-evaluation logic (`_evaluate`) and action-building logic (`_build_action`) this LLD adapts.
- `docs/dragonframe-messages-research.md § Empirically validated: direct axis addressing` — the `gotoPosition`/`getAllPosition`/Manual-function findings this design is built on.
- `docs/llds/osc-io.md` — axis discovery (`getAllPosition` parsing) that populates the axis picker for this target type.
