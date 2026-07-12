# OSC Transport (Client + Listener)

## Context and Design Philosophy

Two independent UDP responsibilities that share the OSC 1.0 wire format:

1. **Client** — encodes and sends Dragonframe OSC commands produced by the Static Mapping Engine to Dragonframe's OSC Input port.
2. **Listener** — binds a local UDP port and treats incoming datagrams as evidence that Dragonframe is alive and reachable, per the HLD's decision to use bidirectional OSC rather than a send-only heartbeat. It does not need to decode *what* Dragonframe sent in phase 1 — only that something arrived.

Both share the same small OSC 1.0 message encoder; the Listener does not need a full decoder, only enough to optionally sanity-check that a datagram looks like an OSC packet (see Decisions).

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
- **Encoder type coverage is a closed invariant:** the Static Mapping Engine (`static-mapping.md`) only ever produces `float`, `int`, or no-argument OSC messages, which is a strict subset of what this encoder supports. No fallback path is needed for argument types the mapping engine never produces.

## Listener (Receive, status only)

- Binds a UDP socket to `0.0.0.0:<local listen port>` on a background thread/loop, at app startup.
- **Every bind attempt — at startup, or triggered by an Apply of a changed local listen port (see below) — clears the Dragonframe channel's error flag before attempting the bind**, so the flag always reflects only the most recent attempt's outcome, mirroring the same lifecycle rule as `midi-input.md`'s Native Mode error flag.
- If the bind fails (e.g. port already in use by a previous instance that didn't shut down cleanly), this is a real configuration problem, not ordinary "no signal yet" — it surfaces as the *error* state on the Status UI's Dragonframe indicator (3-state: live / quiet / error — see `app-ui.md`), resolved jointly with `midi-input.md`'s Native-Mode-failure surfacing question.
- **Rebind on config change:** when the user applies a changed local listen port via the Status UI's Apply action (`app-ui.md`), the existing listener socket is closed and a new one is bound to the new port, going through the same clear-error-flag-then-bind-attempt path described above. Without this, editing the listen port in the UI would silently have no effect on the actual listener. The Client (send) side needs no equivalent rebind: it is stateless per send and simply reads the current configured host/port on every `sendto` call.
- On receiving any datagram, updates a "last Dragonframe activity" timestamp, consumed by the Signal Monitor (`app-ui.md`) to drive the Dragonframe signal indicator. No size validation is applied — UDP datagrams are inherently bounded, and since content isn't parsed, size is irrelevant to the liveness purpose.
- A datagram that arrives in the brief window before the listener thread finishes binding at startup is simply not received (no listener yet exists to catch it) — accepted as a harmless, sub-second startup race; the indicator lights on the next packet instead.
- Does not attempt to parse Dragonframe's OSC content (axis positions, frame/shutter/shoot events) in this phase — content interpretation is an explicit HLD non-goal for phase 1.

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

## Open Questions & Future Decisions

### Resolved
1. ✅ Send-path exceptions, listener bind failure surfacing, port-collision validation, datagram size validation, and pre-bind datagram loss are all resolved above (decided together with the user during the Phase 2 LLD edge-case review).
2. ✅ Error-flag clearing lifecycle and listener rebind-on-Apply are resolved above (decided together with the user during the Phase 4 cross-spec edge audit).

### Deferred
1. Should the Listener verify the sender's source address matches the configured Dragonframe host, to avoid a false-positive "Dragonframe signal" from some unrelated traffic hitting the same port? Cheap to add; currently deferred as unnecessary complexity until it causes a real false positive.
2. Default local listen port (`7011`) is arbitrary and only needs to not collide with `7010`; no other constraint identified yet.

## References

- `~/github/DragonMIDI-vibed/dragonmidi/osc.py` — source of the OSC 1.0 message encoder reused here.
- Dragonframe official manual, "Outputting Axis Positions via Open Sound Control (OSC)" (`Using Dragonframe 2025.pdf`) — confirms Dragonframe's OSC Output capability that the Listener depends on.
