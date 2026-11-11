# MIDI Input Monitor — EARS Specs

Traces to `docs/llds/midi-monitor.md`.

## Capture Pipeline

- [ ] **MON-CAPTURE-001**: The system shall maintain exactly one `MidiMonitor` instance for the application's lifetime, shared by the MIDI dispatch path and the MIDI Input Monitor dialog, rather than opening a second MIDI input connection.
- [ ] **MON-CAPTURE-002**: When a raw MIDI event reaches the MIDI dispatch path, the system shall record it in the MIDI Input Monitor before evaluating diagnostic mode, so every event reaching the app is observable regardless of whether it is later suppressed.
- [ ] **MON-CAPTURE-003**: The system shall record the event's device/port name, message type, channel, CC/note number, value/velocity, and timestamp exactly as received, without modification by Grid or any other resolution step.
- [ ] **MON-CAPTURE-004**: When the active controller is Intech Grid and its topology has settled, the system shall additionally record the resolved logical control identity and owning module, when the raw event resolves to one.
- [ ] **MON-CAPTURE-005**: If the active controller is not Intech Grid, or Grid's resolution does not produce a match (unresolved, stale, or no address-table entry), the system shall record no resolved identity or module for that event, rather than guessing one.
- [ ] **MON-CAPTURE-006**: The system shall retain at most a fixed maximum number of the most recently recorded events (default 500), discarding the oldest event first when the limit is exceeded.
- [ ] **MON-CAPTURE-007**: The system shall not create a second MIDI backend connection, Grid topology link, or MIDI router for the purpose of monitoring.
- [ ] **MON-CAPTURE-008**: When the active Controller Profile changes while the Monitor is recording, the system shall reflect the newly active controller in subsequently recorded events without discarding or reinterpreting events recorded before the change.

## Diagnostic Mode

- [ ] **MON-DIAG-001**: The system shall maintain a single diagnostic-mode flag, checked once per MIDI event, immediately after recording it.
- [ ] **MON-DIAG-002**: When the diagnostic-mode flag is true, the system shall return from MIDI event processing without calling the Mapping Engine's OSC, Keystroke, or WebSocket processing, and without sending any OSC, keystroke, or WebSocket output for that event.
- [ ] **MON-DIAG-003**: When the diagnostic-mode flag is false, the system shall process a recorded MIDI event identically to how it was processed before this feature existed.
- [ ] **MON-DIAG-004**: When the MIDI Input Monitor dialog is opened, the system shall set the diagnostic-mode flag to true and send a WebSocket `E-Stop` command, regardless of whether a WebSocket connection is currently active.
- [ ] **MON-DIAG-005**: The system shall perform the same set-true-and-send-`E-Stop` action every time the dialog transitions from closed to open, not only the first time, and every time the diagnostic-mode checkbox is checked by the user while the dialog is open.
- [ ] **MON-DIAG-006**: If no WebSocket connection is active when `E-Stop` is sent on entering diagnostic mode, the system shall log and drop the command exactly as the existing WebSocket Output Adapter already does for any other send with no active connection, without surfacing a new error state.
- [ ] **MON-DIAG-007**: When the MIDI Input Monitor dialog's diagnostic-mode checkbox is unchecked by the user while the dialog remains open, the system shall set the diagnostic-mode flag to false, with no WebSocket command sent.
- [ ] **MON-DIAG-008**: When the MIDI Input Monitor dialog is closed by any means, the system shall set the diagnostic-mode flag to false, regardless of the checkbox's state at that moment.
- [ ] **MON-DIAG-009**: The system shall not alter Grid topology discovery, MIDI device discovery/connection, the Status UI indicators, or any Controller Profile/Named Controller behavior as a result of diagnostic mode being on or off.

## Monitor Dialog

- [ ] **MON-UI-001**: The system shall provide access to the MIDI Input Monitor from the Settings dialog, via a clearly labeled button.
- [ ] **MON-UI-002**: The system shall display, for each recorded event currently retained, its device/port, message type, channel, CC/note number, value/velocity, timestamp, and (when available) resolved module/control identity.
- [ ] **MON-UI-003**: The system shall render a missing optional field (channel, number, module, or resolved identity) as a clear placeholder rather than omitting the column or raising an error.
- [ ] **MON-UI-004**: The system shall provide a Clear control that empties the displayed and retained event log without altering the diagnostic-mode flag or a pending Capture Next Input request.
- [ ] **MON-UI-005**: The system shall provide a Capture Next Input control that, when activated, marks the next recorded event as the captured event and displays its full detail distinctly from the ongoing event log, until Capture Next Input is activated again.
- [ ] **MON-UI-006**: If Capture Next Input is activated while a previous capture request is already pending, the system shall treat the activation as a no-op, leaving the existing pending request unchanged.
- [ ] **MON-UI-007**: The system shall refresh the dialog's displayed event log on the application's existing periodic UI tick, rather than performing a widget update for every individual MIDI event, so that a high-frequency input source does not freeze the interface.
- [ ] **MON-UI-008**: If no new event has been recorded since the dialog's last refresh, the system shall perform no table update on that tick.
- [ ] **MON-UI-009**: The system shall keep the dialog's own controls (Clear, Capture Next Input, diagnostic-mode checkbox) limited to the fields described in this spec, without introducing controller-selection, network-configuration, or mapping-editing controls.

## References

- `docs/llds/midi-monitor.md`
