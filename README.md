# DragonMIDI

DragonMIDI lets you control [Dragonframe](https://www.dragonframe.com/) (stop-motion capture software) with a **KORG nanoKONTROL Studio** MIDI controller. Plug in the controller, launch DragonMIDI, and its faders, knobs, and transport buttons act as physical controls for Dragonframe — playback, shooting, and moving motorized rig axes — instead of reaching for the mouse and keyboard every time.

## Quick start

1. **Install it** (see [Installing](#installing) below if you don't already have this set up).
2. **Turn on OSC in Dragonframe** (see [Configuring Dragonframe](#configuring-dragonframe) below) — a one-time setup per machine.
3. **Plug in your nanoKONTROL Studio**, then run:
   ```bash
   dragonmidi
   ```
4. A window opens showing two status lights and a table of every control. Once both lights turn green, you're connected and every control below is live.

## What each control does by default

DragonMIDI ships with a ready-to-use set of defaults — no setup required to start using the transport/shoot/marker buttons. This is the "Mapping" table you'll see in the app window:

| Control | What it does in Dragonframe |
|---|---|
| Faders 1-8 | Drive a motion-control axis directly — pick which one in the Mapping table (see [Controlling a motor axis](#controlling-a-motor-axis) below) |
| Knobs 1-8 | Fine-tune nudge for the axis its own fader is driving (see below); drives an OSC encoder channel instead if that fader has no axis picked |
| Mute 1-8 | Marks the axis's *current* position as its zero reference, once its fader has an axis assigned; otherwise resets the fallback encoder channel |
| Solo 1-8 | Marks the axis's *current* position as its home reference, once its fader has an axis assigned; otherwise resets the fallback encoder channel |
| Jog wheel / Return to Zero | Not assigned — the jog wheel isn't used for motion-control input in this project |
| Play | Play back your shot frames |
| Stop | Return to the live camera view |
| Transport Record (●) | Shoot one frame |
| Rewind (◄◄) / Fast Forward (►►) | Step one frame backward / forward |
| Cycle | Loop playback |
| Marker ◄/► and Track ◄/► | Step one frame backward / forward |
| Set Marker | Not assigned — no matching Dragonframe action |
| Scene button | Black out the display |

You don't need to memorize this — the app's window shows this same table live, alongside each control's current assignment.

## The status window

When you run `dragonmidi`, you'll see:

- **MIDI signal** — lights up when your nanoKONTROL Studio is actively sending input.
- **Dragonframe signal** — lights up when Dragonframe is talking back to DragonMIDI. This is the one to watch to confirm the two apps are actually connected, not just that DragonMIDI is running.
- Each light is one of three colors:
  - 🟢 **Green** — working, recent activity.
  - 🟠 **Amber** — a real problem (the controller's handshake failed, or DragonMIDI couldn't open its network port).
  - ⚪ **Gray** — quiet. Normal if nothing's happening right now; not an error.
- Below the lights: the network address DragonMIDI sends to and listens on, with an **Apply** button if you ever need to change them (most people never will).
- Below that: the **Mapping** table described above.

## Controlling a motor axis

Each fader, together with the knob, Mute button, and Solo button directly above/below it in the same column, forms a **bank**. Assigning an axis to the fader is the only step — the other three controls in that bank pick it up automatically:

| Control | Behavior once the bank's fader has an axis assigned |
|---|---|
| Fader | Drives the axis to an absolute position across the fader's travel |
| Knob | Nudges that axis by however far you just turned it — turning it further right moves the axis one way, further left the other way, proportional to the turn. Holding it still does nothing further. Useful for fine-tuning a position the fader got you close to. Can't push the axis below the fader's configured **min** or above its **max** — it stops exactly at whichever bound you reach. |
| Mute | Marks the axis's current position as its zero reference — it does **not** move the axis anywhere |
| Solo | Marks the axis's current position as its home reference — it does **not** move the axis anywhere |

Faders start out already in this mode with no axis picked yet — until you pick one, that fader (and its bank) produces no output. To assign one:

1. In the app's Mapping table, find the fader's row. It defaults to **Target type: OSC axis** with an empty dropdown.
2. The dropdown lists the axis names DragonMIDI found in your currently-open Dragonframe project. Pick one.
   - If it says **"Discovering…"**, DragonMIDI is still checking — wait a second and it'll populate.
   - If it says **"No axes found"**, your current Dragonframe project doesn't have any motion-control axes set up yet.
   - Just added a new axis in Dragonframe, or opened a different project? Click **Rescan axes** to refresh the list.
3. Enter a **min** and **max** value next to the dropdown — this is the range the axis moves across as you slide the fader from empty to full. The knob's nudge is kept inside this same range (it stops at whichever bound it reaches, never overshoots); the Mute/Solo zero/home actions aren't affected by min/max — those are fixed Dragonframe commands.

If you'd rather use the older encoder-channel approach for a given fader instead (see [Configuring Dragonframe](#configuring-dragonframe) below), switch that fader's **Target type** to **OSC encoder** — its bank's knob and Mute/Solo fall back to their encoder-channel/reset behavior too.

**Important:** for the fader to actually move the axis, that axis's **Function** must be set to **Manual** in Dragonframe's Arc Motion Control workspace (axis settings). If it's left on `Function: Normal` without a real motor attached, Dragonframe will silently accept the commands without moving anything — this is a Dragonframe-side setting DragonMIDI can't detect or fix for you.

**Watch out for accidental Mute/Solo presses:** Dragonframe has no OSC command to move an axis to a stored zero/home position — `setZero`/`setHome` are the only related commands, and they *recalibrate* the reference point to wherever the axis currently is. Bumping Mute or Solo mid-shoot won't move anything, but it will quietly redefine that axis's zero or home to its current position.

Bank assignments reset back to the defaults every time you restart DragonMIDI — they aren't saved between sessions yet.

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

That's it for the transport/shoot/marker buttons to work. A fader/knob/Mute/Solo bank left on OSC encoder mode instead of picking an axis needs one more step: open Dragonframe's **Arc Motion Control** workspace and, for each axis, set its **OSC encoder channel** to match the control driving it (Fader 1 → channel 1, Knob 1 → channel 9, and so on — see the table above), plus the scale/absolute-vs-relative setting for that axis.

Once you've configured a rig's axes once, you can reuse that setup in future projects: in the Arc Motion Control workspace, use **Export | Arc Axis Setup (ARCX)** to save it, then **Import | Arc Axis Setup (ARCX)** in a new project instead of redoing it by hand.

## Current limitations

- Only faders have their own axis picker. Knobs and Mute/Solo automatically follow whichever axis their bank's fader is set to (nudge / zero / home) — they can't be pointed at a *different* axis independently. The jog wheel and Return to Zero aren't mapped to anything.
- No custom mapping editor yet — you can retarget a fader's (and its bank's) axis assignment, but not reassign what any other control does, and nothing is saved between restarts.
- Only the KORG nanoKONTROL Studio is supported.

---

## For developers

This project follows [linked-intent development](CLAUDE.md): every behavior traces `docs/high-level-design.md` → `docs/llds/` → `docs/specs/` → tests → code. Start there before making changes.

```bash
pip install -e ".[dev]"
python -m pytest
```

Tests use `pytest` and `hypothesis` (property-based tests).

See [`docs/high-level-design.md`](docs/high-level-design.md) for full architecture and phasing rationale, and [`docs/dragonframe-messages-research.md`](docs/dragonframe-messages-research.md) for the research behind Dragonframe's OSC surface.
