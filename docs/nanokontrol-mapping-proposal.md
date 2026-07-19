# nanoKONTROL Mapping Proposal — Status Tracker

A friend proposed a set of Arc Motion Control mappings for the KORG nanoKONTROL2 (see the diagram shared 2026-07-19) as a brainstorm — none of it is implemented. This tracks each proposed function against what's actually reachable from DragonMIDI, translated to the nanoKONTROL Studio (the hardware DragonMIDI targets — see `docs/high-level-design.md`).

**Status legend:**
- **Done** — already implemented in DragonMIDI today.
- **Possible** — a real mechanism exists or is plausible, but isn't built yet (may still need confirmation).
- **Not possible** — no mechanism DragonMIDI can reach has been found (would need gamepad, DMC hardware, or another unavailable protocol).
- **Not building** — a mechanism exists, but was deliberately rejected (see Implementation column for why).

| nanoKONTROL Studio control | Proposed mapping | Status | Implementation |
|---|---|---|---|
| Faders 1–8 | Jog Motor | **Done** | Already the default: Fader → `/dragonframe/axis/{name}/gotoPosition` (OSC axis direct target). `docs/llds/static-mapping.md` § OSC Axis (Direct) Target. |
| Knobs 1–8 | Axis Position Fine Tune | **Done** | Already the default: bank-derived Knob N → `stepPosition` nudge, scaled `0.1` per raw-value increment. `docs/llds/static-mapping.md` § Bank Derivation. |
| Play (▶) | Play Test Move | **Done** (partial) | Existing default `Play` → `/dragonframe/play` already plays back shot frames, including ones from a motion-control move — covers "review a shot move." Does **not** cover DMC hardware's specific live "Run Move Test" (running the move live *before* shooting) — that requires real DMC-class hardware speaking its own protocol, not reachable from here. |
| Scene selector (up to 5 onboard scenes) | Page Through Axis Channels — click next scene to shift Fader 1↔9, 2↔10, etc., up to 40 addressable axes | **Possible** (unconfirmed) | Reinterpreted from the original diagram's Track ◄/► suggestion — using the nanoKONTROL Studio's own onboard Scene selector to shift DragonMIDI's own fader/knob bank offset is entirely self-contained (no Dragonframe jogpad-mode risk at all, since it never touches Dragonframe's UI state). A KVR Audio forum thread confirms the hardware sends a distinguishable SysEx per scene change, but the exact byte pattern isn't documented and needs empirical capture (debug-logging raw SysEx while pressing the physical scene control, the same way the original Scene-button pattern was reverse-engineered). Not yet attempted. |
| S (Solo) 1–8 | Solo Axis Channel | **Not possible** | Closest Dragonframe match is the "Animator Controlled Axis" feature, whose manual entry explicitly says to use a gamepad or Monogram Creative Console — not keyboard, not OSC. Gamepad is the path already found blocked by macOS's DriverKit entitlement requirement (`docs/dragonframe-gamepad-research.md`). |
| M (Mute) 1–8 | Mute (Disable/Off) Axis | **Not possible** | Same as Solo Axis Channel — Animator Controlled Axis, gamepad/Monogram-only. |
| R (Record) 1–8 | Record (Enable/On) Axis | **Not possible** | Same as Solo Axis Channel — Animator Controlled Axis, gamepad/Monogram-only. |
| Marker ◄/► | Inch Motor | **Not possible** | Documented only as mouse-only controls in the Arc workspace's axis list, or as the gamepad's "Inching (Slow Jogging)" feature — no keyboard or OSC path found. |
| Cycle | Cycle Select Axis Channels (Highlight) | **Not building** | Same undetectable jogpad-mode precondition as the reverted Record N feature (Dragonframe's blue "jogpad controls" icon must already be on, and DragonMIDI has no way to detect or force it). Also has no DragonMIDI-side equivalent concept to fall back on, since "highlighted axis" is purely Dragonframe's own Jogpad UI state. |
| Set (Marker section) | Set Keyframe | **Not building** | Same jogpad-mode precondition as Record N; user decision (2026-07-19) was not to repeat that risk. |
| Transport Record (●) | Set Keyframe | **Not building** | Same as above. Also conflicts with the existing default: this button already sends `/dragonframe/shoot` — repurposing it for keyframing would require deciding which of the two wins. |
| Rewind (◄◄) / Fast Forward (►►) | Move Motors to Previous/Next Keyframe | **Not building** | Same jogpad-mode precondition as Record N. Also conflicts with the existing default: these already send `stepBackward`/`stepForward` frame stepping. |
| Stop (■) | E-Stop | **Not building** | Same jogpad-mode precondition as Record N (the Jogpad's own stop-motors gesture is `/`, `*`, or Backspace). Also conflicts with the existing default: this button already sends `/dragonframe/live`. |

## Open Item

The one row still worth pursuing is the **Scene selector paging** idea — it's architecturally clean (entirely inside DragonMIDI, no Dragonframe-side precondition) and would meaningfully extend the app (up to 40 addressable axes instead of 8). Next step is capturing the real SysEx the nanoKONTROL Studio sends on a scene change, with DragonMIDI's Native Mode handshake active. Offered to add temporary debug logging for this; not yet done.

## References

- `docs/dragonframe-hotkeys-research.md` — the Hot Keys table this analysis cross-references.
- `docs/dragonframe-gamepad-research.md` — the gamepad path blocked by macOS's DriverKit entitlement, relevant to the Solo/Mute/Record Axis Channel rows.
- `docs/high-level-design.md` § Non-Goals — "Multi-instance or bank-switching support" is currently scoped out; the Scene selector paging idea would revisit this if pursued.
