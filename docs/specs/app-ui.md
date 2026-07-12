# Application Shell, Signal Monitor & Status UI — EARS Specs

Traces to `docs/llds/app-ui.md`.

## Signal Monitor

- [ ] **UI-MONITOR-001**: The system shall initialize each channel's (`midi`, `dragonframe`) last-activity value to a "never seen" sentinel, distinct from any real timestamp, at startup.
- [ ] **UI-MONITOR-002**: The system shall compute liveness using a monotonic clock, such that a channel is reported live only while its last-activity value is not the "never seen" sentinel and the elapsed monotonic time since that value is strictly less than the liveness window (proposed 2.0s).
- [ ] **UI-MONITOR-003**: While a channel's error flag is set (MIDI: Native Mode handshake failure per `MIDI-NATIVE-003`; Dragonframe: listener bind failure per `OSC-LISTEN-003`), the system shall report that channel's display state as error, taking precedence over both live and quiet.

## Status UI

- [ ] **UI-STATUS-001**: The system shall display two indicator rows, "MIDI signal" and "Dragonframe signal," each rendering a 3-state dot (live / error / quiet) and a short label, both derived from a single Signal Monitor read per UI update tick.
- [ ] **UI-STATUS-002**: While the MIDI channel has not yet connected to a nanoKONTROL Studio (per `MIDI-CONN-007`, see `docs/specs/midi-input.md`), the system shall display "Waiting for nanoKONTROL Studio…" as the MIDI row's secondary text; when connected, it shall display the connected device's name instead.
- [ ] **UI-STATUS-003**: The system shall display the configured local listen port on the Dragonframe row, and the configured Dragonframe host and port in an editable "Sending to" field pair.
- [ ] **UI-STATUS-004**: The system shall treat the indicator dot's live/error/quiet state and the row's secondary label (connection/device-name text) as independent signals; a channel may simultaneously display an error dot and a connected-device label (e.g., a physically connected controller whose Native Mode handshake failed), and this combination is intended, not a defect.
- [ ] **UI-CONFIG-001**: When the user edits the host, Dragonframe port, or listen port fields and presses Apply, the system shall validate and apply the new configuration; edits shall not take effect, and no rebind shall occur, before Apply is pressed. Applying a changed local listen port shall trigger the OSC Listener to close and rebind its socket (`OSC-LISTEN-006`, see `docs/specs/osc-io.md`).
- [D] **UI-CONFIG-002**: Where settings persistence is enabled, the system shall persist the Dragonframe host, Dragonframe port, and local listen port across app launches (deferred pending a decision on whether phase 1 includes any persisted state).

## Threading and Shutdown

- [ ] **UI-THREAD-001**: The system shall bridge MIDI events and OSC Listener datagrams from their background threads into the Qt main thread using thread-safe queues drained by a timer, fully draining each queue on every tick with no per-tick cap.
- [ ] **UI-SHUTDOWN-001**: When the application quits, the system shall run each cleanup step (Native Mode release, MIDI port close, OSC Listener stop, UDP client socket close) with its own isolated error handling, such that a failure in one step does not prevent the others from running, and shall bound the overall shutdown sequence with a timeout before force-exiting.

## References

- `docs/llds/app-ui.md`
