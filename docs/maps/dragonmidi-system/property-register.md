# Property Register

Phase 2/3 artifact. The authoritative list of admitted assurance concerns and properties. See `docs/property-discovery.md` and `docs/prioritization.md`.

This register supersedes the prior DragonMIDI MAPS package's `MAPS-001`..`MAPS-007` IDs entirely; none are reused (`docs/maps/dragonmidi-system/` git history retains the superseded package).

## Concern Classification

Every concern `system-assurance-map.md` raised, with its role and resulting disposition.

| Phase 1 item | Concern role | Disposition |
|---|---|---|
| `decode_osc_packet` malformed-bundle robustness (chokepoint + failure path) | Current assurance property | Registered — `DM-001` |
| `MappingEngine.process()`/`.process_websocket()`/`.process_keystroke()` general dispatch correctness | Current assurance property | Merged — the materially risky sub-concern (Group-switch dispatch precedence) is `DM-009`; general per-control-type routing has no identified gap beyond the existing example-test suite and is not separately tracked |
| `MappingEngine.set_profile()` full state isolation (chokepoint + failure path) | Current assurance property | Registered — `DM-002` |
| Bank-derived knob clamp-to-range formula, incl. out-of-range recovery (chokepoint + failure path) | Current assurance property | Registered — `DM-003` |
| `build_opinionated_map` / shared-helper synthesis correctness (chokepoint + failure path + known-fragile area) | Current assurance property | Registered — `DM-004` (freshly worded against the current Opinionated Table/Bank-Derivation specs, not against historical constants) |
| `MAP-CONFIG-003` as literally worded ("identical in content to... pre-Phase-5 `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` constants") | Migration/transition acceptance criterion | Retired/completed — Phase 5 shipped; no pre-Phase-5 hardcoded implementation remains in production (the named constants are now themselves derived from the function this criterion was bridging away from). See `Rejected / withdrawn` below. Its live successor concern is `DM-004`. |
| `controller_profile_loader.py` config parsing/validation robustness | Current assurance property | Registered — `DM-005` |
| `preset_store.py` Bank/Group index bounds validation (chokepoint + failure path) | Current assurance property | Registered — `DM-006` |
| `E-Stop`/WebSocket command correct encode+dispatch on press-edge | Current assurance property | Registered — `DM-007` |
| `E-Stop`/WebSocket command delivery has no operator-visible failure signal | Accepted or deferred risk | Tracked outside the register — already an explicit HLD decision ("fails silently, not as a new status indicator... deferred, not ruled out"); recorded directly in `correctness-assurance.md § 6`, not a property |
| Keystroke output stuck-modifier release ordering on failure | Current assurance property | Registered — `DM-008` |
| Group-switch dispatch precedence and dedup-discard rules (`MAP-GROUP-005/007/011`) | Current assurance property | Registered — `DM-009` (lower priority; existing coverage, evidence design likely concludes little/no additional work — see Prioritization) |
| Dragonframe trusted-local-peer assumption | External assumption | Registered — `DM-EA-001` |
| AXn axis-identity/discovery-order assumption | External assumption | Registered — `DM-EA-002` |
| nanoKONTROL2 default CC map matches real hardware | External assumption | Registered — `DM-EA-003` |
| No frontmost-window detection before keystroke delivery | Accepted or deferred risk | Tracked outside the register — explicit HLD Non-Goal; recorded directly in `correctness-assurance.md § 6` |
| Single-Dragonframe-connection-at-a-time WebSocket assumption | External assumption (minor) | Merged — folded into `DM-007`'s Assumptions field rather than separately registered; no independent evidence path exists to verify Dragonframe's own connection behavior beyond what DragonMIDI's own code structurally enforces |
| `build_opinionated_map` circularity (existing test compares the function's output to constants derived from itself) | N/A — a finding about evidence quality, not a concern of its own | Folded into `DM-004`'s evidence design (Phase 4A); does not affect `DM-004`'s Authority (`docs/property-discovery.md § Authority is never downgraded by a finding about evidence quality`) |
| `decode_osc_packet`'s original "prevents a hang" justification, found overclaimed by direct testing | N/A — a finding about claim wording, not a concern of its own | Folded into `DM-001`'s claim wording (registered narrower, as a bounded-input-handling/well-typed-rejection claim, not a hang-prevention claim) |
| `test_listener_resends_discovery_query_on_rebind` flakiness | N/A — test-infrastructure defect, not an assurance concern | Out of scope for this MAPS pass — confirmed pre-existing and unrelated via `git stash`; a LID/test-maintenance matter, not tracked as a residual gap of any property here |
| Higher-level goal: bridge should not corrupt/misdirect Dragonframe motion-control state under malformed/adversarial input | Higher-level assurance goal | Tracked in `system-assurance-map.md`; decomposes into `DM-001`, `DM-003`, `DM-004`, `DM-006` |
| Higher-level goal: safety-relevant WebSocket commands should reliably reach Dragonframe, or failure should be visible | Higher-level assurance goal | Tracked in `system-assurance-map.md`; decomposes into `DM-007` (correctness half) plus the accepted-risk note above (visibility half) |
| Higher-level goal: every profile's synthesized opinionated map should match intended behavior | Higher-level assurance goal | Tracked in `system-assurance-map.md`; decomposes into `DM-004` |

## Register

### DM-001: OSC bundle-decode robustness

- **Behavioral segment:** OSC I/O (`docs/llds/osc-io.md`)
- **Claim:** `decode_osc_packet` never raises an unhandled exception for any byte input, and specifically rejects non-positive or out-of-bounds declared `element_size` and nesting beyond `MAX_BUNDLE_DEPTH` (8) by raising the well-typed `BundleBoundsError`, which `AxisDiscovery.handle_datagram` catches and logs rather than propagating.
- **Quantifiers in the claim:** for every byte-string input (arbitrary malformed content); for every nesting depth; for every declared `element_size` value.
- **Claim dimensions:**
  - negative `element_size`
  - zero `element_size`
  - `element_size` exceeding remaining buffer
  - nesting depth at/beyond `MAX_BUNDLE_DEPTH`
  - arbitrary malformed byte input generally (termination / no crash)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a — stateless per-call decode, no persistent invariant to bound
- **Property class:** Boundedness; Error/failure semantics
- **Discovery source:** implementation observation + EARS requirement
- **Authority:** SPECIFIED — Authority basis: `OSC-DISCOVER-010`, `OSC-DISCOVER-011`, `OSC-DISCOVER-012` (`docs/specs/osc-io.md`), confirmed user intent
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/osc_io.py` (`BundleBoundsError`, `MAX_BUNDLE_DEPTH`); `docs/specs/osc-io.md`
- **Confidence in intent:** high
- **Consequence if false:** unbounded recursion cost or an unhandled exception in the OSC Listener thread, potentially affecting every subsequent direct-axis mapping that depends on discovered axis names
- **Downstream dependencies:** `AxisDiscovery`, every direct-axis Mapping View feature
- **Preconditions:** none
- **Assumptions:** Dragonframe is a trusted local peer (`DM-EA-001`) — these guards are a robustness/contract boundary, not a defense against a deliberately adversarial sender
- **Prioritization rationale:** chokepoint for all OSC traffic; high likelihood ordinary tests miss malformed-framing edge cases; consequence bounded by `DM-EA-001`, so not maximal
- **Priority:** medium
- **Disposition:** Approved
- **Evidence coverage:** all claim dimensions covered — see `EVID-001`
- **Evidence state (set):** Example-tested; Property-tested (fuzz); Structural enforcement + verification; Supported by multiple complementary layers
- **Residual gaps:** none currently identified
- **Evidence-matrix row:** `EVID-001`

### DM-002: Controller Profile switch fully isolates per-control engine state

- **Behavioral segment:** Static Mapping / Mapping Engine (`docs/llds/static-mapping.md`)
- **Claim:** After `MappingEngine.set_profile()` returns, no dedup state, Group index, axis-target assignment, or bank-derived tracked position from the previous profile influences any subsequent MIDI event's dispatch.
- **Quantifiers in the claim:** for every subsequent operation after a profile switch (not merely the first).
- **Claim dimensions:** n/a — single-instance claim (the full post-switch trace is one claim, not several sub-parts)
- **Canonical definition:** n/a
- **Valid initial-state domain:** the engine may be in any reachable state at the moment `set_profile()` is called; the claim is about the state immediately after the call
- **Property class:** Isolation; State-machine safety
- **Discovery source:** EARS requirement
- **Authority:** SPECIFIED — Authority basis: `MAP-PROFILE-004` (`docs/specs/static-mapping.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/mapping.py::MappingEngine.set_profile`; `docs/specs/static-mapping.md`
- **Confidence in intent:** high
- **Consequence if false:** a control fires an action derived from the wrong (previous) profile immediately after a switch
- **Downstream dependencies:** every control's dispatch correctness
- **Preconditions:** none
- **Assumptions:** none beyond ordinary single-threaded engine access
- **Prioritization rationale:** silent-failure risk on every profile switch (a common operation for anyone using more than one controller)
- **Priority:** medium
- **Disposition:** Approved
- **Evidence coverage:** n/a — single-instance claim, fully covered — see `EVID-002`
- **Evidence state (set):** Property-tested
- **Residual gaps:** none currently identified
- **Evidence-matrix row:** `EVID-002`

### DM-003: Bank-derived knob nudge never sends an out-of-range axis position

- **Behavioral segment:** Static Mapping — Bank Derivation (`docs/llds/static-mapping.md`)
- **Claim:** For any Bank with a real axis name assigned in the active Group, every derived `stepPosition` send keeps the tracked axis position within the fader's configured `[min, max]` range — including when the tracked position (live-reported or internally estimated) starts outside that range at the time of a nudge.
- **Quantifiers in the claim:** for every knob-nudge sequence, any starting tracked position (in-range or out-of-range), any sequence length.
- **Claim dimensions:**
  - in-range starting position, ordinary clamp behavior
  - out-of-range starting position, first corrective nudge
  - out-of-range starting position, full multi-step nudge sequence
  - interior (non-boundary) landing position, order-independence of the clamp formula
- **Canonical definition:** "effective bounds" = the lower and higher of the two configured `min`/`max` values, regardless of which is named which (`MAP-BANK-008`)
- **Valid initial-state domain:** tracked position may start anywhere in ℝ, not only within `[min, max]` — this is explicitly part of the claim (`MAP-BANK-010`), not a separate recovery claim
- **Property class:** Boundedness; Numeric correctness
- **Discovery source:** EARS requirement
- **Authority:** SPECIFIED — Authority basis: `MAP-BANK-008`, `MAP-BANK-009`, `MAP-BANK-010` (`docs/specs/static-mapping.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/mapping.py::_process_bank_derived`; `docs/specs/static-mapping.md`
- **Confidence in intent:** high
- **Consequence if false:** Dragonframe receives a position command outside the user-configured safe range — a physical/motion-control consequence, not merely a display bug
- **Downstream dependencies:** every Bank with a direct-axis assignment
- **Preconditions:** Bank's fader has a real axis name assigned in the active Group
- **Assumptions:** Dragonframe's reported live position, when available, is itself accurate (external assumption not separately tracked — Dragonframe's OSC output fidelity is outside this project's control and not currently a registered concern)
- **Prioritization rationale:** physical/motion-control safety consequence (an out-of-range axis command); common usage path (every knob nudge on an axis-assigned Bank)
- **Priority:** high
- **Disposition:** Approved
- **Evidence coverage:** all claim dimensions covered — see `EVID-003`
- **Evidence state (set):** Example-tested; Property-tested; Structural enforcement + verification; Supported by multiple complementary layers
- **Residual gaps:** none currently identified
- **Evidence-matrix row:** `EVID-003`

### DM-004: Synthesized opinionated map matches the specified per-control behavior

- **Behavioral segment:** Static Mapping — Controller Profile Config Schema / Opinionated Table (`docs/llds/static-mapping.md`)
- **Claim:** For any Controller Profile (bundled or third-party), `build_opinionated_map` (via `_fader_entries()`/`_knob_entries()`/`_mute_entries()`/`_shared_button_entries()`) synthesizes a MIDI-event-to-OSC/keystroke/WebSocket-target table that matches what the Opinionated Table and Bank Derivation specs (`MAP-TABLE-001/002/003/005`, `MAP-CONFIG-004/005/006/007/008`) require for that profile's declared `controls:` block.
- **Quantifiers in the claim:** for every entry the shared helpers can produce, for any valid `controls:` declaration (not merely the two bundled profiles' specific CC values).
- **Claim dimensions:**
  - fader entries (`_fader_entries()`)
  - knob entries (`_knob_entries()`)
  - mute entries (`_mute_entries()`)
  - shared button entries (`_shared_button_entries()`, incl. transport, Scene button override behavior)
  - absent-key handling (`MAP-CONFIG-004` — an omitted `transport` key produces no row, not a disabled one)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a — pure synthesis function, no persistent state
- **Property class:** Functional correctness; Refinement/equivalence (config declaration → derived table)
- **Discovery source:** EARS requirement + implementation observation
- **Authority:** SPECIFIED — Authority basis: `MAP-TABLE-001/002/003/005`, `MAP-CONFIG-004/005/006/007/008` (`docs/specs/static-mapping.md`). This claim is worded against the *current* Opinionated Table/Bank-Derivation spec text, not against the retired pre-Phase-5 historical constants (see `Rejected / withdrawn` below) — the two are related but not the same claim.
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/mapping.py::build_opinionated_map` and shared helpers; `docs/specs/static-mapping.md`
- **Confidence in intent:** high
- **Consequence if false:** every control on every Controller Profile using the shared helpers (both bundled profiles, and any third-party config) is silently mis-mapped — the single highest blast-radius chokepoint in the mapping layer
- **Downstream dependencies:** every profile's runtime behavior; `controller_profile_loader.py`'s output correctness depends on this transitively
- **Preconditions:** a syntactically valid `controls:` declaration (malformed declarations are `DM-005`'s concern, not this one)
- **Assumptions:** none beyond the config schema itself being correctly documented
- **Prioritization rationale:** highest-blast-radius chokepoint in the mapping layer; existing test (`test_mapping_config_schema.py:76,81`) is circular (compares the function's output to constants derived from the same function) — this is a genuine, currently-uncovered correctness gap, not merely a stale record
- **Priority:** highest
- **Disposition:** Approved
- **Evidence coverage:** planned — see `EVID-004` for the per-dimension plan (fader/knob/mute/shared-button/absent-key)
- **Evidence state (set):** No evidence (correctness); existing test provides regression/change-detection value only (`docs/evidence-selection.md § Self-derived snapshots are not correctness evidence`) — not correctness evidence, and must not be described as such in `correctness-assurance.md`. Evidence planned.
- **Residual gaps:** evidence missing — no evidence currently establishes this claim is *correct*, only that it's self-consistent over time. Type: Evidence missing. Disposition: Produce evidence — routed to `evidence-handoff.md`.
- **Evidence-matrix row:** `EVID-004`

### DM-005: Controller Profile config parsing degrades gracefully on malformed input

- **Behavioral segment:** MIDI Input — Controller Profile Loading (`docs/llds/midi-input.md`)
- **Claim:** A malformed or invalid Controller Profile config file (missing required field, wrong type, malformed YAML, invalid `controls:` shape) is skipped with a logged warning and does not prevent the remaining valid profiles (bundled or user-local) from loading, and does not crash the app.
- **Quantifiers in the claim:** for every malformed-file shape in `_REQUIRED_FIELDS`/type-validation's domain.
- **Claim dimensions:**
  - missing required top-level field
  - wrong type for a required field (`name`, flags, `default_channel`, `setup_hint`)
  - malformed `controls:` block (not a mapping, missing sub-field)
  - malformed YAML syntax
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** Error/failure semantics; Deployment/configuration safety
- **Discovery source:** EARS requirement
- **Authority:** SPECIFIED — Authority basis: `PROFILE-LOAD-002`, `PROFILE-LOAD-008`, `PROFILE-LOAD-009`, `PROFILE-LOAD-010` (`docs/specs/midi-input.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/controller_profile_loader.py`
- **Confidence in intent:** high
- **Consequence if false:** one malformed third-party config file (a likely occurrence, given the HLD's non-programmer-contributor target audience) could take down profile discovery for every controller, including the bundled ones
- **Downstream dependencies:** Controller Profile dropdown population, every profile's availability
- **Preconditions:** none
- **Assumptions:** none
- **Prioritization rationale:** moderate blast radius (one malformed third-party file could theoretically affect discovery of others); defensive code and per-file isolation already in place with existing example coverage
- **Priority:** medium
- **Disposition:** Approved
- **Evidence coverage:** all named dimensions covered — see `EVID-005`
- **Evidence state (set):** Example-tested
- **Residual gaps:** none currently identified
- **Evidence-matrix row:** `EVID-005`

### DM-006: Preset Store rejects out-of-range Bank/Group indices rather than misdirecting

- **Behavioral segment:** Preset Store (`docs/llds/static-mapping.md § Preset Store`)
- **Claim:** `load_group_axis_targets` skips (with a logged warning) any Bank index outside `[1, 8]` or Group index outside `[1, 5]` found in a persisted file, rather than allowing it to reach code that resolves Bank/Group indices positionally (where an unvalidated `0` or negative index could resolve via Python negative indexing to the wrong Bank).
- **Quantifiers in the claim:** for every Bank index value, every Group index value, every malformed entry shape found in a persisted file.
- **Claim dimensions:**
  - Bank index below range (`<= 0`)
  - Bank index above range (`> 8`)
  - Group index below/above range
  - malformed entry shape (missing `axis_name`/`min`/`max`, wrong type)
  - unreadable/non-JSON file (treated as empty table, not an error)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** Boundedness; Error/failure semantics
- **Discovery source:** implementation observation
- **Authority:** SPECIFIED — Authority basis: `MAP-STORE-001/002/003` (`docs/specs/static-mapping.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/preset_store.py::load_group_axis_targets`, `_parse_index`, `_validate_entry`
- **Confidence in intent:** high
- **Consequence if false:** a corrupted or hand-edited Preset Store file could silently misdirect an axis assignment to the wrong Bank via Python's negative-indexing behavior — a specific, previously-identified risk the guard exists to close
- **Downstream dependencies:** every (Bank, Group) axis assignment loaded at startup/profile switch
- **Preconditions:** none
- **Assumptions:** none
- **Prioritization rationale:** guard already in place and tested; low exposure in practice (Preset Store files are normally only written by the app itself, not hand-edited)
- **Priority:** low-medium
- **Disposition:** Approved
- **Evidence coverage:** all named dimensions covered — see `EVID-006`
- **Evidence state (set):** Example-tested
- **Residual gaps:** none currently identified as blocking (see `EVID-006` for a light, non-blocking boundary-value confirmation note)
- **Evidence-matrix row:** `EVID-006`

### DM-007: WebSocket-targeted commands encode and dispatch correctly on press-edge

- **Behavioral segment:** WebSocket Output (`docs/llds/websocket-output.md`)
- **Claim:** For a control mapped to a WebSocket target (`E-Stop`, `select-AXn`, `jog-AXn`), a press-transition produces exactly one correctly-shaped `{"input": ...}` JSON send to the currently-connected peer, with no send when no connection is active.
- **Quantifiers in the claim:** for every press-transition, every WebSocket target name, any connection state (connected / not connected).
- **Claim dimensions:**
  - `E-Stop` (fixed input name, no params)
  - `select-AXn` (Group-aware offset, `MAP-WS-002`)
  - `jog-AXn` (per-axis incremental jog)
  - no-connection case (send is dropped, not queued or errored)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** Functional correctness; Determinism
- **Discovery source:** EARS requirement
- **Authority:** SPECIFIED — Authority basis: `WS-SEND-001` through `WS-SEND-008`, `MAP-WS-001` through `MAP-WS-009` (`docs/specs/websocket-output.md`, `docs/specs/static-mapping.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/websocket_output.py`, `dragonmidi/mapping.py`
- **Confidence in intent:** high
- **Consequence if false:** `E-Stop` specifically is a motion-control emergency-stop function — a wrong or duplicated send is a safety-relevant correctness defect, not merely a UX bug
- **Downstream dependencies:** none beyond Dragonframe's own handling of the command
- **Preconditions:** a WebSocket connection is currently active (delivery when no connection exists is explicitly out of scope for *this* claim — see the Accepted-risk note in `system-assurance-map.md` for the separate, deliberately-unaddressed visibility gap)
- **Assumptions:** at most one Dragonframe client connects at a time (structurally enforced by `WebSocketOutputAdapter`'s single `_connection` slot; never independently confirmed against Dragonframe's own connection behavior — a minor, unregistered external assumption, not expected to be revisited without evidence of Dragonframe opening multiple connections)
- **Prioritization rationale:** `E-Stop` is an explicit safety-relevant function (motion-control emergency stop); narrower exposure than the mapping-wide chokepoints, but consequence-if-false is not merely cosmetic
- **Priority:** high
- **Disposition:** Approved
- **Evidence coverage:** all claim dimensions covered — see `EVID-007`
- **Evidence state (set):** Example-tested
- **Residual gaps:** environment-platform validation gap (test suite currently fails to import in this dev environment — `websockets` not installed; not a code defect) — Type: Environment-platform validation gap. Disposition: Resolve through LID/design — routed to `evidence-handoff.md`.
- **Evidence-matrix row:** `EVID-007`

### DM-008: Keystroke synthesis never leaves a modifier key stuck after a failed press

- **Behavioral segment:** Keystroke Output (`docs/llds/keystroke-output.md`)
- **Claim:** If pressing a modifier or the main key raises during `KeystrokeOutputAdapter.send()`, every modifier already pressed for that call is still released (in reverse order), even though the failure is otherwise swallowed and logged rather than propagated.
- **Quantifiers in the claim:** for every combination of which press/release call raises (modifier press, main key press, main key release), for any number of modifiers.
- **Claim dimensions:** n/a — single-instance claim (the finally-block release guarantee is one claim)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** Error/failure semantics; Safety
- **Discovery source:** implementation observation
- **Authority:** SPECIFIED — Authority basis: `KEY-SEND-001` through `KEY-SEND-006` (`docs/specs/keystroke-output.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/keystroke_output.py::KeystrokeOutputAdapter.send`
- **Confidence in intent:** high
- **Consequence if false:** a stuck modifier key at the OS level corrupts every subsequent real keystroke system-wide until manually cleared — explicitly called out in the code's own reasoning as "a far worse failure than one missed send"
- **Downstream dependencies:** every keystroke-mapped control, and every other application receiving keyboard input afterward
- **Preconditions:** none
- **Assumptions:** the backend's `release()` call itself doesn't also fail in a way that leaves the OS-level key state stuck
- **Prioritization rationale:** high consequence-if-false (a stuck modifier corrupts all subsequent keyboard input system-wide) but only reachable via an already-rare backend-failure path
- **Priority:** medium
- **Disposition:** Approved
- **Evidence coverage:** n/a — single-instance claim, covered — see `EVID-008`
- **Evidence state (set):** Example-tested
- **Residual gaps:** evidence missing — a doubly-failing `release()` sequence's ordering isn't explicitly asserted. Type: Evidence missing. Disposition: Defer — judged low-value given Priority: medium; tracked in `evidence-handoff.md` (No action scheduled).
- **Evidence-matrix row:** `EVID-008`

### DM-009: Group-switch dispatch precedence and dedup-state discard

- **Behavioral segment:** Static Mapping — Group Switching (`docs/llds/static-mapping.md § Group Switching`)
- **Claim:** A CC collision between a Group-switch key (`previous_track`/`next_track`) and any other control's CC resolves in favor of Group switching (`MAP-GROUP-005`); a Group-switch discards dedup/position state only for Banks currently in OSC axis (direct) mode, not for Banks in OSC encoder mode (`MAP-GROUP-011`); a Controller Profile switch, not an ordinary Group switch, resets the active Group to 1 (`MAP-GROUP-007`).
- **Quantifiers in the claim:** for every CC-collision case; for every Bank's fader-mode state at the moment of a Group switch.
- **Claim dimensions:**
  - dispatch-order precedence under CC collision
  - dedup-discard scope (axis-direct-mode Banks only)
  - Group-index reset scope (profile switch, not Group switch or ordinary MIDI reconnect)
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** State-machine safety; Determinism
- **Discovery source:** EARS requirement
- **Authority:** SPECIFIED — Authority basis: `MAP-GROUP-005`, `MAP-GROUP-007`, `MAP-GROUP-011` (`docs/specs/static-mapping.md`)
- **Claim nature:** Property
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/mapping.py`
- **Confidence in intent:** high
- **Consequence if false:** a Group switch could silently fail to fire, or discard/retain the wrong Banks' dedup state, producing an incorrect first nudge after switching
- **Downstream dependencies:** every Bank in OSC axis (direct) mode
- **Preconditions:** none
- **Assumptions:** none
- **Prioritization rationale:** substantial existing example-test coverage per `docs/specs/static-mapping.md`'s own dense spec set for this area; no gap identified during Phase 1 mapping
- **Priority:** low
- **Disposition:** Approved
- **Evidence coverage:** n/a — Phase 4A concluded "additional evidence: none justified" — see `EVID-009`
- **Evidence state (set):** Example-tested (existing)
- **Residual gaps:** none currently identified
- **Evidence-matrix row:** `EVID-009`

### DM-EA-001: Dragonframe is a trusted local peer for OSC input

- **Behavioral segment:** OSC I/O
- **Claim:** DragonMIDI's OSC decode path does not defend against a deliberately adversarial Dragonframe-equivalent sender — it is designed and documented as trusting the local peer, with `DM-001`'s guards framed as robustness/contract enforcement (against accidental malformation), not a security boundary.
- **Quantifiers in the claim:** n/a — a design-posture statement, not a testable universal
- **Claim dimensions:** n/a
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** n/a (External assumption, not a Property)
- **Discovery source:** implementation observation (`osc_io.py` docstring: "Dragonframe is a trusted local peer, not untrusted input")
- **Authority:** SPECIFIED — Authority basis: explicit docstring statement of accepted threat model
- **Claim nature:** External assumption
- **Lifecycle:** Enduring
- **Source evidence:** `dragonmidi/osc_io.py`
- **Confidence in intent:** high
- **Consequence if false:** if a hostile process on the same machine/LAN can send to the OSC Listener's bound port, `DM-001`'s guards reduce but do not eliminate risk (e.g. no resource-exhaustion defense against a flood of valid-but-numerous packets)
- **Downstream dependencies:** `DM-001`'s scope (guards are contract enforcement, not adversarial hardening)
- **Preconditions:** n/a
- **Assumptions:** n/a (this entry is itself the assumption)
- **Prioritization rationale:** intentional, accepted threat-model boundary — not an evidence-task candidate
- **Priority:** n/a
- **Disposition:** Approved
- **Evidence coverage:** n/a
- **Evidence state (set):** No evidence — by design; not intended to be defended against
- **Residual gaps:** none currently identified — this is an accepted, intentional threat-model boundary, not an open question
- **Evidence-matrix row:** `EVID-010`

### DM-EA-002: AXn axis identity matches OSC discovery order

- **Behavioral segment:** OSC I/O / Mapping
- **Claim:** Dragonframe's internal `AXn` axis numbering (used in `select-AXn`/`jog-AXn` WebSocket commands and in the Solo mapping) corresponds to the order DragonMIDI discovers axis names via `getAllPosition`.
- **Quantifiers in the claim:** for every discovered axis, in every axis ordering Dragonframe might present
- **Claim dimensions:** n/a
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** n/a (External assumption)
- **Discovery source:** implementation observation (explicit docstring: "the accepted assumption")
- **Authority:** SPECIFIED — Authority basis: explicit docstring statement
- **Claim nature:** External assumption
- **Lifecycle:** Enduring
- **Source evidence:** relevant source docstring (mapping/osc_io)
- **Confidence in intent:** medium — stated as an accepted assumption, not independently confirmed against real Dragonframe behavior across non-trivial axis orderings
- **Consequence if false:** `select-AXn`/`jog-AXn`/Solo commands could target the wrong physical axis with no error, no crash, silently wrong
- **Downstream dependencies:** `DM-007` (`select-AXn`/`jog-AXn` correctness assumes this holds)
- **Preconditions:** n/a
- **Assumptions:** n/a
- **Prioritization rationale:** silent-wrong-axis failure mode with no automated way to verify (Dragonframe's own AXn assignment isn't queryable) — a manual verification candidate
- **Priority:** medium-high
- **Disposition:** Approved
- **Evidence coverage:** n/a
- **Evidence state (set):** No evidence currently — manual verification procedure specified, see `evidence-handoff.md`
- **Residual gaps:** external verification unavailable or missing — Type: External verification unavailable or missing. Disposition: Manual/operational verification — routed to `evidence-handoff.md`.
- **Evidence-matrix row:** `EVID-011`

### DM-EA-003: nanoKONTROL2 bundled default CC map matches real hardware factory defaults

- **Behavioral segment:** MIDI Input / Static Mapping (nanoKONTROL2 profile)
- **Claim:** The CC numbers and channel bundled in DragonMIDI's default nanoKONTROL2 Controller Profile match the device's actual factory-default CC-mode assignment.
- **Quantifiers in the claim:** for every control on the nanoKONTROL2 (faders, knobs, mutes, solos, transport)
- **Claim dimensions:** n/a
- **Canonical definition:** n/a
- **Valid initial-state domain:** n/a
- **Property class:** n/a (External assumption)
- **Discovery source:** direct user statement (HLD: manually confirmed against real hardware, 2026-07-21)
- **Authority:** SPECIFIED — Authority basis: HLD Key Design Decisions, citing an in-practice confirmation against real hardware
- **Claim nature:** External assumption
- **Lifecycle:** Enduring
- **Source evidence:** `docs/high-level-design.md` (References / Key Design Decisions)
- **Confidence in intent:** medium-high — confirmed once, behaviorally (every control produced expected Dragonframe behavior), not via a byte-level MIDI-monitor trace, and not confirmed across multiple hardware/firmware revisions
- **Consequence if false:** a control silently maps to the wrong physical control on some nanoKONTROL2 units/firmware revisions
- **Downstream dependencies:** the bundled nanoKONTROL2 profile's default behavior
- **Preconditions:** n/a
- **Assumptions:** n/a
- **Prioritization rationale:** already manually verified in practice; no further evidence action needed absent a divergence report
- **Priority:** low
- **Disposition:** Approved
- **Evidence coverage:** n/a
- **Evidence state (set):** Manually verified (as of 2026-07-21, in-practice behavioral confirmation — not a byte-level trace)
- **Residual gaps:** none currently identified against the verified unit; freshness noted below
- **Freshness:** verified as of 2026-07-21 against one physical unit — stale-renewal trigger: a future report of a nanoKONTROL2 unit/firmware behaving differently
- **Evidence-matrix row:** `EVID-012`

## Rejected / withdrawn

| Property ID | Reason rejected/withdrawn | Date |
|---|---|---|
| `DM-RETIRED-001` (would-be ID for "synthesized map identical to pre-Phase-5 `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` constants") | Migration/transition acceptance criterion, Lifecycle: Migration-only, satisfied — Phase 5 (pluggable Controller Profiles) shipped; no pre-Phase-5 hardcoded implementation remains in production for this to be a bridge toward. Not registered. Its live successor concern, freshly worded against the current Opinionated Table/Bank-Derivation specs rather than historical constants, is `DM-004`. | 2026-08-26 |
