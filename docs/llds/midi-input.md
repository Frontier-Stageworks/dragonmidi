# MIDI Input Adapter

## Context and Design Philosophy

This component owns everything between "a supported KORG nanoKONTROL controller exists somewhere on the system" and "a normalized MIDI event is available to the Static Mapping Engine." It supports exactly two controllers — the nanoKONTROL Studio and the nanoKONTROL2 — chosen explicitly by the user from the Status UI's Controller Profile dropdown (`docs/llds/app-ui.md`), not auto-detected between them. Within whichever profile is currently selected, device discovery is still auto-connect-by-name with no further picker (per HLD "auto-connect within the selected profile, no general device picker").

It also owns the controller-specific quirk that makes the Studio side of the app possible: the nanoKONTROL Studio's KORG Native Mode. Without requesting Native Mode, the Studio's physical controls report whatever the controller's currently-selected Scene has assigned, which is not fixed and not under this app's control. Native Mode makes every control report one fixed message regardless of the controller's own on-device state. The nanoKONTROL2 has no equivalent software-triggered mode: it ships with two operation modes (DAW mode, CC mode) selected by holding a specific button while powering the unit on, and it remembers whichever mode was last used across power cycles — nothing DragonMIDI can request over MIDI. Getting a nanoKONTROL2 into CC mode (holding SET MARKER + CYCLE while powering on, per Korg's manual) is documented user-facing setup guidance, the same "documented precondition, not detected" treatment already established for the axis `Function: Manual` requirement in `docs/llds/static-mapping.md`.

## Controller Profiles

A `ControllerProfile` is the one place this component's (and, downstream, the Static Mapping Engine's) per-device knowledge lives, so neither component hardcodes a single controller's quirks:

| Field | Meaning |
|---|---|
| `name` | Display name for the Controller Profile dropdown (`"nanoKONTROL Studio"`, `"nanoKONTROL2"`). |
| `matches(port_name) -> bool` | Fuzzy name match against an enumerated MIDI port name, same normalization as today (strip non-alphanumeric, lowercase, substring match). |
| `has_native_mode` | Whether a Native-Mode-style SysEx handshake exists for this device. `True` for the Studio, `False` for the nanoKONTROL2. |
| `default_channel` | The 0-based MIDI channel this device's controls transmit on. `15` (channel 16) for the Studio's Native Mode output; `0` (channel 1) for the nanoKONTROL2's factory CC-mode default — a documented user-facing precondition, not detected or enforced (see `docs/llds/static-mapping.md`). |
| `has_jog_wheel` / `has_scene_button` | Feature flags consumed by the Static Mapping Engine to gate the jog-wheel and Scene-button special-case dispatch (`docs/llds/static-mapping.md`). Both `True` for the Studio; both `False` for the nanoKONTROL2, which has neither control. |
| `opinionated_map` | This profile's default control table (`docs/llds/static-mapping.md`'s `OPINIONATED_MAP`). |

Two concrete profiles ship: `STUDIO_PROFILE` (`matches` looks for `nanokontrolstudio`, per the existing fuzzy match) and `NANOKONTROL2_PROFILE` (`matches` looks for `nanokontrol2`) — the two substrings can't collide with each other's port names.

**Accepted gap: a nanoKONTROL2 stuck in DAW mode looks identical to a healthy one.** Device discovery matches by port name only, which doesn't depend on which of the two operation modes the hardware is actually in (`docs/llds/midi-input.md`'s own Context above) — so a nanoKONTROL2 left in DAW mode still connects, and the Signal Monitor's liveness timestamp still updates on *any* raw MIDI it sends (`midi-input.md`'s existing "liveness before normalization" rule), including Mackie Control protocol bytes the normalizer doesn't recognize. The MIDI indicator can therefore show live/green while every physical control is silently producing nothing the mapping table matches — worse than the Studio's case, which at least has a real handshake that can fail into the *error* state. **Accepted, not built around**, matching this project's established pattern of accepting rare, self-evident setup-precondition gaps (e.g. the axis `Function: Manual` requirement) rather than adding detection machinery — a heuristic ("no recognized CC seen recently") was considered and rejected as prone to false-positiving during normal idle periods between control moves. The Controller Profile dropdown's setup hint (`docs/llds/app-ui.md`) is the mitigation: it tells the user how to get into CC mode up front, rather than DragonMIDI detecting the failure after the fact.

**Switching profiles** (the user changes the dropdown selection, `docs/llds/app-ui.md`): two things happen, in the same synchronous handler, independent of each other's outcome:

1. **The Mapping Engine's map and state reset immediately** — not gated on finding a device under the new profile. The Mapping View should reflect the newly-selected profile's controls (and the MIDI indicator should read "Waiting for {new profile}…") the instant the dropdown changes, even if the matching hardware isn't plugged in yet or discovery hasn't ticked. This is a *separate* trigger from the existing `on_reset_mapping` hook that fires when a fresh connect completes (`midi-input.md`'s Reconnect invariant, below) — the two can both fire in sequence (immediate switch, then again whenever a device is actually found), which is redundant but harmless, since clearing already-empty state is a no-op.
2. If the adapter is currently connected, it disconnects first (releasing Native Mode if the outgoing profile had it, exactly like an unplug), then begins polling for the newly-selected profile's name match — the normal disconnect/reconnect path, which will independently trigger `on_reset_mapping` again once a new device actually connects.

`set_profile()` is called from the Qt main thread (the dropdown's change handler) and shares the same serialization as `poll_discovery()`/`connect()`/`disconnect()` — it respects the same `_busy` reentrancy guard rather than being a separate, uncoordinated entry point, so a profile switch landing mid-tick can't race an in-flight connect/disconnect any more than two overlapping timer ticks already can't.

**Independent of Dragonframe/OSC-side state.** A Controller Profile switch only affects the MIDI-input side (this component) and the Static Mapping Engine's active map/state. Axis discovery (`AxisDiscovery.axes`), the OSC listener, and the WebSocket server connection are untouched — switching which physical controller drives DragonMIDI has no bearing on which Dragonframe project or axes are currently discovered.

## Device Discovery and Auto-Connect

- Poll available MIDI input port names on a timer (proposed: every 2s). If a connect or disconnect operation is already in progress when a tick fires, that tick is skipped rather than starting an overlapping operation.
- A port name matches the currently-selected Controller Profile if `profile.matches(port_name)` returns true (see Controller Profiles above) — for the Studio, this is the same fuzzy match as before (strips non-alphanumeric characters, lowercases, checks for `nanokontrolstudio`), reused from the prototype to handle OS-specific naming variants like "nanoKONTROL Studio" vs "KORG nanoKONTROL Studio SLIDER/KNOB"; for the nanoKONTROL2, the equivalent match looks for `nanokontrol2`.
- If more than one available port matches, connect to the first one returned by the MIDI backend's port enumeration and log which one was chosen. (Two physical units present simultaneously is an accepted rare case, not one that needs real tie-break logic.)
- When a matching port is found and the adapter is not already connected, connect automatically.
- When the connected port disappears (raises on read, or vanishes from the port list), treat as disconnected: release Native Mode if it was active, close the input/output ports, and resume polling. No user action or dialog is involved — the MIDI signal indicator simply goes dark.
- **Invariant:** connect and disconnect are only ever processed serially, on the single MIDI-management thread/loop that also runs discovery polling — they cannot overlap by construction, so a reconnect can never race an in-flight disconnect cleanup.
- **Connection status is exposed as its own piece of state**, independent of the Signal Monitor's liveness/error tracking (see `app-ui.md`): whether a nanoKONTROL Studio port is currently open, and if so, its device name. The Status UI reads this directly to choose between "Waiting for nanoKONTROL Studio…" and the connected device's name (`UI-STATUS-002`). This is deliberately a separate axis from the MIDI indicator dot's live/error/quiet state — see "Decisions & Alternatives" and `app-ui.md` for why the two can disagree (e.g., a physically connected device whose Native Mode handshake failed shows the device name *and* an error dot at the same time).

## Native Mode Handshake

**Only runs when the connected profile's `has_native_mode` is `True`** (currently: the Studio only). For a profile with no Native Mode (the nanoKONTROL2), `connect()` skips this section entirely — no output port is opened, no SysEx is sent, and the MIDI indicator's *error* state (below) can never fire for that profile, since there is nothing to fail. This is a real, not merely cosmetic, difference in capability: the nanoKONTROL2's "is CC mode actually engaged" question is answered by the physical button-hold-at-power-on procedure the user performs themselves (see Controller Profiles above), which DragonMIDI cannot verify — there is no software-observable equivalent of a failed handshake for it.

- **Every fresh connect attempt clears the MIDI channel's error flag before attempting the handshake**, so the flag always reflects only the current attempt's outcome — a stale failure from a previous connection never lingers past a new connect, and a successful handshake on reconnect clears a prior error just as cleanly as an unplugged device leaving the error behind would otherwise be confusing. This clear still runs unconditionally on every connect, regardless of profile, so switching from the Studio (possibly mid-error) to the nanoKONTROL2 (which never errors) doesn't leave a stale error dot lit.
- On connect, find the matching MIDI **output** port for the same physical device (exact name match first, else fuzzy-match by shared name tokens — reused from the prototype's `_matching_output`).
- If a matching output port is found, send the Native-Mode-enter SysEx request. The request is addressed by the controller's global MIDI channel, which this app does not know or store — so, following the prototype's approach, the request is sent once per channel ID for all 16 possible IDs, guaranteeing delivery without requiring the user to know or reset that setting.
- On disconnect (device lost or app quit), send the Native-Mode-exit SysEx the same way: each of the 16 per-channel sends is wrapped individually in try/except so one failing send doesn't abort the rest of the loop, and the output port is closed in a `finally` unconditionally, regardless of whether any SysEx sends failed.
- If no matching output port can be opened (e.g., another app has it open), or if the previously-matched output port vanishes between being found and the SysEx send, MIDI input still proceeds without Native Mode — both cases are treated identically as "Native Mode unavailable," not specially distinguished. This is a degraded-but-functional state, not a connection failure. It surfaces as the *error* state on the Status UI's MIDI indicator (a third state distinct from "quiet" — see `app-ui.md`), since a silently-degraded Native Mode is exactly the kind of misleading "looks fine" state this app exists to prevent.

## Normalized MIDI Event

Raw `mido` messages are converted into one normalized event shape before being handed to the Static Mapping Engine:

| Field | Meaning |
|---|---|
| `type` | `note`, `cc`, `pitchbend`, `program`, `aftertouch`, `polytouch`, or `korg_scene` |
| `channel` | 0-based MIDI channel, or the SysEx-derived channel for `korg_scene` |
| `number` | note number / CC number / program number, when applicable |
| `raw_value` | the untranslated 0–127 (or SysEx byte) value |
| `normalized` | `raw_value` scaled to `0.0–1.0` where meaningful |
| `is_press` / `is_release` | edge flags for button-like sources |

The `korg_scene` type is recognized from the specific 13-byte Native Mode Scene-button SysEx pattern (reused byte-for-byte from the prototype's parser), since the Scene button has no ordinary Note/CC representation even in Native Mode. The nanoKONTROL2 has no Scene button and never emits this SysEx pattern, so `_normalize_sysex` naturally never produces a `korg_scene` event for it — no profile check is needed in the normalizer itself; `has_scene_button` (Controller Profiles above) exists for the Static Mapping Engine's dispatch, not for gating recognition here.

`normalized` is only defined, and only needs to be defined, for the event types the static map actually consumes in phase 1: `cc` (7-bit scaled to 0.0–1.0) and `korg_scene` (SysEx value byte scaled to 0.0–1.0). `pitchbend`, `program`, `aftertouch`, and `polytouch` normalization is unspecified and unused until a future mapping references one of those types.

**Liveness update happens before normalization, not after.** Any raw MIDI message received on the connected port — including SysEx bytes that fail to match the `korg_scene` pattern, or any other message the normalizer doesn't recognize — updates the "last MIDI activity" timestamp the Signal Monitor (see `app-ui.md`) uses to drive the MIDI signal indicator. Liveness means "the device is talking to us," not "we understood what it said," so it is intentionally decoupled from successful parsing.

**Reconnect invariant:** the Static Mapping Engine's previous-value map (see `static-mapping.md`) is cleared whenever this adapter completes a fresh connect, so no stale per-control state survives a disconnect/reconnect cycle.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Device selection | Auto-connect by fuzzy name match within the selected Controller Profile | Manual dropdown + Connect button (prototype's approach); a single hardcoded device | Removes a manual per-device connect step per HLD's "simple UI" goal, while the Controller Profile dropdown (not a device picker) covers "which of the two supported controllers" |
| Multi-controller support | A `ControllerProfile` abstraction driving both this adapter and the Static Mapping Engine | Fork the adapter/engine per device; scatter `if profile == "studio"` conditionals through shared code | A third controller becomes a new profile, not a parallel adapter or more conditionals — see `docs/high-level-design.md § Key Design Decisions` |
| Native Mode addressing | Send enter/exit request across all 16 channel IDs | Detect and use the controller's actual stored global channel | Matches prototype's validated workaround; avoids needing to read/know a setting stored on the device |
| Native Mode failure handling | Non-fatal; MIDI input continues without it | Block connection / surface as hard error | A missing output port (e.g., held by other software) shouldn't stop faders/knobs from working, only the Scene-button mapping |
| nanoKONTROL2 mode readiness | Documented user-facing setup guidance (hold SET MARKER + CYCLE at power-on for CC mode), not detected | Attempt to query or infer the device's current operation mode | The nanoKONTROL2 exposes no software-observable handshake or mode query; matches the project's existing "documented precondition, not enforced" pattern (e.g. axis `Function: Manual`) |
| nanoKONTROL2 default channel | Assumed fixed at its factory default (channel 1), not detected | Attempt to auto-detect the channel from observed traffic | No handshake exists to confirm it; channel is a `ControllerProfile` field the map is built against, same documented-precondition treatment as mode readiness above |
| nanoKONTROL2 stuck in DAW mode | Accepted, undetected gap — MIDI indicator can show live with nothing actually mapped | Heuristic staleness check (no recognized CC seen recently → treat as error) | User's explicit choice (2026-07-21); a heuristic would risk false-positiving during ordinary idle periods between control moves, and matches this project's existing tolerance for self-evident, documented setup-precondition gaps |
| Axis assignments on profile switch | Wiped, same as a MIDI reconnect | Preserve by fader/bank number across profiles | User's explicit choice (2026-07-21); simpler mental model ("switching controllers starts over") and consistent with this phase's broader no-persistence design, even though Fader 1–8 occupy the same bank position on both devices |
| MIDI library | `mido` (+ `python-rtmidi` backend) | Direct `rtmidi` bindings, `pygame.midi` | Already validated against this exact controller's SysEx behavior in the prototype |
| Duplicate matching ports | Connect to the first match in enumeration order, log the choice | Prompt the user to pick; refuse to connect | Two physical units simultaneously present is a rare, accepted edge case not worth a picker UI in a "no device picker" app |
| Native Mode failure surfacing | Distinct *error* state on the MIDI indicator (see `app-ui.md`'s 3-state indicator) | Log-only, no UI signal | A degraded Native Mode is a real, silent-looking failure mode; the indicator should not look identical to "healthy but quiet" |
| Exit-SysEx send failures | Per-send try/except inside the 16-channel loop; port close always runs in `finally` | Abort the whole loop on first failure | Guarantees port cleanup always completes even if some/all SysEx sends fail |
| Connect/disconnect concurrency | Serial only, single MIDI-management thread | Locking/flags across multiple threads | Simpler to reason about; discovery polling and connect/disconnect already share one loop |
| Liveness vs. parse success | Liveness timestamp updates on any raw MIDI message, before normalization | Only update on successfully normalized/mapped events | Liveness should mean "device is talking," independent of whether the message parses |
| Reconnect state hygiene | Clear the mapping engine's previous-value map on every fresh connect | Leave state untouched across reconnects | Prevents stale pre-disconnect state from causing spurious or missed edges after reconnect |
| Error-flag lifecycle | Clear the MIDI error flag at the start of every fresh connect attempt, before the handshake runs | Clear only on explicit user action; leave set until app restart | A stale error flag from a prior connection shouldn't outlive that connection; each attempt should be judged on its own outcome |
| Connection status vs. liveness/error | Exposed as a separate piece of state (device open + name) from the Signal Monitor's live/error/quiet | Fold connection status into the same 3-state model | "Is a controller present" and "is it healthy right now" are independent questions and can disagree (connected device, failed handshake) |

## Open Questions & Future Decisions

### Resolved
1. Duplicate matching ports, mid-handshake output-port loss, exit-SysEx partial failure, connect/disconnect concurrency, liveness-vs-parse-success, pitchbend/aftertouch/program normalization scope, and reconnect state hygiene — see Decisions & Alternatives above.
2. Failed Native Mode handshake surfaces as a distinct *error* state on the Status UI's MIDI indicator (3-state: live / quiet / error), jointly with `osc-io.md`'s listener-bind-failure state — see `app-ui.md`.
3. Error-flag clearing lifecycle (cleared at the start of each connect attempt) and connection-status/device-name being an independent axis from the liveness/error dot — see Decisions & Alternatives above.
4. Multi-controller support via a `ControllerProfile` abstraction (name match, Native Mode presence, default channel, feature flags, opinionated map); the nanoKONTROL2's lack of a software-observable handshake or mode query is documented user guidance, not detected; profile switching disconnects and re-polls, reusing the existing reconnect-clear hygiene — see Controller Profiles above and Decisions & Alternatives.
5. Edge audit (2026-07-21): a nanoKONTROL2 stuck in DAW mode is an accepted, undetected gap (indistinguishable from a healthy connection by liveness alone); axis assignments are wiped, not preserved, across a Controller Profile switch — see Decisions & Alternatives above.

### Deferred
1. Exact poll interval for device discovery (proposed 2s) is a tunable constant, not yet load-bearing on any spec.
2. Whether the Controller Profile selection should persist across app restarts, or always reset to the Studio default — same open question as `docs/llds/app-ui.md`'s host/port persistence, not yet decided.

## References

- Prior prototype — source of the Native Mode SysEx handshake and fuzzy device-name matching, reused as validated reference.
- Prior prototype — source of the `korg_scene` SysEx byte pattern and normalized-event shape this LLD adapts.
- KORG nanoKONTROL2 Owner's Manual — source of the nanoKONTROL2's DAW-mode/CC-mode power-on procedure and confirmation that no Native-Mode-style SysEx handshake exists for it.
