# High-Level Design: DragonMIDI

## Problem

Dragonframe (stop-motion capture software) accepts live axis input over OSC, but a MIDI control surface like the KORG nanoKONTROL Studio has no direct way to speak OSC. A prior prototype proved the bridge is possible and captured real protocol knowledge — the nanoKONTROL Studio's Native Mode SysEx handshake, Dragonframe's OSC address space — but its architecture grew unconstrained and isn't a foundation worth building on directly.

Dragonframe's OSC surface includes direct axis-name addressing (`gotoPosition`/`stepPosition`), but DragonMIDI's current mapping only reaches axes indirectly through numbered "OSC encoder channels," which the user must separately wire to an axis inside Dragonframe. A virtual-gamepad approach to real-time jogging is blocked by Apple's DriverKit entitlement requirement. The chosen path instead extends the OSC connection already built: discover axis names via `getAllPosition` and address them directly.

Some Dragonframe functions have no OSC equivalent: the Arc Motion Control workspace's frame stepping ("Step Moco Forward"/"Step Moco Back" in Dragonframe's Hot Keys preferences) is reachable only by its keyboard shortcut. For these, DragonMIDI adds a second, narrower output path alongside OSC: synthesizing the OS-level keystroke that Dragonframe's Hot Keys preferences bind that action to.

A third gap exists: Dragonframe, at startup, opens an outbound WebSocket connection accepting `{"input": "<name>"}` JSON commands; unlike keystroke synthesis, delivery does not depend on Dragonframe holding OS focus. The channel exposes `E-Stop` (motion-control emergency stop), `select-AXn` (axis select/highlight), and `jog-AXn` (per-axis incremental jog) — none reachable by OSC or a safe keystroke. Axis mute/enable-disable and keyframe-setting are not exposed on this channel. For the confirmed subset, DragonMIDI adds a third, narrower output path alongside OSC and keystroke synthesis: a WebSocket server that accepts Dragonframe's connection and forwards mapped controls as Dragonframe WebSocket commands.

DragonMIDI is a clean rebuild: a MIDI-to-OSC bridge for the nanoKONTROL Studio and Dragonframe, with a status UI that shows whether the bridge is alive in both directions, and a mapping view for choosing and confirming what each physical control does.

A second controller, the KORG nanoKONTROL2, is also in scope. It shares the Studio's 8-channel-strip layout (fader/knob/solo/mute) but has no jog wheel, no Scene button, and no Native-Mode-style SysEx handshake — it ships in a fixed-CC "CC mode" selected by a physical button-hold-at-power-on procedure, not something DragonMIDI can request over the wire, and its default CC assignments and MIDI channel differ from the Studio's. Supporting it means the MIDI input and mapping layers can no longer hardcode Studio-only assumptions (a handshake exists, a jog wheel and Scene button exist, channel 16 is the match channel).

## Approach

A single desktop app with one continuously-running pipeline:

1. **MIDI in** — connect to the selected controller (KORG nanoKONTROL Studio or nanoKONTROL2, picked from a Controller Profile dropdown), requesting KORG Native Mode only when the selected profile defines one (the Studio's fixed-CC handshake; the nanoKONTROL2 has none) so every physical control reports a fixed MIDI message.
2. **Mapping engine** — an editable table (add/edit/remove entries, enable/disable per control, MIDI-learn, save/load presets) turns each incoming MIDI event into a Dragonframe OSC message. Each entry has exactly one target, chosen per control: an OSC action, an OSC encoder channel, a direct OSC axis (by discovered name, with user-specified min/max scaling), or an arbitrary custom OSC path. Ships pre-loaded with the nanoKONTROL Studio's default map (mirroring the prior prototype's validated default, see References) as its built-in starting preset.
3. **OSC out** — send the mapped message to Dragonframe's OSC Input port over UDP.
4. **OSC in** — listen on a local UDP port that Dragonframe's OSC Output preference is pointed at. Any packet's presence is treated as proof Dragonframe is alive and talking back; additionally, responses to a `getAllPosition` query are parsed specifically to discover the current project's axis names, for the mapping view's axis picker.
5. **Keystroke out** — for the small set of Dragonframe functions with no OSC equivalent, synthesize the OS-level keystroke for that function's Dragonframe Hot Key instead. A narrower, secondary output path alongside OSC out, not a replacement for it — most controls never use it.
6. **WebSocket out** — for functions reachable only through Dragonframe's own WebSocket channel (`E-Stop`, axis select, per-axis jog), run a local WebSocket server that Dragonframe connects to at startup, and send it `{"input": "<name>"}` JSON commands. A third, narrower output path alongside OSC out and Keystroke out.
7. **Status UI** — two indicators, "MIDI signal" and "Dragonframe signal," each lit when traffic on that channel has been seen within a short recency window.
8. **Mapping view** — a table of every control's current MIDI source and target, editable in place, including picking a discovered axis name and its scaling range for direct axis targets.

Liveness is recency-based, not connection-based: both indicators answer "was there traffic in the last N seconds," not "is a socket/port open," because UDP has no connection state and MIDI devices can go quiet between moves without being unplugged.

## Target Users

A single-person or small-crew stop-motion animator/DP running Dragonframe on the same or a networked machine, driving axes and transport commands from physical faders instead of a mouse. They need the app's status to be a glance, not a debugging session, and need to be able to confirm and correct a control's assignment without reading source code.

## Goals

- Plug in a nanoKONTROL Studio, launch DragonMIDI, open Dragonframe: both status indicators go live within seconds, no manual configuration required.
- Selecting a controller from the Controller Profile dropdown (nanoKONTROL Studio or nanoKONTROL2) and plugging in the matching device brings both status indicators live within seconds — the same zero-extra-configuration experience, once the profile is chosen.
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
- A control whose only Dragonframe equivalent is a keyboard-only action (no OSC message) can still be mapped, by synthesizing that action's default Dragonframe Hot Key as an OS-level keystroke.
- A control can be mapped to send a Dragonframe WebSocket command (`E-Stop`, axis select, per-axis jog) for functions reachable by no other means.

## Non-Goals

- Interpreting Dragonframe's OSC output beyond liveness and `getAllPosition` responses — other output (motor-position streaming, custom output-event templates) isn't parsed.
- A general MIDI device picker: within a selected Controller Profile, auto-connect stays scoped to that profile's name match — no picking among arbitrary/multiple MIDI ports. The Controller Profile dropdown (nanoKONTROL Studio / nanoKONTROL2) is a closed choice between the two profiles this app ships, not a general controller-picker; MIDI-learn operates on whatever device the currently selected profile is connected to.
- Dragonframe→controller feedback (LEDs, motorized faders).
- Multi-instance or bank-switching support — the Scene button maps to Black, not a layer switch.
- Discovering an axis's practical min/max range automatically — Dragonframe has no `getLimits` over OSC, only `setLimits`. The scaling range for a direct-axis target is entered by the user, not read from Dragonframe.
- A general keystroke-automation or macro tool. Keystroke out is scoped to synthesizing the *default* Dragonframe Hot Key binding for specific, documented OSC-gap functions — not arbitrary key combinations, not other applications, and not tracking whether the user has since remapped that Hot Key in Dragonframe's own preferences (same "documented setup precondition, not detected" treatment as the axis `Function: Manual` requirement).
- Detecting or requiring that Dragonframe is the OS-focused application before sending a synthesized keystroke. Like a real keypress, the keystroke lands wherever the OS has focus; DragonMIDI doesn't verify that's Dragonframe first. Accepted as a narrow, self-evident risk for this single-purpose app rather than adding frontmost-window-detection machinery.
- A general third-party control-surface protocol client. DragonMIDI's WebSocket server accepts only Dragonframe's own connection on the well-known port and sends only a fixed set of input names — no dynamic input discovery, coloring, or profile system.
- Coexisting with another process already bound to the same well-known port (59177): not detected, not negotiated around.
- Axis mute/enable-disable or keyframe-setting via the WebSocket path — no command exists for either; unreachable by any output path DragonMIDI has.

## Delivery Phasing

This HLD describes the target architecture. It is delivered in phases rather than all at once:

- **Phase 1 — Axis discovery, direct axis addressing, and bank derivation.** The OSC Listener gains the ability to parse `getAllPosition` responses into a list of axis names. The mapping view lets the user assign each of the 8 faders to a discovered axis name with a min/max scaling range — this is now the fader's default target, not an opt-in alternative. The Mapping Engine sends `gotoPosition` continuously, scaled into that range, on every distinct fader value. Each fader's channel strip forms a **bank**: once a fader has an axis assigned, its bank's knob automatically sends `stepPosition` (a signed nudge relative to center) and its Mute button automatically sends `setZero` — neither is independently configurable. (Solo originally followed the same pattern with `setHome`; superseded in Phase 3 below, where Solo becomes an unconditional WebSocket target instead.) Record/Select keep their existing (unmapped) target untouched in this phase. The jog wheel drives frame-by-frame timeline stepping (`stepForward`/`stepBackward`, one step per detent, direction from the wheel's rotation) rather than motion-control axis input, and additionally synthesizes the "Step Moco Forward"/"Step Moco Back" keystroke on the same detent so stepping also works while the Arc Motion Control workspace is focused, where the OSC commands alone have no effect; Return to Zero remains unmapped.
- **Phase 2 — The rest of the configuration.** Extend target selection (OSC action/encoder/direct-axis/custom-path) to knobs and buttons; add MIDI-learn, enable/disable, add/remove/duplicate entries, and preset save/load. This is where the mapping view reaches the full editor generality described elsewhere in this document.
- **Phase 3 — WebSocket output.** Add the WebSocket target type (`E-Stop`, axis select, per-axis jog — the confirmed subset) and the WebSocket Output Adapter that serves it. Independent of Phase 2's OSC/Keystroke target work; can land before or after it.
- **Phase 4 — nanoKONTROL2 support.** Introduce the Controller Profile abstraction (`docs/llds/midi-input.md`, `docs/llds/static-mapping.md`), a nanoKONTROL2 profile (no handshake, no jog wheel, no Scene button, its own default channel/CC map), and the Controller Profile dropdown in the Status UI (`docs/llds/app-ui.md`). Independent of Phases 1–3's OSC/Keystroke/WebSocket target work — it changes which device profile feeds the same mapping/output pipeline, not the pipeline itself.

Everything below describes the full target architecture; phase boundaries are tracked in the LLDs, not restated per-section here.

## System Design

```mermaid
flowchart LR
    subgraph Hardware
        KORG[KORG nanoKONTROL Studio]
        DF[Dragonframe]
    end

    subgraph OS
        FOCUS[OS keyboard focus]
    end

    subgraph DragonMIDI app
        MIDIIN[MIDI Input Adapter\n(per selected Controller Profile)]
        MAP[Mapping Engine\n(editable table, MIDI event -> OSC message / keystroke)]
        STORE[Preset Store\n(load/save mapping files)]
        OSCOUT[OSC Client\nUDP send]
        OSCIN[OSC Listener\nUDP receive + getAllPosition parsing]
        KEYOUT[Keystroke Output Adapter\nsynthesizes OS-level key events]
        WSOUT[WebSocket Output Adapter\nserves ws://localhost:59177,\nsends Dragonframe WebSocket commands]
        MON[Signal Monitor\nrecency timers]
        UI[Status UI\nPySide6]
        MAPUI[Mapping View\n(table + editor dialogs + axis picker)]
    end

    KORG -- MIDI (Native Mode) --> MIDIIN
    MIDIIN --> MAP
    MAP --> OSCOUT
    MAP --> KEYOUT
    MAP --> WSOUT
    OSCOUT -- UDP: Dragonframe OSC Input port --> DF
    DF -- UDP: Dragonframe OSC Output port --> OSCIN
    KEYOUT -- synthesized keystroke --> FOCUS
    FOCUS -. delivered only if DF is frontmost .-> DF
    DF -- WebSocket: connects out to WSOUT --> WSOUT

    MIDIIN -. last-seen timestamp .-> MON
    OSCIN -. last-seen timestamp .-> MON
    MON --> UI

    OSCIN -. discovered axis names .-> MAPUI
    MAP <--> STORE
    MAPUI --> MAP
    MIDIIN -. learn: next raw event .-> MAPUI
```

**Threading model:** MIDI input arrives on a callback thread; the OSC listener runs its own receive loop/thread. Both push into thread-safe queues that the Qt event loop drains on a timer, avoiding Qt widget access from a non-UI thread.

**Controller Profile:** `MIDIIN` and `MAP` are driven by whichever `ControllerProfile` is currently selected (see Key Design Decisions) — the diagram's boxes are the same regardless of which controller is active; only their internal behavior (handshake yes/no, opinionated map contents, default channel) varies per profile. Switching the dropdown disconnects the current device (releasing Native Mode first, if the outgoing profile had it) and starts discovery for the newly-selected profile's name pattern.

**Status window:**

```
+-----------------------------------------------+
|  DragonMIDI                                    |
|                                                 |
|  Controller: [nanoKONTROL Studio ▾]            |
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
| On  Name          MIDI            Trigger      Target type   Target    |
|-------------------------------------------------------------------------|
| ✓   Fader 1       CC0, ch16       Absolute     OSC axis       PAN (0-100)|
| ✓   Knob 1        CC16, ch16      Absolute     OSC encoder    Encoder 9  |
| ✓   Mute 1        CC48, ch16      Press        OSC action     Reset enc. 1|
| ✓   Play          CC41, ch16      Press        OSC action     Play      |
| ✓   Jog Wheel     CC110, ch16     Directional   OSC action     stepForward/stepBackward |
| ✓   Jog Wheel (Arc) CC110, ch16   Directional   Keystroke      ⌥⇧→ / ⌥⇧← |
| ✓   Stop          CC42, ch16      Press         WebSocket      E-Stop     |
|  ...              ...             ...           ...           ...       |
+-----------------------------------------------------------------------+
[Load nanoKONTROL default] [Add…] [Edit…] [Duplicate] [Enable/disable] [Remove]
[Load preset…] [Save preset…]
```

Target type is one of: OSC action, OSC encoder channel, OSC axis (direct, picked from a discovered-names list, with a min/max scaling range), custom OSC path, **Keystroke** (a synthesized OS-level keystroke, per Keystroke out above), or **WebSocket** (a Dragonframe WebSocket command sent over WebSocket out, picked from a fixed list) — exactly one per *row*, chosen by the user for editable rows. A control that produces more than one output (the jog wheel: an OSC command and a keystroke) appears as two separate rows, one per output, rather than stretching a single row to hold two targets — this keeps "exactly one target per row" true everywhere, instead of introducing a second kind of row or an extra column just for the one control that needs it.

## Key Design Decisions

- **Python + PySide6.** Domain knowledge (Native Mode SysEx handshake, OSC address space) is already validated against mature Python MIDI/OSC libraries. PySide6 over the prototype's tkinter for a cleaner UI; over native Swift or Electron to keep Windows support without an Electron-scale runtime for an always-on utility.
- **Liveness via recency window, not connection state.** MIDI has no "hello" and Dragonframe's OSC is UDP (connectionless), so "connected" is meaningless for either channel. Native Mode handshake success/failure is a separate, orthogonal signal (surfaced as the *error* state) since a control can be silent yet still alive.
- **Bidirectional OSC instead of a send-side heartbeat.** Dragonframe's documented "Outputting Axis Positions via OSC" feature lets it emit traffic on its own; listening for that is real evidence Dragonframe is alive, versus a send-only heartbeat which only proves the local socket didn't error.
- **Direct axis-name addressing instead of a virtual gamepad.** A virtual gamepad is Dragonframe's only mechanism for true continuous jogging, but both the current (`IOHIDUserDeviceCreateWithProperties`) and legacy (`IOHIDUserDeviceCreate`) macOS APIs require the same Apple-granted DriverKit entitlement, unavailable without an approval process outside this project's control. Extending the already-working OSC path with `gotoPosition`/`stepPosition` avoids introducing a new OS-level dependency; whether the resulting feel is smooth enough remains open, not a blocker to building it.
- **Axis names discovered via `getAllPosition`, not hand-typed.** Dragonframe has no other way to enumerate an axis's name; the OSC Listener parses this one specific response shape into a name list for the mapping view, without becoming a general interpreter of Dragonframe's other OSC output.
- **Per-axis min/max scaling entered by the user, not discovered.** Dragonframe has `setLimits` but no `getLimits` over OSC — an axis's practical range cannot be read back, only set. The mapping view asks the user for it directly.
- **Mapping isolated behind one interface.** The mapping engine (MIDI event in, OSC message out) is a pure, swappable component — the editor, persistence, and MIDI-learn sit on top of it without touching MIDI I/O, OSC I/O, or the status indicators.
- **Mapping editor defaults to the nanoKONTROL Studio's opinionated map** rather than an empty table, so the zero-config experience is unchanged for anyone who never opens the mapping view.
- **One target per mapping entry, not multiple.** A control drives exactly one target — matches "select what I want each control to do" as a single choice, not a dual-purpose one, and keeps the mapping engine's per-entry logic simple.
- **Auto-connect by name within the selected Controller Profile, no general device picker.** Scanning MIDI inputs for a name match removes a manual connect step. If the device isn't found, the MIDI indicator stays quiet and the app keeps retrying.
- **Controller Profile abstraction, not per-device forked code.** `MidiInputAdapter` and the Mapping Engine are driven by a `ControllerProfile` (device name-match pattern, optional Native-Mode-style handshake, default MIDI channel, feature flags, opinionated default map) rather than hardcoding the nanoKONTROL Studio's quirks throughout. The nanoKONTROL Studio and nanoKONTROL2 are two profile instances; a third controller is a new profile, not a parallel adapter. Chosen over forking the adapter/engine per device (more duplicated boilerplate — discovery polling, bank derivation, WebSocket-targeted controls all repeated) or scattering `if profile == "studio"` conditionals through shared code (doesn't scale past two devices).
- **Controller selection is an explicit dropdown, not auto-detection.** The user picks nanoKONTROL Studio or nanoKONTROL2 from a Status UI dropdown; auto-connect-by-name then applies only within that profile. This is a closed choice between exactly the two controller families DragonMIDI ships, not a general device picker — see Non-Goals.
- **nanoKONTROL2's opinionated map omits jog-wheel and Scene-button entries entirely**, rather than including them as disabled/greyed-out placeholders. The nanoKONTROL2 has no jog wheel and no Scene button, so the Studio-only frame-stepping (OSC + Arc keystroke) and Scene→Black mappings simply don't exist as rows in its profile.
- **nanoKONTROL2's default CC map is the commonly-documented factory-default CC-mode assignment, confirmed working against real hardware.** Korg's owner's manual documents the physical layout and operation modes but not the actual CC-number table (a separate Parameter Guide has that, and it likewise doesn't list the factory defaults — see References); the map was written from the widely-cited community-documented values and confirmed in practice against a real nanoKONTROL2 (2026-07-21) — every control produced its expected Dragonframe behavior. This was a practical, in-app confirmation (controls behaving correctly), not a byte-level MIDI-monitor trace of the raw CC numbers.
- **`pynput` for keystroke synthesis, over native platform APIs.** One dependency covers both macOS (via the same Accessibility-permission-gated mechanism as `Quartz`/`CGEvent`) and Windows (via `SendInput` under the hood), matching the existing preference for validated, portable libraries (`mido`+`python-rtmidi` for MIDI) over hand-rolled per-OS code.
- **Keystroke output fails silently, not as a new status indicator.** Unlike the MIDI Native Mode handshake (surfaced as an *error* state) or the OSC listener bind failure, a missing macOS Accessibility grant or a Windows `SendInput` failure is logged but does not add a third Status UI indicator in this phase — the affected controls are few, and the existing two indicators (MIDI signal, Dragonframe signal) already tell the user whether the *OSC* half of the bridge is healthy. A dedicated indicator is deferred, not ruled out, if more controls come to depend on keystroke output later.
- **No frontmost-application check before sending a keystroke.** Synthesizing a keystroke without first verifying Dragonframe is the OS-focused app mirrors how the physical keyboard shortcut itself behaves — it also does nothing useful if focus is elsewhere. Adding detection machinery for a single-purpose app used almost exclusively alongside Dragonframe wasn't judged worth the added platform-specific code (`NSWorkspace` on macOS, `GetForegroundWindow` on Windows).
- **DragonMIDI runs the WebSocket server; Dragonframe is the client.** Dragonframe connects outward to `ws://localhost:59177/com.dzed.dragonframe/DragonframeConnection` at startup. DragonMIDI's WebSocket Output Adapter binds that port and accepts the connection — inverted from OSC out (DragonMIDI-initiated); Dragonframe does not listen on this channel.
- **A fixed, curated list of WebSocket target names, not a free-text field.** Dragonframe recognizes 19 static input names plus the dynamic `select-AXn`/`jog-AXn` pair; only `E-Stop`, `select-AXn`, and `jog-AXn` fill a gap no other output path covers. The mapping editor's WebSocket target picker offers only these, mirroring how OSC action targets are picked from a known list rather than typed freehand.
- **WebSocket output fails silently on bind failure**, matching the Keystroke precedent above — if port 59177 is already held, the adapter logs the failure and WebSocket-mapped controls do not fire; no third status indicator, no retry-with-backoff UI.

## Success Metrics

- Moving any enabled fader/knob/button lights the MIDI indicator within ~1 second and dims it again within a few seconds of going quiet.
- With Dragonframe's OSC Output pointed at DragonMIDI's listener, the Dragonframe indicator lights within ~1 second of any Dragonframe-originated OSC event.
- Querying `getAllPosition` against a project with configured axes returns responses that DragonMIDI correctly parses into that project's exact axis names.
- A fader mapped to a discovered axis, with a configured min/max range, produces `gotoPosition` messages scaled correctly into that range on every distinct value, with no debounce.
- Every control in the default preset produces the identical OSC address/argument shape as the prototype's `mappings.md` for the same physical control moves.
- The mapping view always reflects what the engine actually enforces: editing an assignment, restarting, and moving the control fires the *new* assignment, not the old default.
- Turning the jog wheel steps the timeline frame-by-frame both on the main Animation/Cinematography timeline (via OSC) and, with Dragonframe as the OS-focused app, inside the Arc Motion Control workspace (via the synthesized "Step Moco Forward"/"Step Moco Back" keystroke) — the latter has no OSC equivalent at all.
- A control mapped to a WebSocket target (`E-Stop`, `select-AXn`, or `jog-AXn`) sends the corresponding `{"input": "<name>"}` JSON command and Dragonframe recognizes it, verifiable via Dragonframe's debug log (e.g. `HARD STOP` for `E-Stop`).
- Falsification signal: either indicator lit while its channel has gone silent, or dark while traffic is genuinely flowing, means the liveness design has failed.
- Selecting nanoKONTROL2 from the Controller Profile dropdown and plugging one in brings the MIDI indicator live and drives Dragonframe via the nanoKONTROL2's default map, with jog-wheel- and Scene-button-only behaviors correctly absent rather than silently no-op.

## References

- Prior prototype — source of the Native Mode SysEx handshake and the default control mapping.
- KORG nanoKONTROL2 Owner's Manual — source of the nanoKONTROL2's physical control layout, operation-mode (DAW/CC mode) behavior, and confirmation that no Native-Mode-style handshake exists. Its default CC-number assignments are not in this manual (nor in Korg's separate Parameter Guide, which documents the editable fields but not their factory values) — see Key Design Decisions for how the map was confirmed instead.
