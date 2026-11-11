# MIDI Input Monitor

## Context and Design Philosophy

Before Shuttle and Jog behavior can be implemented (`docs/roadmap.md`), several physical controls' MIDI identities are unconfirmed: the nanoKONTROL Studio/2's Record/Select/Set Marker/Return to Zero buttons (`docs/llds/static-mapping.md`'s `unconfirmed_channel_controls`/`unconfirmed_global_controls`), and real-hardware CC/note confirmation for PBF4 and VSN1 (`docs/roadmap.md § Hardware verification tasks`). This LLD adds a diagnostic tool for identifying those messages directly from physical hardware, without guessing and without risking unintended motion while doing it.

This is a passive observation feature layered on the existing MIDI pipeline, not a new input or output path. It reuses `MidiInputAdapter`'s single existing connection and `GridRuntimeController`'s existing resolution (`docs/llds/intech-grid.md § MIDI → Module/Element Resolution`) rather than opening a second `MidiBackend.open_input()` or building a second router — see `docs/high-level-design.md § Key Design Decisions`. Its one behavioral effect on the rest of the app is **diagnostic mode**: a single boolean, checked once at the app's existing dispatch choke point (`app.py`'s `_process_midi_event`), that withholds a raw event from the Mapping Engine, Keystroke, and WebSocket output paths without altering how any of those three already behave when it's off.

Out of scope (`docs/high-level-design.md § Non-Goals`): MIDI Learn, automatic assignment, new controller mappings, Shuttle/Jog/Center Stop, endpoint teaching. This LLD only displays and (while diagnostic mode is on) suppresses; it never writes to the Mapping Engine, the Preset Store, or any controller definition.

## Interface

```python
# midi_monitor.py - Qt-free

@dataclass(frozen=True)
class MonitorEvent:
    timestamp: float          # time.time(), wall-clock, for display only
    device_name: str | None
    raw: MidiEvent            # exactly as received, before Grid resolution
    resolved: tuple[str, int | None] | None   # (type, number) of the logical
                                               # control, when the active
                                               # controller resolves one; None
                                               # for an unresolved/pending Grid
                                               # event (never guessed)
    module: ModuleRef | None  # Grid module ownership, when resolved and known
    captured: bool             # True iff this is the event "Capture Next
                                # Input" was waiting for

class MidiMonitor:
    def __init__(self, capacity: int = 500) -> None: ...

    diagnostic_active: bool    # plain attribute; False until a dialog turns
                                # it on. Read directly by app.py's dispatch.
    capture_pending: bool      # plain attribute, set by request_capture_next()

    @property
    def events(self) -> Sequence[MonitorEvent]: ...   # oldest-first, bounded
    @property
    def last_captured(self) -> MonitorEvent | None: ...
    @property
    def version(self) -> int: ...   # increments on every record()/clear()

    def record(
        self,
        raw: MidiEvent,
        *,
        device_name: str | None,
        resolved: tuple[str, int | None] | None,
        module: ModuleRef | None,
    ) -> MonitorEvent: ...

    def request_capture_next(self) -> None: ...
    def clear(self) -> None: ...


def format_event_type(event: MidiEvent) -> str: ...     # "CC" / "Note On" /
    # "Note Off" / "Pitch Bend" / "Program Change" / "Aftertouch" /
    # "Poly Aftertouch" / "KORG Scene"

def format_channel(channel: int | None) -> str: ...      # "ch{channel+1}" or
    # "-"  (matches mapping_view_model.midi_source_label's existing +1 display
    # convention; a distinct function, not a shared one - that one is scoped
    # to declared mapping keys, not raw event display)

def format_module(module: ModuleRef | None) -> str: ...  # "PBF4 #2" / "VSN1 #1" / "-"

def format_resolved(resolved: tuple[str, int | None] | None) -> str: ...  # "grid_fader 3" / "-"
```

```python
# midi_monitor_widgets.py - Qt

class MidiMonitorDialog(QDialog):
    def __init__(
        self,
        monitor: MidiMonitor,
        on_enter_diagnostic: Callable[[], None],
    ) -> None: ...

    def refresh(self) -> None: ...   # called every tick from app.py's
                                      # _on_tick(), same as every other
                                      # live-refreshed dialog/widget
```

```python
# settings_dialog.py - one new constructor parameter

class SettingsDialog(QDialog):
    def __init__(
        self,
        config: ConfigController,
        load_failure_text: str | None,
        on_open_monitor: Callable[[], None],
    ) -> None: ...
```

## Capture Pipeline

- **`app.py` constructs one `MidiMonitor` and one `MidiMonitorDialog`** at the same point it constructs the other long-lived dialogs (`_build_header()`), passing `on_enter_diagnostic=lambda: self._websocket_output.send(WebSocketCommand("E-Stop"))`. `SettingsDialog` gains `on_open_monitor=self._midi_monitor_dialog.exec`, wired to a new "MIDI Input Monitor…" button placed above its existing "Close" button — reachable from Settings per the task's requirement, not a new top-level header button.
- **`_process_midi_event(raw_event)` calls `self._grid_coordinator.route_event(raw_event)` exactly once, unconditionally** — the same call it already makes, computed before the diagnostic check rather than after. `route_midi_event`/`resolve_grid_event` are pure (confirmed by inspection: no mutation, `docs/llds/intech-grid.md § MIDI → Module/Element Resolution`), so calling it before the diagnostic branch has no observable effect on Grid's own state whether or not diagnostic mode goes on to suppress what follows.
- When Grid is active and resolution succeeds, `GridRuntimeController.control_module.get((resolved.type, resolved.number))` gives the `ModuleRef`, already populated for every logical key (`docs/llds/intech-grid.md § 14`). When Grid isn't active, or resolution fails/is stale, `resolved` and `module` are `None` — the Monitor never guesses an identity Grid itself can't confirm (`GRID-MIDI-006`, `GRID-MIDI-007`).
- `self._midi_monitor.record(raw_event, device_name=self._midi_device_name, resolved=..., module=...)` is called unconditionally, before the diagnostic check — the log reflects every event reaching the app, not only events that were suppressed.
- **Immediately after recording, if `self._midi_monitor.diagnostic_active` is true, `_process_midi_event` returns** — skipping Grid-event-dropped-handling, `self._mapping.process/process_keystroke/process_websocket`, and every output adapter `.send()` call that would otherwise follow. When diagnostic mode is off, the method's remaining body is byte-identical to its pre-existing form, using the already-computed `resolved` value in place of the local `event` it used to compute inline.
- `self._midi_device_name` (already tracked for the Status UI) is read directly as the "source device/port" — there is exactly one connected MIDI device at a time (`docs/high-level-design.md § Non-Goals`, no multi-instance), so no change to `MidiEvent` or `MidiInputAdapter` is needed to attach a device identity per event.
- **Switching the Controller Profile dropdown (including into or out of Intech Grid) while the Monitor is open needs no special handling.** `device_name`/`resolved`/`module` are computed fresh, per event, from whatever controller is active at the moment `_process_midi_event` runs — not cached or retroactively reinterpreted. Rows recorded before a switch keep showing what was true when they were recorded; rows after the switch reflect the newly active controller, exactly like every other per-tick read in this app (`mapping_view_model.py`'s row builders, etc.).

## Diagnostic Mode

- `MidiMonitor.diagnostic_active` starts `False` and is mutated only by `MidiMonitorDialog` (via direct attribute assignment — a plain flag read by `app.py`'s dispatch path on the same thread it's set from, no lock needed, matching every other plain-bool UI-thread flag in this app, e.g. `self._dirty`).
- **`MidiMonitorDialog.showEvent()`** forces its diagnostic checkbox checked (signals blocked while doing so) and calls a single `_enter_diagnostic()` method — on *every* `exec()`, not only the first, so reopening the dialog is always safe-by-default again regardless of how the previous session was left.
- **`_enter_diagnostic()`**: sets `monitor.diagnostic_active = True`, then calls the injected `on_enter_diagnostic()` callback (the `E-Stop` send). Called from `showEvent()` and from the checkbox's own `toggled` handler when checked by the user mid-session.
- **`_exit_diagnostic()`**: sets `monitor.diagnostic_active = False`. No side effect beyond that — resuming dispatch doesn't need an announcement, only the entry does (per the task: entering is the unsafe transition to guard, not leaving). Called from the checkbox's `toggled` handler when unchecked, and unconditionally from `closeEvent()`.
- **`closeEvent()` always calls `_exit_diagnostic()`**, regardless of the checkbox's state at that moment — closing the window is defined as "done observing," and normal processing must resume whether or not the user remembered to uncheck the box first. This is what satisfies "ensure normal MIDI processing resumes cleanly when diagnostic mode ends" unconditionally rather than depending on checkbox state.
- `WebSocketCommand("E-Stop")` reuses `WebSocketOutputAdapter.send()`'s existing fail-silent behavior verbatim (`docs/llds/websocket-output.md § Sending a Command`): if no connection is active, the send is logged and dropped — the Monitor does not add a new status indicator or retry logic for this, matching the HLD's existing silent-fail precedent for this output path.
- Diagnostic mode has no effect on Grid's own topology/MIDI connection, the Status UI indicators, or `MidiInputAdapter` — it only gates the three dispatch calls in `_process_midi_event`. Re-selecting a Controller Profile, Grid reconnecting, and Save/Load all behave exactly as before regardless of diagnostic mode's state.
- **The safety guarantee the task requires — pressing a physical control while identifying it must not move a motor — is carried entirely by the suppression itself, not by `E-Stop` landing successfully.** Any event recorded while `diagnostic_active` is true is, by construction, never handed to `process`/`process_keystroke`/`process_websocket`; that holds whether or not a WebSocket connection exists. `E-Stop` on entry is a second, independent, best-effort layer addressing a *different* gap — motion Dragonframe may already be executing from a message sent *before* diagnostic mode turned on — and its silent failure (no connection) does not weaken the first guarantee.

## Monitor Dialog Contents

- **Event table**: one row per `MonitorEvent`, oldest-first (or newest-first — an open question below), columns Time / Device / Type / Channel / Number / Value / Module / Resolved. `format_module`/`format_resolved` render `"-"` when the corresponding field is `None`, never inventing a label; `format_channel`/the Number column likewise render `"-"` for the `channel`/`number is None` cases a real `MidiEvent` can carry (pitch bend has no CC/note number; KORG Scene's SysEx-decoded event has no `number` either) — formatting never raises or prints Python's `None`.
- **Clear button**: calls `monitor.clear()`, which empties the ring buffer and resets `last_captured` to `None`. Does not touch `diagnostic_active` or `capture_pending` — clearing the visible log and a pending capture request are orthogonal; a capture already waiting stays armed through a Clear.
- **Capture Next Input button**: calls `monitor.request_capture_next()`, which sets `capture_pending = True`. Idempotent — pressing it again while already pending leaves the wait exactly as it was, no reset or double-arm. There is no timeout: if no physical control is moved, the dialog simply keeps showing "Waiting for next input…" until an event arrives or the user presses Clear. A label above the table shows that waiting text while `capture_pending` is true, then switches to the captured event's full formatted detail once `record()` observes `capture_pending` and flips it back to `False`, setting that `MonitorEvent.captured = True` and updating `last_captured`. The captured event is also visually marked (bold row) in the table — "isolates" via the dedicated label, "highlights" via the table row, satisfying both verbs in the task without choosing just one.
- **`refresh()`** compares `monitor.version` to the dialog's own last-rendered version; if unchanged, does nothing (no Qt work at all on an idle tick). If changed, rebuilds the table from `monitor.events` in one pass and updates the captured-event label. Called from `app.py`'s existing `_on_tick()` (30 ms), the same batching every other live-refreshed widget in this app already uses — multiple MIDI events arriving within one tick (a fast jog wheel) are coalesced into a single Qt update, not one per event, which is what keeps a high-frequency source from freezing the interface.
- **Diagnostic checkbox**: "Diagnostic mode (block Dragonframe output while open)", defaults checked on every open (see Diagnostic Mode, above).
- No Settings/host/port fields, no controller selection — this dialog has exactly the controls above, kept deliberately small per the task's "keep the UI compact" instruction.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Hook point | Tap `_process_midi_event`'s existing `route_event` call and dispatch gate | A second `MidiBackend.open_input()` dedicated to the monitor | Would either miss events the primary connection already claimed, or double-handle them; the existing single-connection, single-dispatch-point architecture already has exactly one place every event passes through |
| Diagnostic mode trigger | Defaults on at dialog open (every open), explicit checkbox to turn off while open, forced off at close | Separate persistent toggle independent of dialog lifecycle; or no checkbox, strictly tied to dialog open/close | Default-on matches the task's safety emphasis without losing the ability to watch normal round-trip dispatch while the window stays open; forcing off at close guarantees clean resumption regardless of checkbox state |
| Entry side effect | Unconditional `E-Stop` WebSocket command on every ON transition | No side effect; rely on suppression alone | Suppressing future messages cannot recall motion Dragonframe may already be executing from a message sent moments before the dialog opened |
| Raw vs. resolved identity | Both always captured; raw never discarded | Store only the resolved identity | Grid's `resolve_grid_event` overwrites `type`/`number` with the logical key, discarding the CC/note that validates the module; hardware validation needs the original wire value, not just the derived name |
| Device identity per event | Reuse `self._midi_device_name` (one connected device at a time) | Add a `source` field to `MidiEvent` itself | `MidiEvent` is a widely-shared type (`mapping.py`, tests); this app has no multi-instance/multi-device support to motivate widening it for a diagnostic-only need |
| Event storage | Bounded ring buffer (`deque(maxlen=capacity)`), default 500 | Unbounded list; or a fixed on-disk log | Task explicitly requires no unbounded growth under sustained high-frequency input; 500 is enough history for identifying a control's message without noticeable memory growth |
| Table refresh | Batched on the existing 30 ms UI tick, skipped entirely when unchanged (`version` check) | Append a table row synchronously inside `record()` | A jog wheel can emit far faster than 30 Hz; per-event Qt widget mutation from a background-thread-drained queue would be the freeze risk the task calls out, and an unconditional per-tick rebuild would waste cycles while idle |
| Capture Next Input semantics | One-shot flag; next recorded event is marked `captured` and shown in a dedicated label plus a highlighted table row | Filter the table to show only the captured event | Isolating-by-filtering would hide the surrounding event stream, which is often exactly what's needed to tell a genuine button press apart from incidental noise (e.g., a jog wheel's own CC flood) right before/after it |
| Module scope | Two new files (`midi_monitor.py`, `midi_monitor_widgets.py`), no changes to `mapping.py`, `control_descriptor.py`, or `inspector_registry.py` | Extend the Inspector Editor Registry with a "monitor" control type | The Monitor is global (one log for the whole device), not per-control; forcing it through the per-control Inspector dispatch would be a worse fit than a standalone dialog reachable from Settings, as the task specifies |

## Open Questions & Future Decisions

### Resolved

None yet — new LLD.

### Deferred

1. Table order (oldest-first vs. newest-first/auto-scroll) is a presentation detail left to implementation and can be adjusted without an EARS change, since no spec in this LLD commits to a direction.
2. Exporting the captured log to a file (for attaching to a roadmap update or an issue) is not requested by the task and is deferred.
3. A dedicated Status UI indicator for "diagnostic mode is currently on" (beyond the dialog's own checkbox, visible only while the dialog is open) is not requested; if diagnostic mode needs to be visible from the main window, this is the natural place to add it later.
4. Distinguishing *why* an event shows no Module/Resolved identity (Grid not active, controller stale, or a genuine address-table miss) is not surfaced — all three render identically as `"-"`. The task asks only that identification be shown "when the current discovery data provides it," not that failure reasons be diagnosed; revisit only if hardware validation work finds this ambiguity actually slows someone down.

## References

- `docs/high-level-design.md § Approach` (item 11) and `§ Key Design Decisions` — why this taps the existing dispatch point, defaults diagnostic mode on, and bounds the event log.
- `docs/llds/intech-grid.md § MIDI → Module/Element Resolution` — `resolve_grid_event`/`route_midi_event`, confirmed pure, reused here unmodified.
- `docs/llds/websocket-output.md § Sending a Command` — `E-Stop`'s existing fail-silent `send()` behavior, reused unmodified.
- `docs/llds/app-ui.md § Settings Dialog` — the existing thin-dialog precedent this Monitor's entry point is added to.
- `docs/roadmap.md § Hardware verification tasks` — the specific unconfirmed controls this tool exists to help identify.
