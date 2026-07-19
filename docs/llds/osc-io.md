# OSC Transport (Client + Listener)

## Context and Design Philosophy

Two independent UDP responsibilities that share the OSC 1.0 wire format:

1. **Client** — encodes and sends Dragonframe OSC commands produced by the Mapping Engine to Dragonframe's OSC Input port.
2. **Listener** — binds a local UDP port and treats incoming datagrams as evidence that Dragonframe is alive and reachable, per the HLD's decision to use bidirectional OSC rather than a send-only heartbeat. It additionally parses `getAllPosition` responses specifically, to discover the current project's axis names for the mapping view's axis picker (`docs/high-level-design.md § Delivery Phasing`) — it does not decode any other OSC content Dragonframe sends.

Both share the same OSC 1.0 message encoder. The Listener now also needs a **decoder** — for the one response shape it cares about (`getAllPosition`'s bundled per-axis replies) — where phase 1's original design only needed to detect "a datagram arrived," not parse it.

## Axis Discovery (`getAllPosition`)

- To discover axis names, the Listener sends `/dragonframe/axis/getAllPosition` (no arguments) to Dragonframe's OSC Input port, **from the same socket it has bound for listening**, not from the Client's separate send socket.
- **This is a real, empirically-required constraint, not a simplification:** sending the query from an unbound (ephemeral-port) socket while listening on a different socket bound to the configured listen port failed to receive any reply in direct testing against a real Dragonframe instance. Sending from the same bound socket worked reliably. Dragonframe's exact reply-addressing convention (reply-to-source vs. reply-to-configured-output-port) isn't documented; using one socket for both roles is robust regardless of which it actually is.
- **The response arrives as an OSC 1.0 `#bundle`**, not a bare message: `"#bundle\0"` (8 bytes) + an 8-byte OSC time tag + a sequence of `(int32 size, message bytes)` elements. Each element is itself an OSC message of the form `/dragonframe/axis/{axisname},f (position)` (one per known axis) and must be unwrapped before the per-axis address/value pairs are usable. A bundle element may in principle nest another bundle; the decoder handles this recursively rather than assuming exactly one level of nesting.
- Discovered `(axis_name, position)` pairs are handed to the mapping view for its axis picker (`static-mapping.md`'s OSC axis (direct) target type) — this is the only content interpretation this component performs; all other incoming traffic is still treated as opaque liveness signal only.
- **Discovered axes are stored keyed by name**, overwritten on each new response for that name. This gives two behaviors "for free," without dedicated logic: duplicate responses for the same axis (whether from a genuine re-query or the unprompted motor-position broadcast described below) simply overwrite with whichever arrived most recently, and if Dragonframe ever reports two axes under the same name, the later one silently wins in the picker — an accepted limitation, not something this component disambiguates.
- **Duplicate responses are expected and tolerated, not an error.** With "Output motor positions" enabled in Dragonframe's OSC preferences, a `gotoPosition` command can trigger both an unprompted motor-position broadcast and the explicit `getAllPosition` reply. In practice these carry the same value, but even if a real move happened between the two (making them genuinely differ), the store-by-name/last-write-wins behavior above already resolves it without needing a dedicated "which one is authoritative" rule.
- **Discovery is triggered automatically after every successful bind of the listening socket — not only the very first one at startup, but also any rebind** (e.g. via `OSC-LISTEN-006`'s Apply-triggered rebind on a changed listen port) — since a rebind is functionally "starting fresh" for the listener; there's no reason to special-case it out and leave a real staleness window right after a config change. Additionally available on-demand via an explicit **"Rescan"** action in the mapping view — for example after the user adds a new axis in Dragonframe, or switches to a different project, and wants the axis list to reflect it without restarting DragonMIDI. No periodic/background re-query loop otherwise.
- **The discovery query's target host/port is stored on the Listener and updated explicitly, not read live from config on every send.** Unlike the Client (below), which reads the current configured Dragonframe host/port fresh on every `sendto`, the discovery query is only ever sent from inside the Listener's own code paths (bind, rebind, Rescan), so it needs an explicit `update_dragonframe_target(host, port)` call whenever the Status UI's Apply changes the Dragonframe host/port — otherwise a host/port change would leave discovery silently querying the old target (and, since only a listen-port change triggers a rebind, would never automatically re-query at all). Applying **any** config change calls this unconditionally, mirroring the Client's `configure()` call in the same handler, rather than tracking whether the Dragonframe host/port specifically changed.
- **Two distinct empty states are tracked, not conflated:** "never queried yet" (no `getAllPosition` has been sent or answered since startup) versus "queried, and the current project reports zero axes." The discovered-axes store starts as `None` (never queried) and only becomes an empty collection once a query round-trip is considered complete with no axes reported — the same sentinel-vs-empty pattern already used for Signal Monitor's `last_activity` in `app-ui.md`.
- **Zero-axes detection is timeout-based, not response-based.** Confirmed empirically: a project with zero Arc axes sends **no response at all** to `getAllPosition` (complete silence, not an empty bundle) — verified by removing every axis and re-querying. A query round-trip is therefore considered "complete" 2.0 seconds after being sent (matching the Signal Monitor's existing `LIVENESS_WINDOW` constant) if no axis has been reported by then; the store transitions from `None` to an empty collection at that point. Any axis response arriving before or after that timeout still updates the store normally — the timeout only governs the never-queried → empty-collection transition, not whether individual axis entries are recorded.
- **No recursion-depth or size-consistency bounds on bundle decoding.** Dragonframe is a trusted local peer, not untrusted input; the decoder trusts each element's declared size field and recurses without a depth limit. A decode failure (malformed/truncated framing) is caught and skipped at the top level, same as the existing "tolerate decode failures, liveness still counts" handling for any other unrecognized datagram.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| Dragonframe host | `127.0.0.1` | Where Dragonframe's OSC Input is listening |
| Dragonframe port | `7010` | Dragonframe's OSC Input UDP port (its own documented default) |
| Local listen port | `7011` | Where this app listens for Dragonframe's OSC Output; the user must separately point Dragonframe's OSC Output preference at this app's IP and this port |

These three values are machine-specific network configuration, not part of the opinionated control mapping, so they remain lightly editable in the UI (see `app-ui.md`) even though the mapping table itself is not.

**Config-apply validation:** applying a new Dragonframe port and local listen port that are equal is rejected with a clear error rather than allowed to silently create two sockets fighting over one port.

## Client (Send)

- Encodes `(address, *args)` into an OSC 1.0 message: address string, type-tag string, then arguments (`int32`, `float32`, or `string`), each NUL-padded to a 4-byte boundary — reused directly from the prototype's `osc.py`, since it is a small, correct, side-effect-free wire-format implementation rather than "architecture."
- Sends via a UDP socket to the configured Dragonframe host:port. UDP send is fire-and-forget; a successful `sendto` call does not indicate Dragonframe received or understood the message (this is exactly why the Listener exists).
- If `sendto` raises (e.g. `ENETUNREACH`, a full send buffer), the exception is caught and logged; the send is treated like any other dropped UDP packet. There is no retry queue in phase 1.
- **Encoder type coverage is a closed invariant:** the Mapping Engine (`static-mapping.md`) only ever produces `float`, `int`, or no-argument OSC messages, which is a strict subset of what this encoder supports. No fallback path is needed for argument types the mapping engine never produces.

## Listener (Receive)

- Binds a UDP socket to `0.0.0.0:<local listen port>` on a background thread/loop, at app startup.
- **Every bind attempt — at startup, or triggered by an Apply of a changed local listen port (see below) — clears the Dragonframe channel's error flag before attempting the bind**, so the flag always reflects only the most recent attempt's outcome, mirroring the same lifecycle rule as `midi-input.md`'s Native Mode error flag.
- If the bind fails (e.g. port already in use by a previous instance that didn't shut down cleanly), this is a real configuration problem, not ordinary "no signal yet" — it surfaces as the *error* state on the Status UI's Dragonframe indicator (3-state: live / quiet / error — see `app-ui.md`), resolved jointly with `midi-input.md`'s Native-Mode-failure surfacing question.
- **Rebind on config change:** when the user applies a changed local listen port via the Status UI's Apply action (`app-ui.md`), the existing listener socket is closed and a new one is bound to the new port, going through the same clear-error-flag-then-bind-attempt path described above. Without this, editing the listen port in the UI would silently have no effect on the actual listener. The Client (send) side needs no equivalent rebind: it is stateless per send and simply reads the current configured host/port on every `sendto` call.
- On receiving any datagram, updates a "last Dragonframe activity" timestamp, consumed by the Signal Monitor (`app-ui.md`) to drive the Dragonframe signal indicator — **this happens regardless of whether the datagram decodes successfully**, matching the same "liveness before parsing" principle already used in `midi-input.md`. No size validation is applied — UDP datagrams are inherently bounded, and content that isn't a recognized response doesn't need to be size-checked either.
- A datagram that arrives in the brief window before the listener thread finishes binding at startup is simply not received (no listener yet exists to catch it) — accepted as a harmless, sub-second startup race; the indicator lights on the next packet instead.
- Beyond liveness and the `getAllPosition` bundle parsing described above, does not attempt to interpret any other OSC content Dragonframe sends (frame/shutter/shoot events, unprompted motor-position streaming outside of a discovery query) — those remain opaque liveness signal only.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| OSC encoder | Reuse prototype's `build_message` nearly verbatim | Pull in a third-party OSC library (`python-osc`, `pyOSC3`) | The existing encoder is small, correct, and already validated against real Dragonframe input; no need for a dependency to do 20 lines of struct packing |
| Listener validation depth | Accept any UDP datagram on the port as a liveness signal | Fully decode and validate OSC framing before counting it as "signal" | Phase 1 only needs "is Dragonframe talking to us," not "is it saying something well-formed"; simpler and more robust to any Dragonframe version quirks |
| Source filtering | None — any datagram on the bound port counts | Verify sender IP matches configured Dragonframe host | Simplicity; the listen port is presumed private to this Dragonframe/DragonMIDI pairing on set (see Open Questions) |
| Send-path exceptions | Catch, log, continue | Retry queue | Fire-and-forget UDP already has no delivery guarantee; a failed send is just another dropped packet |
| Listener bind failure | Distinct *error* state on the Dragonframe indicator | Silent failure (indicator just never lights) | A silently-failed-to-bind listener would look identical to ordinary "no traffic yet," which is actively misleading for the app's core purpose |
| Port collision (Dragonframe port == listen port) | Reject at config-apply time with a clear error | Allow it and let sockets misbehave | Cheap, proactive catch of an easy user misconfiguration |
| Datagram size validation | None | Enforce a max size before counting as signal | UDP is inherently bounded; content isn't parsed, so size doesn't affect the liveness purpose |
| Pre-bind datagram loss | Accepted as harmless | Buffer/replay | Sub-second startup race with no meaningful consequence — indicator lights on the next packet |
| Error-flag lifecycle | Clear before every bind attempt (startup or rebind) | Clear only on explicit user action; leave set until app restart | Mirrors `midi-input.md`'s rule; each attempt should be judged on its own outcome, not haunted by a prior one |
| Listen-port change while running | Close and rebind the listener socket when Apply is pressed with a changed port | Require an app restart to change the listen port | Apply already exists as the config-change mechanism (`app-ui.md`); without a rebind, editing the field would silently do nothing |
| Axis-discovery query socket | Send `getAllPosition` from the same socket the Listener is bound to | Send from the Client's separate socket | Empirically required — sending from a separate, unbound socket failed to receive the reply against a real Dragonframe instance |
| `getAllPosition` response format | Decode as an OSC `#bundle` containing per-axis messages, recursively | Assume a bare single message | Confirmed by direct testing; a single-message-only decoder silently fails on the real response shape |
| Duplicate discovery responses | Tolerated, not deduplicated by content | Track and suppress repeats | Both the motor-position broadcast and the explicit query reply carry the same value in practice; simpler to just accept both |
| Content interpretation scope | Only `getAllPosition` bundles are parsed; everything else stays opaque liveness signal | Build a general OSC content interpreter | Matches the HLD's non-goal of not interpreting Dragonframe's other output (frame events, unprompted motor-position streaming) |
| Discovered-axis storage | Keyed by name, overwritten on each response | Track a list/history per axis | Gives duplicate-response tolerance and same-name-collision behavior "for free," with no dedicated conflict-resolution logic needed |
| Discovery trigger | Automatic after every successful bind (startup or rebind), plus an explicit on-demand "Rescan" action | Periodic background re-query; or automatic only at the very first startup bind | Matches the always-on-pipeline pattern elsewhere; a rebind is functionally a fresh start for the listener, so excluding it would leave a real staleness window after a listen-port change |
| Empty discovery states | Two distinct states tracked: never-queried (`None`) vs. queried-with-zero-axes (empty collection) | Conflate both into one "no axes" display | Same sentinel-vs-empty pattern as Signal Monitor's `last_activity`; lets the UI distinguish "still waiting" from "genuinely empty project" |
| Zero-axes detection mechanism | Timeout-based (2.0s, no response yet) | Assume Dragonframe sends an empty bundle for zero axes | Confirmed empirically: Dragonframe sends no response at all for a zero-axis project, so a response-based detection would hang forever; a timeout is the only mechanism that works |
| Bundle decode bounds | None — trust declared sizes, recurse without a depth limit | Enforce a max recursion depth / validate size consistency | Dragonframe is a trusted local peer, not untrusted input; a malformed/truncated packet is caught and skipped like any other decode failure |
| Discovery target on config change | Explicit `update_dragonframe_target(host, port)` call, re-fires the query, invoked unconditionally on every Apply | Read the host/port live from config on every discovery send, like the Client does | The discovery query is only ever sent from inside the Listener's own bind/rebind/Rescan code paths, not per-send like the Client; an explicit update call is simpler than threading a live config reference through the Listener just for this one send site |

## Open Questions & Future Decisions

### Resolved
1. Send-path exceptions, listener bind failure surfacing, port-collision validation, datagram size validation, and pre-bind datagram loss — see Decisions & Alternatives above.
2. Error-flag clearing lifecycle and listener rebind-on-Apply — see Decisions & Alternatives above.
3. Axis-discovery query socket choice, `getAllPosition`'s bundle response format, and duplicate-response handling — see Decisions & Alternatives above.
4. Discovered-axis storage/collision behavior, discovery trigger timing, empty-state tracking, and bundle decode bounds — see Decisions & Alternatives above.
5. Cross-spec edge audit (Phase 4): discovery now re-fires on every successful bind, not just the initial startup one, closing the staleness window a listen-port change would otherwise leave — see Decisions & Alternatives above.
6. The mapping view's UI treatment of the two empty-discovery states — `docs/llds/app-ui.md`'s Mapping View section renders "Discovering…" and "No axes found" respectively (`UI-MAP-005`).

### Deferred
1. Should the Listener verify the sender's source address matches the configured Dragonframe host, to avoid a false-positive "Dragonframe signal" from some unrelated traffic hitting the same port? Cheap to add; currently deferred as unnecessary complexity until it causes a real false positive.
2. Default local listen port (`7011`) is arbitrary and only needs to not collide with `7010`; no other constraint identified yet.

## References

- `~/github/DragonMIDI-vibed/dragonmidi/osc.py` — source of the OSC 1.0 message encoder reused here.
- Dragonframe official manual, "Outputting Axis Positions via Open Sound Control (OSC)" (`Using Dragonframe 2025.pdf`) — confirms Dragonframe's OSC Output capability that the Listener depends on.
- `docs/dragonframe-messages-research.md § Empirically validated: direct axis addressing` — the bundle format, single-socket query requirement, and duplicate-response findings this LLD's axis-discovery design is built on.
