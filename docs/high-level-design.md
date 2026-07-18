# High-Level Design: DragonMIDI

## Problem

Dragonframe (stop-motion capture software) accepts live axis input over OSC, but a MIDI control surface like the KORG nanoKONTROL Studio has no direct way to speak OSC. A prior prototype (`DragonMIDI-vibed`) proved the bridge is possible and captured real protocol knowledge — the nanoKONTROL Studio's Native Mode SysEx handshake, Dragonframe's OSC address space — but its architecture grew unconstrained and isn't a foundation worth building on directly.

DragonMIDI is a clean rebuild: a MIDI-to-OSC bridge for the nanoKONTROL Studio and Dragonframe, with a status UI that shows whether the bridge is alive in both directions, and a mapping view for confirming and changing what each control does.

## Approach

A single desktop app with one continuously-running pipeline:

1. **MIDI in** — connect to the nanoKONTROL Studio, request KORG Native Mode so every physical control reports a fixed MIDI message.
2. **Mapping engine** — an editable table (add/edit/remove entries, enable/disable per control, MIDI-learn, arbitrary custom OSC paths, save/load presets) turns each incoming MIDI event into a Dragonframe OSC message. Ships pre-loaded with the nanoKONTROL Studio's default map (mirroring `DragonMIDI-vibed`'s validated default, see References) as its built-in starting preset.
3. **OSC out** — send the mapped message to Dragonframe's OSC Input port over UDP.
4. **OSC in (status only)** — listen on a local UDP port that Dragonframe's OSC Output preference is pointed at. Any packet arriving there is treated as proof Dragonframe is alive and talking back; content isn't interpreted.
5. **Status UI** — two indicators, "MIDI signal" and "Dragonframe signal," each lit when traffic on that channel has been seen within a short recency window.
6. **Mapping view** — a table of every control's current MIDI source and Dragonframe OSC target, editable in place.

Liveness is recency-based, not connection-based: both indicators answer "was there traffic in the last N seconds," not "is a socket/port open," because UDP has no connection state and MIDI devices can go quiet between moves without being unplugged.

## Target Users

A single-person or small-crew stop-motion animator/DP running Dragonframe on the same or a networked machine, driving axes and transport commands from physical faders instead of a mouse. They need the app's status to be a glance, not a debugging session, and need to be able to confirm and correct a control's assignment without reading source code.

## Goals

- Plug in a nanoKONTROL Studio, launch DragonMIDI, open Dragonframe: both status indicators go live within seconds, no manual configuration required.
- Every enabled control in the default map produces the exact Dragonframe OSC message documented for it (see References) — faders/knobs as absolute encoders, jog wheel as relative encoder 17, transport/shoot/mute/black/delete buttons as one-shot commands, mute/solo as encoder resets.
- The mapping view shows every control's current MIDI source and Dragonframe target in one place, confirmable at a glance.
- Any control's assignment can be changed — MIDI-learn a different physical control, retarget to a different encoder channel or Dragonframe action, or point at an arbitrary custom OSC path — without editing code.
- Mapping changes persist across restarts.
- "MIDI signal" reflects real, recent MIDI traffic from the nanoKONTROL Studio, not just "port opened."
- "Dragonframe signal" reflects real, recent OSC traffic received *from* Dragonframe, not just "we sent something and didn't error."
- Single small desktop build for macOS and Windows, launched like a normal app.

## Non-Goals

- Interpreting *what* Dragonframe's OSC output contains (axis positions, frame events) — only its presence matters, for liveness.
- A device picker: auto-connect stays scoped to the KORG nanoKONTROL Studio by name. MIDI-learn operates on whatever the adapter is already connected to; it doesn't add support for picking among multiple/other controllers.
- Dragonframe→controller feedback (LEDs, motorized faders).
- Multi-instance or bank-switching support — the Scene button maps to Black, not a layer switch.

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
        OSCIN[OSC Listener\nUDP receive]
        MON[Signal Monitor\nrecency timers]
        UI[Status UI\nPySide6]
        MAPUI[Mapping View\n(table + editor dialogs)]
    end

    KORG -- MIDI (Native Mode) --> MIDIIN
    MIDIIN --> MAP
    MAP --> OSCOUT
    OSCOUT -- UDP: Dragonframe OSC Input port --> DF
    DF -- UDP: Dragonframe OSC Output port --> OSCIN

    MIDIIN -. last-seen timestamp .-> MON
    OSCIN -. last-seen timestamp .-> MON
    MON --> UI

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

**Mapping view** (opened from the status window):

```
+-----------------------------------------------------------------+
| On  Name       MIDI            Trigger      Dragonframe target   |
|-------------------------------------------------------------------|
| ✓   Fader 1    CC0, ch16       Absolute     Encoder 1             |
| ✓   Knob 1     CC16, ch16      Absolute     Encoder 9             |
| ✓   Mute 1     CC48, ch16      Press        Reset encoder 1       |
| ✓   Play       CC41, ch16      Press        Play                 |
|  ...           ...             ...           ...                  |
+-----------------------------------------------------------------+
[Load nanoKONTROL default] [Add…] [Edit…] [Duplicate] [Enable/disable] [Remove]
[Load preset…] [Save preset…]
```

Add/edit/remove, MIDI-learn (via "Edit…", learn the next control moved), enable/disable per row, and named presets. Default content is the nanoKONTROL Studio's opinionated map, not an empty table.

## Key Design Decisions

- **Python + PySide6.** Domain knowledge (Native Mode SysEx handshake, OSC address space) is already validated against mature Python MIDI/OSC libraries. PySide6 over the prototype's tkinter for a cleaner UI; over native Swift or Electron to keep Windows support without an Electron-scale runtime for an always-on utility.
- **Liveness via recency window, not connection state.** MIDI has no "hello" and Dragonframe's OSC is UDP (connectionless), so "connected" is meaningless for either channel. Native Mode handshake success/failure is a separate, orthogonal signal (surfaced as the *error* state) since a control can be silent yet still alive.
- **Bidirectional OSC instead of a send-side heartbeat.** Dragonframe's documented "Outputting Axis Positions via OSC" feature lets it emit traffic on its own; listening for that is real evidence Dragonframe is alive, versus a send-only heartbeat which only proves the local socket didn't error.
- **Mapping isolated behind one interface.** The mapping engine (MIDI event in, OSC message out) is a pure, swappable component — the editor, persistence, and MIDI-learn sit on top of it without touching MIDI I/O, OSC I/O, or the status indicators.
- **Mapping editor defaults to the nanoKONTROL Studio's opinionated map** rather than an empty table, so the zero-config experience is unchanged for anyone who never opens the mapping view.
- **Auto-connect to the nanoKONTROL Studio by name, no device picker.** Single-purpose app, one supported controller — scanning MIDI inputs for a name match removes a manual connect step. If the device isn't found, the MIDI indicator stays quiet and the app keeps retrying.

## Success Metrics

- Moving any enabled fader/knob/button lights the MIDI indicator within ~1 second and dims it again within a few seconds of going quiet.
- With Dragonframe's OSC Output pointed at DragonMIDI's listener, the Dragonframe indicator lights within ~1 second of any Dragonframe-originated OSC event.
- Every control in the default preset produces the identical OSC address/argument shape as the prototype's `mappings.md` for the same physical control moves.
- The mapping view always reflects what the engine actually enforces: editing an assignment, restarting, and moving the control fires the *new* assignment, not the old default.
- Falsification signal: either indicator lit while its channel has gone silent, or dark while traffic is genuinely flowing, means the liveness design has failed.

## References

- `~/github/DragonMIDI-vibed` — prior prototype; source of the Native Mode SysEx handshake (`dragonmidi/midi_io.py`) and the default control mapping (`mappings.md`).
- Dragonframe official manual, "Outputting Axis Positions via Open Sound Control (OSC)" section (`Using Dragonframe 2025.pdf`, dragonframe.com).
