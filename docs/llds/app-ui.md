# Application Shell, Signal Monitor & Status UI

## Context and Design Philosophy

This is the glue-and-presentation layer: it starts the MIDI Input Adapter and OSC Transport, bridges their background-thread activity into Qt's main thread, tracks recency-based liveness for both channels, and renders the two-indicator status window described in the HLD. It deliberately owns nothing about MIDI/OSC protocol details or mapping semantics — those are `midi-input.md`, `osc-io.md`, and `static-mapping.md`'s territory.

**Module split:** to keep this layer testable without a running Qt application, its logic is split into plain-Python modules with no Qt dependency, plus a thin Qt shell that wires them to real widgets/timers:

- `dragonmidi/signal_monitor.py` — the Signal Monitor (below).
- `dragonmidi/status_presenter.py` — pure functions computing each indicator's display state (dot + label) from Signal Monitor reads and connection status; this is where the "single read per tick" and "dot/label independence" invariants live as testable code, not just prose.
- `dragonmidi/config.py` — the editable host/port fields' pending-vs-applied state and Apply/validation logic.
- `dragonmidi/queue_drain.py` — the generic full-drain-per-tick queue helper.
- `dragonmidi/shutdown.py` — the per-step-isolated, timeout-bounded shutdown sequence runner.
- `dragonmidi/mapping_view_model.py` — pure functions computing the Mapping View's table rows, axis-picker candidates, and min/max field validation from `MappingEngine` and `AxisDiscovery` state (below).
- `dragonmidi/status_widgets.py` — the `IndicatorRow` Qt widget (dot + label), the only Qt piece of the Signal Monitor's presentation.
- `dragonmidi/mapping_widgets.py` — the Mapping View's Qt widgets (`MappingView`, `_AxisTargetEditor`), wiring `mapping_view_model.py`'s pure functions to real combo boxes/table cells.
- `dragonmidi/app.py` — the thin Qt shell: `DragonMidiWindow` and `run()`. Constructs the real widgets, timers, and MIDI/OSC background threads, and wires them to the modules above. This and the two widget modules above are the only modules that require a Qt application to exercise; none of them carry independent logic beyond wiring.

## Signal Monitor

- Tracks one "last activity" timestamp per channel: `midi` (updated by any raw MIDI message, per `midi-input.md`'s liveness-before-normalization rule) and `dragonframe` (updated by any datagram reaching the OSC Listener, per `osc-io.md`).
- Each channel's `last_activity` is initialized to `None` ("never seen") at startup, distinct from any real timestamp — a channel with `last_activity is None` is always reported not-live, avoiding any false-positive "live" flash before the first real event arrives.
- Timestamps use a **monotonic clock** (`time.monotonic()`), not wall-clock time, so system sleep/wake or NTP corrections can never produce a negative or artificially huge elapsed time.
- A channel is considered **live** if `last_activity is not None and (now - last_activity) < LIVENESS_WINDOW` (strict less-than — the boundary itself counts as no-longer-live). Proposed default: `LIVENESS_WINDOW = 2.0` seconds — long enough that normal pauses between control moves don't flicker the indicator, short enough that "the controller was unplugged" or "Dragonframe was closed" shows up within a couple seconds.
- Both channels share the same window rather than independently-tuned windows, since the two failure modes (controller unplugged, Dragonframe closed) have similar detection-latency needs and a single constant is simpler to reason about.
- Each channel additionally carries an **error flag**, independent of the liveness timestamp: set for MIDI on a Native Mode handshake failure (`midi-input.md`), and for Dragonframe on a listener bind failure (`osc-io.md`). Combined with liveness, a channel's displayed state is one of three: **live** (recent activity), **error** (a real failure condition, regardless of activity), **quiet** (neither) — error takes precedence over quiet when both could apply. See Status UI below.
- This is the only place liveness and error-state are computed; MIDI-IN and OSC-IO only report raw timestamps and raw error flags.

## Threading and the Qt Bridge

- MIDI events arrive on `mido`'s callback thread; the OSC Listener runs its receive loop on its own thread. Neither may touch Qt widgets directly.
- Both push into thread-safe `queue.Queue` instances. A `QTimer` on the Qt main thread (proposed: 15–50ms interval, matching the prototype's proven polling cadence) drains each queue **completely** on every tick — no per-tick cap — updates the Signal Monitor's timestamps, and feeds normalized MIDI events into the Static Mapping Engine → OSC Client path. A single controller's traffic plus Dragonframe's own OSC output is far below any volume that would stall a 15–50ms tick; a cap is only worth adding if real-world testing shows otherwise.
- Each timer tick reads the Signal Monitor's state for both channels exactly once, and renders both the indicator dot and its label text from that single read — by construction, the dot and its label can never disagree about which tick's state they reflect.
- This queue-plus-poll pattern is reused deliberately from the prototype: it is a correct, already-proven way to avoid cross-thread Qt calls, independent of the prototype's tkinter-specific implementation.

## Status UI

```
+-----------------------------------------------------------------------+
|  DragonMIDI                                                            |
|                                                                         |
|  Controller: [nanoKONTROL Studio ▾]                                   |
|                                                                         |
|   ●  MIDI signal        nanoKONTROL Studio                             |
|   ●  Dragonframe signal  127.0.0.1:7011 (listen)                       |
|                                                                         |
|   Sending to: [127.0.0.1] [7010]   Listen port: [7011]   [Apply]      |
|                                                                         |
|   Mapping                                                              |
|  +---------------------------------------------------------------+   |
|  | Name       MIDI            Trigger      Target type   Target   |   |
|  |-------------------------------------------------------------- |   |
|  | Fader 1    CC0, ch16       Absolute     OSC axis ▾    [PAN ▾]  |   |
|  | Fader 2    CC1, ch16       Absolute     OSC encoder   Encoder 2|   |
|  |  ...        ...             ...          ...           ...     |   |
|  +---------------------------------------------------------------+   |
|  [Rescan axes]                                                        |
+-----------------------------------------------------------------------+
```

- **Controller Profile dropdown**, above the indicator rows: populated at startup from whichever profiles the Controller Profile Loader discovered (`docs/llds/midi-input.md § Controller Profile Loading`) — today that's two, "nanoKONTROL Studio" and "nanoKONTROL2," but the dropdown itself has no fixed count or hardcoded option list; it renders whatever list it's given. Defaults to the first bundled profile (nanoKONTROL Studio) on launch, preserving the existing zero-config experience for anyone who never touches it. Changing the selection applies immediately (no Apply step, unlike the host/port fields below) — it disconnects the currently-connected device (if any), resets the Mapping Engine to the newly-selected profile's opinionated default map, and starts polling for the new profile's name match. This is a heavier action than the host/port fields' Apply, so it's a plain dropdown rather than needing a confirm step: switching controllers is inherently a "start over with a different device" action, and there is no partially-applied state to protect against the way there is with in-progress host/port text.
- **Setup hint is per-profile, sourced from config, not hardcoded to one controller.** When the selected profile has a non-empty `setup_hint` (`docs/llds/midi-input.md § Controller Profiles`), a short helper line appears beneath the dropdown showing that text verbatim — today, only the bundled nanoKONTROL2 profile sets one ("Hold SET MARKER + CYCLE while powering on for CC mode"), a direct pointer to a one-time physical setup step DragonMIDI cannot detect or perform itself. A profile with no `setup_hint` (the Studio) shows no line at all. This generalizes what was previously a hardcoded `NANOKONTROL2_SETUP_HINT` constant in `app.py` shown only for a name equality check against "nanoKONTROL2" specifically — a check that would silently do nothing for any newly-added profile needing its own hint.
- **Config load-failure indicator, independent of the setup hint.** When the Controller Profile Loader (`docs/llds/midi-input.md § Controller Profile Loading`) reports one or more config files that failed to load, a second short line appears near the dropdown — count-only, e.g. "2 controller config files failed to load" — regardless of which profile is currently selected. Absent when the failure count is zero. This is deliberately not a log viewer or a list of per-file error messages (the HLD's "no log pane" Non-Goal stays intact): it tells a novice contributor *that* something didn't load, so they know to look further, without DragonMIDI growing a detail UI for it. It can appear at the same time as a `setup_hint` line, since the two are unrelated questions.
- Two indicator rows, each a **3-state** colored dot plus a short label: **green/lit** = live (recent activity), **amber/red** = error (Native Mode handshake failed for MIDI — Studio profile only, since the nanoKONTROL2 has no handshake to fail; listener bind failed for Dragonframe), **dim/gray** = quiet (neither — normal "waiting" state, not a failure). Error takes visual precedence over quiet.
- The MIDI row's secondary text names the connected device once found; before discovery it reads something like "Waiting for nanoKONTROL Studio…" or "Waiting for nanoKONTROL2…", matching whichever profile is currently selected. This text is driven by the MIDI Input Adapter's connection status (`midi-input.md`), **not** by the indicator dot's live/error/quiet state — the two are independent axes. **This means the dot and the label can validly disagree**: a physically connected nanoKONTROL Studio whose Native Mode handshake just failed shows the device's name *and* an amber error dot simultaneously. That combination is intended — it tells the user "your controller is plugged in, but something's wrong with it" — not a bug to be reconciled into one state. For the nanoKONTROL2 profile, the error dot never lights regardless of what the physical device is doing (no handshake exists to fail), so the dot/label pair is simpler there: live, or quiet with a name once found.
- The Dragonframe row's secondary text shows the local listen port; the "Sending to" fields show the configured Dragonframe host:port.
- Host, Dragonframe port, and listen port are lightly editable (small text fields) behind an explicit **Apply** action — edits do not take effect, and no rebind happens, until Apply is pressed. This matches the prototype's existing Apply-button pattern and avoids rebinding on invalid or partial in-progress text. Applying a Dragonframe port equal to the listen port is rejected per `osc-io.md`'s config-apply validation. Applying a changed local listen port triggers the OSC Listener to close its existing socket and rebind to the new port (`osc-io.md`'s rebind-on-config-change rule) — without this, editing the field would silently do nothing.
- These fields are machine-specific network configuration, distinct from the opinionated control mapping, which has its own surface below.
- No log pane, no menu bar (explicit non-goals carried from the HLD).

## Mapping View

Embedded directly in the main window, as a section below the host/port configuration form — one window, not a separate dialog. Scoped to this phase's capability only — assigning a fader to a discovered Dragonframe axis. The full editor implied by the HLD's mockup (Add/Edit/Duplicate/Remove, MIDI-learn, presets, arbitrary custom OSC paths) is Phase 2 and not built here.

**Reflects the active Controller Profile.** The table's rows are built from whichever profile is currently selected (`docs/llds/midi-input.md § Controller Profiles`), recomputed at the same time the engine's map is swapped on a profile switch (`docs/llds/app-ui.md`'s Status UI section above). For the nanoKONTROL2 profile, the "Jog Wheel" / "Jog Wheel (Arc)" rows described below simply don't appear — there is no control to represent — and the Scene-button row (mapped to `/dragonframe/black` in the Studio's map) is likewise absent. No placeholder or greyed-out row stands in for either; the row just isn't in the table, the same "doesn't exist as a row" treatment the HLD and `docs/llds/static-mapping.md` establish for the underlying map data.

```
+-----------------------------------------------------------------------+
| Name              MIDI       Trigger      Target type   Target        |
|-------------------------------------------------------------------------|
| Fader Channel 1   CC0, ch16  Absolute     OSC axis ▾    [PAN ▾] [0][100]|
| Fader Channel 2   CC1, ch16  Absolute     OSC axis ▾    [ ▾]            |
| Play              CC41, ch16 Press        OSC action    Play           |
| Solo 1-8          CC32-39,   Press        WebSocket      select-AX1 – select-AX8 (button N → AXN) |
|                   ch16                                                 |
|  ...               ...        ...          ...           ...           |
+-----------------------------------------------------------------------+
[Rescan axes]
```

- One row per `OPINIONATED_MAP` entry, in table order, **except** Knob/Mute entries: those are bank-derived (`docs/llds/static-mapping.md` § Bank Derivation) and folded into their bank's "Fader Channel N" row rather than shown as their own rows — their behavior doesn't change, only their display is no longer a separate table row. Only the 8 "Fader Channel N" rows are directly editable (`MAP-AXIS-004`) — the "Target type" and "Target" cells.
- **Solo 1–8 is one additional summary row, not folded into the fader rows and not eight separate rows.** Solo is no longer bank-derived (`docs/llds/static-mapping.md § WebSocket-Targeted Controls`, `MAP-WS-002`) — each Solo N unconditionally sends `select-AXN` regardless of any fader's axis assignment, so folding it into "Fader Channel N" would misrepresent it as still fader-dependent. But the mapping from button number to command is entirely mechanical (button N → `select-AXN`), so eight near-identical rows would repeat the same fact eight times for no added information — one row, MIDI source `CC32-39, ch16`, Target type `WebSocket`, Target `select-AX1 – select-AX8 (button N → AXN)`, covers it exactly once. Not editable.
- **The jog wheel appears as two additional rows, appended after the `OPINIONATED_MAP` rows**, since it isn't itself an `OPINIONATED_MAP` entry (its dispatch is special-cased in `MappingEngine.process()`/`process_keystroke()`, not a static table lookup — `docs/llds/static-mapping.md` § Jog Wheel Frame Stepping). Both rows share the same MIDI source (`CC110, ch16`) and `Trigger` label (`Directional`), since both describe the same physical control's same messages, just its two independent outputs:
  - **"Jog Wheel"** — Target type `OSC action`, Target `stepForward / stepBackward` (both addresses shown together, since which one fires depends on rotation direction, not a fixed choice like every other OSC-action row).
  - **"Jog Wheel (Arc)"** — Target type `Keystroke`, Target `Option+Shift+Right / Option+Shift+Left` (matching `docs/high-level-design.md § Problem`'s and `README.md`'s wording for the same combo).
  - Neither row is editable — no target-type toggle, no picker — matching every other non-fader row's read-only treatment.
- **Stop, Cycle, Previous Marker, and Next Marker each already get their own row** as ordinary (non-bank) `OPINIONATED_MAP`-shaped entries — no structural change needed for them, only their displayed Target type (`WebSocket`) and Target content (`E-Stop`; `select-AXn` cycling; `Jog All` backward/forward) change to reflect `docs/llds/static-mapping.md`'s WebSocket-Targeted Controls. None are editable, matching every other non-fader row.
- A fader row's "Target type" cell is a two-way toggle: **OSC axis** (the default, picker pre-selecting nothing) or **OSC encoder**. A fresh fader row already shows the axis picker and two numeric fields pre-filled with `0.0`/`100.0`, since axis is the starting state; switching to OSC encoder hides them and calls `MappingEngine.clear_axis_target(key)`, which is always safe to call even if no axis target was ever actually established for that key (`MAP-AXIS-007`).
- **The engine's live target can lag the row's displayed target type — including at startup.** A fresh fader shows "OSC axis" with no name picked and produces **no OSC output at all** until one is chosen; there is no fallback to the opinionated encoder target while unconfigured (`docs/llds/static-mapping.md` § Fader Axis Mode). This mirrors `MAP-AXIS-006`'s existing principle that the engine only ever acts on the last target it was actually given, never on UI intent alone.
- The axis-name picker lists exactly the names currently in `AxisDiscovery.axes` (`MAP-AXIS-003`) — never free-text. Its content depends on discovery state:
  - `axes is None` (never queried, or a query is outstanding): picker shows "Discovering…" and is disabled.
  - `axes == {}` (queried, zero axes — including the confirmed zero-axes-sends-nothing case, resolved via `OSC-DISCOVER-008`'s timeout): picker shows "No axes found" and is disabled.
  - `axes` non-empty: picker lists the names, sorted for stable display order.
  - This candidate list is recomputed every UI tick (same tick that drains the Signal Monitor and redraws the status indicators), not only when the Mapping View is opened or Rescan is pressed — a Rescan response or ordinary discovery arriving while the view is open updates the picker within one tick, with no reopen needed.
- **A row's picker always shows its currently configured axis name as the selected value**, even if that name has since dropped out of the live discovered list (device reconfigured, Dragonframe restarted with a different project) — it is not hidden or replaced by a placeholder. The rest of the list still reflects the current discovery state; the configured name is simply always present as the current selection, greyed to indicate it can't be re-picked once deselected if it's no longer a real candidate. The engine keeps sending to that name regardless (`MAP-AXIS-006`); the picker's job is to restrict *new* selections, not to babysit existing ones.
- Selecting a name, once both it and valid min/max values are present, calls `MappingEngine.set_axis_target(key, axis_name, min_value, max_value)` immediately — there is no separate "Save" step, matching the fader's live-tracking behavior everywhere else in the app. Min/max accept any real values including `min > max` or `min == max` (`MAP-AXIS-002`) — no field-level validation beyond "is a number." Text that fails to parse as a number is not applied — the row's last successfully-applied target (if any) is left in effect, with no error dialog.
- **Rescan axes** calls `OscListener.rescan()` directly; it does not reset any row's already-configured target, only what the picker offers going forward.
- The view has no persistence: like the status window's host/port fields, it reflects live in-memory `MappingEngine`/`AxisDiscovery` state and resets to the opinionated defaults on next launch — no preset file in this phase.

## Bootstrap and Shutdown

- Single entry point: start the MIDI discovery/poll loop, start the OSC Listener thread, construct the Qt application and main window, start the drain `QTimer`, enter the Qt event loop.
- On quit: release Native Mode if active, close MIDI input/output ports, stop the OSC Listener thread, close the UDP client socket — mirrors the prototype's `_on_close` cleanup sequence. Each step runs in its own try/except so one failing or hanging step (e.g. a bad port blocking Native Mode release) cannot prevent the others from running; the overall shutdown sequence is capped by a short timeout before the process force-exits.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Liveness computation location | Centralized Signal Monitor, single shared window | Per-channel independently tuned windows | Simplicity; both channels' expected quiet periods are similar enough for one constant in phase 1 |
| Thread bridge | `queue.Queue` + `QTimer` poll | Qt signals/slots emitted directly from worker threads | Reuses the prototype's already-proven pattern; avoids subtleties of emitting Qt signals from non-Qt threads |
| Settings persistence | *(open — see below)* | Persist host/ports across launches (prototype's `storage.py`) vs. always reset to defaults | Not yet decided; brushes against the "no config UI" non-goal even though it's arguably just network defaults, not mapping config |
| Indicator state model | 3-state (live / error / quiet) | 2-state (lit / dim) | A silently-failed listener bind or Native Mode handshake would otherwise look identical to ordinary "no traffic yet" — actively misleading for an app whose purpose is accurate status |
| `last_activity` initial value | `None` sentinel, distinct from any timestamp | Default to `now()` or epoch `0` | Avoids a false-positive "live" flash at boot (`now()`) and is more explicit than relying on a huge-elapsed-time side effect (`0`) |
| Clock source | `time.monotonic()` | Wall-clock `time.time()` | Immune to sleep/wake and NTP corrections by construction, fully resolving the clock-jump concern |
| Liveness boundary | Strict `<` (boundary itself is not-live) | Inclusive `<=` | Arbitrary but explicit; needed a pick, `<` was simpler to state as "not live" |
| Queue drain strategy | Full drain every tick, no cap | Bounded per-tick drain | Realistic traffic volume from one controller + Dragonframe is far below what would stall a 15–50ms tick; add a cap only if testing proves otherwise |
| Shutdown robustness | Per-step try/except + overall timeout | Single try/except around the whole sequence | One hanging/failing step (e.g. bad port during Native Mode release) must not block the rest of cleanup or hang app quit indefinitely |
| Live host/port edits | Explicit Apply action, no live-as-you-type rebind | Rebind immediately on every keystroke/change | Matches the prototype's existing pattern; avoids rebinding on invalid or partial text |
| Dot/label consistency | One Signal Monitor read per tick feeds both | Independent reads for dot and label | Guarantees by construction that the two can never show different ticks' state |
| Dot state vs. connection-status label | Two independent axes; may disagree (e.g. connected device name + error dot) | Fold connection status into the 3-state model as a 4th state | "Is a controller present" and "is it healthy" are independent questions; collapsing them loses the distinction between device-present-but-broken and no-device-at-all |
| Listen-port Apply behavior | Triggers listener socket close+rebind (`osc-io.md`) | Require app restart for listen-port changes | Apply already exists as the change mechanism; a field that visibly does nothing on Apply would be a worse experience than a working rebind |
| Mapping View scope | Fader target-type toggle only (OSC encoder ↔ OSC axis); other rows read-only | Full editor (Add/Edit/Duplicate/Remove, MIDI-learn, presets) in this phase | Matches `MAP-AXIS-004`'s fader-only restriction and the HLD's Phase 1/Phase 2 split; the full editor is explicitly Phase 2 |
| Jog wheel's dual-output display | Two separate rows ("Jog Wheel", "Jog Wheel (Arc)"), one per output | A new "Keystroke" column alongside the existing "Target type"/"Target" pair, shown blank for every other row | Keeps "exactly one target per row" true everywhere rather than introducing a second kind of row (single-vs-dual-target) or a column that's empty for every control but one; matches the existing pattern of one row per output already established by the Knob/Mute-folding decision (one row per *thing the user can confirm at a glance*, not one row per physical control) |
| "Keystroke" as a Target type value | Added as a fourth read-only Target type, alongside OSC action/encoder/axis | Give Keystroke its own separate concept outside the Target type/Target column pair | Reuses the existing column pair and its established "Target type describes the kind, Target describes the specifics" shape, rather than inventing a parallel display mechanism for one target kind |
| "WebSocket" as a Target type value | Added as a fifth read-only Target type, alongside OSC action/encoder/axis/Keystroke | Same alternative as "Keystroke," rejected for the same reason | Reuses the existing column pair rather than inventing a parallel display mechanism per output kind |
| Mapping View window placement | Embedded as a section of the single main window | Separate dialog opened on demand | One window is simpler for an always-on utility meant to be glanced at continuously, and keeps the mapping table visible without an extra open/close step |
| Knob/Mute row display | Not shown as separate rows at all — folded into their bank's Fader Channel row | Read-only rows recomputed every tick from the bank's fader state | The behavior already lives entirely in the fader's own assignment; a separate row per bank member added 16 rows of information the user never acts on independently |
| Solo row display | One summary row ("Solo 1-8"), covering all 8 buttons at once | Fold into the fader row (like Knob/Mute); or eight separate per-button rows | Solo is no longer fader-dependent, so folding it would misrepresent it as still bank-derived; but the button→command mapping is entirely mechanical (button N → `select-AXN`), so eight rows would repeat the same fact eight times for no added information a user could act on differently per row (none are editable) |
| Mapping View apply timing | Immediate — picker selection and min/max fields call `set_axis_target` on change, no Save step | Explicit Save/Cancel per row | Matches the rest of the app's live-tracking behavior (faders already stream continuously); a Save step would be the only delayed-apply control in the UI |
| Mapping View persistence | None — resets to opinionated defaults each launch | Persist fader axis assignments across launches | Consistent with host/port fields' current no-persistence state; a persisted mapping is a bigger step than this phase's scope |
| Stale axis reference in picker | Keep showing the configured name (greyed out), engine still sends to it | Auto-clear the row's target when its axis drops out of the discovered list | Matches `MAP-AXIS-006` — the engine already sends unconditionally; silently clearing the UI's record of user intent would contradict that |
| Engine target vs. displayed target type while mid-edit | Allowed to lag — revealing axis controls doesn't retarget until a name is picked | Force an immediate placeholder target the instant OSC axis is selected | The engine should only ever act on a target it was explicitly given; an auto-chosen placeholder axis name would be worse than briefly lagging the display |
| Default min/max on reveal | Pre-filled `0.0`/`100.0` | Start blank, require the user to fill both before anything applies | Lets picking just a name immediately produce a valid, immediately-applied target, consistent with the no-Save-step decision |
| Invalid min/max text | Not applied; last successfully-applied target stays in effect, no error dialog | Reject with a visible error state | Matches the app's general pattern of accepting rare input mistakes without new error-handling machinery |
| Picker's current-value display for a stale name | Always shown as the selected value, greyed if no longer a real candidate | Show a separate "current: X" label next to an otherwise-empty disabled picker | One widget, one source of truth for "what is this row actually configured to," rather than splitting it across two UI elements |
| Picker refresh cadence | Recomputed every UI tick, same tick as the status indicators | Only recomputed when the Mapping View is opened or Rescan is pressed | Consistent with the app's existing "single read per tick" pattern; avoids a picker that looks stale until manually reopened |
| Controller Profile selector | Plain dropdown, applies immediately on change | Explicit "Connect" button per profile (prototype's approach); Apply-gated like the host/port fields | Switching controllers is a "start over with a different device" action with no partially-applied state to protect against, unlike host/port text; immediate apply matches the Mapping View's own live-tracking precedent |
| Controller Profile default on launch | The first bundled profile (nanoKONTROL Studio) | Remember the last-selected profile; require an explicit choice before connecting | Preserves the existing zero-config experience for current users; matches "no persistence yet" pattern elsewhere in this LLD |
| Controller Profile dropdown population | Sourced from the Controller Profile Loader's discovered list at startup (`docs/llds/midi-input.md § Controller Profile Loading`) | Keep a fixed, hardcoded two-item option list | The dropdown must reflect however many profiles were actually discovered (bundled + user-local), not a compile-time constant — the entire point of pluggability |
| Setup guidance mechanism | Per-profile `setup_hint` config field, shown when non-empty for the selected profile | Hardcoded hint text keyed to one profile's name (`app.py`'s prior `NANOKONTROL2_SETUP_HINT`) | A name-keyed hardcoded hint silently shows nothing for any newly-added profile that needs its own setup guidance — must be config-driven for pluggability to make sense |
| Config load-failure surfacing | Minimal count-only Status UI line (e.g. "2 controller config files failed to load"), in addition to a logged warning | Log-only, no UI signal; a full log pane or per-error detail list | User's explicit choice (2026-07-22) — matches the novice-authoring goal without reopening the "no log pane" Non-Goal; a bare count is not a log viewer |
| Mapping View rows for absent controls (jog wheel, Scene) | Not shown at all when the active profile lacks the control | Shown greyed-out/disabled as a placeholder | Matches the "doesn't exist as a row" treatment already established for the underlying map data (`docs/llds/static-mapping.md`); a disabled placeholder row would misleadingly suggest the control could be enabled |

## Open Questions & Future Decisions

### Resolved
1. Indicator state model (3-state), `last_activity` initialization, clock source, liveness boundary, queue drain strategy, shutdown robustness, live host/port edit behavior, and dot/label consistency — see Decisions & Alternatives above.
2. Native Mode handshake failure (`midi-input.md`) and listener bind failure (`osc-io.md`) both surface via the shared 3-state indicator's *error* state, as one design rather than two separate mechanisms.
3. Connection-status label and indicator dot are independent axes that may validly disagree; Apply-triggered listener rebind on listen-port change — see Decisions & Alternatives above.
4. Mapping View scope, apply timing, persistence, and stale-axis-reference handling — see Decisions & Alternatives above.
5. Phase 4 edge audit: engine-target-vs-displayed-type lag while mid-edit, default min/max on reveal, invalid min/max text handling, the picker's stale-name current-value display, and picker refresh cadence — see Decisions & Alternatives above.
6. Knob/Mute entries are folded into their bank's Fader Channel row rather than shown as their own rows; Solo gets one summary row ("Solo 1-8") instead, since it's no longer bank-derived — see Decisions & Alternatives above.
7. The jog wheel's two outputs are shown as two separate, read-only rows ("Jog Wheel", "Jog Wheel (Arc)") rather than a new column, and "Keystroke"/"WebSocket" are read-only Target type values alongside OSC action/encoder/axis — see Decisions & Alternatives above.
8. **Controller Profile dropdown:** immediate-apply (no Apply step), defaults to the first bundled profile on launch, triggers a disconnect + Mapping Engine reset on change. Mapping View rows for controls the active profile lacks (jog wheel, Scene button) are omitted entirely rather than shown disabled — see Decisions & Alternatives above.
9. **Pluggable Controller Profiles (Phase 5):** the dropdown populates from the Controller Profile Loader's discovered list (`docs/llds/midi-input.md § Controller Profile Loading`), not a fixed two-item constant; per-profile setup guidance is a config-sourced `setup_hint` field, generalizing what was previously a hardcoded nanoKONTROL2-specific hint; a config load-failure count is shown as its own line, independent of `setup_hint`, without becoming a log viewer — see Decisions & Alternatives above.

### Deferred
1. Should the Dragonframe host, Dragonframe port, and local listen port persist across app launches (like the prototype's JSON state file), or always reset to their defaults? A minimal persisted-settings file is small in scope but is the first piece of "state the app remembers," which is adjacent to the deferred configuration phase.
2. Phase 2's full Mapping View (Add/Edit/Duplicate/Remove, MIDI-learn, presets, arbitrary custom OSC paths) is out of scope for this section entirely — see the HLD's Phase 2 description. Knob/Mute are now bank-derived (see above), but remain non-independently-configurable; independently retargeting them is still Phase 2.
3. Exact `LIVENESS_WINDOW` value (proposed 2.0s) is a tunable constant pending real hardware testing, not a hard requirement yet.
4. Whether the Controller Profile selection should persist across app launches — same open question as host/port persistence above, not yet decided (also noted in `docs/llds/midi-input.md`).

## References

- Prior prototype — source of the queue-plus-poll threading pattern and the shutdown sequence this LLD adapts (structure only, not the mapping-editor UI built around it).
- `docs/llds/static-mapping.md § Jog Wheel Frame Stepping` and `§ Keystroke Output (Arc Motion Control)` — the two independent outputs the jog wheel's two rows display.
- `docs/llds/keystroke-output.md` — the `KeyCombo` shape the "Jog Wheel (Arc)" row's Target text is derived from.
- `docs/llds/static-mapping.md § WebSocket-Targeted Controls` — the Stop/Cycle/Solo/Marker bindings the "WebSocket" Target type and the "Solo 1-8" summary row display.
- `docs/llds/websocket-output.md` — the `WebSocketCommand` shape the WebSocket-targeted rows' Target text is derived from.
- `docs/llds/midi-input.md § Controller Profiles` — the `ControllerProfile` shape and profile-switch behavior (disconnect + re-poll + Mapping Engine reset) this LLD's dropdown drives.
- `docs/llds/midi-input.md § Controller Profile Loading` — the bundled + user-local discovery this LLD's dropdown population and `setup_hint` display now depend on.
