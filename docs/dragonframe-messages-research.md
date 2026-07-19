# Dragonframe OSC Messages — Reference

Dragonframe's OSC input surface has two mechanisms, plus a separate OSC output mechanism.

## 1. Fixed Named Commands

The complete "Messages" list (Preferences → Open Sound Control):

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

## 2. Encoder / Axis Addressing

Configured per-axis in the Arc Motion Control workspace; not part of the Messages list above.

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

There is no `getLimits` — an axis's configured min/max range can be set (`setLimits`) but not read back over OSC. Scaling an external control's 0–1 range into an axis's real range must be configured client-side, not discovered from Dragonframe.

## 3. OSC Output

- **Live motor positions** (enabled via "Output Motor Positions"): as motors jog, shoot, or run live moves, Dragonframe sends:
  ```
  /dragonframe/axis/axisname [float position]   -- spaces in axis names become underscores
  /dragonframe/axis/FRAME [float frame]         -- current rig frame position, output as a pseudo-axis
  ```
- **User-configurable output events** ("Position Frame Event," "Shoot Event," "Delete Event" fields in OSC Preferences): custom OSC message templates using Dragonframe's variable-substitution syntax. Default example:
  ```
  /composition/selectedclip/transport/position "a" [frameTimeMillis]
  ```
  Variables: `[frame]` (frame number, int), `[frameTime]` (frame time, double), `[frameTimeMillis]` (frame time in milliseconds, int), `[exposure]` (exposure number, starting at 1, int), `[exposureName]` (exposure name, e.g. "X1", "X2"), `[production]` (production name), `[scene]` (scene name), `[take]` (take name), `[stereoIndex]` (stereo position), `[imageFileName]` (file name, present with shoot/delete events).

## Axis Discovery and Direct Addressing

- `getAllPosition` responses arrive wrapped in an OSC 1.0 `#bundle`, not a bare message: `"#bundle\0"` (8 bytes) + an 8-byte OSC time tag + a sequence of `(int32 size, message bytes)` elements, each itself a message or a nested bundle.
- The discovery query must be sent from the same socket the listener is bound to, not a separate socket — sending from an unbound/ephemeral socket while listening on the configured "Outgoing UDP Port" does not receive a reply.
- An axis with a real hardware `Connect` type (e.g. `ArcMoco #1`) and `Function: Normal`, with no physical device attached, reports its position via `getAllPosition` but does not move in response to `gotoPosition` — the command is accepted without error but has no effect, including with "Ready to Capture" enabled.
- Setting that axis's `Function` to `Manual` makes `gotoPosition` move it as expected. `Function: Manual` is required for a hardware-free, OSC-addressable axis; `Function: Normal` requires a genuinely connected device to execute position commands, even though it reports a static position when merely queried. Function type is not exposed in any OSC response, so DragonMIDI cannot detect or enforce this — it is a Dragonframe-side project setup requirement.
- With "Output motor positions" enabled, a `gotoPosition` command can produce two near-identical responses for one query: an unprompted motor-position broadcast plus the explicit `getAllPosition` reply, carrying the same value. Client code must tolerate the duplicate.
- A project with zero Arc axes configured sends no response at all to `getAllPosition` — not an empty bundle, complete silence. Client code cannot distinguish "not yet answered" from "answered with zero axes" by waiting; it must use a timeout.

## Per-Project Setup: Encoder Channels

An OSC encoder channel number (e.g. `4`) is an arbitrary numeric identifier — nothing in Dragonframe listens on it by default. To make `/dragonframe/encoder/4` drive an axis, open the **Arc Motion Control** workspace, select the axis, and set:

- **OSC encoder channel** — the number it listens on (e.g. `4`)
- **OSC encoder scale** — how the incoming value maps to the axis's real range of motion
- **OSC encoder absolute** — whether incoming values are absolute position or relative step

This is a one-time setup step per axis, done entirely inside Dragonframe.

## Axis Setup Export/Import (`.arcx`)

Dragonframe can save and reuse per-axis configuration across projects, in the Arc Motion Control workspace:

- **Export**: workspace menu → `EXPORT | ARC AXIS SETUP (ARCX)` → saves an `.arcx` file.
- **Import**: workspace menu → `IMPORT | ARC AXIS SETUP (ARCX)` → loads one into another project.

This exports channel, limits, scale, and absolute/relative settings without keyframe data — configure a rig's axes once, export as a template, and import into new projects instead of re-entering settings per axis.

Open items:
1. The `.arcx` file format (XML vs. proprietary binary, schema) is not documented — Dragonframe writes and reads it only through its own dialogs.
2. Creating one requires configuring at least one axis manually and exporting from a real project first; there is no blank/starter template.

## What DragonMIDI Uses

- **Fixed named commands**: `shoot`, `shootVideoAssist`, `delete`, `play`, `live`, `mute`, `black`, `loop`, `stepForward`, `stepBackward`. Not used: `shortPlay`, `liveToggle`, `autoToggle`, `opacityDown`, `opacityUp`, `save`.
- **Encoder / encoderReset**: knobs, mute/solo, and faders not retargeted to a direct axis use `/dragonframe/encoder/{1-17}` / `/dragonframe/encoderReset/{1-17}`.
- **Direct axis addressing** (`gotoPosition`, `getAllPosition`): used by the Mapping View's OSC axis (direct) target type, faders only (`docs/llds/static-mapping.md`, `docs/llds/app-ui.md`).
- **Not used**: `stepPosition`, `setLimits`, `setZero`, `setHome`, arbitrary custom OSC paths, and OSC output beyond liveness and `getAllPosition` parsing (`docs/llds/osc-io.md`).

## References

- `Using Dragonframe 2025.pdf`, dragonframe.com — "Using an OSC Encoder" (p. 304–305) and "Open Sound Control (OSC) Preferences" (p. 407).
- `docs/llds/static-mapping.md` — DragonMIDI's opinionated map.
- `docs/llds/osc-io.md` — DragonMIDI's OSC transport, including axis discovery.
- `docs/llds/app-ui.md` — Mapping View, including the OSC axis (direct) target type.
