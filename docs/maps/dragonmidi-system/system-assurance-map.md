# System Assurance Map

Phase 1 artifact. Identifies where assurance matters without remapping the codebase — reference LID artifacts wherever possible instead of re-describing architecture. See `docs/workflow.md § Phase 1`.

## System / segment(s) covered

- **System:** DragonMIDI — MIDI-to-OSC/keystroke/WebSocket bridge between a KORG control surface and Dragonframe.
- **Segment(s) in scope:** Whole system (OSC I/O, MIDI input, mapping engine, Controller Profile loading, Preset Store, keystroke output, WebSocket output). App UI (`app.py`, `mapping_widgets.py`, `status_widgets.py`) covered only where it affects an assurance claim about the pipeline; pure layout/rendering excluded.
- **LID artifacts consulted:** `docs/high-level-design.md` (current — Phase 6/Group-switching is the latest delivered phase); `docs/llds/{app-ui,keystroke-output,midi-input,osc-io,static-mapping,websocket-output}.md`; `docs/specs/{app-ui,keystroke-output,midi-input,osc-io,static-mapping,websocket-output}.md` (EARS, `[x]`/`[ ]` markers); direct inspection of `dragonmidi/*.py` and `tests/*.py`.
- **LID artifacts NOT consulted / not available:** None missing — LID Mode: Full, HLD/LLD/EARS all present and current.

## Trust boundaries

| Boundary | What crosses it | Trust level of the far side | Notes |
|---|---|---|---|
| Dragonframe OSC Output → OSC Listener (UDP) | Arbitrary bytes on a local UDP port; well-formed `getAllPosition` responses and OSC `#bundle`/message packets | Local peer, explicitly documented as trusted ("Dragonframe is a trusted local peer, not untrusted input" — `osc_io.py`), but reachable by anything on localhost/LAN able to send UDP to the bound port | `decode_osc_packet` has structural guards (`MAX_BUNDLE_DEPTH`, `element_size` validation); still no authentication of the sender. |
| Dragonframe → WebSocket Output Adapter | A single inbound WebSocket connection at a fixed path; DragonMIDI discards every message the peer sends (`async for _ in connection: pass`) | Local peer, unauthenticated; DragonMIDI is the server, Dragonframe the client | No message content ever flows from Dragonframe over this channel into DragonMIDI logic — the only cross-boundary data is connection presence/absence. |
| Controller Profile config files (`.yaml`) | User- or contributor-authored files from a bundled folder and `~/Documents/DragonMIDI/controllers/` | Untrusted-shape but locally-authored input; explicitly designed for non-programmer third parties (HLD "secondary audience") | `_parse_profile_file`/`_validate_top_level_fields` reject malformed files per-file, with the rest of the merge proceeding (`PROFILE-LOAD-010`). |
| Preset Store files (`~/Documents/DragonMIDI/configurations/*.json`) | Persisted (Bank, Group) → axis-name/min/max table, re-read on every launch/profile switch | Locally-written, but editable by hand or corruptible; not signed or checksummed | `load_group_axis_targets` explicitly bounds-checks Bank (1–8) and Group (1–5) indices before use, citing a specific negative-indexing risk it closes. |
| MIDI hardware → MIDI Input Adapter | Raw MIDI messages from whatever device matches the active profile's `match_substring` | Physical device, assumed to be the declared controller; no protocol-level authentication | Native Mode handshake (Studio only) increases confidence the right device is attached but is not a security boundary. |
| OS keyboard focus (Keystroke Output) | A synthesized keystroke, delivered to whichever application currently holds OS focus | Explicitly not trust-checked — HLD Non-Goal: no frontmost-window detection | A control mapped to Keystroke output can affect an unrelated foreground application if Dragonframe isn't focused; accepted risk per HLD. |

## Semantic chokepoints

| Chokepoint | What routes through it | Why it's a chokepoint | Existing safeguards |
|---|---|---|---|
| `osc_io.py::decode_osc_packet` | Every UDP datagram Dragonframe sends, including every `getAllPosition` response the Mapping View's axis picker depends on | Sole OSC decoder; malformed input here can propagate a bad "discovered axis" into every subsequent direct-axis mapping | `MAX_BUNDLE_DEPTH` recursion cap, `element_size` bounds validation; broad `except Exception: return` in `AxisDiscovery.handle_datagram` as a backstop. |
| `mapping.py::MappingEngine.process()` / `.process_websocket()` / `.process_keystroke()` | Every incoming MIDI event, dispatched to OSC/WebSocket/keystroke output | Sole MIDI-event-to-output dispatcher; a dispatch-order or channel-match bug affects every mapped control at once | Channel-match check, Group-switch special-case ordering (`MAP-GROUP-005`), example-test coverage per control type. |
| `mapping.py::MappingEngine.set_profile()` | Full engine state (dedup, Group index, axis targets, bank-derived positions) whenever the user switches Controller Profile | A single state-reset bug leaks state from the old profile into the new one across every subsequent control move | Property-tested full post-switch trace isolation (`test_mapping_profiles.py`). |
| `mapping.py::_process_bank_derived` (Knob N clamp formula, `MAP-BANK-008/009/010`) | Every Knob-driven axis nudge, for every Bank with an axis assigned, in every Group | Directly commands physical/virtual rig motion in Dragonframe; a clamp bug can send an out-of-configured-range position | Property-tested clamp-to-range including a mutation-verified interior-point test. |
| `mapping.py::build_opinionated_map` / `_fader_entries()`/`_knob_entries()`/`_mute_entries()`/`_transport_entries()` (plus the Scene-button insertion in `build_opinionated_map()` itself) | Every Controller Profile's synthesized static key→`_MapEntry` table, both bundled profiles and every third-party config | If wrong, every control on every profile using the shared helpers is silently mis-mapped at its source (static table content, not runtime dispatch — that's `MappingEngine.process()`, a separate chokepoint) | Hand-derived golden-value tests, mutation-verified (`DM-004`), for the two bundled profiles; third-party configs unaddressed. |
| `controller_profile_loader.py::_parse_profile_file` / `load_controller_profiles` | Every third-party Controller Profile config file, merged with the two bundled profiles | Determines what a contributor's config file actually causes the app to do; wrong parsing silently changes another person's rig behavior | Per-file validation with graceful skip-and-warn (`PROFILE-LOAD-010`); user-local-wins merge semantics (`PROFILE-LOAD-004`). |
| `preset_store.py::load_group_axis_targets` | Every persisted (Bank, Group) axis assignment, re-loaded on every launch and profile switch | Feeds directly into which axis a fader/knob addresses; a bad index here was explicitly identified as capable of causing `bank_fader_keys[-1]` to silently resolve to the wrong Bank | Explicit bounds-check on Bank/Group indices, entry-level validation with skip-and-warn. |

## Externally visible outputs

| Output | Consumed by | Consequence if wrong | Currently checked by |
|---|---|---|---|
| OSC messages (`gotoPosition`, `stepPosition`, action addresses) | Dragonframe's OSC Input port | Wrong/out-of-range axis position commands physical motion incorrectly; wrong action address fails silently (no-op in Dragonframe) | Large example-test suite; property tests for bank-derived clamp behavior. |
| WebSocket JSON commands (`E-Stop`, `select-AXn`, `jog-AXn`) | Dragonframe's WebSocket client, `{"input": ...}` shape | `E-Stop` is a motion-control emergency-stop function — a dropped or malformed send is a safety-relevant silent failure | Example tests for encoding/dispatch, executed and passing (`DM-007`); no evidence characterizes delivery reliability under adapter *failure* specifically. |
| Synthesized OS keystrokes | Whatever application currently holds OS focus (intended: Dragonframe) | Wrong keystroke, or delivery to the wrong app, silently fails to perform the intended action (or performs an unintended one in another app) | Example tests for the encode/press/release sequence and stuck-modifier release ordering. |
| Status UI indicators (MIDI signal, Dragonframe signal) | The human operator, at a glance | A falsely "live" indicator masks a genuinely dead channel; a falsely "quiet"/"error" indicator could cause the operator to distrust a working system | `signal_monitor.py` recency-window logic; example tests. |

## High-consequence failure paths

| Failure path | Trigger | Consequence | Blast radius | Currently mitigated by |
|---|---|---|---|---|
| Malformed/adversarial OSC bundle framing | Non-positive/oversized `element_size`, deeply nested `#bundle` | Without the guards below: unbounded recursion depth / large stack-walk cost on `RecursionError`. Direct testing (negative/zero `element_size`, deep nesting) found no actual hang without the guards either — they already failed fast or raised, caught by the broad handler; the real, narrower consequence is unbounded recursion cost, not a hang | Whole OSC Listener thread, transitively every direct-axis mapping relying on discovered axis names | `MAX_BUNDLE_DEPTH=8` + `element_size` validation (`BundleBoundsError`), mutation-verified (`property-register.md` `DM-001`). |
| Out-of-range tracked axis position at nudge time | Dragonframe's live-reported position (or DragonMIDI's internal estimate) starts outside the fader's configured `[min, max]` | A knob nudge could, if unclamped, send Dragonframe a position outside the user-configured range | Single axis per occurrence, but potentially every nudge afterward if the recovery formula is wrong | `MAP-BANK-010`'s formula (reuses `MAP-BANK-008`'s clamp), property-tested and mutation-verified (`DM-003`). |
| `E-Stop` / WebSocket command silently dropped | Port 59177 bind failure, no active connection, or a send-time exception | A safety/emergency-stop control that appears mapped in the UI does nothing when triggered, with no operator-visible signal (WebSocket has no dedicated status indicator by design — HLD "fails silently, not as a new status indicator") | Whole WebSocket output path, and specifically the one control (`E-Stop`) the HLD singles out as safety-relevant | `logger.warning`/`logger.debug` only — no runtime signal reaches the operator. Example tests covering encode/dispatch are executed and passing (`DM-007`); delivery-failure *visibility* is unaddressed by design, a separate concern from dispatch correctness. |
| Stale per-control state surviving a Controller Profile switch | `set_profile()` incompletely clearing dedup/Group/axis-target state | A control could send an action derived from the *previous* profile's assignment immediately after switching | Every control, for one MIDI event after a switch | Property-tested full post-switch trace (`DM-002`). |
| Malformed Preset Store JSON with an out-of-range Bank/Group index | Hand-edited or corrupted `~/Documents/DragonMIDI/configurations/<profile>.json` | Without the guard, a `0` or negative Bank index would resolve via Python's negative indexing to the *last* Bank instead of erroring — silently misdirecting axis assignment | One (Bank, Group) entry, but silently wrong rather than absent | Explicit `_parse_index` bounds-check, already in place. |
| `build_opinionated_map` producing an incorrect entry for a third-party profile | A bug in `_fader_entries()`/`_knob_entries()`/`_mute_entries()`/`_transport_entries()`/the Scene-button insertion (shared code, now golden-tested for the two bundled profiles — `DM-004`), or a config file whose `controls:` values don't mean what the author intended | Every control the shared helpers derive is silently wrong for every third-party profile using them | All controls across all third-party profiles | Unaddressed — `DM-004`'s evidence covers only the two bundled profiles; deferred (`property-register.md` `DM-004`). |

## Important state machines

| State machine | States | Dangerous transitions | Existing model/spec (if any) |
|---|---|---|---|
| `MappingEngine` active Group (1–5) + per-(Bank, Group) axis assignments | 5 Groups × 8 Banks, each Bank/Group pair either unassigned or bound to an axis name + range | Group switch discarding/retaining dedup state incorrectly (`MAP-GROUP-011`); Controller Profile switch not resetting Group index to 1 (`MAP-GROUP-007`) | `docs/specs/static-mapping.md` Group Switching section (`MAP-GROUP-001..012`). |
| `WebSocketOutputAdapter` connection lifecycle | Unbound / bound-no-connection / bound-with-connection; single connection slot, superseded on reconnect | A second Dragonframe connection attempt while one is active; shutdown racing an in-flight send | `docs/specs/websocket-output.md` (`WS-LIFECYCLE-*`, `WS-CONN-*`). |
| Controller Profile discovery/merge (bundled vs. user-local) | Per-name: bundled-only, user-local-only, or both (user-local wins) | A user-local file silently failing validation, falling back to the bundled profile without the user realizing their override didn't take | `PROFILE-LOAD-001..011`. |

## External assumptions

| Assumption | Depended on by | Currently enforced / merely assumed |
|---|---|---|
| Dragonframe is a trusted local peer (not a hostile OSC sender) | The entire OSC decode path's threat model — `DM-001`'s guards are robustness/contract enforcement, not a security boundary against an adversarial Dragonframe | Documented assumption (`osc_io.py` docstring); not enforced by any authentication. |
| Dragonframe's internal axis numbering ("AXn") matches the order DragonMIDI discovers axes via OSC | Any feature that maps a discovered axis index back to a specific physical/logical axis identity | Explicitly stated as "the accepted assumption" in code; not automatically verified — DragonMIDI has no way to query Dragonframe's own AXn assignment. |
| The community-documented nanoKONTROL2 default CC-mode map matches real hardware factory defaults | The bundled nanoKONTROL2 Controller Profile's correctness | Manually confirmed in practice against real hardware once (2026-07-21, per HLD), described as behavioral confirmation, not a byte-level MIDI trace. |
| A synthesized keystroke reaches Dragonframe because Dragonframe holds OS focus | Keystroke-mapped controls (jog wheel's Arc Motion Control stepping) | Not enforced at all — explicit HLD Non-Goal (no frontmost-window check); accepted risk. |
| Only one Dragonframe instance connects to the WebSocket server at a time | WebSocket command delivery semantics (single `_connection` slot) | Enforced structurally (new connections supersede the old one) but never verified as Dragonframe's actual behavior — assumed from the HLD's description of Dragonframe's own connection behavior. |

## Production / model boundaries

| Model | Covers | Production correspondence status |
|---|---|---|
| None | — | No formal or reference model exists for any part of this system; all evidence is test-based (example, property, fuzz) or structural (guards + boundary tests). No claim proposes formal proof — see `evidence-matrix.md`'s per-property evidence-design rationale. |

## Existing tests and verification mechanisms

| Mechanism | Covers | Type |
|---|---|---|
| `tests/test_osc_io.py` | `decode_osc_packet` bundle/message parsing, including `MAX_BUNDLE_DEPTH`/`element_size` guards | Example tests, property tests, a hypothesis fuzz test (`@settings(deadline=500)`) |
| `tests/test_mapping.py` | Dispatch, Bank derivation/clamp formula, dedup, Group switching | Example tests; property tests including a mutation-verified interior-point clamp test |
| `tests/test_mapping_profiles.py` | Profile construction, `set_profile()` full post-switch-trace isolation, opinionated-map shared-key structure | Example tests; one property test |
| `tests/test_mapping_config_schema.py` | `build_opinionated_map` static table content (hand-derived golden values, `DM-004`); the original circular output-equality assertions against `OPINIONATED_MAP_STUDIO`/`NANOKONTROL2` (regression-only, see Known fragile areas); Controller Profile validation error paths | Example tests; golden-value tests, mutation-verified |
| `tests/test_controller_profile_loader.py` | File discovery, merge/override semantics, per-file validation, collision warnings | Example tests |
| `tests/test_preset_store.py` | Bank/Group index bounds-checking, entry validation, write/read roundtrip | Example tests |
| `tests/test_websocket_output.py` | Encoding, bind, connection handling, send dispatch | Example tests, 22/22 passing under the project's declared environment (`.venv`, Python 3.11.15) |
| `tests/test_keystroke_output.py` | Press/release sequencing, stuck-modifier release-on-failure ordering | Example tests |
| `tests/test_midi_input.py`, `test_signal_monitor.py`, `test_status_presenter.py`, `test_queue_drain.py`, `test_shutdown.py`, `test_config.py`, `test_controller_profile.py`, `test_mapping_view_model.py` | MIDI input adapter, liveness/recency logic, status presentation, threading/queue draining, shutdown sequencing, config, profile dataclass, mapping view-model | Example tests |

## Known fragile areas

| Area | Current state | Current risk |
|---|---|---|
| `mapping.py::build_opinionated_map` / `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` | `test_mapping_config_schema.py:76,81` asserts the function's output equals two constants that are themselves defined as `STUDIO_PROFILE.opinionated_map`/`NANOKONTROL2_PROFILE.opinionated_map`, both built by calling the identical function with the identical arguments | That specific test still cannot distinguish a correct opinionated map from a consistently-wrong one, but this is no longer the only evidence — independent hand-derived golden-value tests now cover the two bundled profiles (`DM-004`); third-party profiles remain uncovered. |
| `osc_io.py::decode_osc_packet`'s in-code comments | The guard-related comments describe the guards as preventing a hang; direct testing shows the pre-guard code never actually hung on the tested malformed inputs — the accurate justification is bounded recursion cost | `DM-001`'s claim wording does not rely on the hang-prevention framing; the code comments themselves remain inaccurate and could mislead a future reader. |

## Higher-level assurance goals

| Goal | Decomposes into |
|---|---|
| The bridge should not corrupt or misdirect Dragonframe's motion-control state even under malformed OSC input, a bad Preset Store file, or an incorrect third-party Controller Profile | `DM-001`, `DM-003`, `DM-004`, `DM-006` |
| A control mapped to a safety-relevant WebSocket command (`E-Stop`) should reliably reach Dragonframe, or the operator should be able to tell when it hasn't | `DM-007` (dispatch correctness half — established, see `correctness-assurance.md §3.7`); delivery-failure visibility is an accepted risk, not decomposed into a property (`correctness-assurance.md §6.1`) |
| Every bundled or third-party Controller Profile's synthesized opinionated map should actually match its intended per-control behavior, not merely stay self-consistent over time | `DM-004` — established for the two bundled profiles; third-party-profile generalization is a deferred, unaddressed gap (`property-register.md` `DM-004`) |

## Open questions

- None currently open requiring reconciliation.
