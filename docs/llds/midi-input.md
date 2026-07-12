# MIDI Input Adapter

## Context and Design Philosophy

This component owns everything between "a KORG nanoKONTROL Studio exists somewhere on the system" and "a normalized MIDI event is available to the Static Mapping Engine." It is single-purpose: exactly one supported controller, auto-discovered by name, with no user-facing device picker (per HLD "auto-connect, no manual device picker").

It also owns the controller-specific quirk that makes the rest of the app possible: the nanoKONTROL Studio's KORG Native Mode. Without requesting Native Mode, the physical controls report whatever the controller's currently-selected Scene has assigned, which is not fixed and not under this app's control. Native Mode makes every control report one fixed message regardless of the controller's own on-device state.

## Device Discovery and Auto-Connect

- Poll available MIDI input port names on a timer (proposed: every 2s). If a connect or disconnect operation is already in progress when a tick fires, that tick is skipped rather than starting an overlapping operation.
- A port name matches the nanoKONTROL Studio if, after stripping non-alphanumeric characters and lowercasing, it contains `nanokontrolstudio` (reused fuzzy match from the prototype, which already handles OS-specific naming variants like "nanoKONTROL Studio" vs "KORG nanoKONTROL Studio SLIDER/KNOB").
- If more than one available port matches, connect to the first one returned by the MIDI backend's port enumeration and log which one was chosen. (Two physical units present simultaneously is an accepted rare case, not one that needs real tie-break logic.)
- When a matching port is found and the adapter is not already connected, connect automatically.
- When the connected port disappears (raises on read, or vanishes from the port list), treat as disconnected: release Native Mode if it was active, close the input/output ports, and resume polling. No user action or dialog is involved — the MIDI signal indicator simply goes dark.
- **Invariant:** connect and disconnect are only ever processed serially, on the single MIDI-management thread/loop that also runs discovery polling — they cannot overlap by construction, so a reconnect can never race an in-flight disconnect cleanup.
- **Connection status is exposed as its own piece of state**, independent of the Signal Monitor's liveness/error tracking (see `app-ui.md`): whether a nanoKONTROL Studio port is currently open, and if so, its device name. The Status UI reads this directly to choose between "Waiting for nanoKONTROL Studio…" and the connected device's name (`UI-STATUS-002`). This is deliberately a separate axis from the MIDI indicator dot's live/error/quiet state — see "Decisions & Alternatives" and `app-ui.md` for why the two can disagree (e.g., a physically connected device whose Native Mode handshake failed shows the device name *and* an error dot at the same time).

## Native Mode Handshake

- **Every fresh connect attempt clears the MIDI channel's error flag before attempting the handshake**, so the flag always reflects only the current attempt's outcome — a stale failure from a previous connection never lingers past a new connect, and a successful handshake on reconnect clears a prior error just as cleanly as an unplugged device leaving the error behind would otherwise be confusing.
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

The `korg_scene` type is recognized from the specific 13-byte Native Mode Scene-button SysEx pattern (reused byte-for-byte from the prototype's parser), since the Scene button has no ordinary Note/CC representation even in Native Mode.

`normalized` is only defined, and only needs to be defined, for the event types the static map actually consumes in phase 1: `cc` (7-bit scaled to 0.0–1.0) and `korg_scene` (SysEx value byte scaled to 0.0–1.0). `pitchbend`, `program`, `aftertouch`, and `polytouch` normalization is unspecified and unused until a future mapping references one of those types.

**Liveness update happens before normalization, not after.** Any raw MIDI message received on the connected port — including SysEx bytes that fail to match the `korg_scene` pattern, or any other message the normalizer doesn't recognize — updates the "last MIDI activity" timestamp the Signal Monitor (see `app-ui.md`) uses to drive the MIDI signal indicator. Liveness means "the device is talking to us," not "we understood what it said," so it is intentionally decoupled from successful parsing.

**Reconnect invariant:** the Static Mapping Engine's previous-value map (see `static-mapping.md`) is cleared whenever this adapter completes a fresh connect, so no stale per-control state survives a disconnect/reconnect cycle.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Device selection | Auto-connect by fuzzy name match, no picker | Manual dropdown + Connect button (prototype's approach) | App is single-purpose (one supported controller); removes a manual step per HLD's "simple UI" goal |
| Native Mode addressing | Send enter/exit request across all 16 channel IDs | Detect and use the controller's actual stored global channel | Matches prototype's validated workaround; avoids needing to read/know a setting stored on the device |
| Native Mode failure handling | Non-fatal; MIDI input continues without it | Block connection / surface as hard error | A missing output port (e.g., held by other software) shouldn't stop faders/knobs from working, only the Scene-button mapping |
| MIDI library | `mido` (+ `python-rtmidi` backend) | Direct `rtmidi` bindings, `pygame.midi` | Already validated against this exact controller's SysEx behavior in the prototype |
| Duplicate matching ports | Connect to the first match in enumeration order, log the choice | Prompt the user to pick; refuse to connect | Two physical units simultaneously present is a rare, accepted edge case not worth a picker UI in a "no device picker" app |
| Native Mode failure surfacing | Distinct *error* state on the MIDI indicator (see `app-ui.md`'s 3-state indicator) | Log-only, no UI signal | A degraded Native Mode is a real, silent-looking failure mode; the indicator should not look identical to "healthy but quiet" |
| Exit-SysEx send failures | Per-send try/except inside the 16-channel loop; port close always runs in `finally` | Abort the whole loop on first failure | Guarantees port cleanup always completes even if some/all SysEx sends fail |
| Connect/disconnect concurrency | Serial only, single MIDI-management thread | Locking/flags across multiple threads | Simpler to reason about; discovery polling and connect/disconnect already share one loop |
| Liveness vs. parse success | Liveness timestamp updates on any raw MIDI message, before normalization | Only update on successfully normalized/mapped events | Liveness should mean "device is talking," independent of whether the message parses |
| Reconnect state hygiene | Clear the mapping engine's previous-value map on every fresh connect | Leave state untouched across reconnects | Prevents stale pre-disconnect state from causing spurious or missed edges after reconnect |
| Error-flag lifecycle | Clear the MIDI error flag at the start of every fresh connect attempt, before the handshake runs | Clear only on explicit user action; leave set until app restart | A stale error flag from a prior connection shouldn't outlive that connection; each attempt should be judged on its own outcome |
| Connection status vs. liveness/error | Exposed as a separate piece of state (device open + name) from the Signal Monitor's live/error/quiet | Fold connection status into the same 3-state model | The two questions ("is a controller present" vs. "is it healthy right now") are genuinely independent and can disagree (connected device, failed handshake) |

## Open Questions & Future Decisions

### Resolved
1. ✅ Duplicate matching ports, mid-handshake output-port loss, exit-SysEx partial failure, connect/disconnect concurrency, liveness-vs-parse-success, pitchbend/aftertouch/program normalization scope, and reconnect state hygiene are all resolved above (decided together with the user during the Phase 2 LLD edge-case review).
2. ✅ Failed Native Mode handshake surfaces as a distinct *error* state on the Status UI's MIDI indicator (3-state: live / quiet / error), resolved jointly with `osc-io.md`'s listener-bind-failure question — see `app-ui.md`.
3. ✅ Error-flag clearing lifecycle (cleared at the start of each connect attempt) and connection-status/device-name being an independent axis from the liveness/error dot are resolved above (decided together with the user during the Phase 4 cross-spec edge audit).

### Deferred
1. Exact poll interval for device discovery (proposed 2s) is a tunable constant, not yet load-bearing on any spec.

## References

- `~/github/DragonMIDI-vibed/dragonmidi/midi_io.py` — source of the Native Mode SysEx handshake and fuzzy device-name matching, reused as validated reference.
- `~/github/DragonMIDI-vibed/dragonmidi/engine.py` — source of the `korg_scene` SysEx byte pattern and normalized-event shape this LLD adapts.
