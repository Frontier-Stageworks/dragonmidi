# OSC Transport (Client + Listener) — EARS Specs

Traces to `docs/llds/osc-io.md`.

## Client (Send)

- [ ] **OSC-CLIENT-001**: When the Static Mapping Engine produces an OSC message, the system shall encode it as an OSC 1.0 packet (address string, type-tag string, then `int32`/`float32`/`string` arguments, each NUL-padded to a 4-byte boundary) and send it via UDP to the configured Dragonframe host and port.
- [ ] **OSC-CLIENT-002**: If a UDP send raises an exception (e.g. unreachable network, full send buffer), then the system shall catch and log it and continue processing subsequent messages, without retrying or queueing the failed send.

## Listener (Receive, Status Only)

- [ ] **OSC-LISTEN-001**: The system shall bind a UDP socket to `0.0.0.0:<local listen port>` at startup, on a background thread, to receive Dragonframe's OSC Output traffic.
- [ ] **OSC-LISTEN-002**: When any datagram is received on the local listen port, the system shall update the Dragonframe channel's last-activity timestamp, without validating the datagram's size or parsing its OSC content.
- [ ] **OSC-LISTEN-003**: If the local listen port fails to bind at startup (e.g. already in use), then the system shall set the Dragonframe channel's error flag (consumed by `UI-MONITOR-003`, see `docs/specs/app-ui.md`) rather than behaving as if no traffic has simply arrived yet.
- [ ] **OSC-LISTEN-005**: When a bind attempt begins (at startup, or triggered by an Apply of a changed local listen port per `UI-CONFIG-001`), the system shall clear the Dragonframe channel's error flag before attempting the bind, so the flag reflects only the current attempt's outcome.
- [ ] **OSC-LISTEN-006**: When the user applies a changed local listen port (`UI-CONFIG-001`), the system shall close the existing listener socket and bind a new one to the new port, following the same clear-flag-then-bind path as the startup bind (`OSC-LISTEN-001`, `OSC-LISTEN-005`, `OSC-LISTEN-003`).
- [D] **OSC-LISTEN-004**: Where source-address verification is enabled, the system shall discard datagrams whose source IP does not match the configured Dragonframe host (deferred until a real false-positive liveness signal is observed).

## Configuration

- [ ] **OSC-CONFIG-001**: The system shall default the Dragonframe host to `127.0.0.1`, the Dragonframe port to `7010`, and the local listen port to `7011`.
- [ ] **OSC-CONFIG-002**: If a configuration change would set the Dragonframe port equal to the local listen port, then the system shall reject the change with a clear error rather than applying it.

## References

- `docs/llds/osc-io.md`
- `~/github/DragonMIDI-vibed/dragonmidi/osc.py` — source of the OSC 1.0 encoder this LLD reuses.
