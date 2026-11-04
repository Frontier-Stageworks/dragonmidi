# Adding a Controller Profile

A Controller Profile is a YAML file that tells DragonMIDI about one MIDI control
surface: how to recognize it, which physical control sends which MIDI message, and
what each control should do. No programming or rebuild required.

## Where the file goes

Put your file in:

```
~/Documents/DragonMIDI/controllers/
```

Create the folder if it doesn't already exist — DragonMIDI creates and seeds it
with a starter example (`nanokontrol2.yaml.example`) the first time it runs, if the
folder wasn't already there.

- File extension: `.yaml` or `.yml`.
- One controller per file.
- Restart DragonMIDI after adding, editing, or removing a file — it's read once at
  launch, not watched live.
- If your file's `name` matches one of DragonMIDI's built-in profiles (e.g.
  "nanoKONTROL2"), yours replaces it entirely for that launch.

## Minimal example

```yaml
name: "My Controller"
match_substring: "mycontroller"
has_native_mode: false
default_channel: 1
has_jog_wheel: false
has_scene_button: false

controls:
  faders: [0, 1, 2, 3, 4, 5, 6, 7]
  knobs: [16, 17, 18, 19, 20, 21, 22, 23]
  mutes: [48, 49, 50, 51, 52, 53, 54, 55]
  solos: [32, 33, 34, 35, 36, 37, 38, 39]
  transport:
    play: 41
    stop: 42
```

## Field reference

| Field | Required | Type | Meaning |
|---|---|---|---|
| `name` | yes | text | Shown in the Controller Profile dropdown. Also the identity DragonMIDI uses to match your file against a built-in profile of the same name. |
| `match_substring` | yes | text | A short, lowercase, letters-and-numbers-only fragment of your device's MIDI port name, used to auto-connect. Example: for a port named "My Controller MIDI 1", use `mycontroller`. |
| `has_native_mode` | yes | true / false | Almost always `false`. Only `true` for a device with a KORG-style SysEx handshake (the nanoKONTROL Studio is the only one today). |
| `default_channel` | yes | number, 1–16 | The MIDI channel your device transmits on. Use the channel number as your device's manual documents it (1–16), not a zero-based number. |
| `has_jog_wheel` | yes | true / false | `true` only if your device has a KORG-style relative jog wheel and `controls.jog_wheel` is set. |
| `has_scene_button` | yes | true / false | `true` only if your device has a KORG nanoKONTROL-style Scene button (SysEx-based, no CC number). |
| `setup_hint` | no | text | A one-line reminder shown under the dropdown when your profile is selected — for a one-time setup step DragonMIDI can't do for you (e.g. a power-on button combo). Omit if none applies. |
| `controls` | yes | see below | The physical control layout. |

## The `controls` block

| Field | Required | Type | Meaning |
|---|---|---|---|
| `faders` | yes | list of CC numbers, at least 1 | Fader 1 through Fader N, in order. **The length of this list is your device's logical strip/Bank count** — 8 for a nanoKONTROL-shaped device, but any count is fine. |
| `knobs` | no (default: none) | list of CC numbers, any length | Knob 1 through Knob N, in order. Doesn't need to match `faders`' count — a device can have more (or fewer, or zero) encoders than channel strips; only the first as-many-as-`faders` pair up with a Bank (see Limits below). |
| `mutes` | no (default: none) | list of CC numbers, any length | Mute button 1 through N, in order. Same independent-length rule as `knobs`. |
| `solos` | no (default: none) | list of CC numbers, any length | Solo button 1 through N, in order. Same independent-length rule as `knobs`. |
| `transport` | yes (may be empty: `{}`) | named CC numbers | See table below. Any name you leave out simply doesn't exist as a control for this device. |
| `jog_wheel` | required only if `has_jog_wheel` is `true` | CC number | The jog wheel's CC number. Omit entirely if your device has no jog wheel. |

`transport` names, all optional:

| Name | Physical control |
|---|---|
| `record` | Transport Record |
| `play` | Play |
| `stop` | Stop |
| `rewind` | Rewind (`<<`) |
| `fast_forward` | Fast Forward (`>>`) |
| `cycle` | Cycle |
| `previous_marker` | Previous Marker |
| `next_marker` | Next Marker |
| `previous_track` | Previous Track |
| `next_track` | Next Track |

Every CC number is an integer, 0–127, as reported by your device (check its MIDI
implementation chart or use a MIDI monitor tool to read the numbers directly).

## Limits

- **`faders` sets your device's strip/Bank count; the other three don't need to match it.** `faders` must list at least 1 CC number — its length *is* the Bank count (8 for a nanoKONTROL-shaped device, but a 4-strip or 12-strip device is just as supported). `knobs`/`mutes`/`solos` can each be omitted, empty, shorter, the same length, or longer than `faders` — a device with 8 faders but 16 knobs declares that directly.
- **Fader/knob/mute CCs don't need to line up numerically.** Bank 1 is always
  index 0 of each list, Bank 2 is index 1, and so on, up through the Bank count —
  the numbers themselves can be anything. If `knobs`/`mutes` has more entries than
  `faders`, the extra ones still work as plain controls; they just aren't paired to
  a Bank.
- **`has_jog_wheel`/`has_scene_button` assume KORG's own encoding.** Setting either
  to `true` tells DragonMIDI to expect the exact same signal shape the KORG
  nanoKONTROL family uses (a specific relative-value encoding for the jog wheel, a
  specific SysEx message for the Scene button) — not a general "any jog
  wheel/button will work" flag. If your device's jog wheel or Scene-like button
  works differently, leave the corresponding flag `false`.

## If your file doesn't show up

- Check that the extension is `.yaml` or `.yml`, and that you restarted
  DragonMIDI after adding it.
- If DragonMIDI shows "N controller config file(s) failed to load" beneath the
  dropdown, your file (or another one) has a mistake — check the required fields
  above, then check DragonMIDI's log output for the specific error.
