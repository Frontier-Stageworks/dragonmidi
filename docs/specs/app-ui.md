# Application Shell, Signal Monitor & Status UI — EARS Specs

Traces to `docs/llds/app-ui.md`.

## Signal Monitor

- [x] **UI-MONITOR-001**: The system shall initialize each channel's (`midi`, `dragonframe`) last-activity value to a "never seen" sentinel, distinct from any real timestamp, at startup.
- [x] **UI-MONITOR-002**: The system shall compute liveness using a monotonic clock, such that a channel is reported live only while its last-activity value is not the "never seen" sentinel and the elapsed monotonic time since that value is strictly less than the liveness window (proposed 2.0s).
- [x] **UI-MONITOR-003**: While a channel's error flag is set (MIDI: Native Mode handshake failure per `MIDI-NATIVE-003`; Dragonframe: listener bind failure per `OSC-LISTEN-003`), the system shall report that channel's display state as error, taking precedence over both live and quiet.

## Status UI

- [x] **UI-STATUS-001**: The system shall display two indicator rows, "MIDI signal" and "Dragonframe signal," each rendering a 3-state dot (live / error / quiet) and a short label, both derived from a single Signal Monitor read per UI update tick.
- [x] **UI-STATUS-002**: While the MIDI channel has not yet connected to a nanoKONTROL Studio (per `MIDI-CONN-007`, see `docs/specs/midi-input.md`), the system shall display "Waiting for nanoKONTROL Studio…" as the MIDI row's secondary text; when connected, it shall display the connected device's name instead.
- [x] **UI-STATUS-003**: The system shall display the configured local listen port on the Dragonframe row, and the configured Dragonframe host and port in an editable "Sending to" field pair.
- [x] **UI-STATUS-004**: The system shall treat the indicator dot's live/error/quiet state and the row's secondary label (connection/device-name text) as independent signals; a channel may simultaneously display an error dot and a connected-device label (e.g., a physically connected controller whose Native Mode handshake failed), and this combination is intended, not a defect.
- [x] **UI-CONFIG-001**: When the user edits the host, Dragonframe port, or listen port fields and presses Apply, the system shall validate and apply the new configuration; edits shall not take effect, and no rebind shall occur, before Apply is pressed. Applying a changed local listen port shall trigger the OSC Listener to close and rebind its socket (`OSC-LISTEN-006`, see `docs/specs/osc-io.md`).
- [D] **UI-CONFIG-002**: Where settings persistence is enabled, the system shall persist the Dragonframe host, Dragonframe port, and local listen port across app launches (deferred pending a decision on whether phase 1 includes any persisted state).

## Mapping View

- [x] **UI-MAP-001**: The system shall render one table row per entry in the opinionated map, in table order, showing that entry's name, MIDI source, trigger type, target type, and target.
- [x] **UI-MAP-002**: The system shall permit editing the target type and target only on the 8 fader rows (`MAP-AXIS-004`, see `docs/specs/static-mapping.md`); knob, button, and jog-wheel rows shall display their target with no control to change it.
- [x] **UI-MAP-003**: On a fader row, the system shall offer exactly two target types, OSC encoder and OSC axis; selecting OSC axis shall reveal an axis-name picker (with no name pre-selected) and min/max numeric fields pre-filled with `0.0`/`100.0`, without itself calling `MappingEngine.set_axis_target`; selecting OSC encoder shall hide those controls and call `MappingEngine.clear_axis_target(key)` (`MAP-AXIS-007`, see `docs/specs/static-mapping.md`), which is safe to call whether or not an axis target had actually been established for that key.
- [x] **UI-MAP-004**: The system shall recompute the axis-name picker's candidate list from `AxisDiscovery.axes` on every UI update tick (the same tick that updates the status indicators), not only when the picker is opened or Rescan is pressed, and shall not accept a free-text or arbitrary name (`MAP-AXIS-003`, see `docs/specs/static-mapping.md`).
- [x] **UI-MAP-005**: While `AxisDiscovery.axes` is `None` (never queried, or a query outstanding), the system shall render the picker's candidate list as disabled with the text "Discovering…"; while `AxisDiscovery.axes` is an empty dict (queried, zero axes found), the system shall render it as disabled with the text "No axes found"; otherwise the system shall render it enabled with the discovered names, sorted for stable display order.
- [x] **UI-MAP-006**: When the user selects an axis name or edits a min/max field on a fader row set to OSC axis, the system shall call `MappingEngine.set_axis_target` with the row's current name/min/max once both a name is selected and both fields parse as real numbers, with no separate save step; until then, the fader continues driving whatever target it was last actually given (`MAP-AXIS-006`).
- [x] **UI-MAP-007**: The system shall accept any value parseable as a real number in the min/max fields, including `min > max` or `min == max` (`MAP-AXIS-002`), and shall not reject or warn on either case; text that fails to parse as a number shall not be applied, and the row's last successfully-applied target (if any) shall remain in effect, with no error dialog.
- [x] **UI-MAP-008**: If a fader row's configured axis name is no longer present in `AxisDiscovery.axes`, the system shall continue showing that name as the picker's current selection (greyed to indicate it cannot be re-selected once deselected), rather than clearing or replacing it, and shall not alter the row's configured target as a result (`MAP-AXIS-006`, see `docs/specs/static-mapping.md`).
- [x] **UI-MAP-009**: When the user activates "Rescan axes," the system shall call `OscListener.rescan()` and shall not modify any row's already-configured target as a result of the call itself.
- [x] **UI-MAP-010**: The Mapping View shall hold no persisted state; on next application launch, all fader rows shall reflect the opinionated default map's OSC encoder targets, not any OSC axis target configured in a prior session.

## Threading and Shutdown

- [x] **UI-THREAD-001**: The system shall bridge MIDI events and OSC Listener datagrams from their background threads into the Qt main thread using thread-safe queues drained by a timer, fully draining each queue on every tick with no per-tick cap.
- [x] **UI-SHUTDOWN-001**: When the application quits, the system shall run each cleanup step (Native Mode release, MIDI port close, OSC Listener stop, UDP client socket close) with its own isolated error handling, such that a failure in one step does not prevent the others from running, and shall bound the overall shutdown sequence with a timeout before force-exiting.

## References

- `docs/llds/app-ui.md`
