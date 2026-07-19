# OSC Transport (Client + Listener) — EARS Specs

Traces to `docs/llds/osc-io.md`.

## Client (Send)

- [ ] **OSC-CLIENT-001**: When the Mapping Engine produces an OSC message, the system shall encode it as an OSC 1.0 packet (address string, type-tag string, then `int32`/`float32`/`string` arguments, each NUL-padded to a 4-byte boundary) and send it via UDP to the configured Dragonframe host and port.
- [ ] **OSC-CLIENT-002**: If a UDP send raises an exception (e.g. unreachable network, full send buffer), then the system shall catch and log it and continue processing subsequent messages, without retrying or queueing the failed send.

## Listener (Receive, Status Only)

- [ ] **OSC-LISTEN-001**: The system shall bind a UDP socket to `0.0.0.0:<local listen port>` at startup, on a background thread, to receive Dragonframe's OSC Output traffic.
- [ ] **OSC-LISTEN-002**: When any datagram is received on the local listen port, the system shall update the Dragonframe channel's last-activity timestamp, without validating the datagram's size or parsing its OSC content.
- [ ] **OSC-LISTEN-003**: If the local listen port fails to bind at startup (e.g. already in use), then the system shall set the Dragonframe channel's error flag (consumed by `UI-MONITOR-003`, see `docs/specs/app-ui.md`) rather than behaving as if no traffic has simply arrived yet.
- [ ] **OSC-LISTEN-005**: When a bind attempt begins (at startup, or triggered by an Apply of a changed local listen port per `UI-CONFIG-001`), the system shall clear the Dragonframe channel's error flag before attempting the bind, so the flag reflects only the current attempt's outcome.
- [ ] **OSC-LISTEN-006**: When the user applies a changed local listen port (`UI-CONFIG-001`), the system shall close the existing listener socket and bind a new one to the new port, following the same clear-flag-then-bind path as the startup bind (`OSC-LISTEN-001`, `OSC-LISTEN-005`, `OSC-LISTEN-003`).
- [D] **OSC-LISTEN-004**: Where source-address verification is enabled, the system shall discard datagrams whose source IP does not match the configured Dragonframe host (deferred until a real false-positive liveness signal is observed).

## Axis Discovery (`getAllPosition`)

- [ ] **OSC-DISCOVER-001**: Whenever a `getAllPosition` discovery query is sent (at startup or via the on-demand refresh action), the system shall send it from the same UDP socket bound for listening, not from a separate socket.
- [ ] **OSC-DISCOVER-002**: The system shall automatically send one `/dragonframe/axis/getAllPosition` discovery query (no arguments) immediately after the listening socket successfully binds at startup.
- [ ] **OSC-DISCOVER-003**: The system shall provide an explicit user-triggered action that re-sends the `getAllPosition` discovery query on demand, independent of the automatic startup query.
- [ ] **OSC-DISCOVER-004**: When a received datagram begins with the OSC bundle marker (`#bundle\0`), the system shall recursively decode its contained elements (each itself an OSC message or a nested bundle), without imposing a recursion-depth or size-consistency bound, rather than treating the datagram as a single non-bundle message.
- [ ] **OSC-DISCOVER-005**: When a decoded element is an OSC message of the form `/dragonframe/axis/{name},f (position)` (excluding the literal `/dragonframe/axis/getAllPosition` query address itself), the system shall record it in the discovered-axis store keyed by `{name}`, overwriting any prior entry for that same name.
- [ ] **OSC-DISCOVER-006**: The system shall distinguish two discovered-axis states — "never queried" (no discovery query has completed since startup) and "queried, zero axes" (at least one query round-trip completed with no axis entries reported) — using a sentinel distinct from an empty collection for the former state.
- [ ] **OSC-DISCOVER-007**: If a received datagram fails to decode as a valid OSC message or bundle, the system shall skip it without raising, while still crediting it toward the Dragonframe channel's liveness timestamp per `OSC-LISTEN-002`.

## Configuration

- [ ] **OSC-CONFIG-001**: The system shall default the Dragonframe host to `127.0.0.1`, the Dragonframe port to `7010`, and the local listen port to `7011`.
- [ ] **OSC-CONFIG-002**: If a configuration change would set the Dragonframe port equal to the local listen port, then the system shall reject the change with a clear error rather than applying it.

## References

- `docs/llds/osc-io.md`
- `~/github/DragonMIDI-vibed/dragonmidi/osc.py` — source of the OSC 1.0 encoder this LLD reuses.
- `docs/dragonframe-messages-research.md § Empirically validated: direct axis addressing` — the bundle format, single-socket query, and duplicate-response findings behind the Axis Discovery specs.
