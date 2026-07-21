# DragonMIDI

DragonMIDI lets you control [Dragonframe](https://www.dragonframe.com/) (stop-motion capture software) with a **KORG nanoKONTROL Studio** or **nanoKONTROL2** MIDI controller. Plug in the controller, launch DragonMIDI, and its faders, knobs, and transport buttons act as physical controls for Dragonframe — playback, shooting, and moving motorized rig axes — instead of reaching for the mouse and keyboard every time.

**Unofficial project:** DragonMIDI is an independent interoperability utility and is not affiliated with, endorsed by, or supported by DZED Systems LLC or KORG. Product names and trademarks are the property of their respective owners. DragonMIDI does not include or redistribute Dragonframe software and requires a separately licensed Dragonframe installation.

**Motion-control safety:** DragonMIDI is not a safety system or a substitute for a physical emergency stop. Test mappings at low speed with the rig's travel area clear before operating connected motors.

## Quick start

1. **Install it** (see [Installing](#installing) below if you don't already have this set up).
2. **Turn on OSC in Dragonframe** (see [Configuring Dragonframe](#configuring-dragonframe) below) — a one-time setup per machine.
3. **Plug in your controller** — see [Using a nanoKONTROL Studio](#using-a-nanokontrol-studio) or [Using a nanoKONTROL2](#using-a-nanokontrol2) for anything device-specific — then run:
   ```bash
   dragonmidi
   ```
4. A window opens with a **Controller** dropdown at the top (defaults to nanoKONTROL Studio) — pick whichever one you plugged in. Below that: two status lights and a table of every control. Once both lights turn green, you're connected and every control below is live.

## Using a nanoKONTROL Studio

Nothing device-specific to do — plug it in, pick it in the Controller dropdown (the default), and DragonMIDI auto-detects it and puts it into Native Mode automatically over MIDI. It has the full control set described below, including the jog wheel and Scene button.

## Using a nanoKONTROL2

The nanoKONTROL2 needs a one-time manual step DragonMIDI can't do for you: putting it into **CC mode**.

1. Unplug the nanoKONTROL2's USB cable if it's connected.
2. Hold down the **SET MARKER** and **CYCLE** buttons.
3. While still holding both, plug the USB cable back in (or otherwise power it on).

It remembers CC mode across power cycles, so this is normally a one-time step per unit — unless something else (a DAW's own setup routine) later switches it into one of its other operating modes, in which case you'd repeat the steps above. DragonMIDI shows this same reminder in the status window whenever nanoKONTROL2 is selected in the Controller dropdown, so you don't need to remember it.

If you've previously customized this unit's control assignments (e.g. with Korg's Kontrol Editor) and want to start fresh, you can restore its factory defaults by holding **PREV TRACK + NEXT TRACK + CYCLE** while powering it on.

A few differences from the Studio:

- **No jog wheel and no Scene button** — the nanoKONTROL2 doesn't have either control, so frame-stepping via the wheel and the Scene→Black mapping aren't available. Every other control in the table below behaves the same as on the Studio.
- **No handshake to fail**, unlike the Studio's Native Mode — the MIDI status light can only show green (working) or gray (quiet) for a nanoKONTROL2, never amber. If it's plugged in, in CC mode, and selected in the dropdown but the light stays gray, double-check your OS actually sees the device (check your system's MIDI/audio device list).
- **CC-number mapping is carried over from the Studio's**, using commonly-documented factory-default values — this hasn't yet been confirmed against a real nanoKONTROL2 over MIDI. If a control doesn't do what the table below says it should, that mismatch is the most likely reason; please open an issue with what you're seeing.

## What each control does by default

DragonMIDI ships with a ready-to-use set of defaults — no setup required to start using the transport/shoot/marker buttons. This is the "Mapping" table you'll see in the app window. It's written from the nanoKONTROL Studio's control layout; the nanoKONTROL2's table is identical except it has no **Jog wheel**, **Return to Zero**, or **Scene button** rows — it has neither the jog wheel assembly nor the Scene button (see [Using a nanoKONTROL2](#using-a-nanokontrol2) above). Every other row below applies to both.

| Control | What it does in Dragonframe |
|---|---|
| Faders 1-8 | Drive a motion-control axis directly — pick which one in the Mapping table (see [Controlling a motor axis](#controlling-a-motor-axis) below) |
| Knobs 1-8 | Fine-tune nudge for the axis its own fader is driving (see below); drives an OSC encoder channel instead if that fader has no axis picked |
| Mute 1-8 | Marks the axis's *current* position as its zero reference, once its fader has an axis assigned; otherwise resets the fallback encoder channel |
| Solo 1-8 | Selects that motion-control axis, for use with Marker ◄/► below (see [Selecting and jogging an axis](#selecting-and-jogging-an-axis)) |
| Jog wheel | Step through the timeline frame-by-frame — turn clockwise to step forward, counterclockwise to step backward, one frame per detent. Also steps frames inside the Arc Motion Control workspace (see note below), where the main timeline step doesn't reach |
| Return to Zero | Not assigned — no matching Dragonframe action |
| Play | Play back your shot frames |
| Stop | Emergency-stop any motion-control axis currently moving |
| Transport Record (●) | Shoot one frame |
| Rewind (◄◄) / Fast Forward (►►) | Step one frame backward / forward |
| Cycle | Selects the next motion-control axis in turn, cycling back to the first after the last (see [Selecting and jogging an axis](#selecting-and-jogging-an-axis)) |
| Marker ◄/► | Jog the currently-selected axis backward/forward, one step per press (see [Selecting and jogging an axis](#selecting-and-jogging-an-axis)) |
| Track ◄/► | Step one frame backward / forward |
| Set Marker | Not assigned — no matching Dragonframe action |
| Scene button | Black out the display |

You don't need to memorize this — the app's window shows this same table live, alongside each control's current assignment.

**About the jog wheel and Arc Motion Control:** Dragonframe has no network command for stepping frames inside the Arc Motion Control workspace — the only way to do it is the `Option+Shift+Right`/`Option+Shift+Left` ("Step Moco Forward"/"Step Moco Back") keyboard shortcut. DragonMIDI reaches this by sending that exact keystroke to your computer, not by talking to Dragonframe directly, so two things follow:

- **Dragonframe must be the frontmost app** for the keystroke to land there — DragonMIDI doesn't check this for you, so turning the jog wheel while some other app is focused sends the keystroke to that app instead.
- **On macOS, you'll need to grant DragonMIDI Accessibility access** (System Settings → Privacy & Security → Accessibility) the first time this runs — without it, the keystroke is silently not sent (the main-timeline stepping still works either way, since that goes over OSC).
- If you've remapped "Step Moco Forward"/"Step Moco Back" to a different shortcut in Dragonframe's own Hot Keys preferences, DragonMIDI still sends the *default* combo above — it has no way to read your custom binding.

## The status window

When you run `dragonmidi`, you'll see:

- **Controller** — a dropdown to pick nanoKONTROL Studio or nanoKONTROL2. Defaults to nanoKONTROL Studio; switching it takes effect immediately (disconnects whichever device was connected and starts looking for the other one). When nanoKONTROL2 is selected, a reminder about getting it into CC mode appears right below (see [Using a nanoKONTROL2](#using-a-nanokontrol2)).
- **MIDI signal** — lights up when your selected controller is actively sending input.
- **Dragonframe signal** — lights up when Dragonframe is talking back to DragonMIDI. This is the one to watch to confirm the two apps are actually connected, not just that DragonMIDI is running.
- Each light is one of three colors:
  - 🟢 **Green** — working, recent activity.
  - 🟠 **Amber** — a real problem (the controller's handshake failed, or DragonMIDI couldn't open its network port). The nanoKONTROL2 has no handshake to fail, so its MIDI light only ever shows green or gray, never amber.
  - ⚪ **Gray** — quiet. Normal if nothing's happening right now; not an error.
- Below the lights: the network address DragonMIDI sends to and listens on, with an **Apply** button if you ever need to change them (most people never will).
- Below that: the **Mapping** table described above.

## Controlling a motor axis

Each fader, together with the knob and Mute button directly above/below it in the same column, forms a **bank**. Assigning an axis to the fader is the only step — the other two controls in that bank pick it up automatically:

| Control | Behavior once the bank's fader has an axis assigned |
|---|---|
| Fader | Drives the axis to an absolute position across the fader's travel |
| Knob | Nudges that axis by however far you just turned it — turning it further right moves the axis one way, further left the other way, proportional to the turn. Holding it still does nothing further. Useful for fine-tuning a position the fader got you close to. Can't push the axis below the fader's configured **min** or above its **max** — it stops exactly at whichever bound you reach. |
| Mute | Marks the axis's current position as its zero reference — it does **not** move the axis anywhere |

(Solo isn't part of this bank behavior — see [Selecting and jogging an axis](#selecting-and-jogging-an-axis) below.)

Faders start out already in this mode with no axis picked yet — until you pick one, that fader (and its bank) produces no output. To assign one:

1. In the app's Mapping table, find the fader's row. It defaults to **Target type: OSC axis** with an empty dropdown.
2. The dropdown lists the axis names DragonMIDI found in your currently-open Dragonframe project. Pick one.
   - If it says **"Discovering…"**, DragonMIDI is still checking — wait a second and it'll populate.
   - If it says **"No axes found"**, your current Dragonframe project doesn't have any motion-control axes set up yet.
   - Just added a new axis in Dragonframe, or opened a different project? Click **Rescan axes** to refresh the list.
3. Enter a **min** and **max** value next to the dropdown — this is the range the axis moves across as you slide the fader from empty to full. The knob's nudge is kept inside this same range (it stops at whichever bound it reaches, never overshoots); Mute's zero action isn't affected by min/max — it's a fixed Dragonframe command.

If you'd rather use the older encoder-channel approach for a given fader instead (see [Configuring Dragonframe](#configuring-dragonframe) below), switch that fader's **Target type** to **OSC encoder** — its bank's knob and Mute fall back to their encoder-channel/reset behavior too.

**Important:** for the fader to actually move the axis, that axis's **Function** must be set to **Manual** in Dragonframe's Arc Motion Control workspace (axis settings). If it's left on `Function: Normal` without a real motor attached, Dragonframe will silently accept the commands without moving anything — this is a Dragonframe-side setting DragonMIDI can't detect or fix for you.

**Watch out for accidental Mute presses:** Dragonframe has no OSC command to move an axis to a stored zero position — `setZero` is the only related command, and it *recalibrates* the reference point to wherever the axis currently is. Bumping Mute mid-shoot won't move anything, but it will quietly redefine that axis's zero to its current position.

Bank assignments reset back to the defaults every time you restart DragonMIDI — they aren't saved between sessions yet.

## Selecting and jogging an axis

Solo, Cycle, Stop, and Marker ◄/► work together, independently of the fader banks above, using a connection Dragonframe opens to DragonMIDI on its own (no setup needed — see [Configuring Dragonframe](#configuring-dragonframe)):

| Control | Behavior |
|---|---|
| Solo N | Selects axis N on Dragonframe's motion-control side, whether or not that axis has a fader assigned |
| Cycle | Selects the next axis in turn (1, 2, 3, …), wrapping back to the first after the last |
| Marker ◄/► | Jogs whichever axis was last selected by Solo or Cycle, one step per press |
| Stop | Emergency-stops motion-control movement |

Marker ◄/► does nothing until you've pressed Solo or Cycle at least once in the current Dragonframe session — there's no default selected axis. This selection lives inside Dragonframe itself, not DragonMIDI, so it also survives independently of anything DragonMIDI tracks.

These four don't require picking an axis name or a min/max range — Solo addresses axes by their fixed position (1st, 2nd, …) in Dragonframe's own motion-control setup, not by the name you'd see in the fader's axis picker.

## Installing

Requires Python 3.10 or newer.

```bash
cd ~/github/dragonmidi
pip install -e .
```

Then run it from anywhere with:

```bash
dragonmidi
```

<details>
<summary>Having trouble installing? (Conda, virtual environments, Xcode tools)</summary>

- Install into whichever Python environment your terminal normally opens into — including Conda's `base` environment, if that's what you see by default. Fighting that with a separate virtual environment just means remembering to activate it every time before running `dragonmidi`.
- If you do want an isolated environment, create and activate it *before* running `pip install -e .`, and remember to activate it again in every new terminal before running `dragonmidi`.
- On macOS, installing may trigger a build step for the `python-rtmidi` package the first time — this needs Xcode's command-line tools, which most Mac developer setups already have. If it fails, run `xcode-select --install` and try again.

</details>

## Configuring Dragonframe

One-time setup, per machine:

1. In Dragonframe, open **Preferences → Open Sound Control**.
2. Enable **OSC Input** on UDP port `7010`.
3. Enable **OSC Output**, sending to `127.0.0.1` port `7011`.

That's it for the transport/shoot/marker buttons, and for Solo/Cycle/Stop/Marker ◄/►, to work. A fader/knob/Mute bank left on OSC encoder mode instead of picking an axis needs one more step: open Dragonframe's **Arc Motion Control** workspace and, for each axis, set its **OSC encoder channel** to match the control driving it (Fader 1 → channel 1, Knob 1 → channel 9, and so on — see the table above), plus the scale/absolute-vs-relative setting for that axis.

Once you've configured a rig's axes once, you can reuse that setup in future projects: in the Arc Motion Control workspace, use **Export | Arc Axis Setup (ARCX)** to save it, then **Import | Arc Axis Setup (ARCX)** in a new project instead of redoing it by hand.

Solo/Cycle/Stop/Marker ◄/► use a second connection Dragonframe opens on its own at startup, separate from the OSC setup above — nothing to configure for it, but it means these four controls need Dragonframe to have (re)started or regained focus at least once since DragonMIDI launched. If they seem unresponsive, click into the Dragonframe window and try again.

## Current limitations

- Only faders have their own axis picker. Knobs and Mute automatically follow whichever axis their bank's fader is set to (nudge / zero) — they can't be pointed at a *different* axis independently. Return to Zero isn't mapped to anything.
- No custom mapping editor yet — you can retarget a fader's (and its bank's) axis assignment, but not reassign what any other control does, and nothing is saved between restarts.
- Only the KORG nanoKONTROL Studio and nanoKONTROL2 are supported — no other MIDI controllers.
- The Controller dropdown's selection isn't remembered between restarts — DragonMIDI always starts on nanoKONTROL Studio; switch it back to nanoKONTROL2 each time if that's what you're using.
- The nanoKONTROL2's CC-number mapping hasn't yet been confirmed against real hardware (see [Using a nanoKONTROL2](#using-a-nanokontrol2)).
- If another application also connects to Dragonframe's WebSocket integration on the same local port, only one can have Solo/Cycle/Stop/Marker ◄/► working at a time.

---

## For developers

This project follows [linked-intent development](CLAUDE.md): every behavior traces `docs/high-level-design.md` → `docs/llds/` → `docs/specs/` → tests → code. Start there before making changes.

```bash
pip install -e ".[dev]"
python -m pytest
```

Tests use `pytest` and `hypothesis` (property-based tests).

See [`docs/high-level-design.md`](docs/high-level-design.md) for full architecture and phasing rationale.

---

## Acknowledgments

Our app icon uses a glyph from [Phosphor Icons](https://phosphoricons.com/).
