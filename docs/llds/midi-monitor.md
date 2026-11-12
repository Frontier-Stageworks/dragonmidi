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
    on_record: Callable[[MonitorEvent], None] | None  # set by a running
                                # Guided Capture session; None otherwise

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
# capture_session.py - Qt-free (added for Guided Capture, below)

@dataclass(frozen=True)
class CaptureStep:
    label: str  # e.g. "Record 3", or "Set Marker" for a global control

@dataclass(frozen=True)
class CaptureResult:
    label: str
    skipped: bool
    raw: MidiEvent | None       # None iff skipped
    device_name: str | None

def build_capture_steps(controller: ActiveController) -> list[CaptureStep]: ...
    # Reads getattr(controller, "unconfirmed_channel_controls", ()) x bank_count,
    # then getattr(controller, "unconfirmed_global_controls", ()) x1. Empty list
    # for a controller with neither attribute (e.g. Intech Grid today).

class GuidedCaptureSession:
    def __init__(self, profile_name: str, steps: Sequence[CaptureStep]) -> None: ...
    @property
    def current_step(self) -> CaptureStep | None: ...   # None once finished
    @property
    def pending(self) -> MonitorEvent | None: ...        # this step's not-yet-confirmed candidate
    @property
    def results(self) -> Sequence[CaptureResult]: ...     # confirmed/skipped so far, in step order
    @property
    def finished(self) -> bool: ...
    @property
    def total_steps(self) -> int: ...  # len(steps) - display convenience for "Step N of M"

    def offer(self, entry: MonitorEvent) -> None: ...  # sets/replaces `pending` for the current step
    def confirm(self) -> None: ...                     # locks in `pending` (or a skip if none), advances
    def skip(self) -> None: ...                        # records a skip regardless of `pending`, advances

def save_capture_session(directory: Path, profile_name: str, results: Sequence[CaptureResult]) -> Path: ...
    # Writes directory / f"{profile_name}-{timestamp}.json"; creates directory
    # if needed. Returns the path written, for the dialog to display.

@dataclass(frozen=True)
class VerifyStep:
    label: str
    expected_key: _Key          # a descriptor's own key - "cc" tuple for a
                                 # static profile, logical key for Grid

@dataclass(frozen=True)
class VerifyResult:
    label: str
    expected_key: _Key
    actual_key: _Key
    passed: bool
    raw: MidiEvent
    device_name: str | None

def build_verify_steps(descriptors: Sequence[ControlDescriptor]) -> list[VerifyStep]: ...
    # One step per descriptor, in that list's own order - no separate model.

def actual_key(entry: MonitorEvent) -> _Key: ...
    # entry.resolved if not None, else (entry.raw.type, entry.raw.number).

class GuidedVerifySession:
    def __init__(self, profile_name: str, steps: Sequence[VerifyStep]) -> None: ...
    @property
    def current_step(self) -> VerifyStep | None: ...   # None once finished
    @property
    def pending(self) -> MonitorEvent | None: ...
    @property
    def pending_passed(self) -> bool | None: ...  # None while nothing pending
    @property
    def results(self) -> Sequence[VerifyResult]: ...
    @property
    def finished(self) -> bool: ...
    @property
    def total_steps(self) -> int: ...

    def offer(self, entry: MonitorEvent) -> None: ...  # replaces `pending`
    def advance(self) -> None: ...  # locks in pending (pass or fail per
                                     # pending_passed), advances
    def retry(self) -> None: ...    # discards pending, no result, same step

def save_verify_session(directory: Path, profile_name: str, results: Sequence[VerifyResult]) -> Path: ...
    # Writes directory / f"{profile_name}-verify-{timestamp}.json".
```

```python
# midi_monitor_widgets.py - Qt

class MidiMonitorDialog(QDialog):
    def __init__(
        self,
        monitor: MidiMonitor,
        on_enter_diagnostic: Callable[[], None],
        get_mapping_engine: Callable[[], MappingEngine],
        capture_sessions_dir: Path,
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

## Guided Capture Session

A second, optional mode within the same dialog — not a new top-level window — for systematically working through a controller's currently-unconfirmed controls instead of using Capture Next Input freehand for each one. Inherits diagnostic mode's suppression for free: a session can only be running while the dialog is open, and the dialog forces diagnostic mode on at open (Diagnostic Mode, above), so actuating a Record/Select/fader during a session is exactly as safe as any other probing in this dialog.

- **Steps come from the active controller's own declared gaps, not a hardcoded list.** `build_capture_steps()` reads `unconfirmed_channel_controls` (expanded ×`bank_count` — `"Record 1"`..`"Record {bank_count}"`, then the next label, in declared order) and `unconfirmed_global_controls` (one step each) off `self._get_active_controller()` (a thin wrapper over the dialog's own `get_mapping_engine().profile`) *at the moment Start is clicked* — not cached from dialog construction, so switching the Controller Profile dropdown before starting a session targets the newly selected controller's own gaps. Both attributes are read via `getattr(..., ())`, matching `setup_hint`'s existing duck-typed, Protocol-absent precedent (`docs/llds/app-ui.md`) — a controller with neither (Intech Grid today) simply produces zero steps, and Start is disabled with an explanatory label rather than opening an empty session.
- **"Start Guided Capture" is disabled when there are zero steps**, with a label explaining why ("No unconfirmed controls for this profile") rather than a silently-empty session.
- **Feeding is push-based, via `MidiMonitor.on_record` - a single optional callback, not a cursor into `events`.** A numeric index into `monitor.events` would break once the ring buffer evicts older entries (every index shifts), so starting a session instead sets `monitor.on_record = session.offer`; `record()` invokes it (if set) with the just-built `MonitorEvent`, synchronously, right after appending it — before `record()` returns. This also means an event recorded a moment before Start (already visible in the ongoing log above) is never fed to the session, since the hook wasn't registered yet. Ending a session (Cancel or Save) sets `monitor.on_record = None`.
- **`offer()` always replaces the current step's `pending` candidate, never accumulates one.** Pressing the wrong control, then the right one, before confirming simply means the right one is what's pending when Confirm is clicked — no separate "undo" is needed for a same-step mis-press.
- **Confirm locks in whatever is currently `pending`** (as a non-skipped `CaptureResult` carrying that event's raw identity and device name) **and advances to the next step; Skip does the same but always records a skip**, even if something is already pending for the current step (the user explicitly chose not to use it). Both are only meaningful while `current_step is not None`; the dialog disables both controls once `finished`.
- **The Confirm button is enabled only while `pending is not None`** for the current step — matches the chosen "capture, then require a confirm click" behavior: an event must actually arrive before advancing is allowed, so the prompt can't be silently skipped by a stray click. Skip has no such gate, by design — it's the explicit "I can't test this one" escape.
- **The current prompt's pending candidate is rendered the same way `last_captured` already is** (`format_event_type`/`format_channel`/`format_number`), so a user sees exactly what was captured before committing to Confirm.
- **Finishing (all steps consumed) shows a summary count** ("16 captured, 2 skipped") and reveals a **Save Session** button; **Cancel** is available at any point before Save and discards the in-memory session with no file written — there is no partial/auto-save.
- **`save_capture_session()` writes one JSON file per completed session**, to `~/Documents/DragonMIDI/capture_sessions/{profile_name}-{timestamp}.json` (the same `~/Documents/DragonMIDI/` root, sibling-folder convention `configurations/`/`named_controllers/`/`controllers/` already use; `profile_name` used as-is in the filename, unsanitized, matching `preset_store.py`'s existing `f"{profile_name}.json"` precedent — spaces are not a filesystem problem on macOS/Windows and this codebase has never bothered escaping them). After saving, the dialog shows the written path so the user (or a later session) can find it.
- **The written report is read-only evidence — nothing in this codebase reads a capture-session file back in.** No code path loads one into a `ControllerProfile`, the Mapping Engine, or any other persisted state; turning a capture session's findings into an actual controller-definition change is a separate, later, human-reviewed change to `dragonmidi/controllers/*.yaml` and `docs/llds/static-mapping.md` — exactly the boundary `docs/high-level-design.md § Key Design Decisions`' "Guided Capture produces a report, never an assignment" bullet states.
- **A session is entirely in-memory until Save; closing the dialog (or the main window) mid-session discards it with no prompt.** No "unsaved guided-capture session" warning is added — this mirrors Capture Next Input's own no-persistence-until-explicit-action behavior one level up, and keeps this feature from growing a second kind of "unsaved changes" concept alongside the existing builtin/dirty tracking (`docs/llds/app-ui.md § Save/Save As/Load UI`), which is about mapping configurations, not diagnostic sessions.
- **The diagnostic checkbox is disabled (forced on, un-clickable) for the duration of a running session.** Today's Guided Capture scope (unconfirmed controls only) happens to be safe either way - those controls are, by definition, absent from `opinionated_map`/bank derivation (`MAP-BANK-006`'s own regression test), so no output path fires for them regardless of the checkbox. This is a forward guard, not a reaction to a live bug: Guided Verify (below) is the concrete case this guard anticipated - its step list genuinely does include confirmed, mapped controls, and this exact mechanism (reused unchanged) is what keeps that from reopening the motion risk this whole dialog exists to prevent. Re-enabled the instant the session ends (Cancel or Save), left checked either way - never force-unchecked.
- **Switching the Controller Profile dropdown mid-session is not a case this LLD needs to handle: it's structurally impossible.** The dropdown lives in the main window, which is blocked by `MidiMonitorDialog`'s own modality for as long as it's open (the same modal-stacking behavior every other dialog in this app already has) - a session can only run while the dialog is open, so the controller a session was built against cannot change out from under it.

## Guided Verify Session

A third mode in the same dialog, added once Guided Capture proved the pattern works: instead of discovering an unknown identity, Guided Verify checks a real move against an identity the running model already claims to know — "press this, and I'll tell you immediately whether what arrived is what I expected." Shares the dialog's diagnostic-mode machinery with Guided Capture (forced on at Start, checkbox disabled for the session's duration) and is mutually exclusive with it — only one guided session, of either kind, runs at a time.

- **Steps are the real Controller View control list, not a separate "known controls" model.** `build_verify_steps()` takes the exact `ControlDescriptor` list `build_control_descriptors(build_fader_rows(engine), build_configuration_rows(engine), engine.profile)` already produces (the same call `ControllerView`/`control_grouping.py` make) and turns each descriptor directly into a `VerifyStep(label, expected_key=descriptor.key)`. This is why Guided Verify needs `get_mapping_engine()`, not just `get_active_controller()` as Guided Capture does — building the real descriptor list needs a real `MappingEngine`, not just its `profile`.
- **An offered event's "actual identity" is its resolved logical key when one exists, otherwise its own raw `(type, number)`** (`actual_key()` in `capture_session.py`) — one formula that is correct for both controller families without a branch: a Korg profile's controls are declared *by* raw CC (no resolution layer exists, `resolved` is always `None`), so the raw fallback already *is* that profile's real identity; a Grid control's `expected_key` is itself a logical key (`("grid_fader", 3)`, never a raw CC — Grid resolution happens before the Mapping Engine ever sees an event), so comparing against `resolved` is the only way to verify it correctly regardless of the chain's current physical arrangement.
- **A match auto-passes and auto-advances with no click** — `_update_verify_ui()` checks `session.pending_passed` on every `refresh()` tick (the same version-gated cadence as everything else in this dialog) and, while it's `True`, logs the result and calls `session.advance()` immediately. This is the one deliberate behavioral difference from Guided Capture's explicit-confirm default: verifying an already-expected value has no "wrong control, try again before locking it in" risk the way discovering an *unknown* one does, so there is nothing to protect by making the user click.
- **A mismatch never auto-advances.** `pending_passed is False` stops the loop, shows "expected X, got Y," and enables exactly two controls: **Retry** (discard the pending candidate, same step, same expected identity — the escape for "I pressed the wrong thing") and **Next** (record the mismatch as a failure anyway and move on — the escape for "I see the problem, I'll deal with it later, let me keep going"). Both are real, logged outcomes; Retry produces no result at all (as if nothing had been offered), Next produces a `passed=False` `VerifyResult`.
- **Finishing shows a pass/fail count and reveals Save Report**, writing `~/Documents/DragonMIDI/capture_sessions/{profile_name}-verify-{timestamp}.json` — the `-verify-` infix (`save_verify_session()`) keeps a verify report from colliding with, or being confused for, a Guided Capture report sharing the same folder and profile name. Same read-only-evidence property as Guided Capture: nothing reads this file back in; a confirmed mismatch is a signal for a human to go investigate (the model is wrong, the hardware is wrong, or the topology changed), not something this dialog acts on.
- **Mutual exclusion is enforced in both `_update_guided_ui()` and `_update_verify_ui()`, not by a single shared "session" slot.** The two session classes (`GuidedCaptureSession`/`GuidedVerifySession`) differ enough (confirm/skip vs. pass/fail/retry) to stay separate attributes (`_guided_session`/`_verify_session`); each Start button checks the *other* attribute and disables itself with an explanatory status line ("Guided Capture is running.") when it's set, rather than the dialog tracking one generic "a session is active" boolean that would need to remember which kind.

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
| Guided Capture scope | Only the active controller's currently-unconfirmed controls (`unconfirmed_channel_controls`/`unconfirmed_global_controls`) | Every control on the active controller, confirmed or not | User's explicit choice - narrower and faster for the immediate hardware-validation need; walking already-confirmed controls too is deferred below, not ruled out |
| Guided Capture advance | Capture, then an explicit "Confirm & Next" click | Auto-advance the instant any event is recorded for the current step | User's explicit choice - a redo window (press the wrong control, then the right one, before confirming) outweighs the extra click per step |
| Guided Capture save location | Fixed app folder, auto-named (`~/Documents/DragonMIDI/capture_sessions/{profile}-{timestamp}.json`) | A `QFileDialog` save prompt each time | User's explicit choice - matches the existing Preset Store/Named Controller/Controller Profile convention of one fixed, predictable folder per concern, no dialog friction |
| Guided Capture's write surface | Produces a JSON report only; no write path into `MappingEngine`, the Preset Store, or a Controller Profile config file | Auto-populate `unconfirmed_channel_controls`'s real CC/note into the YAML directly once captured | The explicit boundary that keeps this from being the MIDI Learn/automatic-assignment feature the task's own Non-Goals exclude - identification and assignment stay separate, human-reviewed steps |
| Session persistence on close | None - discarded with no prompt if the dialog closes before Save | Warn before discarding, like the builtin/dirty mapping-configuration tracking | Keeps this a second, independent "unsaved state" concept out of a feature whose own existing precedent (Capture Next Input) already has no persistence until an explicit action |
| Feeding events to a running session | Push-based `MidiMonitor.on_record` callback, invoked synchronously inside `record()` | A numeric cursor/index into `monitor.events` | A ring-buffer index breaks the moment eviction shifts every index; found during this LLD's own edge-case probe before implementation, not after a bug report |
| Diagnostic checkbox during a session | Disabled (forced on) for the session's duration | Leave it clickable, same as outside a session | Today's unconfirmed-only scope happens to be safe unchecked too (those controls are unmapped by construction), but this is a forward guard against a future scope widening to mapped controls reopening real motion risk |
| Guided Verify's step source | The real `ControlDescriptor` list (`build_control_descriptors()`) | A separate "known controls" list maintained for Verify specifically | Zero new data model; the Controller View's own existing list already *is* "every control the running model knows about with its real expected key" - building a second one risks the two drifting apart |
| Guided Verify advance (pass case) | Auto-advance instantly, no click | Require an explicit confirm, like Guided Capture | Verifying an *already-expected* value has no "which control did I actually just press" ambiguity the way discovering an unknown one does - nothing is protected by a click, and the user explicitly asked for "quickly and automatically" |
| Guided Verify advance (fail case) | Never auto-advances; Retry/Next are both explicit, logged actions | Auto-advance regardless, log the mismatch silently | A mismatch is exactly the signal this tool exists to surface - silently sailing past it would defeat the purpose |
| Guided Verify's "actual identity" formula | One function (`actual_key()`): resolved key if present, else raw `(type, number)` | A per-controller-family branch (Grid vs. static) | The same fallback already matches both cases without conditionals - a static profile's `resolved` is always `None` by construction, so the raw fallback already *is* that profile's real identity |
| Guided Verify vs. Guided Capture scope widening | A third, separate mode and session class, not an extension of Guided Capture's own scope | Add a "verify known controls too" toggle to Guided Capture itself | Confirm-vs-pass/fail and explicit-vs-auto-advance are different enough interaction models that one session class covering both would need a mode flag threaded through most of its methods; two small classes stayed simpler |
| Mutual exclusion mechanism | Each session type's own Start button checks the *other* type's attribute | One shared "a session is active" flag plus a separate "which kind" enum | Two attributes (`_guided_session`/`_verify_session`), each `None` or not, already encode exactly this with no additional state to keep in sync |

## Open Questions & Future Decisions

### Resolved

1. Guided Capture's scope (unconfirmed-only), advance behavior (explicit confirm), and save location (fixed app folder) were resolved directly by the user before this section was drafted - see the Decisions & Alternatives rows above for the rationale each carries.
2. Guided Verify was added directly in response to the user asking for something that "lets me make a move and it validates against the actual value... quickly and automatically" - its auto-pass/auto-advance behavior, its reuse of the real Controller Descriptor list as the step source, and its mutual exclusion with Guided Capture are all captured in the Decisions & Alternatives rows above.

### Deferred

1. Table order (oldest-first vs. newest-first/auto-scroll) is a presentation detail left to implementation and can be adjusted without an EARS change, since no spec in this LLD commits to a direction.
2. Exporting the *ongoing event log* (as opposed to a completed Guided Capture/Verify session) to a file remains deferred — the two sessions' own save actions cover the specific, requested "save the test" need; a general "export whatever's currently in the table" action is a different, broader feature not asked for here.
3. A dedicated Status UI indicator for "diagnostic mode is currently on" (beyond the dialog's own checkbox, visible only while the dialog is open) is not requested; if diagnostic mode needs to be visible from the main window, this is the natural place to add it later.
4. Distinguishing *why* an event shows no Module/Resolved identity (Grid not active, controller stale, or a genuine address-table miss) is not surfaced — all three render identically as `"-"`. The task asks only that identification be shown "when the current discovery data provides it," not that failure reasons be diagnosed; revisit only if hardware validation work finds this ambiguity actually slows someone down.
5. **Resolved by Guided Verify** — Guided Capture itself still walks only the currently-unconfirmed controls (user's explicit choice, unchanged); walking *every* control for cross-checking against the model is now Guided Verify's distinct purpose, not a widening of Capture's own scope.
6. Reordering or re-visiting an already-confirmed/skipped (or passed/failed) step within a session (without restarting it) is not supported by either session class — both only ever advance forward; Cancel-and-restart is the only way to redo an earlier step once a later one has been resolved.
7. Nothing reads a saved capture or verify session JSON file back into the app (no "resume a session," no "load evidence into the Controller Profile editor") — see each session's own "read-only evidence" property above. Turning a session's findings into a real controller-definition change, or acting on a confirmed Guided Verify mismatch, stays a separate, later, human-driven edit.
8. Guided Verify's log (`_verify_log`) is an in-memory, unbounded-for-the-session `QPlainTextEdit` - fine for a session scoped to one controller's control count (tens, not thousands, of steps), but not designed for anything larger; revisit only if that assumption stops holding.

## References

- `docs/high-level-design.md § Approach` (item 11) and `§ Key Design Decisions` — why this taps the existing dispatch point, defaults diagnostic mode on, and bounds the event log.
- `docs/llds/intech-grid.md § MIDI → Module/Element Resolution` — `resolve_grid_event`/`route_midi_event`, confirmed pure, reused here unmodified.
- `docs/llds/websocket-output.md § Sending a Command` — `E-Stop`'s existing fail-silent `send()` behavior, reused unmodified.
- `docs/llds/app-ui.md § Settings Dialog` — the existing thin-dialog precedent this Monitor's entry point is added to.
- `docs/roadmap.md § Hardware verification tasks` — the specific unconfirmed controls this tool exists to help identify.
- `docs/llds/app-ui.md § Settings Dialog` — `setup_hint`'s existing `getattr(..., None)` duck-typed precedent, mirrored by Guided Capture's `unconfirmed_channel_controls`/`unconfirmed_global_controls` reads.
- `dragonmidi/controllers/nanokontrol-studio.yaml`, `dragonmidi/controllers/nanokontrol2.yaml` — the `unconfirmed_channel_controls`/`unconfirmed_global_controls` declarations Guided Capture reads at runtime.
