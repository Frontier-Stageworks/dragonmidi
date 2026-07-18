# Dragonframe Gamepad Integration — Research Notes

**Status: explored, not pursued.** This research led to a Virtual Gamepad Adapter design (macOS via `IOHIDUserDeviceCreate`) that was empirically found to require the same Apple DriverKit entitlement approval as the newer `HIDVirtualDevice` API — confirmed by directly testing both the current and legacy API entry points against a real macOS instance, both returning `NULL`. Given that approval-bottleneck and no viable maintained fallback (`foohid` is archived and self-described as unsafe), the project instead extends the existing OSC path with direct axis-name addressing (`gotoPosition`/`stepPosition`, discovered via `getAllPosition`) — see `docs/high-level-design.md § Delivery Phasing`. This document is retained as a record of what was investigated and why it wasn't pursued, not as an active plan.

## Question

Can Dragonframe's motion-control axes be jogged (continuous, real-time position control) over OSC? If not, what does Dragonframe actually support for real-time jogging, and can DragonMIDI hook into it?

## Method

Read directly from the official manual (`Using Dragonframe 2025.pdf`, downloaded from dragonframe.com; same source as `dragonframe-messages-research.md`), section "Using a Gamepad to Program Moves" (manual page 342 onward).

## Finding: OSC has no jog/continuous-control primitive

The documented OSC axis surface (`dragonframe-messages-research.md`, mechanism 2) is entirely **discrete**: `gotoPosition` (absolute), `stepPosition` (relative step), `getPosition` / `getAllPosition` (query). There is no OSC message for "continuously stream this axis's target position while a physical control is held," and nothing in the manual describes an OSC-driven jog mode. Real-time jogging is documented exclusively as a **gamepad** and keyboard/mouse-in-app feature, driven through Dragonframe's own input handling — not through OSC at all.

## Finding: Dragonframe's gamepad system

Dragonframe uses **SDL2** to read gamepads (manual: *"Dragonframe uses SDL2 to support a wide variety of gamepads"*). Key mechanics:

- **Configure Gamepad dialog** (Arc menu → Configure Gamepad): assigns each gamepad stick axis / d-pad direction / trigger to a motion-control axis. Assignment takes effect immediately — moving the assigned stick jogs the real motor live. This is the basic, direct jog mode.
- **Fixed special-purpose buttons**: rear-left = "Modifier" (engages "jog on line" for virtual axes), rear-right = E-Stop (hard stop; held + jog = reduced/"inching" speed).
- **In-app gamepad menu** (press GUIDE/MENU/START): a full on-screen menu system navigated with the d-pad/left stick and an A-button select, used for setting keyframes, choosing actions per selected axis, and more — this is how the gamepad drives things beyond simple axis jogging (keyframing, focus check, etc.).
- **"Jogging Move with the Gamepad"** (scrubbing an already-recorded, multi-axis-synchronized move in time) is explicitly gated: *"If you have a real-time capable motion control device, such as the DMC, eMotimo ST4, or Slidekamera SLIDELINK PRO, you can perform a live jog of the entire move."* DMC is Dragonframe's own real-time motion-control coordinator hardware (DMC-32/DMC-16/DMC+). **This specific mode is not available without that class of hardware.** It is distinct from the basic per-axis jog described above, which is not documented as having this hardware restriction.
- **Virtual axes cannot be directly assigned to gamepad controls.** Only "real" motor axes (Connect = ArcMoco/Digital Focus/Flair, or similar) can be gamepad-assigned; when Virtuals mode is active, the corresponding virtual axis (vTRACK/vEW/vNS or Z/X/Y) rides along automatically via the real axis's existing gamepad assignment. This reinforces the still-open question from `dragonframe-messages-research.md` about whether a fully hardware-free axis can be created at all — not yet confirmed either way.

## Finding: custom controller support is an open, documented mechanism

Dragonframe ships gamepad recognition via **SDL2 GameController mappings** — the same open format used by `SDL_GameControllerDB` across the game-development ecosystem. For unsupported controllers, the manual documents:

1. Generate a mapping string with the third-party **SDL2 Gamepad Tool** (generalarcade.com/gamepadtool/), which produces a comma-separated string keyed by a device GUID, e.g.:
   ```
   03000000d62000006dca000011010000,PowerA Pro Ex,a:b1,b:b2,back:b8,dpdown:h0.4,...,leftx:a0,lefty:a1,...,rightx:a2,righty:a3,...,platform:Linux,
   ```
2. Save it as a plain-text file in `<Dragonframe install folder>/RESOURCES/GAMEPADS`.
3. Restart Dragonframe — it loads the mapping and the controller works.

This is a **documented, supported extension point**, not an undocumented internal to reverse-engineer. A device that presents itself as a standard HID gamepad, with a custom SDL2 mapping file describing its button/axis layout, is recognized by Dragonframe exactly like a commercial Xbox/PlayStation controller.

## Implication for DragonMIDI

To get continuous, real-time axis jogging from nanoKONTROL Studio controls, DragonMIDI would need to:

1. Present itself to the OS as a **virtual/synthetic gamepad** (a HID joystick device SDL2 can enumerate), translating incoming MIDI CC values into that virtual device's button/axis state in real time.
2. Ship (or generate) an **SDL2 mapping file** describing that virtual device's layout, placed in Dragonframe's `RESOURCES/GAMEPADS` folder, so Dragonframe recognizes it without the user running the third-party SDL2 Gamepad Tool by hand.
3. Rely on Dragonframe's existing **Configure Gamepad** dialog for the user to assign virtual-gamepad axes to motion-control axes — DragonMIDI does not need to (and cannot, since it's in-app UI) automate that assignment step.

This targets the basic per-axis jog mode, which is not documented as requiring special real-time hardware. The more advanced "jog through a recorded move in time" mode remains out of reach without DMC-class hardware, independent of anything DragonMIDI does.

## Finding: creating a virtual gamepad on macOS — no special Apple approval needed

Two distinct macOS mechanisms exist for publishing a virtual HID gamepad, found by examining how existing virtual-controller tools implement this:

1. **DriverKit / `HIDVirtualDevice` (CoreHID framework).** The modern, Apple-sanctioned path. Requires the `com.apple.developer.hid.virtual.device` entitlement, which is **not available to an ordinary developer account** — it must be requested from Apple through the DriverKit entitlement process, which involves an application and an approval wait. This is a real, bureaucratic blocker for a small independent project.
2. **`IOHIDUserDeviceCreate` (IOKit, user-space).** An older API that lets any process publish a virtual HID device directly from user space, gated only by two standard macOS privacy permissions — **Input Monitoring** and **Accessibility** — which any signed app can request from the end user through the normal system permission prompts, with no Apple approval process required.

Confirmed via `OpenJoystickDriver` (xsyetopz/OpenJoystickDriver), an open-source macOS utility that implements both paths side by side and explicitly documents its `IOHIDUserDeviceCreate`-based "compatibility layer" as its **SDL 2/3**-compatible output mode, requiring only Input Monitoring + Accessibility, no DriverKit. Its architecture doc describes the compatibility layer as "traditional user-space HID publication," separate from its DriverKit path, and confirms SDL2 detects devices published this way. (`OpenJoystickDriver` itself is not a dependency DragonMIDI would take on — its normal use case is relaying a *real* physical controller. The relevant fact is that `IOHIDUserDeviceCreate` is a proven, currently-working, approval-free way to publish a virtual gamepad that SDL2 recognizes; DragonMIDI would call this API directly and write MIDI-derived values into the virtual device's report itself, with no third-party app involved.)

**Conclusion:** DragonMIDI's macOS path is `IOHIDUserDeviceCreate`, not DriverKit — avoids the Apple approval bottleneck entirely. A minimal working code example (HID report descriptor + report-writing loop) is an implementation task, not yet produced.

## Finding: the Windows equivalent

**ViGEmBus** is the standard virtual-gamepad kernel driver for Windows (emulates Xbox 360 / DualShock 4 controllers at the driver level). Status: the project was archived/retired over a trademark dispute with a similarly-named company, but the last released build (1.17.333.0) continues to work on current Windows 10/11, including 23H2/24H2.

**`vgamepad`** is a Python library wrapping ViGEmBus with a clean, directly usable API:

```python
import vgamepad as vg
gamepad = vg.VX360Gamepad()
gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
gamepad.left_joystick_float(x_value_float=-0.5, y_value_float=0.0)
gamepad.update()  # pushes the new state to the system
```

It installs the ViGEmBus kernel driver automatically on first install (a one-time, admin-privileged system driver install — unlike the macOS user-space path, this is unavoidable on Windows). Exposes 11 buttons + 2 triggers + 2 analog sticks (Xbox360 profile) or the DS4 equivalent. No published latency/update-rate figures.

**Conclusion:** the Windows and macOS implementations are necessarily separate code paths (`vgamepad`/ViGEmBus vs. `IOHIDUserDeviceCreate`), but both are viable without Apple/Microsoft special approval, and both expose a similar "set button/axis state, then push" programming model.

## Still open (genuinely unresearched — require hands-on testing, not further reading)

1. **Whether a fully virtual (no real hardware) motion-control axis can be gamepad-assigned at all**, or whether a "real" Connect-type selection (ArcMoco/Digital Focus/Flair) is a hard requirement — carried over from `dragonframe-messages-research.md`; the manual ties gamepad assignment to "real motor axes" but doesn't state whether Connect has a no-hardware option. Only resolvable by testing in a running copy of Dragonframe.
2. **Latency and update-rate requirements** for the virtual gamepad's axis reports to register as smooth jogging in Dragonframe — not documented anywhere found; needs empirical testing against a real Dragonframe instance.
3. Whether the "Modifier" (jog-on-line) and "E-Stop" fixed-button behaviors need to be implemented in DragonMIDI's virtual gamepad, or can be left unassigned.
4. A concrete, tested `IOHIDUserDeviceCreate` gamepad report descriptor and read/write loop — the mechanism is confirmed viable, but no working example has been produced or tested yet.

## References

- `Using Dragonframe 2025.pdf`, dragonframe.com — "Using a Gamepad to Program Moves" (p. 342-347).
- `docs/dragonframe-messages-research.md` — the OSC surface this finding is contrasted against, and the still-open "does an axis require real hardware" question this research also bears on.
- SDL2 GameController mapping format / `SDL_GameControllerDB`: https://github.com/mdqinc/SDL_GameControllerDB
- SDL2 Gamepad Tool (referenced by the manual): https://generalarcade.com/gamepadtool/
- `com.apple.developer.hid.virtual.device` entitlement documentation (Apple Developer): confirms the DriverKit path requires Apple-granted approval, not available to a standard account.
- OpenJoystickDriver (xsyetopz/OpenJoystickDriver) — reference implementation proving the `IOHIDUserDeviceCreate` + Input Monitoring/Accessibility path works for SDL2-visible virtual gamepads on current macOS, without DriverKit.
- `vgamepad` (yannbouteiller/vgamepad) and ViGEmBus (nefarius/ViGEmBus) — the Windows equivalent.
