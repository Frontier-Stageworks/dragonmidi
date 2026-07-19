# High-Level Design: DragonMIDI

## Problem

Dragonframe (stop-motion capture software) accepts live axis input over OSC, but a MIDI control surface like the KORG nanoKONTROL Studio has no direct way to speak OSC. A prior prototype (`DragonMIDI-vibed`) proved the bridge is possible and captured real protocol knowledge — the nanoKONTROL Studio's Native Mode SysEx handshake, Dragonframe's OSC address space — but its architecture grew unconstrained and isn't a foundation worth building on directly.

Dragonframe's OSC surface includes direct axis-name addressing (`gotoPosition`/`stepPosition`), but DragonMIDI's current mapping only reaches axes indirectly through numbered "OSC encoder channels," which the user must separately wire to an axis inside Dragonframe. A virtual-gamepad approach to real-time jogging was investigated (see `docs/dragonframe-gamepad-research.md`) and found blocked by Apple's DriverKit entitlement requirement, confirmed empirically. The chosen path instead extends the OSC connection already built: discover axis names via `getAllPosition` and address them directly.

DragonMIDI is a clean rebuild: a MIDI-to-OSC bridge for the nanoKONTROL Studio and Dragonframe, with a status UI that shows whether the bridge is alive in both directions, and a mapping view for choosing and confirming what each physical control does.

## Approach

A single desktop app with one continuously-running pipeline:

1. **MIDI in** — connect to the nanoKONTROL Studio, request KORG Native Mode so every physical control reports a fixed MIDI message.
2. **Mapping engine** — an editable table (add/edit/remove entries, enable/disable per control, MIDI-learn, save/load presets) turns each incoming MIDI event into a Dragonframe OSC message. Each entry has exactly one target, chosen per control: an OSC action, an OSC encoder channel, a direct OSC axis (by discovered name, with user-specified min/max scaling), or an arbitrary custom OSC path. Ships pre-loaded with the nanoKONTROL Studio's default map (mirroring `DragonMIDI-vibed`'s validated default, see References) as its built-in starting preset.
3. **OSC out** — send the mapped message to Dragonframe's OSC Input port over UDP.
4. **OSC in** — listen on a local UDP port that Dragonframe's OSC Output preference is pointed at. Any packet's presence is treated as proof Dragonframe is alive and talking back; additionally, responses to a `getAllPosition` query are parsed specifically to discover the current project's axis names, for the mapping view's axis picker.
5. **Status UI** — two indicators, "MIDI signal" and "Dragonframe signal," each lit when traffic on that channel has been seen within a short recency window.
6. **Mapping view** — a table of every control's current MIDI source and target, editable in place, including picking a discovered axis name and its scaling range for direct axis targets.

Liveness is recency-based, not connection-based: both indicators answer "was there traffic in the last N seconds," not "is a socket/port open," because UDP has no connection state and MIDI devices can go quiet between moves without being unplugged.

## Target Users

A single-person or small-crew stop-motion animator/DP running Dragonframe on the same or a networked machine, driving axes and transport commands from physical faders instead of a mouse. They need the app's status to be a glance, not a debugging session, and need to be able to confirm and correct a control's assignment without reading source code.

## Goals

- Plug in a nanoKONTROL Studio, launch DragonMIDI, open Dragonframe: both status indicators go live within seconds, no manual configuration required.
- Every enabled control in the default map produces the exact Dragonframe OSC message documented for it (see References) — faders/knobs as absolute encoders, transport/shoot/mute/black/delete buttons as one-shot commands, mute/solo as encoder resets.
- DragonMIDI can discover the current Dragonframe project's axis names by querying `getAllPosition` and parsing the per-axis responses.
- The mapping view shows every control's current MIDI source and target in one place, confirmable at a glance.
- Any control's target can be changed to any of: an OSC action, an OSC encoder channel, a direct OSC axis (picked from the discovered list, with a user-specified min/max scaling range), or a custom OSC path — one target per control, chosen by the user, not inferred.
- A fader targeting an axis directly sends `gotoPosition` on every distinct value, scaled into that axis's configured range, with no debounce — matching the same "continuous, no debounce" handling already used for encoder targets.
- MIDI-learn captures a different physical control's exact MIDI source for a mapping entry.
- Mapping changes persist across restarts.
- "MIDI signal" reflects real, recent MIDI traffic from the nanoKONTROL Studio, not just "port opened."
- "Dragonframe signal" reflects real, recent OSC traffic received *from* Dragonframe, not just "we sent something and didn't error."
- Single small desktop build for macOS and Windows, launched like a normal app.

## Non-Goals

- Interpreting Dragonframe's OSC output beyond liveness and `getAllPosition` responses — other output (motor-position streaming, custom output-event templates) isn't parsed.
- A device picker: auto-connect stays scoped to the KORG nanoKONTROL Studio by name. MIDI-learn operates on whatever the adapter is already connected to; it doesn't add support for picking among multiple/other controllers.
- Dragonframe→controller feedback (LEDs, motorized faders).
- Multi-instance or bank-switching support — the Scene button maps to Black, not a layer switch.
- Discovering an axis's practical min/max range automatically — Dragonframe has no `getLimits` over OSC, only `setLimits`. The scaling range for a direct-axis target is entered by the user, not read from Dragonframe.

## Delivery Phasing

This HLD describes the target architecture. It is delivered in phases rather than all at once:

- **Phase 1 — Axis discovery, direct axis addressing, and bank derivation.** The OSC Listener gains the ability to parse `getAllPosition` responses into a list of axis names. The mapping view lets the user assign each of the 8 faders to a discovered axis name with a min/max scaling range — this is now the fader's default target, not an opt-in alternative. The Mapping Engine sends `gotoPosition` continuously, scaled into that range, on every distinct fader value. Each fader's channel strip forms a **bank**: once a fader has an axis assigned, its bank's knob automatically sends `stepPosition` (a signed nudge relative to center) and its Mute/Solo buttons automatically send `setZero`/`setHome` — none of these three are independently configurable. Record/Select keep their existing (unmapped) target untouched in this phase. The jog wheel and Return to Zero are unmapped — the jog wheel is not a motion-control input in this project.
- **Phase 2 — The rest of the configuration.** Extend target selection (OSC action/encoder/direct-axis/custom-path) to knobs and buttons; add MIDI-learn, enable/disable, add/remove/duplicate entries, and preset save/load. This is where the mapping view reaches the full editor generality described elsewhere in this document.

Everything below describes the full target architecture; phase boundaries are tracked in the LLDs, not restated per-section here.

## System Design

```mermaid
flowchart LR
    subgraph Hardware
        KORG[KORG nanoKONTROL Studio]
        DF[Dragonframe]
    end

    subgraph DragonMIDI app
        MIDIIN[MIDI Input Adapter\n(Native Mode handshake)]
        MAP[Mapping Engine\n(editable table, MIDI event -> OSC message)]
        STORE[Preset Store\n(load/save mapping files)]
        OSCOUT[OSC Client\nUDP send]
        OSCIN[OSC Listener\nUDP receive + getAllPosition parsing]
        MON[Signal Monitor\nrecency timers]
        UI[Status UI\nPySide6]
        MAPUI[Mapping View\n(table + editor dialogs + axis picker)]
    end

    KORG -- MIDI (Native Mode) --> MIDIIN
    MIDIIN --> MAP
    MAP --> OSCOUT
    OSCOUT -- UDP: Dragonframe OSC Input port --> DF
    DF -- UDP: Dragonframe OSC Output port --> OSCIN

    MIDIIN -. last-seen timestamp .-> MON
    OSCIN -. last-seen timestamp .-> MON
    MON --> UI

    OSCIN -. discovered axis names .-> MAPUI
    MAP <--> STORE
    MAPUI --> MAP
    MIDIIN -. learn: next raw event .-> MAPUI
```

**Threading model:** MIDI input arrives on a callback thread; the OSC listener runs its own receive loop/thread. Both push into thread-safe queues that the Qt event loop drains on a timer, avoiding Qt widget access from a non-UI thread.

**Status window:**

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

Each indicator is 3-state, not a plain lit/dim toggle: **live** (recent traffic), **error** (Native Mode handshake failure, or listener bind failure — distinct from ordinary quiet), **quiet** (no recent traffic, no error). Host/ports are lightly editable behind an explicit Apply action.

**Mapping view** (a section of the same window, below the status/config area):

```
+-----------------------------------------------------------------------+
| On  Name       MIDI            Trigger      Target type   Target       |
|-------------------------------------------------------------------------|
| ✓   Fader 1    CC0, ch16       Absolute     OSC axis       PAN (0-100)  |
| ✓   Knob 1     CC16, ch16      Absolute     OSC encoder    Encoder 9    |
| ✓   Mute 1     CC48, ch16      Press        OSC action     Reset enc. 1|
| ✓   Play       CC41, ch16      Press        OSC action     Play        |
|  ...           ...             ...           ...           ...          |
+-----------------------------------------------------------------------+
[Load nanoKONTROL default] [Add…] [Edit…] [Duplicate] [Enable/disable] [Remove]
[Load preset…] [Save preset…]
```

Target type is one of: OSC action, OSC encoder channel, OSC axis (direct, picked from a discovered-names list, with a min/max scaling range), custom OSC path — exactly one per entry, chosen by the user. Add/edit/remove, MIDI-learn (via "Edit…", learn the next control moved), enable/disable per row, and named presets. Default content is the nanoKONTROL Studio's opinionated map, not an empty table.

## Key Design Decisions

- **Python + PySide6.** Domain knowledge (Native Mode SysEx handshake, OSC address space) is already validated against mature Python MIDI/OSC libraries. PySide6 over the prototype's tkinter for a cleaner UI; over native Swift or Electron to keep Windows support without an Electron-scale runtime for an always-on utility.
- **Liveness via recency window, not connection state.** MIDI has no "hello" and Dragonframe's OSC is UDP (connectionless), so "connected" is meaningless for either channel. Native Mode handshake success/failure is a separate, orthogonal signal (surfaced as the *error* state) since a control can be silent yet still alive.
- **Bidirectional OSC instead of a send-side heartbeat.** Dragonframe's documented "Outputting Axis Positions via OSC" feature lets it emit traffic on its own; listening for that is real evidence Dragonframe is alive, versus a send-only heartbeat which only proves the local socket didn't error.
- **Direct axis-name addressing instead of a virtual gamepad.** A virtual-gamepad path was investigated first (`docs/dragonframe-gamepad-research.md`) since it's Dragonframe's only mechanism for true continuous jogging, but both the current (`IOHIDUserDeviceCreateWithProperties`) and legacy (`IOHIDUserDeviceCreate`) macOS APIs were confirmed, by direct testing, to require the same Apple-granted DriverKit entitlement — not available without an approval process outside this project's control. Extending the already-working OSC path with `gotoPosition`/`stepPosition` avoids introducing a new OS-level dependency entirely; whether the resulting feel is smooth enough is an open empirical question, not a blocker to building it.
- **Axis names discovered via `getAllPosition`, not hand-typed.** Dragonframe has no other way to enumerate an axis's name; the OSC Listener parses this one specific response shape into a name list for the mapping view, without becoming a general interpreter of Dragonframe's other OSC output.
- **Per-axis min/max scaling entered by the user, not discovered.** Dragonframe has `setLimits` but no `getLimits` over OSC — an axis's practical range cannot be read back, only set. The mapping view asks the user for it directly.
- **Mapping isolated behind one interface.** The mapping engine (MIDI event in, OSC message out) is a pure, swappable component — the editor, persistence, and MIDI-learn sit on top of it without touching MIDI I/O, OSC I/O, or the status indicators.
- **Mapping editor defaults to the nanoKONTROL Studio's opinionated map** rather than an empty table, so the zero-config experience is unchanged for anyone who never opens the mapping view.
- **One target per mapping entry, not multiple.** A control drives exactly one target — matches "select what I want each control to do" as a single choice, not a dual-purpose one, and keeps the mapping engine's per-entry logic simple.
- **Auto-connect to the nanoKONTROL Studio by name, no device picker.** Single-purpose app, one supported controller — scanning MIDI inputs for a name match removes a manual connect step. If the device isn't found, the MIDI indicator stays quiet and the app keeps retrying.

## Success Metrics

- Moving any enabled fader/knob/button lights the MIDI indicator within ~1 second and dims it again within a few seconds of going quiet.
- With Dragonframe's OSC Output pointed at DragonMIDI's listener, the Dragonframe indicator lights within ~1 second of any Dragonframe-originated OSC event.
- Querying `getAllPosition` against a project with configured axes returns responses that DragonMIDI correctly parses into that project's exact axis names.
- A fader mapped to a discovered axis, with a configured min/max range, produces `gotoPosition` messages scaled correctly into that range on every distinct value, with no debounce.
- Every control in the default preset produces the identical OSC address/argument shape as the prototype's `mappings.md` for the same physical control moves.
- The mapping view always reflects what the engine actually enforces: editing an assignment, restarting, and moving the control fires the *new* assignment, not the old default.
- Falsification signal: either indicator lit while its channel has gone silent, or dark while traffic is genuinely flowing, means the liveness design has failed.

## References

- `~/github/DragonMIDI-vibed` — prior prototype; source of the Native Mode SysEx handshake (`dragonmidi/midi_io.py`) and the default control mapping (`mappings.md`).
- `docs/dragonframe-messages-research.md` — Dragonframe's OSC input/output surface, including the full fixed-command list, the encoder/axis addressing mechanism, and the `getAllPosition`/`setLimits` findings this design is built on.
- `docs/dragonframe-gamepad-research.md` — the virtual-gamepad path investigated and set aside; retained as a record of what was tried and why, not an active plan.
