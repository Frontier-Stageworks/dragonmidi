# High-Level Design: DragonMIDI

## Problem

Dragonframe (stop-motion capture software) accepts live axis input over OSC, but a MIDI control surface like the KORG nanoKONTROL Studio has no direct way to speak OSC. A prior vibe-coded prototype (`DragonMIDI-vibed`, built by asking ChatGPT for "an app that does this" with no real constraints) proved the MIDI-to-OSC bridge is possible and captured real protocol knowledge (the nanoKONTROL Studio's Native Mode SysEx handshake, Dragonframe's OSC address space), but it grew into a full mapping-editor GUI nobody asked for, and its provenance ("no constraints given") means its architecture isn't trusted as a foundation to build on directly.

DragonMIDI is a from-scratch rebuild: a small, trustworthy utility that turns nanoKONTROL Studio fader/knob/button moves into Dragonframe OSC commands, with just enough UI to tell a user on set whether the bridge is actually alive in both directions.

## Approach

A single desktop app with one continuously-running pipeline:

1. **MIDI in** — connect to the nanoKONTROL Studio, request KORG Native Mode so every physical control reports a fixed MIDI message.
2. **Static mapping** — an opinionated, hard-coded table (mirroring `DragonMIDI-vibed`'s validated default map, see References) turns each incoming MIDI message into a Dragonframe OSC message. No editor, no MIDI-learn, no user-authored presets in this phase.
3. **OSC out** — send the mapped message to Dragonframe's OSC Input port over UDP.
4. **OSC in (status only)** — listen on a local UDP port that Dragonframe's OSC Output preference is pointed at. Any packet arriving there is treated as proof Dragonframe is alive and talking back; phase 1 does not need to interpret its contents.
5. **Status UI** — two indicators, "MIDI signal" and "Dragonframe signal," each lit when traffic on that channel has been seen within a short recency window.

Two secondary disciplines run alongside the core mechanism:

- **Recency-based liveness**, not connection-based: both indicators are driven by "have I seen a packet/message in the last N seconds," not by a static connect/disconnect state, because UDP has no connection state and MIDI devices can go quiet between control moves without being unplugged.
- **Forward-compatible architecture**: the mapping table is isolated behind a single interface (MIDI event in, OSC message out) so a future configuration/mapping-editor phase can replace the static table without touching MIDI I/O, OSC I/O, or the UI.

## Target Users

A single-person or small-crew stop-motion animator/DP on set who has Dragonframe running on the same or a networked machine and wants to drive Dragonframe axes (and a few transport/shoot commands) from physical faders instead of a mouse or on-screen controls. They need to glance at the app and immediately know "is my controller connected" and "is Dragonframe hearing me" without reading a log — set time is expensive and troubleshooting needs to be a glance, not a debugging session.

## Goals

- A user can plug in a nanoKONTROL Studio, launch DragonMIDI, open Dragonframe, and within seconds see both status indicators go live with no manual configuration of the MIDI device or the control mapping.
- Every enabled control in the opinionated map produces the exact Dragonframe OSC message documented for it (see References) — faders/knobs as absolute encoders, jog wheel as relative encoder 17, transport/shoot/mute/black/delete buttons as their respective one-shot commands, mute/solo as encoder resets.
- The "MIDI signal" indicator reflects real, recent MIDI traffic from the nanoKONTROL Studio (not just "port opened").
- The "Dragonframe signal" indicator reflects real, recent OSC traffic received *from* Dragonframe (not just "we sent something and didn't error"), once the user has pointed Dragonframe's OSC Output at our listener.
- The app is a single small desktop build for macOS and Windows (matching the platforms the prototype already supported), launched like a normal app — no terminal required for day-to-day use.

## Non-Goals

- No mapping editor, MIDI-learn, or user-authored preset files in this phase — the map is fixed in code. (Deferred to a future phase; the architecture must not preclude adding it later.)
- No interpretation of *what* Dragonframe sends back over OSC (axis positions, frame events) — phase 1 only needs "a packet arrived," not its meaning.
- No support for MIDI controllers other than the KORG nanoKONTROL Studio.
- No Dragonframe→controller feedback (LEDs, motorized faders) — matches the prototype's stated scope; still out of scope here.
- No multi-instance / multi-controller / bank-switching support.

## System Design

```mermaid
flowchart LR
    subgraph Hardware
        KORG[KORG nanoKONTROL Studio]
        DF[Dragonframe]
    end

    subgraph DragonMIDI app
        MIDIIN[MIDI Input Adapter\n(Native Mode handshake)]
        MAP[Static Mapping Engine\n(MIDI event -> OSC message)]
        OSCOUT[OSC Client\nUDP send]
        OSCIN[OSC Listener\nUDP receive]
        MON[Signal Monitor\nrecency timers]
        UI[Status UI\nPySide6]
    end

    KORG -- MIDI (Native Mode) --> MIDIIN
    MIDIIN --> MAP
    MAP --> OSCOUT
    OSCOUT -- UDP: Dragonframe OSC Input port --> DF
    DF -- UDP: Dragonframe OSC Output port --> OSCIN

    MIDIIN -. last-seen timestamp .-> MON
    OSCIN -. last-seen timestamp .-> MON
    MON --> UI
```

**Threading model:** MIDI input arrives on a callback thread; the OSC listener runs its own receive loop/thread. Both push into thread-safe queues that the Qt event loop drains on a timer, matching the polling-queue pattern already proven in the prototype — this avoids touching Qt widgets from a non-UI thread.

**UI (status window, phase 1):**

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

Each indicator is a **3-state** dot, not a plain lit/dim toggle: live (recent traffic), error (a real failure — Native Mode handshake failure, or listener bind failure — surfaced distinctly so it can't be mistaken for ordinary quiet), or quiet (no recent traffic, no error). This was resolved during LLD review (see `docs/llds/app-ui.md`) once a plain 2-state light was found to make a silently-failed listener bind or Native Mode handshake look identical to normal "no traffic yet." No per-control table, no log pane, no menu of mapping options. Host/ports may be shown and are lightly editable behind an explicit Apply action (they vary per setup), but the control mapping itself is not.

## Key Design Decisions

- **Python + PySide6, not the prototype's tkinter, and not a rewrite in Swift/Electron.** Chosen over native Swift (would drop Windows support, which the prototype had and nothing has ruled out yet) and over Electron (heavy runtime for an always-on utility). Python is kept because most of the domain-hard-won knowledge (Native Mode SysEx handshake, OSC address space) is already validated against real MIDI/OSC libraries in that ecosystem; PySide6 replaces tkinter for a cleaner, still-lightweight status UI. The user explicitly does not trust the prototype's *architecture* (built with no constraints), not the language choice — so we rebuild clean in the same language rather than also introducing platform risk.
- **Liveness via recency window, not connection state.** MIDI has no "hello" and Dragonframe's OSC is UDP (connectionless), so "connected" is meaningless for either channel. Both indicators instead answer "was there traffic in the last N seconds," decoupling the UI from any transport-level handshake. Native Mode handshake success/failure for the nanoKONTROL Studio is a separate concern (logged, not blocking the indicator) since a control can be silent yet still be alive.
- **Bidirectional OSC (listen for Dragonframe's own OSC Output) instead of a send-side-only heartbeat.** Confirmed against Dragonframe's documented "Outputting Axis Positions via OSC" feature: Dragonframe can be pointed at our host:port and will emit OSC on its own (axis positions, frame/shutter/shoot events). Listening for any of that traffic is real evidence Dragonframe is alive and configured correctly, versus a send-only heartbeat which only proves our own socket didn't error.
- **Static mapping isolated behind one interface.** The mapping table (MIDI event → OSC message) is a pure, swappable component precisely so a later configuration/editor phase can replace it without destabilizing MIDI I/O, OSC I/O, or the status UI — this is a non-goal for phase 1, not a rejected idea.
- **Auto-connect to the nanoKONTROL Studio by name, no manual device picker.** Because this app is single-purpose (one supported controller), scanning MIDI inputs for a name match and auto-connecting removes a manual step the prototype required (choose input, click Connect) — consistent with the "simple UI" goal. If the device isn't found, the MIDI indicator simply stays dim; the app keeps retrying rather than erroring out.

## Success Metrics

- Moving any enabled fader/knob/button on the nanoKONTROL Studio lights the MIDI indicator within ~1 second and dims it again within a few seconds of the control going quiet.
- With Dragonframe's OSC Output pointed at DragonMIDI's listener, the Dragonframe indicator lights within ~1 second of any Dragonframe-originated OSC event and dims similarly after quiet.
- Every control listed as "Enabled" in the prototype's `mappings.md` produces the identical OSC address/argument shape when driven through the new app — falsifiable by comparing captured OSC packets between old and new app for the same physical control moves.
- Falsification signal: if either indicator is lit while its underlying channel has actually gone silent (stale "alive" state), or dark while traffic is genuinely flowing, the liveness design has failed and needs revisiting.

## FAQ

**Why rebuild instead of refactoring `DragonMIDI-vibed`?** The user said "give me an app that does this" with no constraints, so the resulting architecture (full mapping-editor GUI, tkinter, blank-preset/preset-file plumbing) reflects an AI's unconstrained guess, not a considered design. The domain knowledge it captured (Native Mode SysEx, Dragonframe's OSC surface) is trustworthy and worth reusing as reference; the software structure around it is not.

**Will the mapping table match the prototype's default exactly?** Yes, unless told otherwise during the LLD for the mapping component — it's the one part of the prototype the user has actually used and is treating as a known-good starting point, not an unconstrained guess.

## References

- `~/github/DragonMIDI-vibed` — prior vibe-coded prototype; source of the Native Mode SysEx handshake (`dragonmidi/midi_io.py`) and the default control mapping (`mappings.md`).
- Dragonframe official manual, "Outputting Axis Positions via Open Sound Control (OSC)" section (`Using Dragonframe 2025.pdf`, dragonframe.com) — confirms Dragonframe's OSC Output capability used for the Dragonframe-signal listener.
