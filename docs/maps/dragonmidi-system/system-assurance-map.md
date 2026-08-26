# System Assurance Map

Phase 1 artifact. Identifies where assurance matters without remapping the codebase — reference LID artifacts wherever possible instead of re-describing architecture. See `docs/workflow.md § Phase 1`.

## System / segment(s) covered

- **System:** DragonMIDI — MIDI-to-Dragonframe bridge (MIDI in → Mapping Engine → OSC/Keystroke/WebSocket out), plus Controller Profile loading and the (Bank, Group) axis-assignment Preset Store.
- **Segment(s) in scope:** whole system, single pass. Small enough (≈3,700 LOC across 19 modules) that splitting into per-segment MAPS passes would be more ceremony than the task warrants — matches the workflow's small-task allowance.
- **LID artifacts consulted:** `docs/high-level-design.md` (current, describes Phases 1–6, all apparently delivered per code state), `docs/llds/{app-ui,keystroke-output,midi-input,osc-io,static-mapping,websocket-output}.md`, `docs/specs/*.md` (EARS IDs cited directly in code via `@spec`). Freshness: HLD and code agree on structure (Controller Profile abstraction, Group switching, three output paths) — no drift observed during this pass.
- **LID artifacts NOT consulted / not available:** no `docs/arrows/` index or ambiguity register exists in this repo; `CLAUDE.md` states "LID Mode: Full" and cites HLD/LLD/EARS directly instead. Treated as sufficient — the `@spec` annotations in code make requirement traceability directly checkable without a separate arrows index.

## Trust boundaries

| Boundary | What crosses it | Trust level of the far side | Notes |
|---|---|---|---|
| Dragonframe → OSC Listener (UDP, `osc_io.py`) | Raw OSC packets/bundles | Explicitly trusted ("Dragonframe is a trusted local peer, not untrusted input" — `decode_osc_packet` docstring) | But the port is open to *any* local process, not just Dragonframe — the trust label is aspirational, not enforced by the socket. `decode_osc_packet` has no recursion-depth or size-consistency bound (see High-consequence failure paths). |
| KORG hardware → MIDI Input Adapter (`midi_input.py`) | Raw MIDI CC/note events | Trusted (physical device), but not adversarial-safe by construction — CC numbers/channels are taken at face value | A misbehaving/spoofed MIDI source on the same port could drive any mapped control. Low concern given the single-user desktop context. |
| Controller Profile config files (YAML, `controller_profile_loader.py`) | Full `ControllerProfile` definition (CC assignments, channel, capability flags) | **Genuinely external/untrusted** — explicitly designed for third-party, non-maintainer contributors (HLD "secondary audience") | This is the one boundary where content authored by someone outside the project becomes live behavior with no code review gate. Validated structurally (`validate_controls_config`, `_validate_top_level_fields`) but **not** validated for duplicate/colliding CC assignments across faders/knobs/mutes/solos/transport within one profile — see High-consequence failure paths. |
| Preset Store JSON (`preset_store.py`) | Persisted (Bank, Group) → axis-name/min/max table | Semi-trusted — written by DragonMIDI itself, but read back from a user-editable file on every launch | Defensively validated (bounds-checked bank/group indices, type-checked entry shape); invalid entries skipped with a warning, not fatal. Comment explicitly calls out closing a negative-index bug class. |
| Dragonframe → WebSocket server (`websocket_output.py`) | Inbound WS connection + arbitrary messages (discarded) | Path-gated (`CONNECTION_PATH` check rejects non-matching paths with 404) but otherwise **any local process** can connect and supersede the "real" Dragonframe connection | `_handler` closes the previous connection unconditionally when a new one arrives — a second local process connecting to the well-known path would silently steal the channel from the real Dragonframe (no auth, no origin check; accepted per HLD Non-Goals: "coexisting with another process... not detected, not negotiated around"). |
| DragonMIDI → OS keyboard focus (`keystroke_output.py`) | Synthesized keystroke | Untrusted destination — delivered to whatever has OS focus, not verified to be Dragonframe | Explicit HLD Non-Goal ("Detecting or requiring that Dragonframe is the OS-focused application"); accepted risk, not a gap to flag further here. |

## Semantic chokepoints

| Chokepoint | What routes through it | Why it's a chokepoint | Existing safeguards |
|---|---|---|---|
| `MappingEngine.process()` / `.process_keystroke()` / `.process_websocket()` (`mapping.py`) | Every MIDI event, for all three output paths, for every profile | Single translation point from physical control input to all observable behavior; a bug here changes what the operator's hardware actually does to a physical stage rig | 115 example-based unit tests in `test_mapping.py`; no property-based tests found |
| `build_profile()` / `build_opinionated_map()` (`mapping.py`) | A profile's declared `ControlsConfig` → its entire opinionated map, WebSocket keys, Group keys, bank membership | Feeds identically into both bundled (hardcoded) and loaded (YAML) profiles — one function, all profiles' behavior | `validate_controls_config` (shape only, see gap below); `MAP-CONFIG-003`'s migration invariant (byte-identical to pre-Phase-5 hardcoded constants) asserted in comments, not obviously covered by an explicit equivalence test — worth confirming in Phase 2 |
| `decode_osc_packet` / `AxisDiscovery.handle_datagram` (`osc_io.py`) | The only parser for Dragonframe's wire format; feeds axis-name discovery, the mapping view's axis picker, and Cycle's axis count | Sole boundary-decoder for an external protocol | `decode_osc_message`'s malformed input is caught broadly in `handle_datagram` (`except Exception: return`), but `decode_osc_packet`'s bundle-recursion path is **not** wrapped by that same guard when called directly (only reachable via `handle_datagram` today, so currently mitigated in practice) |
| `_parse_profile_file` / `validate_controls_config` (`controller_profile_loader.py`, `mapping.py`) | Untrusted YAML → live `ControllerProfile` | The one point where a non-maintainer's file becomes trusted, executable configuration | Structural validation only; no cross-field collision check (see below) |
| `MappingEngine._process_bank_derived`'s knob-nudge clamping (`mapping.py:636-676`) | Every Knob-driven incremental axis nudge, clamped against `axis_positions` (Dragonframe's live report) or an internal fallback estimate | Directly determines the physical position commanded on a motion-control axis; already has a fix history (see below) | `test_mapping.py` covers it, but this is the one path in the whole system with a **prior confirmed bug** (`81d1397`, `f63a84a`) |

## Externally visible outputs

| Output | Consumed by | Consequence if wrong | Currently checked by |
|---|---|---|---|
| OSC `gotoPosition`/`stepPosition` to a named axis | Dragonframe → physical motion-control axis | Wrong/unclamped position sent to real hardware; a stage-safety concern, not just a UI bug | Unit tests on `MappingEngine`; no differential check against Dragonframe's actual OSC address grammar (Dragonframe itself is not available as a test oracle) |
| WebSocket `E-Stop` command | Dragonframe → **motion-control emergency stop** | If dropped (bind failure, no active connection, send exception), the operator's E-Stop physically does nothing, with no distinct UI indicator (`WS-RUNTIME-*`, "fails silently" by design) | Unit tests confirm the command is sent when a connection exists; no test/monitor confirms the *absence* of a silent-failure state is visible to the operator |
| Synthesized keystroke (Arc Motion Control jog) | Whatever has OS focus | Wrong-app keystroke injection if Dragonframe isn't focused (accepted Non-Goal) | Unit tests on `KeystrokeOutputAdapter`'s modifier press/release symmetry only |
| Status UI "MIDI signal" / "Dragonframe signal" indicators | Human operator, as the sole liveness signal | A false "live" reading is worse than a false "quiet" one — operator trusts a dead bridge | `test_signal_monitor.py`, `test_status_presenter.py` |

## High-consequence failure paths

| Failure path | Trigger | Consequence | Blast radius | Currently mitigated by |
|---|---|---|---|---|
| Silent E-Stop loss | WebSocket bind failure, connection not yet established, or `send()` exception | Emergency stop for motion-control hardware silently no-ops | High (safety) | Logged only; explicit accepted design gap per HLD ("fails silently, matching the Keystroke precedent") |
| Colliding CC numbers within one Controller Profile | A community-authored YAML file assigns the same CC to two different controls (e.g. a fader CC reused as a transport CC) | One physical control silently drives two different outputs, or a later `dict` build silently overwrites an earlier mapping entry with no warning | Medium — scoped to whoever loads that profile | **Not checked** — `validate_controls_config` only checks per-field length (`==8`) and jog-wheel presence, not cross-field uniqueness |
| `decode_osc_packet` malformed/adversarial bundle | A crafted or corrupted UDP packet to DragonMIDI's listen port with `element_size <= 0` or deeply nested `#bundle` framing | A non-positive `element_size` always yields an empty Python slice, which always fails to decode immediately — no loop can get stuck at a non-advancing offset. Uncapped nesting raises Python's own `RecursionError` (~1000 frames), safely caught by `handle_datagram`'s broad exception handler. The residual cost is walking that ~1000-frame stack on a background thread whose stack size isn't guaranteed generous on every platform, and reliance on Python's incidental slicing behavior rather than a stated contract. `decode_osc_packet` now enforces `element_size` validity and a nesting-depth cap explicitly (`docs/llds/osc-io.md`, `OSC-DISCOVER-010`/`011`), replacing that incidental safety with a documented one. | Low | `handle_datagram`'s broad `except Exception` catches both the empty-slice decode failure and `RecursionError`; the explicit guards now also convert both into a single, documented `BundleBoundsError` |
| Knob-nudge clamp arithmetic drift | Floating-point accumulation in `_axis_position` fallback estimate diverging from Dragonframe's true reported position, when no live `axis_positions` reading is available | Axis creeps toward or away from its configured range incorrectly over many nudges | Medium — has already regressed once (`81d1397`/`f63a84a`) | Unit tests only; no property-based test asserting "clamped position always stays within [min,max] regardless of nudge sequence" |
| `MAP-CONFIG-003` migration-invariant regression | A future change to `build_opinionated_map`/`_fader_entries`/etc. that silently diverges the *synthesized* map from what the pre-Phase-5 hardcoded constants produced | Every control on both bundled profiles could shift behavior at once | High (affects 100% of users on both bundled profiles) | Asserted only in a code comment; no visible explicit equivalence test in `test_mapping_profiles.py`/`test_mapping_config_schema.py` (needs Phase 2 confirmation — see Open questions) |

## Important state machines

| State machine | States | Dangerous transitions | Existing model/spec (if any) |
|---|---|---|---|
| `MappingEngine` fader mode | axis mode ⇄ OSC-encoder mode (engine-wide, all 8 faders together) | Switching mode discards `_previous_value`/`_axis_position` dedup state for every Bank (`MAP-AXIS-010/012`) — a bug here could cause a stale nudge baseline to leak across the mode switch | `MAP-AXIS-*` specs; unit-tested |
| Active Group (1–5) | 5 fixed states, wraps (not clamps) at the boundary | Group step discards fader dedup state only when in axis mode (`MAP-GROUP-004/011`); Solo's `select-AXn` offset arithmetic (`N + 8*(g-1)`) must stay in lockstep with the Group index | `MAP-GROUP-*` specs; unit-tested including the wrap case |
| Controller Profile switch | one active `ControllerProfile` at a time | `set_profile` clears *all* tracked per-control state (broader than `reset()`) — an incomplete clear would leak a stale key/state from the old profile's CC layout into the new one, esp. if two profiles reuse the same CC number for different roles | `MAP-PROFILE-004`; unit-tested |
| WebSocket server connection | unbound / bound-no-connection / bound-with-connection | A second inbound connection silently supersedes the first with no operator-visible signal distinguishing "still connected to the real Dragonframe" from "connected to something else" | `WS-CONN-*`; unit-tested for the mechanical supersede behavior, not for the trust implication |

## External assumptions

| Assumption | Depended on by | Currently enforced / merely assumed |
|---|---|---|
| Dragonframe's WebSocket-side `AXn` numbering matches OSC discovery order | Cycle (`process_websocket`), Solo's Group-offset arithmetic | **Merely assumed** — explicitly flagged in the `process_websocket` docstring as "the accepted assumption," not verified against Dragonframe |
| nanoKONTROL2's factory-default CC map (community-documented, not vendor-published) | `NANOKONTROL2_CONTROLS`, the bundled nanoKONTROL2 profile | Confirmed once against real hardware (2026-07-21, per HLD Key Design Decisions) — a practical smoke check, not a byte-level trace; no regression protection if a future firmware/config changes the physical device's factory CCs |
| Dragonframe treats any UDP traffic to its OSC Output port as evidence of liveness (no heartbeat contract) | `OscListener`'s liveness signal | Assumed, per HLD's "Bidirectional OSC instead of a send-side heartbeat" design decision; not something DragonMIDI can verify from its side |
| `pynput`'s cross-platform key model correctly maps `alt`/`shift`/`right`/`left` to the OS-level keys Dragonframe's Hot Keys preferences expect | Keystroke out | Assumed library behavior; not independently verified per-OS in CI (would need platform-specific runners) |
| Socket close from another thread reliably interrupts a blocking `recvfrom()` | `OscListener.stop()`/`rebind()` | **Explicitly not assumed** — code comment documents this failed on Linux CI; worked around with a bounded 0.5s `settimeout()` poll instead of relying on close-interrupts-recv. Good example of an assumption that was tested and found false. |

## Production / model boundaries

| Model | Covers | Production correspondence status |
|---|---|---|
| None present | — | No formal or reference model exists for any part of this system (OSC protocol, mapping engine, controller profile schema). All correctness evidence today is example-based unit testing against the real implementation directly — there is no separate "spec model" to correspond against. |

## Existing tests and verification mechanisms

| Mechanism | Covers | Type |
|---|---|---|
| `test_mapping.py` (115 tests) | `MappingEngine` — all three output paths, Bank/Group/Axis logic, debounce, profile switching | Example-based unit tests |
| `test_osc_io.py` (31 tests) | OSC encode/decode, `AxisDiscovery`, `OscClient`/`OscListener` (via injected `UdpSocket` fake) | Example-based unit tests |
| `test_controller_profile_loader.py` (13 tests), `test_mapping_config_schema.py`, `test_mapping_profiles.py` | YAML profile loading/validation, bundled-vs-user precedence, structural error handling | Example-based unit tests |
| `test_websocket_output.py` (22 tests) | Bind/connect/supersede/send/stop lifecycle (via `websockets` test infrastructure, not a real Dragonframe) | Example-based unit tests |
| `test_preset_store.py` (16 tests) | Load/save round-trip, bounds validation, malformed-file tolerance | Example-based unit tests |
| `test_keystroke_output.py` (10 tests) | Modifier press/release symmetry, exception isolation | Example-based unit tests (fake `KeystrokeBackend`) |
| `test_signal_monitor.py`, `test_status_presenter.py`, `test_shutdown.py`, `test_queue_drain.py`, `test_config.py` | Liveness recency windows, UI state presentation, shutdown ordering, thread-safe queue draining | Example-based unit tests |
| CI (`.github/`) | Presumably runs the above + lint (`ruff`) on every push (see recent commit `361a8bf`) | Not inspected in this pass — treat as "CI green," not a specific correctness claim |
| **Not present anywhere in the repo:** | — | Property-based testing, differential/reference testing (no second OSC/Dragonframe implementation exists to differential-test against), fuzzing of `decode_osc_packet`/YAML profile parsing, static analysis beyond `ruff` lint, formal proof of any invariant |

## Known fragile or historically buggy areas

| Area | History | Why it's still a risk |
|---|---|---|
| Knob-driven axis nudge scaling (`_KNOB_STEP_SCALE`, `_process_bank_derived`) | Two prior fix commits: `81d1397` "fixed fine tuning to be 0.1 instead of 1 on each midi step," `f63a84a` "fixed the pot behvior for micro adjustments" | The exact arithmetic (raw-delta → scaled delta → clamp against live-or-estimated position) is the most fiddly numeric logic in the mapping engine, already wrong once in production before being caught |
| UI layout | Three recent "fixed ... layout/sizing/spacing" commits (`eef3a7e`, `3f744d2`, `25c5e17`) | Out of MAPS's scope (visual layout, not a correctness property) — noted for completeness, not carried into Phase 2 |
| CI/lint configuration | Two recent CI-fix commits (`361a8bf`, `0a1865c`) | Also out of scope — tooling, not system behavior |

## Open questions surfaced during mapping — reconciled 2026-08-25

- **Silent E-Stop loss:** user confirmed this is a **top-priority** assurance property, not an accepted-as-is risk — carried into Phase 2 as a high-priority candidate despite the HLD's engineering-scope acceptance.
- **CC-collision validation gap:** user confirmed this is worth a property — carried into Phase 2.
- **AXn ordering assumption:** user confirmed it remains **unverified** against real Dragonframe behavior — carried into Phase 2 as a live external assumption, not downgraded.
- `MAP-CONFIG-003`'s migration-invariant test coverage was not raised as a question to the user (judged non-blocking, unlike the three above) — carried forward as a Phase 2 candidate to confirm by direct inspection of `test_mapping_profiles.py`/`test_mapping_config_schema.py` rather than by asking.
