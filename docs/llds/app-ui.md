# Application Shell, Signal Monitor & Status UI

## Context and Design Philosophy

This is the glue-and-presentation layer: it starts the MIDI Input Adapter and OSC Transport, bridges their background-thread activity into Qt's main thread, tracks recency-based liveness for both channels, and renders the two-indicator status window described in the HLD. It deliberately owns nothing about MIDI/OSC protocol details or mapping semantics — those are `midi-input.md`, `osc-io.md`, and `static-mapping.md`'s territory.

**Module split:** to keep this layer testable without a running Qt application, its logic is split into plain-Python modules with no Qt dependency, plus a thin Qt shell that wires them to real widgets/timers:

- `dragonmidi/signal_monitor.py` — the Signal Monitor (below).
- `dragonmidi/status_presenter.py` — pure functions computing each indicator's display state (dot + label) from Signal Monitor reads and connection status; this is where the "single read per tick" and "dot/label independence" invariants live as testable code, not just prose.
- `dragonmidi/config.py` — the editable host/port fields' pending-vs-applied state and Apply/validation logic.
- `dragonmidi/queue_drain.py` — the generic full-drain-per-tick queue helper.
- `dragonmidi/shutdown.py` — the per-step-isolated, timeout-bounded shutdown sequence runner.
- `dragonmidi/app.py` — the thin Qt shell: real widgets, a real `QTimer`, and the real MIDI/OSC background threads, wired to the modules above. This is the only module that requires a Qt application to exercise, and it is expected to carry little independent logic of its own.

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
+-----------------------------------------------+
|  DragonMIDI                                    |
|                                                 |
|   ●  MIDI signal        nanoKONTROL Studio      |
|   ●  Dragonframe signal  127.0.0.1:7011 (listen)|
|                                                 |
|   Sending to: [127.0.0.1] [7010]   [Apply]     |
+-----------------------------------------------+
```

- Two indicator rows, each a **3-state** colored dot plus a short label: **green/lit** = live (recent activity), **amber/red** = error (Native Mode handshake failed for MIDI; listener bind failed for Dragonframe), **dim/gray** = quiet (neither — normal "waiting" state, not a failure). Error takes visual precedence over quiet.
- The MIDI row's secondary text names the connected device once found; before discovery it reads something like "Waiting for nanoKONTROL Studio…". This text is driven by the MIDI Input Adapter's connection status (`midi-input.md`), **not** by the indicator dot's live/error/quiet state — the two are independent axes. **This means the dot and the label can validly disagree**: a physically connected nanoKONTROL Studio whose Native Mode handshake just failed shows the device's name *and* an amber error dot simultaneously. That combination is intended — it tells the user "your controller is plugged in, but something's wrong with it" — not a bug to be reconciled into one state.
- The Dragonframe row's secondary text shows the local listen port; the "Sending to" fields show the configured Dragonframe host:port.
- Host, Dragonframe port, and listen port are lightly editable (small text fields) behind an explicit **Apply** action — edits do not take effect, and no rebind happens, until Apply is pressed. This matches the prototype's existing Apply-button pattern and avoids rebinding on invalid or partial in-progress text. Applying a Dragonframe port equal to the listen port is rejected per `osc-io.md`'s config-apply validation. Applying a changed local listen port triggers the OSC Listener to close its existing socket and rebind to the new port (`osc-io.md`'s rebind-on-config-change rule) — without this, editing the field would silently do nothing.
- These fields are machine-specific network configuration, not the opinionated control mapping, which has no UI surface at all in this phase.
- No log pane, no mapping table, no menu bar (explicit non-goals carried from the HLD).

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

## Open Questions & Future Decisions

### Resolved
1. Indicator state model (3-state), `last_activity` initialization, clock source, liveness boundary, queue drain strategy, shutdown robustness, live host/port edit behavior, and dot/label consistency — see Decisions & Alternatives above.
2. Native Mode handshake failure (`midi-input.md`) and listener bind failure (`osc-io.md`) both surface via the shared 3-state indicator's *error* state, as one design rather than two separate mechanisms.
3. Connection-status label and indicator dot are independent axes that may validly disagree; Apply-triggered listener rebind on listen-port change — see Decisions & Alternatives above.

### Deferred
1. Should the Dragonframe host, Dragonframe port, and local listen port persist across app launches (like the prototype's JSON state file), or always reset to their defaults? A minimal persisted-settings file is small in scope but is the first piece of "state the app remembers," which is adjacent to the deferred configuration phase.
2. Exact `LIVENESS_WINDOW` value (proposed 2.0s) is a tunable constant pending real hardware testing, not a hard requirement yet.

## References

- `~/github/DragonMIDI-vibed/dragonmidi/app.py` — source of the proven queue-plus-poll threading pattern and the shutdown sequence this LLD adapts (structure only, not the mapping-editor UI built around it).
