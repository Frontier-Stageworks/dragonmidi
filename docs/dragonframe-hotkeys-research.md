# Dragonframe Hot Keys — Reference

Source: Dragonframe's own **Preferences → Hot Keys** table (Action / Hot Key / Alt 1 / Alt 2 / Alt 3), captured via screenshots on 2026-07-19. This is the authoritative source for action names and default bindings — more complete than the user manual's prose, which only documents a subset of these (e.g. `Step Moco Forward`/`Step Moco Back` and `Test Shot` appear here but nowhere in the manual text).

**Capture is not confirmed complete.** The three screenshots covering this table were scrolled captures, not a full export; there is a likely gap between `Next Camera` and `Toggle Live View` below (the two captured chunks don't visibly connect there), and no confirmation the list doesn't continue past `Script Custom 4`. Treat "not found in this table" as "not found in what's been captured so far," not as proof an action doesn't exist.

## Full Table (as captured)

| Action | Hot Key | Alt 1 | Alt 2 | Alt 3 |
|---|---|---|---|---|
| Shoot | Return | Enter | NUM Enter | Not Set |
| Shoot 2 Frames | Q | Not Set | Not Set | Not Set |
| Shoot 3 Frames | W | Not Set | Not Set | Not Set |
| Shoot 4 Frames | E | Not Set | Not Set | Not Set |
| Test Shot | ' | Not Set | Not Set | Not Set |
| Shoot Burst | Not Set | Not Set | Not Set | Not Set |
| Delete | Del | NUM * | Backspace | * |
| Play | NUM 0 | 0 | Space | Not Set |
| Step Back | NUM Left | NUM 1 | 1 | Not Set |
| Step Forward | NUM Right | NUM 2 | 2 | Not Set |
| Toggle Preview | NUM . | NUM , | Not Set | Not Set |
| Live | NUM 3 | 3 | Not Set | Not Set |
| Auto Toggle | NUM 4 | 4 | Not Set | Not Set |
| Live Toggle | NUM 5 | 5 | Not Set | Not Set |
| Short Play | Not Set | Not Set | Not Set | Not Set |
| Short Play Toggle | NUM 6 | 6 | Not Set | Not Set |
| Black | NUM 7 | 7 | Not Set | Not Set |
| Loop | NUM 8 | 8 | Not Set | Not Set |
| Cut Back | NUM 9 | 9 | Not Set | Not Set |
| Opacity Up | NUM + | Not Set | Not Set | Not Set |
| Opacity Down | NUM - | Not Set | Not Set | Not Set |
| Opacity Up Fine | SHIFT NUM + | Not Set | Not Set | Not Set |
| Opacity Down Fine | SHIFT NUM - | Not Set | Not Set | Not Set |
| Mute | NUM / | / | Not Set | Not Set |
| Home | Home | Not Set | Not Set | Not Set |
| End | End | Not Set | Not Set | Not Set |
| 3 Step | Not Set | Not Set | Not Set | Not Set |
| 3 Step Toggle | Not Set | Not Set | Not Set | Not Set |
| Step by Holds | Not Set | Not Set | Not Set | Not Set |
| Play by Tag | Not Set | Not Set | Not Set | Not Set |
| Next Camera | Not Set | Not Set | Not Set | Not Set |
| *(possible gap in capture)* | | | | |
| Toggle Live View | Not Set | Not Set | Not Set | Not Set |
| Capture Making Of | Not Set | Not Set | Not Set | Not Set |
| Media Layer Toggle | L | Not Set | Not Set | Not Set |
| Guide Group #1 Toggle | SHIFT ! | Not Set | Not Set | Not Set |
| Guide Group #2 Toggle | SHIFT @ | Not Set | Not Set | Not Set |
| Guide Group #3 Toggle | SHIFT # | Not Set | Not Set | Not Set |
| Guide Group #4 Toggle | SHIFT $ | Not Set | Not Set | Not Set |
| Guide Group #5 Toggle | SHIFT % | Not Set | Not Set | Not Set |
| Guide Group #6 Toggle | SHIFT ^ | Not Set | Not Set | Not Set |
| Guide Group #7 Toggle | SHIFT & | Not Set | Not Set | Not Set |
| Guide Group #8 Toggle | SHIFT * | Not Set | Not Set | Not Set |
| Media Layer Opacity Up | K | Not Set | Not Set | Not Set |
| Media Layer Opacity Down | J | Not Set | Not Set | Not Set |
| Toggle X-Sheet/Guide Layers | G | Not Set | Not Set | Not Set |
| Drawing Toggle | D | Not Set | Not Set | Not Set |
| Grid Toggle | Not Set | Not Set | Not Set | Not Set |
| Solo Camera | Not Set | Not Set | Not Set | Not Set |
| Mark In | I | Not Set | Not Set | Not Set |
| Mark Out | O | Not Set | Not Set | Not Set |
| Go to In Point | SHIFT I | Not Set | Not Set | Not Set |
| Go to Out Point | SHIFT O | Not Set | Not Set | Not Set |
| Toggle Step by Tag | Not Set | Not Set | Not Set | Not Set |
| Show/Hide Hidden Frames | H | Not Set | Not Set | Not Set |
| Add Hold | R | Not Set | Not Set | Not Set |
| Remove Hold | OPT R | Not Set | Not Set | Not Set |
| Hold On Still Image | T | Not Set | Not Set | Not Set |
| Next Playback Exposure | Not Set | Not Set | Not Set | Not Set |
| Prev Playback Exposure | Not Set | Not Set | Not Set | Not Set |
| Insert Camera | Not Set | Not Set | Not Set | Not Set |
| Return Camera to End | Not Set | Not Set | Not Set | Not Set |
| Difference with Live | Not Set | Not Set | Not Set | Not Set |
| Toggle Focus Controls | Not Set | Not Set | Not Set | Not Set |
| Toggle Focus Check | Not Set | Not Set | Not Set | Not Set |
| Toggle Focus Peaking | Not Set | Not Set | Not Set | Not Set |
| Increase Video Size | CMD NUM + | Not Set | Not Set | Not Set |
| Decrease Video Size | CMD NUM - | Not Set | Not Set | Not Set |
| Increase Audio Latency | Not Set | Not Set | Not Set | Not Set |
| Decrease Audio Latency | Not Set | Not Set | Not Set | Not Set |
| **Step Moco Forward** | **OPT SHIFT NUM Right** | Not Set | Not Set | Not Set |
| **Step Moco Back** | **OPT SHIFT NUM Left** | Not Set | Not Set | Not Set |
| Toggle Work Light | Not Set | Not Set | Not Set | Not Set |
| Move Playhead to Closest … | Not Set | Not Set | Not Set | Not Set |
| View : Mirror | Not Set | Not Set | Not Set | Not Set |
| View : Rotate | Not Set | Not Set | Not Set | Not Set |
| View : Portrait | Not Set | Not Set | Not Set | Not Set |
| Next Panoramic View | Not Set | Not Set | Not Set | Not Set |
| Script Custom 1 | Not Set | Not Set | Not Set | Not Set |
| Script Custom 2 | Not Set | Not Set | Not Set | Not Set |
| Script Custom 3 | Not Set | Not Set | Not Set | Not Set |
| Script Custom 4 | Not Set | Not Set | Not Set | Not Set |

## Notable Findings

- **`Step Moco Forward`/`Step Moco Back`** (default `Option+Shift+Right`/`Option+Shift+Left`) — the action DragonMIDI's jog wheel already drives for Arc Motion Control frame stepping (`docs/llds/static-mapping.md § Keystroke Output (Arc Motion Control)`). Confirmed here as the actual action name and default binding.
- **No dedicated toggle for the "Jogpad controls with Arc interface" mode** (the blue-highlighted jogpad icon described in `docs/dragonframe-messages-research.md`'s source manual, p.316) appears anywhere in this table. The manual describes this toggle as mouse-only ("click the jogpad icon once") with no keyboard-shortcut alternative documented; this table search neither confirms nor rules out a hotkey existing outside the captured rows (see the capture-completeness caveat above).
- **No standalone "Set Keyframe" action** exists in this table. Setting a keyframe via keyboard is only reachable through the Jogpad's own Enter-key overload (`Setting a Keyframe with the Jogpad`, manual p.312), which is context-dependent: `Enter`/`Return`/`NUM Enter` are *also* the default bindings for `Shoot` (see the table's first row) when the jogpad-in-Arc mode isn't active. There is currently no known way for DragonMIDI to force that mode on or verify it's active before sending a synthesized `Enter`.
- **`Test Shot`** (`'`) has no OSC equivalent either — an addition to the "functions not available via OSC" list from earlier research.

## References

- Dragonframe Preferences → Hot Keys (in-app, screenshots captured 2026-07-19).
- `Using Dragonframe 2025.pdf` — "Using the Jogpad Window with the Dragonframe Keypad" (p.309-316), for the Jogpad's Enter-sets-keyframe / digit-selects-axis behavior this table doesn't itself explain.
- `docs/dragonframe-messages-research.md` — the OSC-message-side counterpart to this hotkey research.
