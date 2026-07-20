# Dragonframe's Monogram WebSocket Channel — Reference

A third Dragonframe control surface, distinct from OSC (`docs/dragonframe-messages-research.md`) and keyboard Hot Keys (`docs/dragonframe-hotkeys-research.md`): Dragonframe ships a bundled **Monogram Creative Console** integration and, at startup, opens an outbound WebSocket connection that accepts the same kind of "input" commands a real Monogram hardware console would send. Discovered and live-tested 2026-07-19 against a real, running Dragonframe 2026 instance (scratch project) — not from documentation, since none of this is publicly documented by either Dragonframe or Monogram.

## How It Was Found

Dragonframe's app bundle includes its own Monogram integration package at `Dragonframe 2026.app/Contents/Resources/dragonframe.monogram/` (also present as a standalone copy on the user's Desktop). This package is the standard third-party format Monogram Creator (Monogram's own hub app) uses to discover and load app integrations — it is *not* Dragonframe-specific in structure, and a generic example (`(any)`) with the identical file layout was found bundled inside Monogram's own installer.

- **`config.json`**: declares the app identity and connection type.
  ```json
  {
    "name": "Dragonframe",
    "id": "com.dzed.dragonframe",
    "connection": [
      { "name": "DragonframeConnection", "type": "websocket" }
    ]
  }
  ```
- **`inputs.json`**: the static list of commands Dragonframe offers (see below).
- **`profiles/animator.monogram`**: one example Monogram-hardware-to-input mapping (not needed to drive the channel directly — it's what a real Monogram console button/dial would be configured to send).
- **`signature.txt`**: a base64 signature blob, presumably for package integrity verification by Monogram Creator; not needed to use the channel.

The actual wire protocol (port number, message framing, connection-ID encoding) is not in Dragonframe's package at all — it comes from Monogram Service's own code, found unminified in Monogram's official installer payload: `~/github/monogram-5.9.1-alpha.2-macos-x86-x64-installer/Monogram_Installer_internal_offline.app/Contents/Resources/installer.dat` (a Qt resource archive). An already-extracted copy of the installed app was found at `/private/tmp/monogram_extract/Monogram Creator Internal.app/Contents/MacOS/Monogram Service.app/Contents/Resources/build/service.ts` — a full, readable (webpack-bundled but not minified/obfuscated) TypeScript source for Monogram Service, ~145,000 lines. All protocol details below trace back to this file. Monogram itself is *not* installed on the machine used for this research; only the installer and this pre-extracted copy exist locally.

## Connection

- **Monogram Service is the WebSocket server**; Dragonframe (and any other integrated app) is the **client**. This is the opposite of what the naming might suggest.
- **Well-known port: `59177`** (`WEBSOCKET_SERVER_PORT` constant in `service.ts`, `src/service/server/websocket-server.ts`). Bound to `system.localhost` (loopback) only.
- **Connection URL**: `ws://localhost:59177/<connectionId>`, where `connectionId` is `<appId>/<connectionName>` — for Dragonframe, `com.dzed.dragonframe/DragonframeConnection`, giving the full URL `ws://localhost:59177/com.dzed.dragonframe/DragonframeConnection`. Confirmed by `App.getConnectionDetails(id)` in `service.ts`, which does `id.split('/')` into `[appId, connectionName]`, and by the connection-ID validation regex `CONNECTION_ID_PATTERN = /^[a-z][a-z0-9_-]*(\.[a-z0-9_-]+)+[0-9a-z_-]\/[a-z][a-z0-9_-]*$/i`.
- **Dragonframe connects on its own at startup**, with no Monogram installation required to observe this — confirmed by `lsof` showing an existing (closed) connection record to port 59177 before any listener existed, and then a live connection once one did.
- **Dragonframe retries in the background.** Reconnect timing observed to vary — sometimes within ~10-15 seconds of a prior disconnect, other times up to ~90 seconds. No relaunch of Dragonframe is needed to get a fresh connection; closing the listening socket from the server side is enough to trigger Dragonframe's own retry logic.

## Wire Format

Newline-delimited JSON, confirmed directly in `service.ts`'s `JsonProtocol` class:

```js
encode(message) {
  return (JSON.stringify(message) || '') + os.EOL;
}
```

Two message shapes, both found as real examples in Monogram's own source comments (`src/service/protocol/json.ts` doc block):

```json
{ "input": "Import", "operation": "", "params": [] }
{ "input": "Jog", "operation": "+", "params": [1] }
{ "input": "Jog", "operation": "+", "params": [-1] }
{ "input": "Contrast", "operation": "=", "params": [42] }
```

In practice, a bare `{"input": "<name>"}` (no `operation`/`params`) works for one-shot trigger commands — confirmed by `{"input": "Shoot"}` successfully capturing a frame.

## Handshake / Session Shape (Dragonframe → us)

Observed sequence on every fresh connection, with a diagnostic listener standing in for Monogram Service:

1. `{"status":"ok"}` — Dragonframe's own greeting.
2. A `replaceInputList` command, declaring the currently-available dynamic inputs:
   ```json
   {"command":{"commandString":"replaceInputList","inputArray":[
     {"label":"Jog Axis.AX1","name":"jog-AX1","reset":0,"step":1,"temporary":true},
     {"label":"Select Axis.AX1","name":"select-AX1","temporary":true},
     {"label":"Jog Axis.AX2","name":"jog-AX2","reset":0,"step":1,"temporary":true},
     {"label":"Select Axis.AX2","name":"select-AX2","temporary":true}
   ]}}
   ```
   Generated live from the current project's configured axes (`jog-{axisname}` / `select-{axisname}` pairs) — not a fixed list, and not present at all in the static `inputs.json`. Observed identically whether or not the axes were marked "Animator Controlled" in Dragonframe's Axis Setup.
3. Periodic `setInputColor` commands, e.g. `{"command":{"color":"#00ffcc","commandString":"setInputColor","input":"jog-AX2"}}` — Dragonframe telling a real Monogram device what LED/button color to display per input. Sent in bursts (all current inputs at once) both on connect and after certain state changes.

## Static Inputs (`inputs.json`)

```json
[
  { "name": "Shoot" },
  { "name": "Test Shot" },
  { "name": "Live" },
  { "name": "Play" },
  { "name": "Loop" },
  { "name": "Black" },
  { "name": "Delete" },
  { "name": "Auto Toggle" },
  { "name": "Short Play" },
  { "name": "Reverse" },
  { "name": "Hi-Res Toggle" },
  { "name": "Step Forward" },
  { "name": "Step Backward" },
  { "name": "E-Stop" },
  { "name": "Step", "range": [-5, 0], "step": 1, "reset": 0 },
  { "name": "Onion Skin", "range": [0, 100], "step": 2, "reset": 0 },
  { "name": "Jog All", "step": 1, "reset": 0 },
  { "name": "Audio Character", "step": 1, "reset": 0 },
  { "name": "Audio Shape", "step": 1, "reset": 0 }
]
```

**Naming correspondence with OSC** (`docs/dragonframe-messages-research.md`) — 8 of these map essentially 1:1 to OSC's fixed named commands, just Title Case vs. camelCase, strongly suggesting both surfaces are generated from the same internal Dragonframe action registry, curated independently into each preference pane:

| OSC | Monogram | |
|---|---|---|
| `shoot` | `Shoot` | same |
| `delete` | `Delete` | same |
| `play` | `Play` | same |
| `live` | `Live` | same |
| `black` | `Black` | same |
| `loop` | `Loop` | same |
| `shortPlay` | `Short Play` | same |
| `autoToggle` | `Auto Toggle` | same |
| `stepForward` | `Step Forward` | same |
| `stepBackward` | `Step Backward` | same |
| `opacityUp`/`opacityDown` | `Onion Skin` (ranged) | same feature, different shape |
| `mute`, `shootVideoAssist`, `liveToggle`, `save` | *(none found)* | OSC-only |
| *(none)* | `Test Shot`, `E-Stop`, `Reverse`, `Hi-Res Toggle`, `Step`, `Jog All`, `Audio Character`, `Audio Shape` | Monogram-only |

`inputs.json` is very likely a **curated subset** for Monogram Creator's own assignment UI, not necessarily an exhaustive list of everything Dragonframe's WebSocket handler will accept — this can't be fully verified since Dragonframe itself is closed-source (unlike Monogram Service, whose installer payload could be read directly).

## Live Test Results (2026-07-19, real Dragonframe, scratch project)

| Input sent | Result | Confidence |
|---|---|---|
| `{"input": "Shoot"}` | **Captured an actual frame.** Full round-trip confirmed. | Confirmed |
| `{"input": "select-AX2"}` | Recolored `select-AX2` and `Jog All` to the same color — confirmed it retargets which axis subsequent generic actions (like `Jog All`) apply to. | Confirmed |
| `{"input": "Step", "operation": "+", "params": [1]}` | **No effect**, tested 4 times. One early sighting of a keyframe appearing was later attributed to a coincidental, unrelated action (most likely the `Shoot` test or an axis-configuration change) — not reproduced in two subsequent deliberately-watched attempts. | Debunked false lead |
| Toggling the axis power/enable icon in Dragonframe's own UI (nothing sent, log-only) | Triggered a fresh burst of `setInputColor` messages; `Jog All`'s color alternated red (`#ff0000`)/blue (`#0000a8`) with each toggle — plausibly "an axis is disabled" vs. normal. | Confirmed observable (state is reported) |
| `enable-AX1`, `disable-AX1`, `power-AX1`, `toggle-AX1`, `{"input":"Enable","params":["AX1"]}`, `{"input":"Disable","params":["AX1"]}` (six candidates, sent individually ~5s apart) | **No effect, no response message at all** for any of them — unlike every working input above, which always produced at least a `setInputColor` echo. | Six clean misses; not proof the mechanism doesn't exist, but confidence lowered |

## Related Protocols Checked and Ruled Out

Both found in `Dragonframe 2026.app/Contents/Resources/`, both investigated as possible alternate paths to the same open questions (axis enable/disable, keyframe control), both set aside:

- **DMC binary protocol** (`Arc Motion Control/dmc/dmc_m7/`, `dmc_msg.h`/`dmc_msg.cpp`) — the real protocol Dragonframe uses to talk to DMC-class real-time motion-control hardware. Well-documented in the source: every message starts with magic bytes `"DF"`, then a 10-byte header (4-byte message ID, 2-byte type, 2-byte length), payload, and a 2-byte checksum. Message IDs include exactly what this investigation wanted — `DMC_MOTOR_CONFIG_ENABLED`, `DMC_MSG_MOTOR_HARD_STOP` (E-Stop), `DMC_MSG_RT_JOG_ALL`, etc. — but the protocol is **Dragonframe commanding hardware**, not hardware/a peer requesting Dragonframe do something. `DMC_MOTOR_CONFIG_ENABLED` is a flag Dragonframe sends *downstream* when the user clicks the power icon in its own UI; there's no message shape for a request flowing the other way. To use this, DragonMIDI would need to impersonate a physical motor rig, which doesn't create a path for DragonMIDI-originated requests — the opposite of what's needed. Also a safety-critical domain (real motor drive control) well outside DragonMIDI's current scope.
- **DFRemote "Simple Serial Interface"** (`DFRemote/DFRemote.ino`, connects via Scene → Connections → DFRemote Arduino as a serial port connection) — Dragonframe's own officially-documented protocol (spec published at `dragonframe.com/arduino/serial.php`). Simple text commands: `S <frames>\r\n` (Shoot), `D\r\n` (Delete), `P\r\n` (Play/toggle), `L\r\n` (Live) outbound; `SH`/`DE`/`PF`/`CC`-prefixed notifications inbound. Ruled out: strictly smaller command set than what the Monogram channel already offers, nothing new for the open questions.

## Architecture Implication for DragonMIDI

This is a genuinely new, third output path alongside OSC and keystroke synthesis (`docs/llds/keystroke-output.md`) — and unlike keystroke synthesis, it's a real app-level API Dragonframe's own developers built for exactly this purpose (external controller → Dragonframe action), with none of the jogpad-mode precondition risk that blocked several keystroke-based ideas (`docs/nanokontrol-mapping-proposal.md`). Building on it would mean adding a WebSocket client component to DragonMIDI — a real architectural addition, not yet decided, warranting its own HLD-level discussion before any implementation. See `docs/nanokontrol-mapping-proposal.md` for how specific proposed nanoKONTROL mappings map onto what's confirmed here.

## Open Questions

1. Whether `inputs.json` is exhaustive of what Dragonframe's WebSocket handler accepts, or just a curated subset for Monogram Creator's UI — unresolved, and probably unresolvable without either finding more undocumented input names empirically or inspecting Dragonframe's own (closed-source) binary.
2. What `Step` and its declared `[-5, 0]` range actually do, if anything — genuinely unknown after debunking the keyframe hypothesis.
3. Whether axis enable/disable is settable via *any* Monogram input name — six guesses failed, but not exhaustive.
4. What `Onion Skin`, `Jog All`, `Audio Character`, and `Audio Shape` actually do when sent — none tested yet, only `Shoot`, `select-AXn`, and `Step` have been.
5. Whether a full Dragonframe relaunch (vs. just a fresh socket connection) would change any of the above — not tested; all reconnects tested were the app's own background retry, not a cold start.

## How to Reproduce This Testing

A minimal Python listener (using the `websockets` package) bound to `127.0.0.1` **and** `::1` on port 59177 (Dragonframe's connection was observed to prefer IPv6 for `localhost`) will receive Dragonframe's connection in place of Monogram Service, with no Monogram installation needed. Send newline-terminated JSON (`json.dumps(message) + os.linesep`) over the accepted connection to test candidate inputs; log everything received to see Dragonframe's own responses (`setInputColor`, `replaceInputList`). No probe script from this session was preserved in the repo (scratchpad-only); rebuild from the wire format documented above if resuming this investigation.

## References

- `~/github/monogram-5.9.1-alpha.2-macos-x86-x64-installer` — Monogram's own installer, source of `service.ts` and all protocol/port/framing details.
- `/private/tmp/monogram_extract/Monogram Creator Internal.app` — a pre-existing extracted copy found locally; not created by this research.
- `~/Desktop/dragonframe.monogram` and `/Applications/Dragonframe 2026/Resources/dragonframe.monogram` — Dragonframe's own Monogram integration package (byte-identical copies).
- `/Applications/Dragonframe 2026/Resources/Arc Motion Control/dmc/` — DMC binary protocol source, ruled out (see above).
- `/Applications/Dragonframe 2026/Resources/DFRemote/` — Simple Serial Interface source and README, ruled out (see above).
- `docs/dragonframe-messages-research.md` — the OSC surface this channel's naming was cross-referenced against.
- `docs/dragonframe-hotkeys-research.md` — the Hot Keys surface, including the "Mute" OSC command's actual behavior (audio playback mute, unrelated to axis muting).
- `docs/nanokontrol-mapping-proposal.md` — how these findings map onto specific proposed nanoKONTROL Studio control assignments.
