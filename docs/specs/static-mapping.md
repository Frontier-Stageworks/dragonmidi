# Static Mapping Engine — EARS Specs

Traces to `docs/llds/static-mapping.md`.

## Opinionated Table

- [x] **MAP-TABLE-001**: For every table entry whose MIDI source is a CC message, the system shall map it to its corresponding Dragonframe OSC message only when the event's MIDI channel is 16 (zero-indexed 15); an otherwise-matching CC control on any other channel shall not match any table entry. This invariant does not apply to the Scene button (`korg_scene` type), which matches on type alone — its `channel` field is the controller's own configured Native Mode global-channel ID (see `MIDI-NATIVE-001`), not a stand-in for MIDI channel 16, and may legitimately be any value 0–15.
- [x] **MAP-TABLE-002**: While a fader (CC 0–7) whose target is in OSC encoder mode, or a knob (CC 16–23) whose bank has no axis assigned, changes value, the system shall send its mapped `/dragonframe/encoder/<n>` OSC message (float 0.0–1.0) on every distinct value received, with no debounce. (A fader in OSC axis (direct) mode instead follows `MAP-AXIS-001`/`MAP-AXIS-009`; a knob whose bank has an axis assigned instead follows `MAP-BANK-001`.)
- [x] **MAP-TABLE-003**: When a mapped button-type control (Transport Record, Play, Rewind, Fast Forward, Previous Track, Next Track, or the Native Mode Scene button) transitions to pressed, the system shall send that control's mapped one-shot Dragonframe OSC message exactly once per transition. Mute 1–8 follows this same one-shot-per-transition timing, but its message depends on its bank's fader state — see `MAP-BANK-002` (bank has an axis) and `MAP-BANK-004` (bank has no axis, encoder-reset fallback). Stop, Cycle, Solo 1–8, and Previous/Next Marker instead produce a WebSocket command on the same press-edge timing — see `MAP-WS-001` through `MAP-WS-009`, not this spec.
- [x] **MAP-TABLE-005**: If a MIDI event does not correspond to any entry in the opinionated table (including Record 1–8, Select 1–8, Set Marker, and Return to Zero), then the system shall produce no OSC output and no log entry for it. This does not apply to Stop, Cycle, Solo 1–8, or Previous/Next Marker — removed from the opinionated table's OSC entries entirely, they instead produce a WebSocket command (`MAP-WS-001` through `MAP-WS-009`), not silence.

## OSC Axis (Direct) Target

- [x] **MAP-AXIS-001**: While a fader targeting an OSC axis (direct) changes value, the system shall send `/dragonframe/axis/{axisname}/gotoPosition,f (position)` on every distinct value, with no debounce, where `position = min + normalized_value * (max - min)` using that mapping entry's configured `min` and `max`.
- [x] **MAP-AXIS-002**: The system shall accept any real-valued `min`/`max` pair for an OSC axis (direct) target — including `min > max` and `min == max` — without validation or rejection.
- [x] **MAP-AXIS-003**: When the user configures an OSC axis (direct) target, the system shall restrict axis name selection to names present in the OSC Listener's discovered list at that moment (`OSC-DISCOVER-005`, `docs/specs/osc-io.md`) and shall not accept an arbitrary or free-text axis name; this restriction applies only at selection time and is not re-enforced afterward against a mapping entry already configured (see `MAP-AXIS-006` for what happens if the axis later disappears). Enforced by the Mapping View UI (picker), not the `MappingEngine` class — see `UI-MAP-004`, `docs/specs/app-ui.md`.
- [x] **MAP-AXIS-006**: If a mapping entry's configured axis name is absent from the OSC Listener's discovered list at the time a `gotoPosition` message would be sent for it, the system shall send the message anyway (targeting that name unconditionally); it shall not withhold the send, warn, or disable the mapping entry based on discovered-list membership.
- [x] **MAP-AXIS-004**: The system shall offer independent OSC axis (direct) target-type selection only for fader controls in this phase; knobs and buttons shall have no independent OSC axis (direct) target-type selection of their own. This does not preclude a knob or Mute button automatically deriving an axis-targeted action from its bank's fader (`MAP-BANK-001`, `MAP-BANK-002`, `MAP-BANK-004`) — derivation is not independent assignment. Solo is unaffected by this spec; it is WebSocket-targeted, not OSC axis (direct)-derived (`MAP-WS-002`).
- [x] **MAP-AXIS-007**: When a fader's OSC axis (direct) target is cleared, the system shall remove that fader's axis-target configuration and dedup state entirely, such that its next event is evaluated against the opinionated OSC encoder channel target as if an axis target had never been set. This also transitions the fader into OSC encoder mode (`MAP-AXIS-010`).
- [x] **MAP-AXIS-008**: The system shall default every fader to OSC axis (direct) mode with no axis name selected, rather than defaulting to OSC encoder mode.
- [x] **MAP-AXIS-009**: While a fader is in OSC axis (direct) mode with no axis name selected, the system shall produce no OSC output for that fader's MIDI events; it shall not fall back to `MAP-TABLE-002`'s OSC encoder channel behavior.
- [x] **MAP-AXIS-010**: The system shall track, per fader, whether it is currently in OSC axis (direct) mode or OSC encoder mode, independent of whether an axis name has been selected. Entering OSC axis (direct) mode without selecting a name shall follow `MAP-AXIS-009` (no output), not silently remain in or revert to OSC encoder mode.

## Bank Derivation

- [x] **MAP-BANK-001**: While Bank N's fader has a real axis name assigned, Knob N shall send `/dragonframe/axis/{axisname}/stepPosition,f (delta)` on every distinct value once a prior reading exists to compare against, with no debounce, where `delta = (raw_value - previous_raw_value) * 0.1` (the change since Knob N's own last reported value, scaled by a fixed factor of `0.1` axis-position units per raw-value increment); the first reading after establishing this state shall produce no send, only a baseline.
- [x] **MAP-BANK-002**: When Bank N's fader has a real axis name assigned, Mute N shall send `/dragonframe/axis/{axisname}/setZero` on its press transition (in place of its opinionated encoder-reset target). This recalibrates the axis's zero reference to its current position; it does not move the axis.
- [x] **MAP-BANK-004**: While Bank N's fader has no axis name assigned (default state, or explicitly in OSC encoder mode), Knob N and Mute N shall produce their opinionated encoder-channel / encoder-reset targets (`MAP-TABLE-002`/`MAP-TABLE-003`), not the derived actions above. This does not apply to Solo N, which is not bank-derived — see `MAP-WS-002`.
- [x] **MAP-BANK-005**: Knob N's derived `stepPosition` send (`MAP-BANK-001`) shall not be repeated for a repeated identical raw value; this follows directly from `MAP-BANK-001`'s delta formula (a repeat computes to a `0` delta) without a separate dedup mechanism.
- [x] **MAP-BANK-006**: Bank derivation shall not apply to Record N or Select N regardless of Bank N's fader state; they shall remain unmapped (`MAP-TABLE-005`) in every case.
- [x] **MAP-BANK-007**: When Bank N's fader transitions between OSC encoder mode and OSC axis (direct) mode (`MAP-AXIS-010`) in either direction, the system shall discard Knob N's dedup state; selecting a different axis name while the fader remains in OSC axis (direct) mode shall not discard it.
- [x] **MAP-BANK-008**: While Bank N's fader has a real axis name assigned, Knob N's derived `stepPosition` send (`MAP-BANK-001`) shall be clamped such that the tracked axis position it accumulates onto never moves outside the fader's configured `min`/`max` range (using the lower and higher of the two configured values as the effective bounds, regardless of which was named `min` and which `max`). If the requested delta would carry the tracked position beyond a bound, the system shall send only the reduced delta needed to reach that bound exactly; if the tracked position is already at that bound in the requested direction, the system shall send nothing.
- [x] **MAP-BANK-009**: When computing the current tracked position for the clamping in `MAP-BANK-008`, the system shall prefer Dragonframe's most recently reported live position for that axis name (`OSC-DISCOVER-005`, `docs/specs/osc-io.md`) over its own internally-accumulated estimate; the internal estimate shall be consulted only when no live position reading exists yet for that axis name. Absent both a live reading and a prior internal estimate, the tracked position shall be assumed to start at the fader's configured lower bound.

## Jog Wheel Frame Stepping

- [x] **MAP-JOG-001**: While the jog wheel (CC 110, MIDI channel 16) reports a sign-magnitude relative value in the clockwise range (`1`–`63`), the system shall send `/dragonframe/stepForward` exactly once per received message, regardless of the value's magnitude.
- [x] **MAP-JOG-002**: While the jog wheel (CC 110, MIDI channel 16) reports a sign-magnitude relative value in the counterclockwise range (`65`–`127`), the system shall send `/dragonframe/stepBackward` exactly once per received message, regardless of the value's magnitude.
- [x] **MAP-JOG-003**: When the jog wheel reports a sign-magnitude relative value of `0` or `64`, the system shall produce no OSC output.
- [x] **MAP-JOG-004**: The system shall not apply `MAP-DEBOUNCE-001`'s debounce window, nor any dedup-on-repeated-value logic, to jog wheel messages; each message qualifying under `MAP-JOG-001` or `MAP-JOG-002` shall produce its OSC send independent of any prior message's raw value, including a repeated identical value.
- [x] **MAP-JOG-005**: The system shall allocate no per-control state (previous-value, pressed-state, or last-fired) for the jog wheel entry.

## Jog Wheel Keystroke Output (Arc Motion Control)

- [x] **MAP-JOGKEY-001**: While the jog wheel (CC 110, MIDI channel 16) reports a sign-magnitude relative value in the clockwise range (`1`–`63`), the system's `process_keystroke()` shall return `KeyCombo(frozenset({"alt", "shift"}), "right")`.
- [x] **MAP-JOGKEY-002**: While the jog wheel (CC 110, MIDI channel 16) reports a sign-magnitude relative value in the counterclockwise range (`65`–`127`), the system's `process_keystroke()` shall return `KeyCombo(frozenset({"alt", "shift"}), "left")`.
- [x] **MAP-JOGKEY-003**: When the jog wheel reports a sign-magnitude relative value of `0` or `64`, or the event does not match the jog wheel, `process_keystroke()` shall return `None`.
- [x] **MAP-JOGKEY-004**: The system shall evaluate `process_keystroke()` for a jog wheel event independent of `process()`'s OSC output for that same event — both shall be evaluated, with neither suppressing the other based on which one would have an effect in Dragonframe's current workspace.
- [x] **MAP-JOGKEY-005**: `process_keystroke()` shall not apply debounce or dedup logic to jog wheel messages, matching `MAP-JOG-004`.
- [x] **MAP-JOGKEY-006**: `process_keystroke()` shall respect the same MIDI-channel-16 match invariant as `process()` (`MAP-TABLE-001`) for the jog wheel's CC-sourced event.
- [x] **MAP-JOGKEY-007**: `process_keystroke()` shall allocate no per-control tracked state; calls to it shall not affect `tracked_controls()` or any state consulted or mutated by `process()`.

## WebSocket-Targeted Controls

- [x] **MAP-WS-001**: When Stop (CC 42, MIDI channel 16) transitions to pressed, the system's `process_websocket()` shall return `WebSocketCommand("E-Stop")` exactly once per transition, debounced identically to `MAP-DEBOUNCE-001`. Stop shall not appear in `OPINIONATED_MAP`; `process()` shall return `None` for it.
- [x] **MAP-WS-002**: When Solo N (CC 32–39, MIDI channel 16, N = 1–8) transitions to pressed, the system's `process_websocket()` shall return `WebSocketCommand(f"select-AX{N}")` exactly once per transition, unconditional on Bank N's fader/axis state.
- [x] **MAP-WS-003**: When Cycle (CC 46, MIDI channel 16) transitions to pressed while `axis_count` (`len(axis_positions or {})`) is greater than `0`, the system's `process_websocket()` shall increment `_cycle_index = (_cycle_index + 1) % axis_count` and return `WebSocketCommand(f"select-AX{_cycle_index + 1}")` exactly once per transition.
- [x] **MAP-WS-004**: If Cycle transitions to pressed while `axis_count` is `0`, then `process_websocket()` shall return `None` and shall not advance `_cycle_index`.
- [x] **MAP-WS-005**: The system shall initialize `_cycle_index` to `-1` on `MappingEngine` construction and reset it to `-1` on every MIDI reconnect clear (`MIDI-EVT-004`, `docs/specs/midi-input.md`), matching `MAP-STATE-002`'s reconnect hygiene for other tracked state.
- [x] **MAP-WS-006**: When Previous Marker (CC 61, MIDI channel 16) transitions to pressed, the system's `process_websocket()` shall return `WebSocketCommand("Jog All", operation="+", params=(-1,))` exactly once per transition.
- [x] **MAP-WS-007**: When Next Marker (CC 62, MIDI channel 16) transitions to pressed, the system's `process_websocket()` shall return `WebSocketCommand("Jog All", operation="+", params=(1,))` exactly once per transition.
- [x] **MAP-WS-008**: Stop, Solo 1–8, Cycle, and Previous/Next Marker shall share the same press-edge/80ms-debounce state (`_pressed_state`/`_last_fired`) that `process()` uses for other button-type controls; `process_websocket()` shall not maintain separate debounce state for these keys.
- [x] **MAP-WS-009**: Stop, Cycle, and Previous/Next Marker shall be removed from `OPINIONATED_MAP` entirely; `process()` shall return `None` for these keys.

## Debounce and State

- [x] **MAP-DEBOUNCE-001**: If a second press-edge for the same button-type control arrives within 80ms of its previous press-edge, then the system shall drop the second press-edge rather than queueing it or re-firing it after the window closes.
- [x] **MAP-STATE-001**: The system shall allocate previous-value state only for controls present in the opinionated table; controls not in the table shall never have state allocated for them.
- [x] **MAP-STATE-002**: While a mapped button-type control has produced no MIDI message since app start (or since the last reconnect clear per `MIDI-EVT-004`, `docs/specs/midi-input.md`), the system shall treat it as not-pressed, such that a control already held down at that time requires one release-then-press cycle before its first press-edge fires.

## References

- `docs/llds/static-mapping.md`
- `~/github/DragonMIDI-vibed/mappings.md` — source table this LLD's map mirrors.
- `docs/dragonframe-messages-research.md § Axis Discovery and Direct Addressing` — the `gotoPosition` scaling and Manual-function findings behind the OSC Axis (Direct) Target specs.
- `docs/llds/app-ui.md` — Mapping View, including the fader row's default axis mode (`UI-MAP-011`), how Knob/Mute entries are folded into it rather than shown as their own rows (`UI-MAP-001`), and Solo's single summary row (`UI-MAP-013`).
- `docs/llds/websocket-output.md` — the WebSocket Output Adapter that consumes `process_websocket()`'s `WebSocketCommand` output.
- `docs/dragonframe-websocket-research.md` — confirmed/rejected WebSocket command list behind `MAP-WS-001` through `MAP-WS-009`.
- `docs/nanokontrol-mapping-proposal.md` — the candidate bindings these specs commit to specific controls.
