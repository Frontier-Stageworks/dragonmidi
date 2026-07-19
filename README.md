# DragonMIDI

DragonMIDI lets you control [Dragonframe](https://www.dragonframe.com/) (stop-motion capture software) with a **KORG nanoKONTROL Studio** MIDI controller. Plug in the controller, launch DragonMIDI, and its faders, knobs, jog wheel, and transport buttons act as physical controls for Dragonframe — playback, shooting, and moving motorized rig axes — instead of reaching for the mouse and keyboard every time.

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
| Faders 1-8 | Drive motion-control axes (see [Controlling a motor axis with a fader](#controlling-a-motor-axis-with-a-fader) to assign one) |
| Knobs 1-8 | Drive motion-control axes (via Dragonframe's "OSC encoder" setup) |
| Jog wheel | Drives a motion-control axis, relative movement |
| Mute 1-8 / Solo 1-8 | Reset the axis assigned to the fader / knob in that same column |
| Return to Zero | Resets the jog wheel's axis |
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

## Controlling a motor axis with a fader

Any of the 8 faders can be pointed directly at one of your Dragonframe project's motion-control axes, instead of going through the manual "OSC encoder" wiring:

1. In the app's Mapping table, find the fader's row and change **Target type** to **OSC axis**.
2. A dropdown appears, listing the axis names DragonMIDI found in your currently-open Dragonframe project. Pick one.
   - If it says **"Discovering…"**, DragonMIDI is still checking — wait a second and it'll populate.
   - If it says **"No axes found"**, your current Dragonframe project doesn't have any motion-control axes set up yet.
   - Just added a new axis in Dragonframe, or opened a different project? Click **Rescan axes** to refresh the list.
3. Enter a **min** and **max** value next to the dropdown — this is the range the axis moves across as you slide the fader from empty to full.

**Important:** for the fader to actually move the axis, that axis's **Function** must be set to **Manual** in Dragonframe's Arc Motion Control workspace (axis settings). If it's left on `Function: Normal` without a real motor attached, Dragonframe will silently accept the commands without moving anything — this is a Dragonframe-side setting DragonMIDI can't detect or fix for you.

Fader-to-axis assignments reset back to the defaults every time you restart DragonMIDI — they aren't saved between sessions yet.

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

That's it for the transport/shoot/marker buttons and knob/jog wheel encoders to work. If you also want faders wired to encoder channels (rather than the direct axis-picker approach above), open Dragonframe's **Arc Motion Control** workspace and, for each axis, set its **OSC encoder channel** to match the fader driving it (Fader 1 → channel 1, Fader 2 → channel 2, and so on), plus the scale/absolute-vs-relative setting for that axis.

Once you've configured a rig's axes once, you can reuse that setup in future projects: in the Arc Motion Control workspace, use **Export | Arc Axis Setup (ARCX)** to save it, then **Import | Arc Axis Setup (ARCX)** in a new project instead of redoing it by hand.

## Current limitations

- Only the 8 faders can be pointed at a motion-control axis directly; knobs, buttons, and the jog wheel use Dragonframe's encoder-channel wiring instead.
- No custom mapping editor yet — you can retarget a fader's axis assignment, but not reassign what any other control does, and nothing is saved between restarts.
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
