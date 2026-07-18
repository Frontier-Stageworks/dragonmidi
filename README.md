# DragonMIDI

DragonMIDI reads MIDI from a KORG nanoKONTROL Studio and forwards it as OSC to [Dragonframe](https://www.dragonframe.com/) (stop-motion capture software), so faders, knobs, and the jog wheel can act as live axis/transport controls for anything Dragonframe is connected to.

This is a **phase-1, opinionated build**: the control mapping is fixed in code (no mapping editor yet), and the UI is deliberately minimal — two status indicators, nothing else. See [Current scope](#current-scope) below for what's intentionally not here yet.

## What it does

- Auto-detects and connects to a KORG nanoKONTROL Studio, switching it into **KORG Native Mode** so every physical control reports a fixed MIDI message regardless of the controller's on-device Scene.
- Translates the controller's inputs to Dragonframe OSC commands using a hard-coded, opinionated map (mirrors the layout in [`docs/llds/static-mapping.md`](docs/llds/static-mapping.md)):

  | Control | Dragonframe action |
  |---|---|
  | Faders 1-8 | OSC encoders 1-8 (absolute) |
  | Knobs 1-8 | OSC encoders 9-16 (absolute) |
  | Jog wheel | OSC encoder 17 (relative) |
  | Mute 1-8 / Solo 1-8 | Reset encoder 1-8 / 9-16 |
  | Return to Zero | Reset encoder 17 |
  | Transport Record | Shoot one frame |
  | Play / Stop | Play / Live view |
  | Fast Forward | Shoot Video Assist |
  | Cycle | Mute |
  | Set Marker | Delete current frame |
  | Scene button | Black |

- Shows a small status window with two indicators:
  - **MIDI signal** — lit when the nanoKONTROL Studio is actively sending MIDI (recency-based, not just "device found").
  - **Dragonframe signal** — lit when Dragonframe's own OSC output is reaching DragonMIDI's listener (proves the link is live in both directions, not just that DragonMIDI's own sends aren't erroring).
  - Each indicator is 3-state: **live** (green), **error** (amber — Native Mode handshake failed, or the listener couldn't bind its port), **quiet** (gray — no recent traffic, not a failure).

## Setup

Requires Python `>=3.10` (3.10 through 3.13 are all fine — `python-rtmidi` builds from source on 3.13 since it has no prebuilt wheel there yet, which needs Xcode's command-line tools, but this happens automatically on `pip install`).

### Install

Install directly into whichever Python environment your terminal normally uses (including a Conda `base` environment — if `conda init` auto-activates `base` in every new terminal, as it does by default, that *is* "your normal environment," so install there rather than fighting it with a separate venv you'd have to remember to activate):

```bash
cd ~/github/dragonmidi
pip install -e .
```

This installs `mido`, `python-rtmidi`, and `PySide6`.

If you'd rather keep dependencies isolated from your main environment, create a dedicated venv or Conda environment first and activate it before running the command above — just remember you'll need to `conda activate <env>` (or `source .venv/bin/activate`) every time before `python -m dragonmidi`, since a fresh terminal will otherwise drop you back into `base`.

### 3. Configure Dragonframe

In Dragonframe, open **Preferences → Open Sound Control**:

- Enable **OSC Input** on UDP port `7010` (DragonMIDI's default send target).
- Enable **OSC Output** to `127.0.0.1` port `7011` (DragonMIDI's default listen port) — this is what lights up the **Dragonframe signal** indicator.

Then, in the **Arc Motion Control** workspace, for each axis you want a fader/knob/jog wheel to drive, set its **OSC encoder channel** to match the table above (e.g. axis driven by Fader 1 → OSC encoder channel `1`), plus the encoder scale and absolute/relative setting appropriate to that axis. An OSC encoder channel number has no meaning to Dragonframe until an axis is configured to listen on it — DragonMIDI has no way to do this configuration for you.

Once you've set this up once for a rig, you can save the per-axis work: workspace menu → **Export | Arc Axis Setup (ARCX)** to save it, then **Import | Arc Axis Setup (ARCX)** into future projects instead of re-configuring every axis by hand. See [`docs/dragonframe-messages-research.md`](docs/dragonframe-messages-research.md) for the full research behind this.

## Running it

```bash
python -m dragonmidi
# or, equivalently, since pip installed a console script:
dragonmidi
```

(If you installed into a dedicated venv/Conda environment instead of your default one, activate it first.)

The host, Dragonframe port, and listen port shown in the window are editable — change them and click **Apply** if your setup differs from the defaults (`127.0.0.1:7010` send, `7011` listen).

## Development

Tests use `pytest` and `hypothesis` (property-based tests):

```bash
pip install -e ".[dev]"
python -m pytest
```

This project follows [linked-intent development](CLAUDE.md): every behavior traces from `docs/high-level-design.md` → `docs/llds/` → `docs/specs/` → tests → code. Start there before making changes.

## Current scope

This is phase 1. Deliberately **not** included yet:

- A mapping/configuration editor, MIDI-learn, or preset files — the map above is fixed in code.
- Support for any MIDI controller other than the KORG nanoKONTROL Studio.
- Interpretation of *what* Dragonframe's OSC output actually contains (axis positions, frame events) — DragonMIDI only uses its presence as a liveness signal.
- Dragonframe-to-controller feedback (LEDs, motorized faders).

See [`docs/high-level-design.md`](docs/high-level-design.md) for the full rationale, and [`docs/dragonframe-messages-research.md`](docs/dragonframe-messages-research.md) for research into Dragonframe's complete OSC surface versus what this phase actually uses.
