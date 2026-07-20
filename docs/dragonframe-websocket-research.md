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
- **Dragonframe's reconnect is focus-triggered, not periodic.** Initial testing assumed a background retry timer (reconnects were observed at varying ~10-90s intervals), but a later fuzzing run stalled with no reconnect for over 10 minutes with Dragonframe in the background. Its debug log showed the actual trigger: `*** ApplicationActivate` / `Activating workspace on change event` — Dragonframe reconnects when it regains OS focus, not on a timer. Clicking the Dragonframe window to bring it forward reliably triggers an immediate reconnect. No relaunch is needed, only a fresh socket connection from the server side (or a focus change) to get Dragonframe to reconnect.

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

## The Log-File Oracle

Watching the WebSocket wire (does Dragonframe send back a `setInputColor` echo?) and watching the UI (did anything visibly happen?) are both unreliable signals — a valid-but-currently-inert input produces neither, indistinguishable over the wire from an input Dragonframe doesn't recognize at all. Dragonframe's own debug log resolves this completely.

**Log location**: `~/Library/Logs/Dragonframe.txt` (rotated as `-2`/`-3`/`-4` on relaunch). Dragonframe logs every single Monogram message it receives, recognized or not:

- **Unrecognized input** → `[D] UNKNOWN Mono MSG:  "<raw json as sent, escaped>"`. This line fires for *every* input name Dragonframe's Monogram handler doesn't have a case for — a complete, unambiguous negative oracle. No false negatives observed: every candidate later confirmed rejected below produced exactly this line, and every candidate confirmed valid (see below) never produced it, even when it had no visible effect.
- **Recognized input** → a distinctive, action-specific log line instead of (or alongside) any `setInputColor` echo. Examples observed directly in this session's logs: `SHOOT TEST AVFCapture(...)` for `Test Shot`, `HARD STOP` for `E-Stop`, and the sequence `initiateJogging` → `joggerEnabled = true` → `updateJogSpeed: value=N` → `stopJogging` for `Jog All`. These confirm the input was recognized and dispatched even when nothing changed on screen (e.g. no axis currently jogging).

This makes "is `<name>` a real Monogram input Dragonframe recognizes?" answerable definitively after the fact, without needing to watch the UI live or trust wire-level silence — just send the candidate, then grep the log for `UNKNOWN Mono MSG` containing that candidate's JSON. Absence of that line, for a message actually delivered, means the input was recognized.

## Live Test Results (2026-07-19, real Dragonframe, scratch project)

| Input sent | Result | Confidence |
|---|---|---|
| `{"input": "Shoot"}` | **Captured an actual frame.** Full round-trip confirmed. | Confirmed |
| `{"input": "select-AX2"}` | Recolored `select-AX2` and `Jog All` to the same color — confirmed it retargets which axis subsequent generic actions (like `Jog All`) apply to. | Confirmed |
| `{"input": "Test Shot"}` | Logged `SHOOT TEST AVFCapture(...)` — recognized and dispatched. | Confirmed valid |
| `{"input": "E-Stop"}` | Logged `HARD STOP` — recognized and dispatched. | Confirmed valid |
| `{"input": "Jog All", ...}` | Logged `initiateJogging` / `joggerEnabled = true` / `updateJogSpeed: value=N` / `stopJogging` — recognized and dispatched. | Confirmed valid |
| `{"input": "Step", "operation": "+", "params": [1]}` | No visible effect in the UI across several tests. One early sighting of a keyframe appearing was traced to a coincidental, unrelated action (an earlier `Record` test), **not** to `Step` — debunked as a false lead. However, retroactively checking the log: `Step` was **never** logged as `UNKNOWN Mono MSG` in any of these tests. | **Confirmed valid, silent under current preconditions** — recognized by Dragonframe, but has no observed effect in this scratch project's current state. Not the same as "invalid": the earlier "debunked" verdict applied only to the keyframe hypothesis, not to whether `Step` is a real command. |
| `{"input": "Reverse"}`, `{"input": "Hi-Res Toggle"}`, `{"input": "Onion Skin", ...}`, `{"input": "Audio Character", ...}`, `{"input": "Audio Shape", ...}` | No visible UI effect observed; retroactively checked against the log — **none were ever logged as `UNKNOWN Mono MSG`**. | **Confirmed valid, silent under current preconditions** (likely require project state this scratch project doesn't have: an audio track loaded for the Audio* inputs, a specific display mode for Hi-Res Toggle, etc. — not yet determined which precondition each needs). |
| Toggling the axis power/enable icon in Dragonframe's own UI (nothing sent, log-only) | Triggered a fresh burst of `setInputColor` messages; `Jog All`'s color alternated red (`#ff0000`)/blue (`#0000a8`) with each toggle — plausibly "an axis is disabled" vs. normal. | Confirmed observable (state is reported) |
| `enable-AX1`, `disable-AX1`, `power-AX1`, `toggle-AX1`, `{"input":"Enable","params":["AX1"]}`, `{"input":"Disable","params":["AX1"]}` (six candidates, sent individually ~5s apart, ~20:54:12–20:54:37) | No response over the wire at the time. **Retroactively confirmed via the log-file oracle**: all six produced `UNKNOWN Mono MSG` lines (e.g. `UNKNOWN Mono MSG:  "{\"input\": \"enable-AX1\"}\n"`). | **Definitively rejected** — no longer just six clean misses, now proven via the oracle. |
| 31-candidate fuzz pass (listed below), sent 3s apart via a scratchpad probe script, checked against the log afterward | **All 31 produced `UNKNOWN Mono MSG`.** None recognized. | **Definitively rejected**, including every keyframe-related guess (`Set Keyframe`, `Keyframe`, `Add Keyframe`), axis-enable guesses (`Enable Axis`, `Disable Axis`, `Axis Enable`, `Axis Disable`, `Toggle Axis`, `Mute Axis`, `Record Axis`, `Solo Axis`), and general editing/transport guesses (`Undo`, `Redo`, `Mark In`, `Mark Out`, `Home`, `End`, `Save`, `Save Scene`, `Toggle Live View`, `Media Layer Toggle`, `Drawing Toggle`, `Grid Toggle`, `Solo Camera`, `Toggle Work Light`, `Step Moco Forward`, `Step Moco Back`, `Insert Camera`, `Return Camera to End`, `Hold Frame`, `3 Step`). |

### Monogram fuzz candidates, round 1 (31, all rejected)

```
Set Keyframe, Keyframe, Add Keyframe, Enable Axis, Disable Axis, Axis Enable,
Axis Disable, Toggle Axis, Mute Axis, Record Axis, Solo Axis, Undo, Redo,
Mark In, Mark Out, Home, End, Save, Save Scene, Toggle Live View,
Media Layer Toggle, Drawing Toggle, Grid Toggle, Solo Camera, Toggle Work Light,
Step Moco Forward, Step Moco Back, Insert Camera, Return Camera to End,
Hold Frame, 3 Step
```

### Monogram fuzz candidates, round 2 — Hot Keys action names (55, all rejected)

Every action name in `docs/dragonframe-hotkeys-research.md`'s Hot Keys table not already covered by round 1 or by a known `inputs.json` entry, sent verbatim (Title Case, as captured from the Hot Keys UI) plus two extra risky guesses the user pre-authorized. All 55 produced `UNKNOWN Mono MSG`, each cleanly correlated 1:1 by timestamp with its send — no exceptions, no ambiguity:

```
Shoot 2 Frames, Shoot 3 Frames, Shoot 4 Frames, Shoot Burst, Toggle Preview,
Live Toggle, Short Play Toggle, Cut Back, Reshoot Frames, Opacity Up,
Opacity Down, Opacity Up Fine, Opacity Down Fine, Mute, 3 Step Toggle,
Step by Holds, Play by Tag, Next Camera, Capture Making Of,
Guide Group #1 Toggle .. #8 Toggle, Media Layer Opacity Up,
Media Layer Opacity Down, Toggle X-Sheet/Guide Layers, Go to In Point,
Go to Out Point, Toggle Step by Tag, Show/Hide Hidden Frames, Add Hold,
Remove Hold, Hold On Still Image, Next Playback Exposure,
Prev Playback Exposure, Difference with Live, Toggle Focus Controls,
Toggle Focus Check, Toggle Focus Peaking, Increase Video Size,
Decrease Video Size, Increase Audio Latency, Decrease Audio Latency,
View Mirror, View Rotate, View Portrait, Next Panoramic View,
Script Custom 1, Script Custom 2, Script Custom 3, Script Custom 4
```

`Cut Back` (hotkey NUM 9 — can remove frames from the timeline) and `Reshoot Frames` (a guess, not a confirmed hotkey name) were included at the user's explicit pre-authorization for this scratch project; both were rejected, so no risk materialized.

**Takeaway**: across both rounds (86 candidates total, plus the original 6 axis-enable guesses = 92), the *only* names Dragonframe's Monogram handler recognizes are the ones already in `inputs.json` plus the dynamic `jog-AXn`/`select-AXn` pair. None of Dragonframe's much larger Hot Keys vocabulary (used for direct keyboard input) leaks into the Monogram protocol under its own action names. This is now fairly strong (not conclusive) evidence that `inputs.json`'s 19 static entries are the complete Monogram-recognized command set — Dragonframe's Monogram integration is a deliberately curated, much smaller surface than its keyboard shortcuts, not a superset or a 1:1 mirror of them.

## Related Protocols Checked and Ruled Out

Both found in `Dragonframe 2026.app/Contents/Resources/`, both investigated as possible alternate paths to the same open questions (axis enable/disable, keyframe control), both set aside:

- **DMC binary protocol** (`Arc Motion Control/dmc/dmc_m7/`, `dmc_msg.h`/`dmc_msg.cpp`) — the real protocol Dragonframe uses to talk to DMC-class real-time motion-control hardware. Well-documented in the source: every message starts with magic bytes `"DF"`, then a 10-byte header (4-byte message ID, 2-byte type, 2-byte length), payload, and a 2-byte checksum. Message IDs include exactly what this investigation wanted — `DMC_MOTOR_CONFIG_ENABLED`, `DMC_MSG_MOTOR_HARD_STOP` (E-Stop), `DMC_MSG_RT_JOG_ALL`, etc. — but the protocol is **Dragonframe commanding hardware**, not hardware/a peer requesting Dragonframe do something. `DMC_MOTOR_CONFIG_ENABLED` is a flag Dragonframe sends *downstream* when the user clicks the power icon in its own UI; there's no message shape for a request flowing the other way. To use this, DragonMIDI would need to impersonate a physical motor rig, which doesn't create a path for DragonMIDI-originated requests — the opposite of what's needed. Also a safety-critical domain (real motor drive control) well outside DragonMIDI's current scope.
- **DFRemote "Simple Serial Interface"** (`DFRemote/DFRemote.ino`, connects via Scene → Connections → DFRemote Arduino as a serial port connection) — Dragonframe's own officially-documented protocol (spec published at `dragonframe.com/arduino/serial.php`). Simple text commands: `S <frames>\r\n` (Shoot), `D\r\n` (Delete), `P\r\n` (Play/toggle), `L\r\n` (Live) outbound; `SH`/`DE`/`PF`/`CC`-prefixed notifications inbound. Ruled out: strictly smaller command set than what the Monogram channel already offers, nothing new for the open questions.

## Architecture Implication for DragonMIDI

This is a genuinely new, third output path alongside OSC and keystroke synthesis (`docs/llds/keystroke-output.md`) — and unlike keystroke synthesis, it's a real app-level API Dragonframe's own developers built for exactly this purpose (external controller → Dragonframe action), with none of the jogpad-mode precondition risk that blocked several keystroke-based ideas (`docs/nanokontrol-mapping-proposal.md`). Building on it would mean adding a WebSocket client component to DragonMIDI — a real architectural addition, not yet decided, warranting its own HLD-level discussion before any implementation. See `docs/nanokontrol-mapping-proposal.md` for how specific proposed nanoKONTROL mappings map onto what's confirmed here.

## Open Questions

1. Whether `inputs.json` is exhaustive of what Dragonframe's WebSocket handler accepts, or just a curated subset for Monogram Creator's UI — still not proven, but now fairly strongly evidenced: 92 candidates tried across three rounds (31 generic guesses, 6 axis-enable guesses, 55 of Dragonframe's own Hot Keys action names) were *all* rejected. Notably, round 2 specifically tried Dragonframe's much larger keyboard-shortcut vocabulary and found none of it recognized by the Monogram handler — the Monogram surface does not mirror or extend the Hot Keys surface, it's a small, independently curated subset. Not conclusive (a wordlist can never prove a negative), but no longer a live "probably a big list we just haven't found" concern.
2. What precondition(s) `Step`, `Reverse`, `Hi-Res Toggle`, `Onion Skin`, `Audio Character`, and `Audio Shape` need before they produce a visible effect — all six are now confirmed *valid, recognized* commands (never logged `UNKNOWN Mono MSG`), so the open question has narrowed from "do these exist" to "what state does the project need to be in" (e.g. an audio track loaded, a different display mode, an axis actively jogging). Not yet tested.
3. Whether axis enable/disable is settable via *any* Monogram input name — now effectively closed to "no evidence found": the original six guesses plus eight more axis-enable-shaped names from the fuzz pass (`Enable Axis`, `Disable Axis`, `Axis Enable`, `Axis Disable`, `Toggle Axis`, `Mute Axis`, `Record Axis`, `Solo Axis`) all definitively rejected via the log oracle. Not exhaustive, but the highest-confidence negative result obtained so far.
4. Set Keyframe — same status as (3): `Set Keyframe`, `Keyframe`, and `Add Keyframe` all definitively rejected via the log oracle. No candidate mechanism remains from wordlist guessing; would need a different approach (e.g. inspecting Monogram Creator's own assignment UI if ever installed, or the closed-source Dragonframe binary) to make further progress.
5. Whether a full Dragonframe relaunch (vs. just a fresh socket connection) would change any of the above — not tested; all reconnects tested were the app's own background retry (focus-triggered, see Connection above), not a cold start.
6. ~~User has pre-authorized a second, broader fuzzing round including riskier candidates (e.g. `Cut Back`, `Reshoot Frames`) — not yet run.~~ **Done** — round 2 (55 candidates, including these two) all rejected, see above.

## How to Reproduce This Testing

A minimal Python listener (using the `websockets` package) bound to `127.0.0.1` **and** `::1` on port 59177 (Dragonframe's connection was observed to prefer IPv6 for `localhost`) will receive Dragonframe's connection in place of Monogram Service, with no Monogram installation needed. Send newline-terminated JSON (`json.dumps(message) + os.linesep`) over the accepted connection to test candidate inputs.

**Preferred method: use the log-file oracle (see above), not the wire response.** Send candidates (a wordlist works fine, spaced a few seconds apart so log lines are attributable), then grep `~/Library/Logs/Dragonframe.txt` for `UNKNOWN Mono MSG` — anything not logged as unknown was recognized. If Dragonframe stops reconnecting mid-run, click its window to bring it to focus; reconnect is focus-triggered, not periodic. No probe script from this session was preserved in the repo (scratchpad-only); rebuild from the wire format documented above if resuming this investigation.

## References

- `~/github/monogram-5.9.1-alpha.2-macos-x86-x64-installer` — Monogram's own installer, source of `service.ts` and all protocol/port/framing details.
- `/private/tmp/monogram_extract/Monogram Creator Internal.app` — a pre-existing extracted copy found locally; not created by this research.
- `~/Desktop/dragonframe.monogram` and `/Applications/Dragonframe 2026/Resources/dragonframe.monogram` — Dragonframe's own Monogram integration package (byte-identical copies).
- `/Applications/Dragonframe 2026/Resources/Arc Motion Control/dmc/` — DMC binary protocol source, ruled out (see above).
- `/Applications/Dragonframe 2026/Resources/DFRemote/` — Simple Serial Interface source and README, ruled out (see above).
- `docs/dragonframe-messages-research.md` — the OSC surface this channel's naming was cross-referenced against.
- `docs/dragonframe-hotkeys-research.md` — the Hot Keys surface, including the "Mute" OSC command's actual behavior (audio playback mute, unrelated to axis muting).
- `docs/nanokontrol-mapping-proposal.md` — how these findings map onto specific proposed nanoKONTROL Studio control assignments.
