# Dragonframe OSC Messages — Research Notes

## Question

Does DragonMIDI's opinionated static map (`docs/llds/static-mapping.md`) cover the *complete* set of OSC actions Dragonframe supports, or only a subset?

## Method

The `baku89/dragonframe-osc` GitHub repository was initially consulted but is **not an official Dragonframe source** and should not be used as reference for Dragonframe's actual OSC command set.

Instead, the official manual was downloaded directly from dragonframe.com and read as primary source:

- `https://www.dragonframe.com/download/Using%20Dragonframe%202025.pdf`

The PDF was converted to text (`pdftotext`) to search for every literal `/dragonframe/...` address string in the document, and the actual "Open Sound Control (OSC) Preferences" screenshot (page 407) was viewed directly to read the real "Messages" list widget, rather than relying on prose summaries.

## Findings

Dragonframe's OSC input surface is made of **two separate mechanisms**, plus a separate OSC output mechanism.

### 1. Fixed named commands ("Messages" list, OSC Preferences screen)

The manual's OSC Preferences screenshot (Preferences → Open Sound Control, item B: "OSC messages that Dragonframe will respond to") was cropped at 7 visible entries, flagged at the time as possibly incomplete since the list widget is scrollable. **Confirmed incomplete** — the full list, copied directly from a running Dragonframe instance's own Messages list, is:

```
Shoot: /dragonframe/shoot [framecount]
Shoot Video Assist: /dragonframe/shootVideoAssist
Delete: /dragonframe/delete
Play: /dragonframe/play
Live: /dragonframe/live
Mute: /dragonframe/mute
Black: /dragonframe/black
Loop: /dragonframe/loop
Short Play: /dragonframe/shortPlay
Live Toggle: /dragonframe/liveToggle [bool]
Auto Toggle: /dragonframe/autoToggle
Opacity Down: /dragonframe/opacityDown
Opacity Up: /dragonframe/opacityUp
Step Forward: /dragonframe/stepForward
Step Backward: /dragonframe/stepBackward
Save: /dragonframe/save
```

This is the authoritative source (a live Dragonframe instance) and supersedes the manual-derived partial list.

### 2. Encoder / axis addressing (documented in prose, "Using an OSC Encoder" section, and confirmed against the live Messages list)

A separate mechanism, configured per-axis in the Arc Motion Control workspace, not shown in the "Messages" list above:

```
Message:  /dragonframe/encoder/{channel},f (value)     -- store a value for an encoder channel
Message:  /dragonframe/encoder/{channel}                -- get the value
Response: /dragonframe/encoder/{channel},f (value)

Message:  /dragonframe/encoderReset/{channel}           -- reset the stored value for a channel

Message:  /dragonframe/axis/{axisname}/gotoPosition,f (position)   -- move axis to absolute position
Message:  /dragonframe/axis/{axisname}/stepPosition,f (delta)      -- move axis by relative amount
Message:  /dragonframe/axis/{axisname}/getPosition                 -- get current position
Response: /dragonframe/axis/{axisname}/getPosition,f (position)

Message:  /dragonframe/axis/getAllPosition                          -- get all axis positions
Response: /dragonframe/axis/{axisname},f (position)   -- one response message per axis, name embedded in the address

Message:  /dragonframe/axis/{axisname}/setLimits [minEnabled] [min] [maxEnabled] [max]   -- set the axis's soft limits
Message:  /dragonframe/axis/{axisname}/setZero     -- set the axis's zero position
Message:  /dragonframe/axis/{axisname}/setHome      -- set the axis's home position
```

Note: there is no documented `getLimits` — an axis's configured min/max range cannot be discovered over OSC, only set (`setLimits`) or implicitly observed via streamed position values. This matters for anything that needs to scale an external control's 0-1 range into the axis's real range: that scaling has to be configured on the client side (DragonMIDI), not discovered from Dragonframe.

### 3. OSC output (separate from input entirely)

- **Live motor positions** (enabled via "Output Motor Positions" checkbox): as motors jog, shoot, or run live moves, Dragonframe sends:
  ```
  /dragonframe/axis/axisname [float position]   -- spaces in axis names become underscores
  /dragonframe/axis/FRAME [float frame]         -- current rig frame position, output as a pseudo-axis
  ```
- **User-configurable output events** ("Position Frame Event," "Shoot Event," "Delete Event" fields in OSC Preferences): fully custom OSC message templates using Dragonframe's own variable-substitution syntax. Example shown in the manual's default:
  ```
  /composition/selectedclip/transport/position "a" [frameTimeMillis]
  ```
  Available variables: `[frame]` (frame number, int), `[frameTime]` (frame time, double), `[frameTimeMillis]` (frame time in milliseconds, int), `[exposure]` (exposure number, starting at 1, int), `[exposureName]` (exposure name, e.g. "X1", "X2"), `[production]` (production name), `[scene]` (scene name), `[take]` (take name), `[stereoIndex]` (stereo position), `[imageFileName]` (file name, present with shoot/delete events).

## What DragonMIDI's opinionated map actually uses

From `docs/llds/static-mapping.md`:

- 7 of the 16 fixed named commands (mechanism 1): shoot, shootVideoAssist, delete, play, live, mute, black. Not yet used: loop, shortPlay, liveToggle, autoToggle, opacityDown, opacityUp, stepForward, stepBackward, save.
- The encoder/encoderReset half of mechanism 2: faders/knobs → `/dragonframe/encoder/{1-16}`, Mute/Solo → `/dragonframe/encoderReset/{1-16}`, jog wheel → `/dragonframe/encoder/17` (relative).

## What's not covered

1. **Direct axis-name addressing** (`gotoPosition` / `stepPosition` / `getPosition` / `getAllPosition` / `setLimits` / `setZero` / `setHome`) — not used anywhere in the current opinionated map. Faders/knobs route through numbered encoder channels instead, which the user assigns to axes inside Dragonframe's Arc workspace. (The old `DragonMIDI-vibed` prototype supported `gotoPosition`/`stepPosition` as a generic action type in its mapping editor, but its own shipped default preset didn't use them either.) **This is the mechanism the mapping-editor work now being built targets directly** — see `docs/high-level-design.md § Delivery Phasing`.
2. **9 of the 16 fixed named commands** (loop, shortPlay, liveToggle, autoToggle, opacityDown, opacityUp, stepForward, stepBackward, save) — real, available commands not yet wired to any control.
3. **Arbitrary custom OSC paths** — the old prototype's mapping editor had a "custom path" escape hatch reaching any OSC address; not yet restored.
4. **OSC output configuration** (mechanism 3) is Dragonframe-side only — DragonMIDI's OSC Listener (`docs/llds/osc-io.md`) currently only uses the *presence* of any output traffic as a liveness signal. Parsing the `getAllPosition` response specifically (to discover axis names) is now a requirement, not just a non-goal — see the HLD.

## Empirically validated: direct axis addressing (`getAllPosition` / `gotoPosition`)

Tested directly against a running Dragonframe instance (not just read from the manual), sending real OSC packets and reading real responses:

- **`getAllPosition` responses arrive wrapped in an OSC 1.0 `#bundle`**, not as a bare message — a decoder that only handles single messages will silently fail to parse it. Bundle format: `"#bundle\0"` (8 bytes) + an 8-byte OSC time tag + a sequence of `(int32 size, message bytes)` elements, each of which may itself be a message or a nested bundle.
- **The reply does not necessarily arrive at the address:port the query's sender socket happened to be bound to as its own local address** — sending the query from an unbound (ephemeral-port) socket while listening on a separate socket bound to the configured "Outgoing UDP Port" failed to receive anything. Sending the query from the *same* socket already bound to the listen port worked reliably. Client code should query using the same socket the listener is bound to, not a separate one, to be robust regardless of which convention Dragonframe uses internally.
- **An axis with `Connect: ArcMoco #1` (or presumably any real hardware Connect type) and `Function: Normal`, with no physical device actually attached, reports its position via `getAllPosition` but does *not* move in response to `gotoPosition`** — confirmed by sending a position, then re-querying and seeing the old value unchanged, repeated across multiple attempts, including with Dragonframe's "Ready to Capture" mode enabled. The command is silently accepted (no error) but has no effect.
- **Switching that same axis's `Function` to `Manual`** (the hand-cranked/no-motor mode described in the manual) **immediately made `gotoPosition` work** — sending a value and re-querying showed the new value correctly. This resolves the long-standing open question from `docs/dragonframe-gamepad-research.md` and earlier notes in this document: a fully hardware-free, OSC-addressable axis is possible, but **only** with `Function: Manual` — `Function: Normal` requires a genuinely connected real device before it will execute any position command, even though it happily reports a (static) position when merely queried.
- Sending `gotoPosition` while "Output motor positions" is enabled in OSC Preferences can produce **two near-identical responses** for one query: an unprompted broadcast triggered by the move itself (the general motor-position-streaming feature), plus the explicit `getAllPosition` reply. Both carry the same value in practice; client code should tolerate the duplicate rather than treat it as an error.

**Practical implication:** DragonMIDI's mapping view, when guiding a user to set up a direct-axis-targeted control, should note that the target axis's Function must be `Manual` (or otherwise not require real hardware) for the mapping to actually move anything — this is a Dragonframe-side project setup requirement DragonMIDI cannot detect or enforce over OSC (Function type isn't exposed in any response).

## Per-project setup: does an encoder channel need configuring in Dragonframe?

Yes. An OSC encoder channel number (e.g. `4`) is just an arbitrary numeric identifier — nothing in Dragonframe listens on it by default. To make `/dragonframe/encoder/4` actually move something, a user must open the **Arc Motion Control workspace**, select the axis they want it to drive, and set that axis's:

- **OSC encoder channel** — the number it should listen on (e.g. `4`)
- **OSC encoder scale** — how the incoming value maps to the axis's real range of motion
- **OSC encoder absolute** — whether incoming values are absolute position or relative step

This is a one-time setup step per axis, done entirely inside Dragonframe. DragonMIDI fixes which physical nanoKONTROL control sends which channel number (fader 4 → channel 4, etc.) but has no way to configure what a channel number actually drives inside Dragonframe.

## Reducing the setup burden: Axis Setup export/import (`.arcx`)

Dragonframe has a built-in way to save and reuse this per-axis configuration across projects, in the same Arc Motion Control workspace:

- **Export**: workspace menu → `EXPORT | ARC AXIS SETUP (ARCX)` → saves an `.arcx` file.
- **Import**: workspace menu → `IMPORT | ARC AXIS SETUP (ARCX)` → loads one into another project.

Per the manual, this exports "the configuration information (**limits, channel**, etc) without exporting keyframe information" — "channel" is exactly the OSC encoder channel field described above, alongside encoder scale, absolute/relative, and axis limits. The manual's own stated use case matches this exactly: *"if you always work with a particular rig, exporting an axis setup would allow you to quickly start a new project without having to re-configure each axis on your rig."*

**Implication:** configure a set of axes once inside Dragonframe with channels 1–17 wired to match DragonMIDI's opinionated map (faders on 1–8, knobs on 9–16, jog wheel on 17), export that as a reusable `.arcx` template, and import it into any new Dragonframe project instead of re-entering channel/scale/absolute settings per axis each time. This reduces per-project setup to a one-time template plus an import step.

**Caveats — not yet resolved from the manual alone:**
1. The manual documents the *menu commands* but not the `.arcx` file's actual format (XML vs. proprietary binary, schema, etc.) — it's described purely as something Dragonframe itself writes and reads via its own dialogs, not a format documented for hand-authoring or third-party generation without reverse-engineering it.
2. It has to be created by first configuring at least one axis manually inside Dragonframe and exporting *from* a real project — no indication Dragonframe ships a blank/starter template, so the first `.arcx` still requires one round of manual setup.
3. Whether DragonMIDI could ever *generate* an `.arcx` file directly (skipping the manual-template step entirely) depends entirely on caveat 1 — this would need either official format documentation from Dragonframe or careful reverse-engineering of an exported sample file.

## Conclusion

DragonMIDI's opinionated map covers 7 of 16 fixed named commands and only the encoder half of the encoder/axis mechanism. It is **not** the complete set of OSC actions Dragonframe supports. Direct axis-name addressing (`gotoPosition`/`stepPosition`) — previously left out by the "opinionated, no editor" scope — is now the mechanism the mapping-editor work targets directly, since it addresses an axis by name without requiring the user to separately configure an OSC encoder channel inside Dragonframe.

## References

- `Using Dragonframe 2025.pdf`, dragonframe.com — "Using an OSC Encoder" (p. 304-305) and "Open Sound Control (OSC) Preferences" (p. 407) sections.
- `docs/llds/static-mapping.md` — DragonMIDI's opinionated map.
- `docs/llds/osc-io.md` — DragonMIDI's OSC transport, including the liveness-only use of OSC output traffic.
