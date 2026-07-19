# Mapping Engine

## Context and Design Philosophy

This component is the one place MIDI meaning becomes Dragonframe meaning. Each mapping entry translates a normalized MIDI event into zero-or-one Dragonframe OSC message, through a single interface (`event -> Optional[OscMessage]`) that keeps this component swappable without touching MIDI I/O, OSC I/O, or the UI.

Unlike the original static-table design, entries are now editable (add/edit/remove, enable/disable, MIDI-learn) and persisted through a Preset Store, per `docs/high-level-design.md`. The table ships pre-loaded with the nanoKONTROL Studio's opinionated default map (mirroring `DragonMIDI-vibed/mappings.md`), so a user who never opens the mapping view sees identical behavior to a fixed table.

**Phase scope** (per `docs/high-level-design.md § Delivery Phasing`): this LLD describes the target design. **App Delivery Phase 1** implements the "OSC axis (direct)" target type, as the **default** for the 8 faders, plus **bank derivation** — knobs and the Mute/Solo buttons automatically follow their bank's fader assignment rather than being independently configurable (see Bank Derivation below). Transport/marker/track buttons and Record/Select are unaffected and keep their existing targets. The jog wheel and Return to Zero are unmapped (see the Opinionated Default Map below) — the jog wheel is not a motion-control input in this project. The general editor (MIDI-learn, add/remove, presets, independently retargeting a knob/button) is **App Delivery Phase 2**.

## The Opinionated Default Map

All controls are on MIDI channel 16 (zero-indexed 15), matching the nanoKONTROL Studio's Native Mode output. This is the table's default *content*, not a fixed structure — every row is editable.

| Control(s) | MIDI source | Behavior | Default target |
|---|---|---|---|
| Faders 1–8 | CC 0–7 | Continuous absolute | OSC axis (direct), no axis selected — see Fader Axis Mode below. `/dragonframe/encoder/1`–`8` only if explicitly switched to OSC encoder. |
| Knobs 1–8 | CC 16–23 | Continuous absolute | Bank-derived — see Bank Derivation below. `/dragonframe/encoder/9`–`16` when that bank has no axis assigned. |
| Mute 1–8 | CC 48–55 | Press edge | Bank-derived — see Bank Derivation below. `/dragonframe/encoderReset/1`–`8` when that bank has no axis assigned. |
| Solo 1–8 | CC 32–39 | Press edge | Bank-derived — see Bank Derivation below. `/dragonframe/encoderReset/9`–`16` when that bank has no axis assigned. |
| Transport Record | CC 45 | Press edge | `/dragonframe/shoot`, int `1` |
| Play | CC 41 | Press edge | `/dragonframe/play` |
| Stop | CC 42 | Press edge | `/dragonframe/live` |
| Rewind (`<<`) | CC 43 | Press edge | `/dragonframe/stepBackward` |
| Fast Forward (`>>`) | CC 44 | Press edge | `/dragonframe/stepForward` |
| Cycle | CC 46 | Press edge | `/dragonframe/loop` |
| Previous Marker | CC 61 | Press edge | `/dragonframe/stepBackward` |
| Next Marker | CC 62 | Press edge | `/dragonframe/stepForward` |
| Previous Track | CC 58 | Press edge | `/dragonframe/stepBackward` |
| Next Track | CC 59 | Press edge | `/dragonframe/stepForward` |
| Scene button | Native Mode SysEx (`korg_scene`) | Press edge | `/dragonframe/black` |
| Record 1–8, Select 1–8, Set Marker, Return to Zero, Jog wheel | various CCs | — | Not mapped by default; silently produce no OSC |

## Target Types

Each entry has exactly one target, chosen by the user (or left at its default):

- **OSC action** — one of Dragonframe's fixed named commands (`shoot`, `play`, `live`, `mute`, `black`, `delete`, `shootVideoAssist`, and the further commands listed in `docs/dragonframe-messages-research.md` not yet defaulted to any control).
- **OSC encoder channel** — `/dragonframe/encoder/{n}` / `/dragonframe/encoderReset/{n}`, requiring the user to separately wire that channel to an axis inside Dragonframe's Arc workspace. The fallback for a fader/knob/Mute/Solo whose bank has no axis assigned; no longer the default for faders.
- **OSC axis (direct)** — addresses a discovered axis by name directly (see below). **The default target type for faders in App Delivery Phase 1.** Knobs and Mute/Solo reach this same mechanism only through bank derivation, not as an independently selectable target.
- **Custom OSC path** — arbitrary address/argument, restoring the old prototype's escape hatch. Not implemented before App Delivery Phase 2.

## Fader Axis Mode (Default) vs. OSC Encoder Mode

- Every fader starts in **axis mode**, with no axis name selected. In this state, moving the fader produces **no OSC output at all** — there is no fallback to the opinionated encoder target while unconfigured. An axis name is inherently project-specific; unlike an encoder channel number, there is no meaningful placeholder to fall back to until the user configures one.
- Switching a fader's target type to **OSC encoder** enters encoder mode: the fader (and its bank, see below) behaves exactly as documented in the Opinionated Default Map table's encoder-fallback column.
- Switching back to **OSC axis** re-enters axis mode; if no name has been picked yet (or was cleared), it again sends nothing until one is chosen.
- This is tracked by `MappingEngine` itself, not only the Mapping View UI — it changes actual dispatch behavior (whether an event produces OSC output at all), not merely what the table displays. `set_axis_target` implies axis mode; `clear_axis_target` implies encoder mode, in addition to their existing effects on the stored target and dedup state.

## Bank Derivation

The 8 channel strips are grouped into **banks**. Bank N = Fader N, Knob N, Mute N, Solo N. Record N and Select N are not part of a bank — no per-axis OSC action exists for them (`docs/dragonframe-messages-research.md`), so they remain unmapped regardless of bank state, unchanged from today.

- **Only Fader N's target is directly configurable** — the OSC axis (direct) picker described above and in `docs/llds/app-ui.md`. Knob N, Mute N, and Solo N have no independent target selection; their effective target is derived from Fader N's current state, recomputed on every event they produce, not fixed at the moment Fader N's axis was chosen.
- **Fader N has a real axis name assigned:**
  - Knob N sends `/dragonframe/axis/{axisname}/stepPosition,f (delta)` on every distinct value once a prior reading exists to compare against, where `delta = (raw_value - previous_raw_value) * 0.1` — the change since Knob N's own last reported value, scaled down by a fixed factor of `0.1` axis-position units per MIDI raw-value increment, for fine adjustment rather than a whole-unit-per-tick jump. The first reading after Fader N's axis is assigned (or after any encoder↔axis mode transition, see below) establishes this baseline only and produces no send, since there is nothing yet to compute a change against. No debounce; the scale factor is a fixed constant, not user-configurable. **Delta must be computed against the knob's own previous reading, not its distance from a fixed center.** Dragonframe accumulates each `stepPosition` onto the axis's current position; a knob's physical rotation typically produces several intermediate MIDI messages, so a formula based on absolute distance from a fixed reference would resend a large, nearly-constant value on each one — producing runaway movement rather than a proportional nudge.
  - Mute N sends `/dragonframe/axis/{axisname}/setZero` on press.
  - Solo N sends `/dragonframe/axis/{axisname}/setHome` on press.
  - **`setZero`/`setHome` are calibration commands, not movement commands.** They redefine the axis's zero/home reference point to its current position; they do not move the axis to a previously-stored zero/home. Dragonframe's OSC surface has no command that does the latter (`docs/dragonframe-messages-research.md`). This is why they're paired with Mute/Solo despite the naming resemblance to "reset" — they're the only argument-free per-axis commands left once Fader/Knob claim `gotoPosition`/`stepPosition`.
- **Fader N has no axis assigned** (default state, or explicitly switched to OSC encoder): Knob N, Mute N, and Solo N fall back to their table-listed static defaults (`/dragonframe/encoder/{9-16}`, `/dragonframe/encoderReset/{1-8}`, `/dragonframe/encoderReset/{9-16}`) — unchanged from today's behavior.
- **A repeated identical raw value produces a computed delta of `0` and is not resent** — this falls directly out of the delta formula (a repeat means `raw_value == previous_raw_value`, so the raw difference — and its scaled result — is `0`), with no separate dedup check needed.
- **Knob N's stored "previous reading" spans two different value semantics** — a normalized absolute float (0.0–1.0) in encoder mode, versus a raw MIDI int in derived-axis mode. Comparing a stale value from one semantic against a fresh value from the other, right at a mode transition, would produce a meaningless delta. Assigning Fader N's first axis name (entering axis mode from encoder mode) or clearing it (leaving axis mode for encoder mode) therefore also discards Knob N's stored reading — mirroring the same "switching a target discards prior dedup state" precedent already established for the fader itself, and forcing the next knob event to re-establish a fresh baseline rather than diff against a stale, incompatible value. Picking a *different* axis name while Fader N is already in axis mode does not discard it, since the delta computation doesn't depend on which axis is targeted.

## OSC Axis (Direct) Target (Fader — `gotoPosition`)

- The user picks an axis name from the list the OSC Listener has discovered via `getAllPosition` (see `docs/llds/osc-io.md`), plus a **min** and **max** position value.
- For a continuous-absolute MIDI source (a fader), the engine sends `/dragonframe/axis/{axisname}/gotoPosition,f (position)` on every distinct MIDI value, with no debounce — position is computed as `min + normalized_value * (max - min)`, matching the same "continuous, no debounce" handling already used for OSC encoder targets.
- Min/max are **entered by the user, not discovered** — Dragonframe has `setLimits` but no `getLimits` over OSC, so an axis's practical range cannot be read back (`docs/dragonframe-messages-research.md`).
- **Setup precondition, not a DragonMIDI-enforced invariant:** the target axis's Function must be `Manual` (or otherwise not require a real connected device) for `gotoPosition` to actually move it. Empirically confirmed: an axis with `Function: Normal` and a real hardware `Connect` type (e.g. ArcMoco) but no physical device attached accepts `gotoPosition` without error but never actually moves, even with Dragonframe's "Ready to Capture" mode enabled; switching to `Function: Manual` fixed this immediately (`docs/dragonframe-messages-research.md § Axis Discovery and Direct Addressing`). DragonMIDI has no way to detect an axis's Function type over OSC, so this is documented user-facing guidance, not something the mapping view can validate or warn about.
- **Axis name selection is picker-only, not free text, and is gated only at selection time.** The user selects from the OSC Listener's currently-discovered axis list at the moment they configure the mapping; there is no way to type an arbitrary/undiscovered name into a direct-axis mapping, and there is no ongoing re-validation afterward (see the stale-reference bullet below — the restriction is a one-time UI gate, not a continuously-enforced invariant). A free-text field would let a typo produce a mapping that silently sends `gotoPosition` to a name Dragonframe doesn't recognize, with no way for DragonMIDI to detect the mistake.
- **Rescan to pick up newly added axes.** If the user adds an axis in Dragonframe after DragonMIDI has already discovered its axis list (or after switching to a different project), the on-demand "Rescan"/refresh action (`OSC-DISCOVER-003`, `docs/llds/osc-io.md`) re-queries `getAllPosition` and updates the discoverable list without requiring a DragonMIDI restart.
- **No validation on min/max ordering.** `min + normalized_value * (max - min)` is a well-defined linear interpolation for any real `min`/`max` pair, including `min > max` (a legitimate reversed/inverted mapping) or `min == max` (a constant output regardless of fader position, which can be a deliberate way to always send one fixed value). Neither is rejected.
- **Stale axis references are an accepted, undetected gap.** If the mapped axis name stops being reported by Dragonframe (the axis was deleted, or a different project with different axes was loaded), the engine keeps sending `gotoPosition` to that name regardless — Dragonframe presumably ignores it silently. DragonMIDI does not compare a mapping's target name against the current discovered list to warn about this, matching the project's general pattern of accepting rare, self-evident gaps rather than building detection machinery for them. Rescanning (above) helps a user find new axes; it does not retroactively validate mappings made against axes that have since disappeared.
- **Switching a mapping entry's target type discards the previous target's configuration.** Retargeting a fader from, say, an OSC encoder channel to an OSC axis (direct) replaces the entry's target-specific fields entirely — the old encoder channel number is not preserved for a later switch-back. This matches "one target per entry, not multiple" cleanly and avoids stale, hidden configuration silently persisting in a mapping entry (and potentially a saved preset). Implemented in the Mapping View UI (`docs/llds/app-ui.md`'s `UI-MAP-003`).
- **Reverting from OSC axis back to OSC encoder is a full clear, not a swap.** `MappingEngine.clear_axis_target(key)` removes the fader's axis-target entry (and its dedup state) entirely; `process()` then falls back to the opinionated `OPINIONATED_MAP` lookup for that key on the very next event, same as if the axis target had never been set. There is no hidden "remembered" encoder-channel override to restore — a fader always reverts to its one opinionated encoder target, symmetric with the discard-on-switch behavior above.

## Trigger Semantics

- **Continuous absolute** (faders, knobs): every distinct MIDI value produces an OSC send, whether the target is an OSC encoder channel, a fader's direct-axis `gotoPosition`, or a knob's bank-derived `stepPosition`. No debounce — Dragonframe needs frequent updates to drive smooth axis motion.
- **Press edge** (buttons, resets, transport, Scene): fires once when the source transitions into "pressed" (velocity/value crossing above 0, or note-on) — reused edge-detection logic from the prototype's `_evaluate`. Debounced at 80ms to absorb switch bounce, matching the prototype's default.

## State

The engine keeps a small per-control "previous normalized value" map, needed for both press-edge detection and continuous-value dedup (skip a resend of the identical value, regardless of whether the target is an OSC encoder channel or a direct axis). This is the only state it holds; it does not know about MIDI connection status or OSC delivery success.

- **Match invariant (CC-sourced controls only):** for every table entry whose MIDI source is a CC message (faders, knobs, Mute, Solo, transport), channel is part of the match condition exactly like the CC number — a message on any channel other than 16 fails to match and is dropped through the same "no match" path as any other non-matching event. **This invariant explicitly excludes the Scene button.** The Scene button's event carries a `channel` field decoded from its Native Mode SysEx payload (the controller's own configured global-channel ID, set during the Native Mode handshake — see `midi-input.md`), which is unrelated to "MIDI channel 16" and may legitimately be any value 0–15. The Scene button entry matches on event `type == "korg_scene"` alone, with no channel check — applying the channel-16 filter to it would silently break the Scene→Black mapping on any controller not configured to global channel 16.
- **State scope:** the previous-value map only has entries for controls that appear in the table. Unmapped/disabled controls never reach stateful evaluation at all, so no state is ever allocated for them.
- **Initial state:** every mapped control starts as "not pressed" / below threshold. A physical control already held down at app launch will not fire its first press-edge until it is released and pressed again — an accepted limitation, not specially handled.
- **Debounce semantics:** a second press-edge arriving inside the 80ms debounce window is dropped, not queued or deferred, matching the prototype's `last_sent`-gate behavior.
- **Reconnect hygiene:** the entire previous-value map is cleared whenever the MIDI Input Adapter completes a fresh connect (see `midi-input.md`), so no state survives a disconnect/reconnect cycle.

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
| Reverting axis → encoder | `clear_axis_target(key)` fully removes the axis entry; engine falls back to the opinionated encoder target | Preserve the axis config for a later switch back to it | Symmetric with the switch-discards-state decision above; a fader has exactly one opinionated encoder target to fall back to, so there's nothing else to remember |
| Unmapped controls | Silently produce no OSC | Log "unmapped control pressed" | Keeps behavior identical to the prototype's default (disabled = no OSC); avoids noise for controls with no assigned meaning yet |
| Fader/knob update rate | Send on every distinct value, no debounce | Fixed-rate throttling (e.g. max 30/sec) | Matches prototype behavior; Dragonframe's own OSC handling is the throttle point if one is ever needed |
| Engine statefulness | Minimal (previous-value map only) | Fully stateless (push edge-detection into MIDI-IN) | Keeps MIDI-IN a pure protocol adapter; edge-detection is inherently a mapping-semantics concern, not a MIDI-parsing concern |
| Channel matching | Channel is one field of the match condition, same mechanism as CC number | Separate explicit channel-filter step | No new mechanism needed; a channel-16-only invariant falls out of the existing per-control match |
| Debounce collision handling | Drop the second press-edge inside the window | Queue and re-fire after the window closes | Matches standard debounce semantics and the prototype's existing gate behavior |
| Stuck-control initial state | Assume "not pressed" at launch; accept the one-cycle detection gap | Query controller for current state at connect | nanoKONTROL Studio has no simple state-dump facility; gap is rare and self-correcting |
| Transport/marker/track section defaults | Rewind, Previous Marker, Previous Track all → `stepBackward`; Fast Forward, Next Marker, Next Track all → `stepForward`; Cycle → `loop` | Leave Rewind/Marker/Track unmapped (no exact Dragonframe equivalent); force each onto a distinct but unrelated command | Dragonframe has no marker or track concept over OSC, but every one of these physical controls is a "step back" or "step forward" gesture — mapping all of them to the same semantic action is a better default than leaving them silent or inventing an unrelated meaning per button |
| Set Marker default | Unmapped (falls through to no-OSC) | Keep the prototype's `/dragonframe/delete` binding | That binding was an arbitrary leftover with no semantic relationship to "set marker," and a marker button silently deleting a frame is an actively dangerous default |
| Fader default target | OSC axis (direct), no name selected | OSC encoder (the original default) | Axis addressing is the primary interaction model for this project; OSC encoder remains available as a manual fallback, not the default |
| Fader-in-axis-mode, no name chosen | Send nothing | Fall back to the opinionated encoder target until configured | An axis name has no meaningful placeholder default; falling back would silently substitute a different target type than what's displayed |
| Bank derivation ownership | Engine-level: only the fader is configurable, Knob/Mute/Solo derive automatically | Give Knob/Mute/Solo their own independent target pickers | Matches "select the bank once" — configuring one control per bank instead of four |
| Knob's derived `stepPosition` delta | `raw_value - previous_raw_value` (change since the knob's own last reading) | `raw_value - 64` (distance from center), resent on every event | Distance-from-center is not a relative step; resending it on every intermediate MIDI message the knob produces while turning caused runaway, exaggerated movement instead of a proportional nudge |
| Knob's derived `stepPosition` scale | Fixed constant `0.1` axis-position units per raw-value increment, not user-configurable | Unscaled raw delta (`1.0` per increment); user-specified sensitivity, like the fader's min/max | The unscaled raw delta moved a whole unit per MIDI tick — too coarse for the fine-adjustment purpose of the knob. A fixed constant is simpler than a configurable field until real usage shows `0.1` itself needs tuning |
| Knob's first reading after a baseline reset | Establishes the baseline silently, sends nothing | Send a delta computed against an assumed center or zero | There is no meaningful "previous reading" yet to diff against; inventing one would produce an arbitrary, not-actually-relative first move |
| Bank membership | Fader + Knob + Mute + Solo; Record/Select excluded | Include Record/Select with an invented per-axis action | No matching per-axis OSC action exists for them; matches the established "no forced unrelated mapping" pattern (Set Marker, above) |
| Mute/Solo derived actions | Mute → `setZero`, Solo → `setHome` — calibration (redefine the reference point to current position), not movement | Leave Mute/Solo as static encoder resets, only Fader/Knob become axis-aware; or unmap them once an axis is assigned, since there's no "move to stored zero/home" command to offer instead | Gives every control in the bank a real, distinct per-axis action rather than an arbitrary subset; accepted despite the accidental-recalibration risk since no better argument-free per-axis command exists |
| Jog wheel and Return to Zero | Unmapped — the jog wheel is not used for motion-control input in this project | Keep the jog wheel driving `/dragonframe/encoder/17` (relative) and Return to Zero resetting it | The jog wheel controlling an axis was never wanted; Return to Zero only ever existed to reset that same channel, so it has nothing left to reset |

## Open Questions & Future Decisions

### Resolved
1. Channel matching, unmapped-control diagnostics (silent), debounce-collision handling (drop), stuck-control initial state (accepted gap), previous-value map scope (mapped controls only), and reconnect state hygiene (cleared on connect) — see Decisions & Alternatives above.
2. Editable map storage, direct axis-name addressing as the continuous-jog mechanism, user-specified axis scaling, and the Manual-function precondition — see Decisions & Alternatives above.
3. Axis name entry (picker-only), min/max validation (none needed), and stale axis reference handling (accepted gap) — see Decisions & Alternatives above.
4. Cross-spec edge audit (Phase 4): the picker-only restriction is selection-time-only, not a continuously re-enforced invariant (clarified above, consistent with the accepted-gap decision); Rescan is the mechanism for picking up newly added axes; an empty picker during the startup discovery window is acceptable, not a bug; and target-type switching discards the previous target's configuration — see the bullets above and Decisions & Alternatives.
5. The picker-only axis-selection UI, how the mapping view surfaces "never discovered yet" vs. "discovered, zero axes," and the discard-on-target-switch behavior are implemented in `docs/llds/app-ui.md`'s Mapping View section (`UI-MAP-003` through `UI-MAP-008`).
6. Fader default target (OSC axis, not encoder), fader-in-axis-mode-with-no-name send behavior (nothing, no fallback), bank derivation ownership and membership, and the knob's derived `stepPosition` scale — see Decisions & Alternatives above.
7. The jog wheel and Return to Zero are unmapped — see Decisions & Alternatives above.

### Deferred
1. Whether DragonMIDI should ever detect a non-responsive axis (e.g., by comparing sent `gotoPosition` values against subsequent position broadcasts, to warn the user their axis might be `Function: Normal` with no hardware attached) — not in scope for Phase 1's minimal implementation.
2. Exact preset persistence format (JSON schema, file location) — a code-level decision, not yet made.
3. Whether `gotoPosition`/`stepPosition` work against an axis with real, genuinely-connected motion-control hardware (`Function: Normal`, a physical device actually attached) is untested — only the "`Function: Normal`, no device attached" case has been confirmed (`docs/dragonframe-messages-research.md`). If direct addressing does not work against real connected hardware, OSC encoder channels may be more than a manual fallback for rigs using real motors, not merely a legacy option.

## References

- `~/github/DragonMIDI-vibed/mappings.md` — the validated default control-by-control table this LLD's default map mirrors.
- `~/github/DragonMIDI-vibed/dragonmidi/engine.py` — source of the trigger-evaluation logic (`_evaluate`) and action-building logic (`_build_action`) this LLD adapts.
- `docs/dragonframe-messages-research.md § Axis Discovery and Direct Addressing` — the `gotoPosition`/`getAllPosition`/Manual-function findings this design is built on.
- `docs/llds/osc-io.md` — axis discovery (`getAllPosition` parsing) that populates the axis picker for this target type.
