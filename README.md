# DragonMIDI

DragonMIDI reads MIDI from a KORG nanoKONTROL Studio and forwards it as OSC to [Dragonframe](https://www.dragonframe.com/) (stop-motion capture software), so faders, knobs, and the jog wheel can act as live axis/transport controls for anything Dragonframe is connected to.

This is a **phase-1 build**: the control mapping ships with an opinionated default, and the app lets you retarget any fader to a Dragonframe axis directly. The rest of the configuration surface — MIDI-learn, add/remove entries, presets, retargeting knobs/buttons/the jog wheel — is phase 2. See [Current scope](#current-scope) for what's intentionally not here yet.

## What it does

- Auto-detects and connects to a KORG nanoKONTROL Studio, switching it into **KORG Native Mode** so every physical control reports a fixed MIDI message regardless of the controller's on-device Scene.
- Translates the controller's inputs to Dragonframe OSC commands using an opinionated default map (mirrors [`docs/llds/static-mapping.md`](docs/llds/static-mapping.md)):

  | Control | Dragonframe action |
  |---|---|
  | Faders 1-8 | OSC encoders 1-8 (absolute) — or a Dragonframe axis directly, see [Mapping view](#mapping-view) |
  | Knobs 1-8 | OSC encoders 9-16 (absolute) |
  | Jog wheel | OSC encoder 17 (relative) |
  | Mute 1-8 / Solo 1-8 | Reset encoder 1-8 / 9-16 |
  | Return to Zero | Reset encoder 17 |
  | Play | Play |
  | Stop | Live view |
  | Transport Record | Shoot one frame |
  | Rewind / Fast Forward | Step backward / forward one frame |
  | Cycle | Loop |
  | Previous/Next Marker, Previous/Next Track | Step backward / forward one frame |
  | Set Marker | Unmapped (no Dragonframe equivalent) |
  | Scene button | Black |

- Shows a status window with:
  - **MIDI signal** and **Dragonframe signal** indicators — each lit when real, recent traffic has been seen on that channel (recency-based, not just "device found" or "socket open"). Each is 3-state: **live** (green), **error** (amber — Native Mode handshake failed, or the listener couldn't bind its port), **quiet** (gray — no recent traffic, not a failure).
  - Editable Dragonframe host/port and local listen port, behind an **Apply** button.
  - A **Mapping** table, embedded below — see the next section.

## Mapping view

The window's Mapping section shows every control's current MIDI source, trigger, and target in one place. Every row in the opinionated table above is listed; only the 8 fader rows are editable in this phase.

A fader's **Target type** can be switched between:

- **OSC encoder** (the default) — drives `/dragonframe/encoder/<n>`, which still needs to be wired to an axis inside Dragonframe's Arc Motion Control workspace (see [Configure Dragonframe](#configure-dragonframe) below).
- **OSC axis** — addresses a Dragonframe axis directly by name, no encoder-channel wiring needed. Pick a name from the dropdown (populated from the axes DragonMIDI discovers in Dragonframe's current project) and enter a min/max range; the fader then sends `gotoPosition` scaled into that range on every move.

Click **Rescan axes** after adding an axis in Dragonframe, or after switching to a different project, to refresh the dropdown without restarting DragonMIDI. The dropdown reads "Discovering…" until the first query completes, and "No axes found" if the current project genuinely has none.

**For direct axis targeting to actually move something**, the target axis's **Function** must be set to **Manual** in Dragonframe (Arc Motion Control workspace → axis settings). An axis left on `Function: Normal` with no real hardware attached silently accepts `gotoPosition` without ever moving — Dragonframe gives no way to detect this over OSC, so it's a manual setup step, not something DragonMIDI can warn about.

Mapping changes are **not persisted** — they reset to the opinionated defaults every time DragonMIDI restarts.

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

### Configure Dragonframe

In Dragonframe, open **Preferences → Open Sound Control**:

- Enable **OSC Input** on UDP port `7010` (DragonMIDI's default send target).
- Enable **OSC Output** to `127.0.0.1` port `7011` (DragonMIDI's default listen port) — this is what lights up the **Dragonframe signal** indicator, and what DragonMIDI's axis discovery relies on.

If you're using **OSC encoder** targets (the default for faders/knobs, and the only option for knobs/mute/solo/the jog wheel in this phase): in the **Arc Motion Control** workspace, for each axis you want a fader/knob/jog wheel to drive, set its **OSC encoder channel** to match the table above (e.g. axis driven by Fader 1 → OSC encoder channel `1`), plus the encoder scale and absolute/relative setting appropriate to that axis. An OSC encoder channel number has no meaning to Dragonframe until an axis is configured to listen on it — DragonMIDI has no way to do this configuration for you.

If you're using **OSC axis** targets instead (faders only, via the Mapping view), no encoder-channel wiring is needed — just make sure the axis's Function is set to `Manual` (see [Mapping view](#mapping-view) above).

Once you've set up encoder channels for a rig, you can save the per-axis work: workspace menu → **Export | Arc Axis Setup (ARCX)** to save it, then **Import | Arc Axis Setup (ARCX)** into future projects instead of re-configuring every axis by hand. See [`docs/dragonframe-messages-research.md`](docs/dragonframe-messages-research.md) for the full research behind this.

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

- MIDI-learn, add/remove/duplicate mapping entries, or preset save/load — phase 2.
- Direct axis (OSC axis) targeting for anything other than the 8 faders — knobs, buttons, and the jog wheel keep their fixed OSC encoder/action targets in this phase.
- An arbitrary custom-OSC-path target type.
- Support for any MIDI controller other than the KORG nanoKONTROL Studio.
- Interpretation of *what* Dragonframe's OSC output actually contains beyond `getAllPosition` responses (other axis-position streaming, frame events) — DragonMIDI only uses those as a liveness signal.
- Dragonframe-to-controller feedback (LEDs, motorized faders).

See [`docs/high-level-design.md`](docs/high-level-design.md) for the full rationale, and [`docs/dragonframe-messages-research.md`](docs/dragonframe-messages-research.md) for research into Dragonframe's complete OSC surface versus what this phase actually uses.
