# MIDI Input Adapter — EARS Specs

Traces to `docs/llds/midi-input.md`.

## Device Discovery and Connection

- [x] **MIDI-CONN-001**: The system shall poll available MIDI input port names on a timer (proposed 2s interval) to detect a KORG nanoKONTROL Studio.
- [x] **MIDI-CONN-002**: When a MIDI input port name matches the nanoKONTROL Studio fuzzy-match pattern (name, stripped of non-alphanumeric characters and lowercased, contains `nanokontrolstudio`) and the adapter is not currently connected, the system shall connect to that port automatically, with no manual device picker.
- [x] **MIDI-CONN-003**: If more than one available MIDI input port matches the nanoKONTROL Studio pattern, then the system shall connect to the first match in port-enumeration order and log which port was chosen.
- [x] **MIDI-CONN-004**: If a discovery poll tick fires while a connect or disconnect operation is already in progress, then the system shall skip that tick rather than starting an overlapping operation.
- [x] **MIDI-CONN-005**: If the connected MIDI input port disappears (a read error occurs, or the port is no longer in the enumerated port list), then the system shall treat the device as disconnected: release Native Mode if it was active, close the input and output ports, and resume discovery polling — with no user-facing dialog.
- [x] **MIDI-CONN-006**: The system shall process connect and disconnect operations only serially, on a single MIDI-management thread, such that they can never run concurrently.
- [x] **MIDI-CONN-007**: The system shall expose the MIDI Input Adapter's connection status (connected or not) and, when connected, the connected device's name, as state read directly by the Status UI (`UI-STATUS-002`, see `docs/specs/app-ui.md`), independent of the MIDI channel's liveness and error state — a connected device and an error condition may be displayed simultaneously.

## KORG Native Mode Handshake

- [x] **MIDI-NATIVE-001**: When the MIDI Input Adapter connects to a nanoKONTROL Studio, the system shall locate the matching MIDI output port for the same physical device (exact name match, else fuzzy token match) and send the Native-Mode-enter SysEx request addressed to each of the 16 possible MIDI channel IDs.
- [x] **MIDI-NATIVE-002**: When the MIDI Input Adapter disconnects from a nanoKONTROL Studio (device lost or app quit), the system shall send the Native-Mode-exit SysEx request to each of the 16 possible MIDI channel IDs, wrapping each per-channel send in its own error handling so a failure on one channel does not prevent the remaining sends, then close the output port unconditionally regardless of send outcomes.
- [x] **MIDI-NATIVE-003**: If no matching MIDI output port can be opened, or a previously-matched output port becomes unavailable before the Native-Mode-enter SysEx is sent, then the system shall continue processing MIDI input without Native Mode and set the MIDI channel's error flag (consumed by `UI-MONITOR-003`, see `docs/specs/app-ui.md`).
- [x] **MIDI-NATIVE-004**: When a fresh connect attempt begins, the system shall clear the MIDI channel's error flag before attempting the Native Mode handshake, so the flag reflects only the current attempt's outcome.

## Normalized MIDI Events and Liveness

- [x] **MIDI-EVT-001**: The system shall normalize incoming `note`, `cc`, `pitchbend`, `program`, `aftertouch`, and `polytouch` MIDI messages, plus the nanoKONTROL Studio's Native Mode Scene-button SysEx pattern (`korg_scene`), into a common event shape: `type`, `channel`, `number`, `raw_value`, `normalized`, `is_press`, `is_release`.
- [D] **MIDI-EVT-002**: Where a future mapping references `pitchbend`, `program`, `aftertouch`, or `polytouch` normalization, the system shall define that type's `raw_value`-to-`normalized` scaling (deferred — the phase-1 opinionated map only consumes `cc` and `korg_scene` normalization).
- [x] **MIDI-EVT-003**: When any raw MIDI message is received on the connected input port, the system shall update the MIDI channel's last-activity timestamp, regardless of whether the message is successfully normalized into an event.
- [x] **MIDI-EVT-004**: When the MIDI Input Adapter completes a fresh connect, the system shall clear the Static Mapping Engine's previous-value state (see `MAP-STATE-001`, `docs/specs/static-mapping.md`) so no per-control state from a prior connection persists across a reconnect.

## References

- `docs/llds/midi-input.md`
