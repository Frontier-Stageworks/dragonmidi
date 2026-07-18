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

Confirmed directly from the OSC Preferences screenshot (Preferences → Open Sound Control, item B: "OSC messages that Dragonframe will respond to"). The visible list shows exactly:

```
Shoot: /dragonframe/shoot [framecount]
Shoot Video Assist: /dragonframe/shootVideoAssist
Delete: /dragonframe/delete
Play: /dragonframe/play
Live: /dragonframe/live
Mute: /dragonframe/mute
Black: /dragonframe/black
```

**Caveat:** the "Messages" box in the screenshot is a scrollable list widget, and the screenshot is cropped right at the "Black:" line. It is not 100% certain there isn't an 8th+ command scrolled below the visible area. This should be checked directly in a running copy of Dragonframe (Preferences → Open Sound Control) for full certainty.

### 2. Encoder / axis addressing (documented in prose, "Using an OSC Encoder" section)

A separate mechanism, configured per-axis in the Arc Motion Control workspace, not shown in the "Messages" list above:

```
Message:  /dragonframe/encoder/{channel},f (value)     -- store a value for an encoder channel
Message:  /dragonframe/encoder/{channel}                -- get the value
Response: /dragonframe/encoder/{channel},f (value)

Message:  /dragonframe/encoderReset/{channel}           -- reset the stored value for a channel

Message:  /dragonframe/axis/{axisname}/gotoPosition,f (position)   -- move axis to absolute position
Message:  /dragonframe/axis/{axisname}/stepPosition,f (position)   -- move axis by relative amount
Message:  /dragonframe/axis/{axisname}/getPosition                 -- get current position
Response: /dragonframe/axis/{axisname}/getPosition,f (position)

Message:  /dragonframe/axis/getAllPosition                          -- get all axis positions
Response: /dragonframe/axis/{axisname},f (position)   -- one response message per axis
```

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
  Available variables: `[frame]` (frame number, int), `[frameTime]` (frame time in double), `[frameTimeMillis]` (frame time in milliseconds, int), `[exposure]` (exposure number, starting at 1, int), `[exposureName]` (exposure name, e.g. "X1", "X2"), `[production]` (production name), `[scene]` (scene name).

## What DragonMIDI's opinionated map actually uses

From `docs/llds/static-mapping.md`:

- All 7 fixed named commands (mechanism 1): shoot, shootVideoAssist, delete, play, live, mute, black.
- The encoder/encoderReset half of mechanism 2: faders/knobs → `/dragonframe/encoder/{1-16}`, Mute/Solo → `/dragonframe/encoderReset/{1-16}`, jog wheel → `/dragonframe/encoder/17` (relative).

## What's not covered

1. **Direct axis-name addressing** (`gotoPosition` / `stepPosition` / `getPosition` / `getAllPosition`) — not used anywhere in the opinionated map. Faders/knobs route through numbered encoder channels instead, which the user assigns to axes inside Dragonframe's Arc workspace. (The old `DragonMIDI-vibed` prototype supported these as a generic action type in its mapping editor, but its own shipped default preset didn't use them either.)
2. **Arbitrary custom OSC paths** — the old prototype's mapping editor had a "custom path" escape hatch reaching any OSC address; DragonMIDI has no mapping editor in this phase, so there is no way to reach any address outside the fixed table.
3. **OSC output configuration** (mechanism 3) is Dragonframe-side only — DragonMIDI's OSC Listener (`docs/llds/osc-io.md`) only uses the *presence* of any output traffic as a liveness signal; it does not configure, request, or interpret Dragonframe's output event templates or motor-position stream.

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

DragonMIDI's opinionated map is a complete implementation of Dragonframe's fixed named-command list (mechanism 1) and a partial, encoder-only implementation of the encoder/axis mechanism (mechanism 2). It is **not** the complete set of OSC actions Dragonframe supports — direct axis addressing and arbitrary custom paths are both real Dragonframe capabilities left out by this phase's "opinionated, no editor" scope, not by oversight.

## References

- `Using Dragonframe 2025.pdf`, dragonframe.com — "Using an OSC Encoder" (p. 304-305) and "Open Sound Control (OSC) Preferences" (p. 407) sections.
- `docs/llds/static-mapping.md` — DragonMIDI's opinionated map.
- `docs/llds/osc-io.md` — DragonMIDI's OSC transport, including the liveness-only use of OSC output traffic.
