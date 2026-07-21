# MIDI Input Adapter — EARS Specs

Traces to `docs/llds/midi-input.md`.

## Controller Profiles

- [x] **MIDI-PROFILE-001**: The system shall provide exactly two Controller Profiles, "nanoKONTROL Studio" and "nanoKONTROL2," each defining: a name-match pattern, whether a Native Mode handshake exists, a default MIDI channel, jog-wheel and Scene-button feature flags, and an opinionated default map.
- [x] **MIDI-PROFILE-002**: The nanoKONTROL Studio profile shall define its name-match pattern as `nanokontrolstudio`, `has_native_mode` as true, `default_channel` as 15 (MIDI channel 16), and both `has_jog_wheel` and `has_scene_button` as true.
- [x] **MIDI-PROFILE-003**: The nanoKONTROL2 profile shall define its name-match pattern as `nanokontrol2`, `has_native_mode` as false, `default_channel` as 0 (MIDI channel 1), and both `has_jog_wheel` and `has_scene_button` as false.
- [x] **MIDI-PROFILE-004**: The system shall select the nanoKONTROL Studio profile as the active Controller Profile at application launch.
- [x] **MIDI-PROFILE-005**: When the user selects a different Controller Profile, the system shall immediately swap the Static Mapping Engine's active opinionated map to the newly-selected profile's map and clear the engine's previous-value state and any axis assignments (same effect as `MIDI-EVT-004`), independent of whether a matching device has yet been found under the new profile.
- [x] **MIDI-PROFILE-006**: When the user selects a different Controller Profile while a device is connected, the system shall disconnect the current device first (releasing Native Mode if the outgoing profile had it, per `MIDI-NATIVE-002`), then begin polling for the newly-selected profile's name-match pattern.
- [x] **MIDI-PROFILE-007**: The system shall process a Controller Profile switch through the same serialization guard as connect/disconnect operations (`MIDI-CONN-006`), such that a profile switch cannot run concurrently with an in-progress connect or disconnect.

## Device Discovery and Connection

- [x] **MIDI-CONN-001**: The system shall poll available MIDI input port names on a timer (proposed 2s interval) to detect a controller matching the currently-selected Controller Profile.
- [x] **MIDI-CONN-002**: When a MIDI input port name matches the currently-selected Controller Profile's name-match pattern (`MIDI-PROFILE-002`/`003`; name stripped of non-alphanumeric characters and lowercased) and the adapter is not currently connected, the system shall connect to that port automatically, with no manual device picker within the profile.
- [x] **MIDI-CONN-003**: If more than one available MIDI input port matches the active profile's pattern, then the system shall connect to the first match in port-enumeration order and log which port was chosen.
- [x] **MIDI-CONN-004**: If a discovery poll tick fires while a connect or disconnect operation is already in progress, then the system shall skip that tick rather than starting an overlapping operation.
- [x] **MIDI-CONN-005**: If the connected MIDI input port disappears (a read error occurs, or the port is no longer in the enumerated port list), then the system shall treat the device as disconnected: release Native Mode if it was active, close the input and output ports, and resume discovery polling — with no user-facing dialog.
- [x] **MIDI-CONN-006**: The system shall process connect and disconnect operations only serially, on a single MIDI-management thread, such that they can never run concurrently.
- [x] **MIDI-CONN-007**: The system shall expose the MIDI Input Adapter's connection status (connected or not) and, when connected, the connected device's name, as state read directly by the Status UI (`UI-STATUS-002`, see `docs/specs/app-ui.md`), independent of the MIDI channel's liveness and error state — a connected device and an error condition may be displayed simultaneously.

## KORG Native Mode Handshake

- [x] **MIDI-NATIVE-001**: When the MIDI Input Adapter connects to a nanoKONTROL Studio, the system shall locate the matching MIDI output port for the same physical device (exact name match, else fuzzy token match) and send the Native-Mode-enter SysEx request addressed to each of the 16 possible MIDI channel IDs.
- [x] **MIDI-NATIVE-002**: When the MIDI Input Adapter disconnects from a nanoKONTROL Studio (device lost or app quit), the system shall send the Native-Mode-exit SysEx request to each of the 16 possible MIDI channel IDs, wrapping each per-channel send in its own error handling so a failure on one channel does not prevent the remaining sends, then close the output port unconditionally regardless of send outcomes.
- [x] **MIDI-NATIVE-003**: If no matching MIDI output port can be opened, or a previously-matched output port becomes unavailable before the Native-Mode-enter SysEx is sent, then the system shall continue processing MIDI input without Native Mode and set the MIDI channel's error flag (consumed by `UI-MONITOR-003`, see `docs/specs/app-ui.md`).
- [x] **MIDI-NATIVE-004**: When a fresh connect attempt begins, the system shall clear the MIDI channel's error flag before attempting the Native Mode handshake, so the flag reflects only the current attempt's outcome. This clear runs on every connect regardless of the active profile's `has_native_mode`, so switching from a possibly-errored Studio connection to the nanoKONTROL2 (which never errors) does not leave a stale error dot lit.
- [x] **MIDI-NATIVE-005**: When the MIDI Input Adapter connects under a Controller Profile with `has_native_mode` false (the nanoKONTROL2), the system shall skip the Native Mode handshake entirely — no output port is opened, no SysEx is sent, and the MIDI channel's error flag shall never be set on that basis for that connection.

## Normalized MIDI Events and Liveness

- [x] **MIDI-EVT-001**: The system shall normalize incoming `note`, `cc`, `pitchbend`, `program`, `aftertouch`, and `polytouch` MIDI messages, plus the nanoKONTROL Studio's Native Mode Scene-button SysEx pattern (`korg_scene`), into a common event shape: `type`, `channel`, `number`, `raw_value`, `normalized`, `is_press`, `is_release`. The `korg_scene` pattern match is unconditional (not gated on the active profile); a nanoKONTROL2 simply never emits SysEx matching it, so no `korg_scene` event is ever produced under that profile.
- [D] **MIDI-EVT-002**: Where a future mapping references `pitchbend`, `program`, `aftertouch`, or `polytouch` normalization, the system shall define that type's `raw_value`-to-`normalized` scaling (deferred — the phase-1 opinionated map only consumes `cc` and `korg_scene` normalization).
- [x] **MIDI-EVT-003**: When any raw MIDI message is received on the connected input port, the system shall update the MIDI channel's last-activity timestamp, regardless of whether the message is successfully normalized into an event.
- [x] **MIDI-EVT-004**: When the MIDI Input Adapter completes a fresh connect, the system shall clear the Static Mapping Engine's previous-value state (see `MAP-STATE-001`, `docs/specs/static-mapping.md`) so no per-control state from a prior connection persists across a reconnect.

## References

- `docs/llds/midi-input.md`
- `docs/llds/midi-input.md § Controller Profiles` — the `ControllerProfile` shape and profile-switch behavior behind the `MIDI-PROFILE-*` specs.
