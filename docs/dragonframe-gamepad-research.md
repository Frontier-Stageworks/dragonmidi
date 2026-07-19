# Dragonframe Gamepad Integration — Research Notes

**Status: explored, not pursued.** Continuous, real-time axis jogging is only reachable in Dragonframe through its gamepad system, not OSC. A virtual-gamepad approach was investigated for both macOS and Windows; on macOS, both the DriverKit (`HIDVirtualDevice`) and user-space (`IOHIDUserDeviceCreate`) APIs were confirmed by direct testing to require the same Apple-granted `com.apple.developer.hid.virtual.device` entitlement, not available to a standard developer account. With no viable maintained fallback (`foohid` is archived and self-described as unsafe), the project instead extends the existing OSC path with direct axis-name addressing (`gotoPosition`/`stepPosition`, discovered via `getAllPosition`) — see `docs/llds/static-mapping.md` § OSC Axis (Direct) Target. This document is retained as a record of what was investigated, not as an active plan.

## OSC has no jog/continuous-control primitive

The documented OSC axis surface (`dragonframe-messages-research.md`, mechanism 2) is entirely discrete: `gotoPosition` (absolute), `stepPosition` (relative step), `getPosition`/`getAllPosition` (query). There is no OSC message for continuously streaming an axis's target position while a physical control is held. Real-time jogging is documented exclusively as a gamepad and keyboard/mouse-in-app feature, driven through Dragonframe's own input handling, not through OSC.

## Dragonframe's gamepad system

Dragonframe uses SDL2 to read gamepads. Key mechanics:

- **Configure Gamepad dialog** (Arc menu → Configure Gamepad): assigns each gamepad stick axis/d-pad direction/trigger to a motion-control axis. Assignment takes effect immediately.
- **Fixed special-purpose buttons**: rear-left = "Modifier" (engages "jog on line" for virtual axes), rear-right = E-Stop (hard stop; held + jog = reduced/"inching" speed).
- **In-app gamepad menu** (GUIDE/MENU/START): an on-screen menu navigated with the d-pad/left stick and an A-button select, for keyframing, per-axis action selection, and more.
- **"Jogging Move with the Gamepad"** (scrubbing an already-recorded, multi-axis-synchronized move in time) requires a real-time capable motion-control device — DMC, eMotimo ST4, or Slidekamera SLIDELINK PRO — and is not available without that class of hardware. This is distinct from the basic per-axis jog above, which carries no such hardware restriction.
- **Virtual axes cannot be directly assigned to gamepad controls.** Only real motor axes (Connect = ArcMoco/Digital Focus/Flair, or similar) can be gamepad-assigned; when Virtuals mode is active, the corresponding virtual axis (vTRACK/vEW/vNS or Z/X/Y) rides along automatically via the real axis's existing gamepad assignment. Whether a fully hardware-free axis can be gamepad-assigned at all is not stated in the manual.

## Custom controller support

Dragonframe recognizes gamepads via SDL2 GameController mappings, the same format used by `SDL_GameControllerDB`. For an unsupported controller:

1. Generate a mapping string with the third-party SDL2 Gamepad Tool (generalarcade.com/gamepadtool/) — a comma-separated string keyed by device GUID, e.g.:
   ```
   03000000d62000006dca000011010000,PowerA Pro Ex,a:b1,b:b2,back:b8,dpdown:h0.4,...,leftx:a0,lefty:a1,...,rightx:a2,righty:a3,...,platform:Linux,
   ```
2. Save it as a plain-text file in `<Dragonframe install folder>/RESOURCES/GAMEPADS`.
3. Restart Dragonframe.

This is a documented, supported extension point: a device presenting itself as a standard HID gamepad, with a custom SDL2 mapping file describing its layout, is recognized like a commercial controller.

## What a DragonMIDI implementation would have required

1. Present itself to the OS as a virtual/synthetic gamepad (a HID joystick device SDL2 can enumerate), translating incoming MIDI CC values into that virtual device's button/axis state in real time.
2. Ship or generate an SDL2 mapping file describing that virtual device's layout, placed in Dragonframe's `RESOURCES/GAMEPADS` folder.
3. Rely on Dragonframe's Configure Gamepad dialog for the user to assign virtual-gamepad axes to motion-control axes — an in-app UI step DragonMIDI cannot automate.

This targets the basic per-axis jog mode; the "jog through a recorded move in time" mode remains out of reach without DMC-class hardware regardless.

## macOS virtual gamepad creation: blocked by DriverKit entitlement

Two mechanisms exist for publishing a virtual HID gamepad on macOS:

1. **DriverKit / `HIDVirtualDevice`** (CoreHID framework) — requires the `com.apple.developer.hid.virtual.device` entitlement, granted only through Apple's DriverKit application/approval process, not available to a standard developer account.
2. **`IOHIDUserDeviceCreate`** (IOKit, user-space) — an older API. `OpenJoystickDriver` (xsyetopz/OpenJoystickDriver), an open-source reference implementation, documents an `IOHIDUserDeviceCreate`-based SDL2-compatible output mode gated only by the standard Input Monitoring and Accessibility permissions, with no DriverKit involvement.

Direct testing against both a sandbox and a real macOS instance — using both the current (`IOHIDUserDeviceCreateWithProperties`) and legacy (`IOHIDUserDeviceCreate`) entry points — found both return `NULL` without the DriverKit entitlement, contradicting `OpenJoystickDriver`'s documented behavior. **Neither macOS API is usable without the same Apple-granted entitlement**, closing off the user-space path as a viable workaround.

## The Windows equivalent

**ViGEmBus** is the standard virtual-gamepad kernel driver for Windows (emulates Xbox 360/DualShock 4 controllers at the driver level). The project is archived over a trademark dispute; the last released build (1.17.333.0) continues to work on current Windows 10/11, including 23H2/24H2.

**`vgamepad`** wraps ViGEmBus with a Python API:

```python
import vgamepad as vg
gamepad = vg.VX360Gamepad()
gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_A)
gamepad.left_joystick_float(x_value_float=-0.5, y_value_float=0.0)
gamepad.update()  # pushes the new state to the system
```

It installs the ViGEmBus kernel driver automatically on first install (a one-time, admin-privileged system driver install). Exposes 11 buttons + 2 triggers + 2 analog sticks (Xbox360 profile) or the DS4 equivalent. No published latency/update-rate figures.

Windows had a viable path (`vgamepad`/ViGEmBus, no vendor approval required); macOS did not, and macOS was the blocking constraint for a cross-platform implementation.

## References

- `Using Dragonframe 2025.pdf`, dragonframe.com — "Using a Gamepad to Program Moves" (p. 342–347).
- `docs/dragonframe-messages-research.md` — the OSC surface this was contrasted against.
- SDL2 GameController mapping format / `SDL_GameControllerDB`: https://github.com/mdqinc/SDL_GameControllerDB
- SDL2 Gamepad Tool (referenced by the manual): https://generalarcade.com/gamepadtool/
- `com.apple.developer.hid.virtual.device` entitlement documentation (Apple Developer) — the DriverKit approval requirement.
- OpenJoystickDriver (xsyetopz/OpenJoystickDriver) — documented an `IOHIDUserDeviceCreate` + Input Monitoring/Accessibility path as approval-free; contradicted by direct testing (see above).
- `vgamepad` (yannbouteiller/vgamepad) and ViGEmBus (nefarius/ViGEmBus) — the Windows equivalent.
