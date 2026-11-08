# DragonMIDI Roadmap

> **Purpose:** Evolve DragonMIDI from a fixed MIDI-to-Dragonframe assignment matrix into a flexible, hardware-aware controller-mapping tool for Korg nanoKONTROL2, Korg nanoKONTROL Studio, and Intech Grid modules (initially PBF4 and VSN1).
>
> **Working document for implementation with Claude.** Check boxes are implementation tasks, **not statements about what is currently missing**. Audit the repository and check off existing capabilities before coding. Hardware counts, MIDI messages, and Dragonframe operations must be checked against the current code, devices, and official documentation; do not assume an idea in this document is already supported by Dragonframe.

## Product direction

**Configure by physical control. Calibrate by Dragonframe axis. Review by mapping.**

DragonMIDI should interpret tactile controls and issue supported Dragonframe commands; Dragonframe should own motor configuration, motion execution, coordinate reference, authoritative soft limits, keyframes, and synchronized axis motion. Preserve the simplicity of the original app while supporting arbitrary combinations of faders, buttons, knobs, and relative encoders.

### Non-goals

- Rebuild Dragonframe's Configure Axis UI, motor driver configuration, timeline, or motion planner.
- Maintain a second authoritative motor position or safety-limit database in DragonMIDI.
- Claim that MIDI-derived limits prevent crashes on open-loop rigs without encoders or limit switches.
- Build a general-purpose node-based patching language in the first release.
- Force a virtual controller image to be the only way to edit assignments; a compact table remains essential.
- Assume every controller can send feedback or identify its own physical layout without verification.

## Supported hardware and control inventory

Treat these as **initial UI modeling assumptions**, then confirm counts and exact message types against actual MIDI mappings and device variants. Intech Grid is a modular family: PBF4 and VSN1 are separate modules that may be used together. The hardware modules are not equivalent to the three device families below.

| Hardware | Faders | Rotary controls | Buttons | Jog wheel | Core affordance |
| --- | --- | --- | --- | --- | --- |
| Intech PBF4 | 4 | 4 rotary potentiometers (verify variant) | 4 primary buttons (verify variant) | No dedicated jog wheel | Compact per-axis fader + knob + button workflow |
| Intech VSN1 | None | Relative jog/encoder wheel (verify output behavior) | 8 primary buttons; verify any additional controls | Yes | Axis selection, jogging, mode/action commands |
| Korg nanoKONTROL Studio | 8 | 8 knobs | Channel buttons + transport buttons (verify mapping) | Yes | Integrated multi-axis and jog control |
| Korg nanoKONTROL2 | 8 | 8 knobs | 24 channel buttons + transport buttons (verify mapping) | No | Eight-axis fader control and button actions |

### Hardware verification tasks

- [ ] Identify exact USB/MIDI port naming and discovery behavior for each supported controller.
- [ ] Confirm PBF4 control count and fader/knob/button MIDI messages on real hardware; do not assume MIDI CC numbers.
- [ ] Confirm VSN1 eight-button mapping, jog-wheel message encoding (relative increments vs absolute value), and whether its display/extra buttons are usable.
- [ ] Confirm nanoKONTROL Studio MIDI mappings and transport/jog behavior, including scene modes if relevant.
- [ ] Confirm nanoKONTROL2 MIDI mappings and transport buttons.
- [ ] Test simultaneous PBF4 + VSN1 modules and the current Intech Grid host connection model.
- [ ] Decide how to identify a specific physical module/control across reconnects, rearrangements, and firmware changes.
- [ ] Record validated inventories and protocol samples in repository tests/fixtures.

## JP's user feedback: feature requirements

JP uses DragonMIDI to keyframe and shuttle mini Stewart-platform and linear-slider rigs. His goals are simple tactile positioning, quick endpoint teaching, reusable settings, and minimal physical hardware. **JP asked for a physical center detent; the configurable software stop zone is our solution for faders that lack one.** He described using Dragonframe-configured shuttle speed/step rate; he did **not** specifically request speed proportional to fader distance from center.

| ID | Feature / request | Design ownership | Notes |
| --- | --- | --- | --- |
| F01 | Bidirectional shuttle from fader | DragonMIDI input interpretation; Dragonframe motion | Below center = reverse, above center = forward, center = stop |
| F02 | Configurable center stop zone/deadband | DragonMIDI | Proposed adaptation for non-detented faders; per control |
| F03 | Respect Dragonframe axis speed/step/jog setup | Dragonframe | Do not silently invent a second motor-speed model |
| F04 | Teach endpoint A using physical controls | Joint / integration-dependent | Trigger supported Dragonframe operation, if exposed |
| F05 | Teach endpoint B using physical controls | Joint / integration-dependent | Same limitation as F04 |
| F06 | Rotary selects A vs B; button captures selection | DragonMIDI mapping | A proposed PBF4 gesture, not mandatory for other controllers |
| F07 | Map full fader throw to calibrated A–B travel | DragonMIDI mapping + Dragonframe authoritative limits | Position mode; avoid surprising jumps |
| F08 | Set/use soft travel limits | Dragonframe | Confirm whether external API can set/read them |
| F09 | Operate rigs with no switches/encoders | Workflow support, not a safety guarantee | Open-loop position estimates can become invalid |
| F10 | Copy settings between matching axes (e.g., six Stewart actuators) | Split ownership | Copy controller behavior in DragonMIDI; motor/limit configuration remains Dragonframe's |
| F11 | Zero/reference axes independently before reuse | Dragonframe | Require explicit reference validation |
| F12 | Save and recall configurations/profiles | Split ownership | DragonMIDI mapping profile vs Dragonframe rig/project settings |
| F13 | Control matched motors in unison | Dragonframe | Prefer supported coupling/motion planning |
| F14 | Control matched motors in opposite directions | Dragonframe | May also require DragonMIDI input inversion for a single-axis mapping |
| F15 | Simple A-to-B operation | Joint | Fader position mode after endpoints are established |
| F16 | Minimal tactile interface | UX requirement | Few physical interactions; software inspector does complexity |
| F17 | Accessible setup for less-technical operators | UX requirement | Clear labels, presets, progressive disclosure |
| F18 | Repeatable calibration, ideally “set and forget” | Dragonframe + profile workflow | Revalidate if coordinate reference may have changed |
| F19 | Keyframe and recall motion actions | DragonMIDI triggering Dragonframe | Confirm individually which actions are externally supported |

### Fundamental modes

1. **Shuttle (center-stop):** Fader position conveys direction (and stop), **not absolute axis position**. Default is fixed Dragonframe-configured motion behavior; variable speed based on fader deflection is a possible later option, not a JP requirement.
2. **Position (absolute):** Fader value maps to an absolute target position within a designated, valid Dragonframe axis range. Include inversion and takeover protection.
3. **Jog (relative):** Rotary encoder/jog wheel increments or jog buttons command small moves on a selected axis. Sensitivity/fine mode can modify step size only when supported by the motion command semantics.
4. **Action (button):** Trigger a command, choose an axis, change a layer/mode, or act as a momentary modifier. Avoid triggering destructive actions from ambiguous press/release events.

## Feature compatibility by physical controller

**Legend:** `✓` = natural fit; `~` = possible via alternative control or mapping; `—` = no appropriate dedicated physical control. These are **hardware affordances, not implementation-complete claims**. Software and Dragonframe API dependencies are tracked separately.

| Behavior | PBF4 | VSN1 | nanoKONTROL Studio | nanoKONTROL2 |
| --- | :---: | :---: | :---: | :---: |
| Center-stop fader shuttle | ✓ | ~ (buttons/wheel only) | ✓ | ✓ |
| Adjustable center stop zone on fader | ✓ | — | ✓ | ✓ |
| Absolute position using fader | ✓ | — | ✓ | ✓ |
| Knob for A/B selection or parameter | ✓ | ~ (wheel, modal) | ✓ | ✓ |
| Button capture A/B endpoints | ✓ | ✓ | ✓ | ✓ |
| Select target axis | ✓ | ✓ | ✓ | ✓ |
| Mode/layer switching | ✓ | ✓ | ✓ | ✓ |
| Dedicated jog-wheel fine positioning | — | ✓ | ✓ | — |
| Fine jog via buttons/other controls | ✓ | ✓ | ✓ | ✓ |
| Trigger keyframes / action commands | ✓ | ✓ | ✓ | ✓ |
| Save/copy settings via desktop UI | ✓ | ✓ | ✓ | ✓ |
| Multiple independent fader axes | 4 | 0 | 8 | 8 |
| Paired/mirrored motor operation | * | * | * | * |

`*` Motor coupling or inversion must be implemented through Dragonframe's supported motion behavior; the physical controller is not the determining factor. A VSN1's ability to choose an axis or send commands does not mean it can directly control many axes at once.

### Candidate starter presets (user-editable)

- **PBF4 — 4-axis shuttle:** Four faders shuttle AX1–4, each with center stop zone; four knobs and buttons handle configurable axis-specific options/actions.
- **PBF4 — shuttle + endpoint teach (advanced):** For each channel, fader shuttles; rotary chooses A/B; button invokes *supported* capture operation. Do **not** expose capture as working until integration passes verification.
- **VSN1 — axis selector + jog:** Buttons 1–6 select AX1–6; remaining buttons provide fine/coarse or actions; wheel jogs the selected axis.
- **nanoKONTROL Studio — 8-axis motion:** Eight faders for AX1–8; channel buttons for selection and actions; wheel for selected-axis jog.
- **nanoKONTROL2 — 8-axis motion:** Eight faders, channel buttons for mode/action; transport keys optional for incremental jog.
- **PBF4 + VSN1 — motion + command station:** PBF4 controls axes, VSN1 handles axis selection, jogging, and common actions.

Presets should be generated from verified device capabilities, not brittle MIDI note/CC constants embedded in UI code. Do not silently overwrite user profiles when applying presets.

## Responsibility boundary

| Area | DragonMIDI | Dragonframe | Verification needed |
| --- | --- | --- | --- |
| MIDI discovery, device layout, input events | Owns | — | Device protocol details |
| Layered mappings and named presets | Owns | — | Existing format/migration |
| Fader stop zone and input inversion | Owns | — | None beyond MIDI sampling |
| Physical controller status/activity | Owns | — | Disconnect events |
| Selected axis for wheel/buttons | Owns UI/input state | Executes target motion | Command targeting |
| Absolute fader scaling and soft takeover | Owns input mapping | Owns actual axis position | Ability to query position / safe takeover fallback |
| Motor speed, acceleration, step rate | — | Owns | External motion command behavior |
| Zero/reference and authoritative endpoints | May trigger if supported | Owns | Set/get APIs and acknowledgement |
| Soft limits and motion constraints | Must respect; not authoritative | Owns | Set/get APIs and enforcement |
| Motor coupling and synchronized travel | Should not emulate synchronization with unsynchronized commands | Owns | Supported coupling configurations |
| Keyframe/timeline operations | Maps physical triggers | Owns | Externally callable actions |
| Rig/project persistence | Saves MIDI-side profiles | Owns rig data | Existing Dragonframe project capabilities |

### Mandatory Dragonframe integration audit — before implementing endpoint teaching

- [ ] Inventory commands **actually used in this repository**: protocol, target axes, payload formats, transport, timing, return/ack patterns.
- [ ] Confirm whether Dragonframe supports continuous **start shuttle / stop shuttle** commands, or only finite jog steps / absolute moves. Do not simulate indefinite motion with a naive flood of steps.
- [ ] Verify whether DragonMIDI can **query current axis position**, and how stale/unavailable feedback is represented.
- [ ] Verify whether it can **read, write, and confirm soft limits**, and distinguish minimum/maximum from saved marks.
- [ ] Verify whether it can **set zero/reference** and report whether the reference is valid.
- [ ] Verify whether the integration can invoke **set keyframe**, mark recall, axis selection, and other desired commands.
- [ ] Determine disconnect/timeout behavior of the motion transport, especially while shuttling.
- [ ] Decide which features are fully supported, manually configured in Dragonframe, or deferred. Document this in the UI and feature flags.

**Fallback if endpoints cannot be read/written through the integration:** Users configure limits in Dragonframe; DragonMIDI offers a manually configured position mapping only after the user explicitly confirms the range/reference. Do not present locally stored values as Dragonframe-enforced safety limits.

## UI architecture

### Core views

#### 1) Controller (default)

Replace the current one-size-fits-all matrix as the primary screen with:

- Compact header: MIDI devices, Dragonframe connection, active profile/layer, settings.
- Left: connected hardware modules or a schematic of their physical controls (PBF4, VSN1, nanoKONTROL Studio, nanoKONTROL2).
- Right: context-specific **Control Inspector** showing type, MIDI input, assignment, target, and behavior-specific options.
- A control lights up when receiving MIDI; selecting it opens its inspector. Show last MIDI value and event type to simplify debugging.
- Provide a compact list fallback, keyboard navigation, and a clear indication of unsupported/unassigned controls.
- Accommodate multiple modules in one Intech Grid configuration, and eventually multiple MIDI devices if the input stack supports it.

**Inspector settings by type:**

| Input type | Inspector options |
| --- | --- |
| Fader | Target axis, behavior (`Position` / `Shuttle` / other), center stop zone, inversion, mapping range, takeover behavior |
| Absolute knob | Parameter/endpoint selector, ranges, inversion, button/action mode if supported |
| Relative jog wheel | Target (`Selected axis` / fixed axis), step/jog action, direction, fine/coarse, relative encoding |
| Button | Press/release event, action, momentary/toggle, modifier, axis select, layer or mode change |

#### 2) Mappings (power-user overview)

- Dense editable rows grouped by device/module and active layer rather than enormous A–E columns.
- Show **physical input → behavior → target** clearly.
- Filter/search by device, control, action, axis, layer, assignment status.
- Multi-select controls; duplicate/copy/paste compatible assignments with target substitution.
- Bulk changes must make it obvious which per-control settings will be overwritten.
- Preserve and migrate current A–E groups; allow friendly layer names (`Camera`, `Focus`, `Rig`, `Fine`, `Utility`) without breaking saved profiles.

#### Optional later: Live / Teach

A small operational/teach panel can surface selected axis, current mode, recent commands, A/B capture actions, and calibration status **only where Dragonframe confirms those states**. Avoid a second motor dashboard unless telemetry and real workflows justify it.

### UX principles

- Clear, compact, utilitarian; avoid oversized cards and decorative controls.
- Device-aware UI, but a unified internal model of inputs and actions.
- Progressive disclosure: simple default settings first; advanced ranges and takeover settings tucked away.
- Labels based on operator meaning (`Shuttle`, `Position`, `Stop zone`, `Fine jog`) rather than raw MIDI internals.
- Explicit state visibility for momentary modes, selected axes, active layer, disconnected inputs, and unavailable commands.
- A user should be able to select a control by moving it, without having to identify its CC manually.
- Do not assume a hardware display can be updated; investigate output support separately.

## Detailed implementation backlog

### P0 — Discover, model, and safely map hardware

- [ ] Audit current architecture, saved configuration schema, and all three supported controller-family integrations.
- [ ] Define a normalized input identity: `{device, module, control, type, rawMidi}`; avoid depending on CC number alone when possible.
- [ ] Add device capability descriptors for faders, absolute knobs, relative wheels, and buttons.
- [ ] Normalize MIDI input events, including relative encoders and press/release pairs.
- [ ] Define a mapping domain model separating **input**, **behavior**, **target**, **layer**, and per-control **options**.
- [ ] Implement controller-aware control selection and a contextual inspector.
- [ ] Implement the Mappings list/table as a dense alternate view.
- [ ] Expose live input activity for each control and MIDI learn/select-by-moving.
- [ ] Maintain backward compatibility with existing mappings, A–E groups, and nanoKONTROL behavior.
- [ ] Test device disconnect/reconnect and mapping identity stability.

**Acceptance criteria**

- Existing nanoKONTROL2 and nanoKONTROL Studio profiles load unchanged or migrate without information loss.
- PBF4 and VSN1 controls appear independently, with correct control type and received events.
- Moving/pressing a physical control highlights the correct UI control and selects its inspector when MIDI Learn is active.
- An arbitrary future input control can be added through descriptors, without adding a new column per controller to the configuration schema.

### P1 — Shuttle, position, wheel, and buttons

- [ ] Implement fader shuttle interpretation: reverse / stop / forward.
- [ ] Add adjustable stop zone per fader, centered near 63–64 on a 0–127 range or on the device's calibrated neutral point.
- [ ] Default to Dragonframe axis-configured shuttle/jog speed; don't equate fader distance with speed in V1.
- [ ] Add optional reverse/invert direction.
- [ ] Define explicit state transitions; prevent redundant commands and handle noisy MIDI values at stop boundaries (consider hysteresis).
- [ ] Ensure a verified stopping path on zone entry, device disconnect, loss of focus/transport, and shutdown. If this cannot be guaranteed, do not offer indefinite shuttle.
- [ ] Implement absolute fader position mapping to a specified, validated target range.
- [ ] Add soft takeover / pickup on mode, layer, target, and profile changes to prevent jumps.
- [ ] Implement VSN1 and nanoKONTROL Studio wheel jogging with correct relative encoding and sensitivity.
- [ ] Implement button behavior types: trigger, momentary hold, toggle, modifier, layer/mode change, select axis.
- [ ] Implement a clear runtime indicator for selected axis, active mode, and fader pickup state.

**Acceptance criteria**

- Fader below zone commands reverse; inside commands stop; above commands forward, under an integration-verified motion protocol.
- MIDI noise around center does not cause rapid reverse/forward chatter.
- Switching a non-motorized fader to position mode cannot command an unexpected large move before pickup/confirmation.
- Releasing a momentary modifier restores its prior mode predictably.
- Wheel rotation directions and amount are correct on VSN1 and nanoKONTROL Studio.
- Loss of input or communications follows a tested safe behavior; UI never labels an unverified emergency-stop mechanism as fail-safe.

### P2 — Profiles, duplication, and presets

- [ ] Add named DragonMIDI mapping profiles and editable layer names.
- [ ] Provide default presets listed above, using verified device capability descriptors.
- [ ] Implement copy/paste/duplicate mapping settings across selected controls/axes.
- [ ] Distinguish mapping copies from motor calibration copies in wording and behavior.
- [ ] Add profile import/export with schema version and migration support.
- [ ] Handle missing devices/modules gracefully when loading a profile.
- [ ] Confirm safe persistence of selected axis, modes, and state (do not restore actively moving state).

**Acceptance criteria**

- Configure one PBF4 channel and copy appropriate settings to channels 2–4 while specifying new axes.
- Assign six controller channels to Stewart actuators without repetitive manual configuration.
- Save/reopen a profile without breaking current nanoKONTROL configurations.
- Profiles work even if a mapped controller is temporarily disconnected; UI identifies missing devices.

### P3 — Endpoint teach workflow (conditional)

**Gate:** Only start once the integration audit confirms the necessary commands and semantics.

- [ ] Design a small `Teach endpoints` workflow: prepare/reference → approach A slowly → capture A → approach B slowly → capture B → review → enable position mapping.
- [ ] Support the PBF4 rotary-select-A/B + button-capture gesture where appropriate.
- [ ] Support alternate button-driven capture on VSN1 and Korg controllers.
- [ ] Query/display the actual Dragonframe axis state and acknowledgement, if supported.
- [ ] Do not mark calibration verified solely because a local button was pressed.
- [ ] Require explicit validation before enabling absolute position mode or copying ranges.
- [ ] Respect Dragonframe authoritative soft limits and configured motion parameters.
- [ ] If API support is insufficient, use a documented manual Dragonframe setup workflow rather than fake software-level calibration.

**Acceptance criteria**

- Capturing A/B cannot silently succeed if Dragonframe rejected or did not support the operation.
- A copied travel range does not imply that another physical actuator has been homed or calibrated.
- Changing the Dragonframe coordinate reference invalidates or clearly warns on affected local mappings where detectable.
- The UI never promises that open-loop soft limits are crash-proof.

### P4 — Advanced / later

- [ ] Optional variable-speed shuttle based on fader deflection (only if user testing supports it and Dragonframe commands permit it).
- [ ] Hold-to-fine modifiers; customizable encoder acceleration.
- [ ] Additional Intech Grid modules via declarative hardware layouts and input descriptors.
- [ ] Hardware display/LED feedback, only after protocol verification.
- [ ] Optional Live view with confirmed motion status and feedback.
- [ ] Operator-friendly guided rig presets and specialized A/B workflows.
- [ ] Investigate Dragonframe-provided coupling or synchronized motion shortcuts; do not implement MIDI-side pseudo-synchronization.

## Technical architecture proposal (adapt to existing repo)

```text
MIDI / Intech hardware discovery
              │
     normalized input events
              │
   device + control descriptors
              │
    mapping / layer / profile
              │
   behavior engine (stateful)
   ├─ Shuttle + stop zone
   ├─ Absolute + pickup
   ├─ Relative jog
   └─ Button / modifier / action
              │
 Dragonframe command adapter
   ├─ capability/availability checks
   ├─ command validation + error reporting
   └─ connection + stop handling
              │
          Dragonframe
```

### Data model sketch (not a prescriptive schema)

```json
{
  "schemaVersion": 2,
  "profileName": "Stewart Platform",
  "layers": [{ "id": "A", "name": "Rig" }],
  "mappings": [
    {
      "input": { "deviceId": "device-instance", "moduleId": "PBF4-1", "controlId": "fader-1", "type": "fader" },
      "layerId": "A",
      "behavior": { "type": "shuttle-center-stop", "stopZonePercent": 12, "invert": false },
      "target": { "type": "dragonframe-axis", "axisId": "AX1" }
    }
  ]
}
```

**Notes:** Device identity, module identity, and position mapping details are deliberately placeholders. Inspect the current source of truth, persistence, and Intech Grid discovery model before adopting this schema. A mapping should not store an asserted physical calibration when Dragonframe owns it.

## Safety and operational constraints

This is motion-control software controlling potentially hazardous machinery, not just MIDI-to-UI shortcuts.

- A configurable stop **zone** is a usability feature, not a mechanical detent or emergency-stop mechanism.
- In open-loop stepper systems, missed steps and lost reference can invalidate virtual position and software limits.
- Never guarantee prevention of crashing or overrun without validated independent hardware safety measures.
- Design finite motion commands and fail-safe stop behavior with the actual Dragonframe protocol, not assumptions about repeated MIDI input.
- Document what happens when the MIDI controller, Intech Grid transport, network, or Dragonframe connection disappears during motion.
- Prefer deliberate reduced-speed, hold-to-move teaching and require an operator to check physical clearances.
- Avoid unintended moves when switching from shuttle to absolute position on non-motorized faders; require pickup or deliberate enable.
- Do not equate local A/B marks with Dragonframe-enforced limits.
- Provide stop/test strategies that can be validated on simulated or unloaded rigs before real hardware.

## Testing plan

### Unit tests

- [ ] Stop-zone boundary behavior across 0–127 inputs, including neutral at 63/64 and customizable centering.
- [ ] Hysteresis, noise, duplicate MIDI events, and direction transitions.
- [ ] Absolute scaling: inversion, clamping, stale position feedback, and pickup.
- [ ] Relative jog decoder for each actual MIDI encoding.
- [ ] Button press/release, latch/toggle, and hold modifier transitions.
- [ ] Profile serialization, schema migration, layer names, copying, and missing devices.
- [ ] Device/control identity after reconnect or module rearrangement.

### Integration tests

- [ ] Run with a mocked Dragonframe command adapter; capture exact commands and verify stop transitions.
- [ ] Test network/transport loss during shuttle and record the resulting behavior.
- [ ] Verify available axis, position, limits, and keyframe commands against a real Dragonframe installation before enabling corresponding UI.
- [ ] Verify PBF4 and VSN1 together, plus both Korg controllers, using captured/real MIDI messages.
- [ ] Confirm old profiles continue to behave identically after migration.

### Hardware acceptance scenarios

1. **PBF4 linear slider:** Set a 12% center stop zone; shuttle reverse/stop/forward predictably without chatter; verify stopping on disconnect.
2. **PBF4 four-channel rig:** Copy fader shuttle settings from channel 1 to 2–4, changing axis targets only.
3. **VSN1:** Select one of six axes via buttons; jog via wheel; temporarily hold a fine modifier.
4. **nanoKONTROL Studio:** Control six Stewart axes with faders, use its jog wheel on a selected axis, and map buttons to actions.
5. **nanoKONTROL2:** Control six axes with faders; use transport/channel buttons for jog/action alternatives.
6. **Position pickup:** Switch layer or motion mode while a fader is at a stale physical position; no unexpected large move occurs.
7. **Endpoint teach (if available):** Capture A/B and confirm state in Dragonframe, then map fader to the valid range; failed capture cannot look successful.

## Implementation sequence for Claude

For each phase, work in small reviewable commits/PRs. Do **not** mark roadmap tasks complete based solely on adding UI; the relevant behavior must be implemented and tested.

1. **Repository reconnaissance:** Read architecture, existing Intech and Korg adapters, MIDI event model, Dragonframe adapter, UI, persistence, and tests. Produce `docs/dragonmidi-capability-audit.md` or equivalent with verified behavior, gaps, and exact files. Cross-check assumptions in this roadmap.
2. **Capabilities and event normalization:** Introduce minimal domain model and regression tests while preserving existing profiles.
3. **Controller UI + Inspector:** Ship usable mapping editor and live input highlighting before redesigning every advanced setting.
4. **Behavior engine:** Add shuttle center-stop, position pickup, relative jog, and button actions behind tested Dragonframe command capabilities.
5. **Profiles and bulk editing:** Add named layers, presets, copy/paste, migration, and missing-device recovery.
6. **Dragonframe capability gate:** Implement endpoint teaching only after proving read/write/capture semantics and safe handling in real integration tests.
7. **Polish and extend:** Accessibility, operator states, additional modules, optional Live view.

### Suggested prompt to start a Claude coding session

> Read `roadmap.md` and audit the repository before editing code. Identify which roadmap capabilities already exist, which hardware facts are verified, what the Dragonframe adapter actually supports, and how existing settings are persisted. Do not assume endpoints/soft limits or continuous shuttle commands are available. Give me a short architecture summary, a list of file-level changes for P0, compatibility risks, and a proposed first small PR. Preserve current nanoKONTROL and Intech functionality. Then implement only the first agreed incremental task with tests and update the roadmap checkboxes based on verified completion.

## Decisions / open questions

- [ ] What is the exact supported set of Dragonframe motion/limit commands in the code and installed Dragonframe version?
- [ ] Can shuttle be implemented safely as a sustained motion command, or must the product use bounded jogging instead?
- [ ] Does the application already support multiple simultaneous MIDI devices, or only modules on one Intech Grid connection?
- [ ] What is the canonical identity of each Intech Grid module and control across reconfiguration?
- [ ] What happens to currently moving axes on disconnect or application exit?
- [ ] Are user-customized nanoKONTROL assignments stored by global CC or per device instance?
- [ ] What are the verified physical MIDI ranges and neutral positions for all faders?
- [ ] Is live Dragonframe axis-position readback available to support accurate soft takeover?
- [ ] Can Dragonframe limits be queried/changed externally, or only through its own UI?
- [ ] Does endpoint teaching need a separate workflow, or can it be an inspector action?
- [ ] Should named layers initially map 1:1 to the current A–E groups, and should more than five be allowed later?
- [ ] Should the eventual UI support simultaneous controllers from different manufacturers?

---

**North star:** A user can connect a supported controller, select a physical control by moving it, choose a meaningful behavior and Dragonframe axis, then operate a rig with clear feedback and no surprises. JP's ideal flow—**shuttle → teach A/B → position**—is a product target, gated by verified Dragonframe APIs and sound motion-safety behavior.
