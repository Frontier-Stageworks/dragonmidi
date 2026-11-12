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
- [ ] **MON-CAPTURE-009**: If an `on_record` callback is registered, the system shall invoke it synchronously with the just-recorded event, after that event has been appended to the retained log, on every call to record an event.

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

## Guided Capture

- [ ] **MON-GUIDE-001**: The system shall provide a Guided Capture mode within the MIDI Input Monitor dialog, building its sequence of steps from the active controller's `unconfirmed_channel_controls` (one step per bank, 1 through `bank_count`) and `unconfirmed_global_controls` (one step each), in declared order.
- [ ] **MON-GUIDE-002**: If the active controller declares neither `unconfirmed_channel_controls` nor `unconfirmed_global_controls`, or both are empty, the system shall disable Start Guided Capture and state that no unconfirmed controls exist for this profile, rather than starting an empty session.
- [ ] **MON-GUIDE-003**: When Guided Capture starts, the system shall register to receive every subsequently recorded MIDI event and shall not retroactively consider any event recorded before that point.
- [ ] **MON-GUIDE-004**: While the current step has no pending candidate event, the system shall keep its Confirm control disabled; Skip shall remain enabled regardless of whether a candidate is pending.
- [ ] **MON-GUIDE-005**: When a MIDI event is offered to the current step, the system shall replace any previously pending candidate for that step with the new one, never accumulate multiple candidates for one step.
- [ ] **MON-GUIDE-006**: When Confirm is activated, the system shall record the current step's pending candidate as a non-skipped result, clear the pending candidate, and advance to the next step.
- [ ] **MON-GUIDE-007**: When Skip is activated, the system shall record the current step as skipped, discarding any pending candidate for it, clear the pending candidate, and advance to the next step - regardless of whether a candidate was pending.
- [ ] **MON-GUIDE-008**: When every step has been confirmed or skipped, the system shall show a summary count of captured versus skipped steps, enable a Save Session control, and no longer accept Confirm or Skip activation.
- [ ] **MON-GUIDE-009**: The system shall disable the diagnostic-mode checkbox for the duration of a running Guided Capture session, independent of whether the session's current controls would themselves produce dispatched output if diagnostic mode were off.
- [ ] **MON-GUIDE-010**: When Save Session is activated, the system shall write one JSON file recording the active controller's name, a timestamp, and every step's label with either its captured raw MIDI identity and device name or a skipped marker, to a fixed, auto-named path under `~/Documents/DragonMIDI/capture_sessions/`, and shall display the written path.
- [ ] **MON-GUIDE-011**: The system shall provide a Cancel control, available at any point before Save Session, that discards the in-memory session without writing a file.
- [ ] **MON-GUIDE-012**: The system shall not write a captured or skipped result to the Mapping Engine, the Preset Store, or any controller definition file, under any Guided Capture action.
- [ ] **MON-GUIDE-013**: The system shall not read a previously saved capture-session file back into the application.

## Guided Verify

Distinct from Guided Capture above: Capture has no expected answer yet (its purpose is discovering one); Verify does — every step's expected identity is a real key the active controller's own control-descriptor list already carries.

- [ ] **MON-VERIFY-001**: The system shall provide a Guided Verify mode within the MIDI Input Monitor dialog, building its sequence of steps from the active controller's full control-descriptor list (the same list the Controller View renders), one step per descriptor, each step's expected identity being that descriptor's own key, in that list's order.
- [ ] **MON-VERIFY-002**: If the active controller's control-descriptor list is empty, the system shall disable Start Guided Verify and state that no known controls exist for this profile, rather than starting an empty session.
- [ ] **MON-VERIFY-003**: When Guided Verify starts, the system shall register to receive every subsequently recorded MIDI event and shall not retroactively consider any event recorded before that point; a MIDI event offered after every step has been resolved shall be a no-op.
- [ ] **MON-VERIFY-004**: The system shall compare an offered event's resolved logical identity, when one exists, against the current step's expected identity; when no resolved identity exists, it shall compare the event's own raw message type and number instead.
- [ ] **MON-VERIFY-005**: When an offered event's identity (per `MON-VERIFY-004`) matches the current step's expected identity, the system shall automatically record a passing result, log it, and advance to the next step without requiring a user action.
- [ ] **MON-VERIFY-006**: When an offered event's identity does not match the current step's expected identity, the system shall report the mismatch (expected versus actual identity) and shall not automatically advance; a Next control shall be available to record the result as a failure and advance anyway.
- [ ] **MON-VERIFY-007**: While a mismatched event is pending, the system shall provide a Retry control that discards the pending candidate without recording a result, leaving the current step unchanged so a different physical control can be tried.
- [ ] **MON-VERIFY-008**: When every step has been resolved (passed or accepted as failed), the system shall show a summary count of passed versus failed steps, enable a Save Report control, and no longer accept Retry or Next activation.
- [ ] **MON-VERIFY-009**: When Save Report is activated, the system shall write one JSON file recording the active controller's name, a timestamp, and every step's label, expected identity, actual identity, and pass/fail outcome, to a fixed, auto-named path under `~/Documents/DragonMIDI/capture_sessions/` distinguishable from a Guided Capture report in the same folder, and shall display the written path. The system shall not write a result to the Mapping Engine, the Preset Store, or any controller definition file, under any Guided Verify action, and shall not read a previously saved report back into the application.
- [ ] **MON-VERIFY-010**: The system shall disable the diagnostic-mode checkbox for the duration of a running Guided Verify session, and shall not allow Guided Capture and Guided Verify to run simultaneously — starting one shall be unavailable while the other is active.

## References

- `docs/llds/midi-monitor.md`
