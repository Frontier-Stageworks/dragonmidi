# Property Register

Phase 2/3/4 artifact. Merged with evidence-matrix fields per `docs/workflow.md § Artifact scaling for small tasks` — six properties, one segment, doesn't warrant a separate `evidence-matrix.md` file.

Built from `system-assurance-map.md`'s chokepoints/failure paths, narrowed by the Phase 1 reconciliation stop (2026-08-25).

## Register

### MAPS-001: E-Stop delivery observability

- **Behavioral segment:** WebSocket Output Adapter (`websocket_output.py`), Status UI
- **Claim:** The operator has some way to determine, without physically pressing Stop and checking Dragonframe's debug log, whether the WebSocket E-Stop path is currently deliverable (server bound *and* a live Dragonframe connection present) versus currently non-functional (unbound, or bound with no connection).
- **Property class:** Operational properties / error-failure semantics
- **Origin:** INFERRED — no existing spec states this claim; it stands in direct tension with the HLD's explicit Non-Goal ("Keystroke output fails silently... WebSocket output fails silently on bind failure... no third status indicator").
- **Source evidence:** `docs/high-level-design.md` Key Design Decisions ("WebSocket output fails silently on bind failure"); `websocket_output.py` `WS-SEND-003`/`WS-RUNTIME-003` (drop-silently-on-not-running, no reconnection machinery); `system-assurance-map.md` High-consequence failure paths.
- **Confidence in intent:** low as currently specified (HLD explicitly rules this out) — but user confirmed 2026-08-25 this should be **top priority**, overriding the existing HLD Non-Goal.
- **Consequence if false (i.e., if the gap stays closed):** operator presses physical Stop believing E-Stop fired; motion-control hardware keeps moving with no indication anything is wrong until physically observed.
- **Downstream dependencies:** none — this is a leaf UI/observability property, doesn't gate other claims.
- **Preconditions:** WebSocket Output Adapter is the only path for E-Stop (`docs/high-level-design.md` Non-Goals: "no command exists" via OSC/keystroke for this).
- **Assumptions:** none beyond what's already in the WS-LIFECYCLE/WS-CONN specs.
- **Prioritization rationale:** highest consequence-if-false in the whole system (safety-relevant, silent, hard to notice mid-shoot); user-confirmed top priority.
- **Priority:** high
- **Approval status:** approved (priority confirmed by user 2026-08-25) — **but the claim requires a design decision MAPS cannot make on its own**: it reverses an explicit HLD Non-Goal, which is LID's territory, not MAPS's. See Phase 6 handoff below.
- **Evidence status:** Known gap (explicit) — no evidence exists because no implementation of the observability signal exists yet.
- **Claim type:** state-machine-visibility (a UI-observable state must correctly reflect an internal bind/connection state machine) — once implemented.
- **Evidence selection:** Not yet applicable — the property has no implementation to evidence. Once a design exists (a third indicator, or folding this into the existing two), the natural evidence method is a **lifecycle/integration test** (state-machine safety class, small state space: unbound / bound-no-connection / bound-with-connection) matching the existing `WS-LIFECYCLE-*` test style — example-based is sufficient here, the state space is small and enumerable, no property-testing or formal proof needed.
- **Residual gap:** requires an LID pass to decide *whether and how* to expose this (revise the HLD Non-Goal), before any MAPS evidence work is meaningful. Flagged for handoff, not solved here.

### MAPS-002: Controller Profile CC-collision detection

- **Behavioral segment:** Controller Profile config schema / loader (`mapping.py::validate_controls_config`, `controller_profile_loader.py`)
- **Claim:** Loading a Controller Profile config file whose `controls:` block assigns the same CC number to two different control roles (e.g. a fader CC reused as a transport CC) either (a) is rejected at load time with a clear error, or (b) has fully deterministic, documented resolution behavior for every possible collision pair.
- **Property class:** Boundary/decoder correctness (validation completeness) + representation invariant (CC-to-role mapping should be injective within a profile)
- **Origin:** **SPECIFIED — as an explicitly accepted, deferred gap**, not a silent oversight. `docs/llds/static-mapping.md` Open Questions #7: "rejecting duplicate CCs reused across two different controls on the same device... not yet specified." `docs/llds/midi-input.md` line 151 documents the *closest* related case (`match_substring` collisions) as "logged, not refused," matching a stated project-wide tolerance for this class of authoring mistake.
- **Source evidence:** `mapping.py::validate_controls_config` (checks only per-field length and jog-wheel presence, no cross-field uniqueness); `docs/llds/static-mapping.md` lines 171, 216, 381 (three separate places documenting this as an accepted gap).
- **Confidence in intent:** high that the gap is *deliberate* as currently documented — user nonetheless asked to track it, 2026-08-25.
- **Consequence if false (gap exploited):** a third-party-authored profile silently double-maps a control (last-dict-write-wins in `build_opinionated_map`'s dict-merge order, or a fader/transport ambiguity) — the contributor gets wrong behavior with no error message pointing at the cause.
- **Downstream dependencies:** every property that assumes a profile's opinionated map is internally consistent (MAPS-004, MAPS-006 below).
- **Preconditions:** only reachable via a user-authored YAML profile — the two bundled profiles are hand-verified and known collision-free.
- **Assumptions:** none.
- **Prioritization rationale:** the one boundary where non-maintainer content becomes live behavior with zero review gate; user requested tracking despite the documented deferral.
- **Priority:** medium — real risk, but deliberately deferred by an existing design decision; not silently overridden here.
- **Approval status:** approved for **tracking**, 2026-08-25 (user confirmed) — **not** approved for closing the gap; that would reverse `docs/llds/static-mapping.md`'s explicit deferral and belongs in LID, not decided unilaterally by MAPS.
- **Evidence status:** Known gap (explicit) for the general cross-field case. **Example-tested** for the one collision case that *is* specified: `MAP-GROUP-005`'s Track-vs-jog-wheel dispatch order is deterministic and covered.
- **Claim type:** representation invariant (if the deferral were reversed).
- **Evidence selection (if the deferral is ever reversed):** property-based testing is the natural fit — generate randomized `ControlsConfig` instances (including deliberately duplicated CCs across fields) and assert a `detect_cc_collisions()` function's output against a simple set-cardinality oracle. Cheap, strong exploration, no need for formal proof (the invariant is a straightforward uniqueness check, not a subtle universal claim).
- **Residual gap:** stays open by design. Recommend re-raising with the user as an explicit HLD/LLD revision proposal if the contributor base for third-party profiles grows past "a handful of trusted people."

### MAPS-003: Dragonframe WebSocket AXn-ordering assumption

- **Behavioral segment:** `MappingEngine.process_websocket()` (Cycle, Group-aware Solo)
- **Claim:** Dragonframe's WebSocket-side `AXn` numbering (used by `select-AXn`) matches the axis ordering DragonMIDI discovers via OSC `getAllPosition` responses.
- **Property class:** External assumption / compatibility property (interop with an external, unverified numbering scheme)
- **Origin:** SPECIFIED as an *assumption* — explicitly written into `process_websocket()`'s own docstring as "the accepted assumption" and cross-referenced from `docs/llds/static-mapping.md`. Not SPECIFIED as a *confirmed fact*.
- **Source evidence:** `mapping.py` `process_websocket()` docstring; `docs/llds/static-mapping.md` WebSocket-Targeted Controls section.
- **Confidence in intent:** the assumption's existence is well-documented; its truth is not — user confirmed 2026-08-25 it remains **unverified** against real Dragonframe.
- **Consequence if false:** Cycle and Solo select the wrong physical axis — silent misdirection (a `select-AXn` command still succeeds, it just targets the wrong axis), with high blast radius on a live rig if noticed late.
- **Downstream dependencies:** MAPS-001 territory conceptually (silent-wrong-behavior class) but functionally independent.
- **Preconditions:** only matters once axis discovery has found ≥1 axis and Group/Cycle actually gets used.
- **Assumptions:** this property *is* the assumption — no further assumption underlies it.
- **Prioritization rationale:** unverifiable by unit testing (depends on real Dragonframe internal numbering, which DragonMIDI cannot query); high consequence, silent failure mode; already flagged by the code itself as the shakiest external assumption in the system.
- **Priority:** high (as a documented, unverified assumption — not as a code-fix task, since there's no code to fix)
- **Approval status:** approved as an **open assumption requiring operational verification**, 2026-08-25 (user confirmed still unverified).
- **Evidence status:** Assumption (per the assurance status vocabulary) — this is the correct terminal status, not a placeholder for future test coverage.
- **Claim type:** compatibility/interop claim against an external, closed system (Dragonframe) with no available reference implementation to differential-test against.
- **Evidence selection:** no unit/property/formal method applies — Dragonframe is not observable or scriptable from outside its own UI/log. The only viable evidence is an **explicit, documented operational verification procedure**: with a real project loaded in Dragonframe, deliberately create an axis ordering where discovery order is *not* alphabetical/creation order (to distinguish coincidental agreement from a real correspondence), fire `select-AXn` for each discovered axis in turn, and log-confirm (Dragonframe's debug log, per the HLD's existing verification precedent for `E-Stop`/`HARD STOP`) that the *intended* axis highlights each time. This is a one-time or per-Dragonframe-version manual check, not automatable — recommend adding it to the project's README/testing-strategy as a documented manual verification step, so it isn't silently forgotten.
- **Residual gap:** stays an assumption until that manual verification is actually run and logged; MAPS's job here ends at specifying the verification procedure.

### MAPS-004: Knob-nudge clamp bound invariant

- **Behavioral segment:** `MappingEngine._process_bank_derived` (`mapping.py:636-676`)
- **Claim:** For any sequence of Knob N raw-value deltas and any interleaving of live (`axis_positions`) vs. internally-estimated position readings, the tracked axis position after each nudge always stays within `[min(min_value, max_value), max(min_value, max_value)]` for that (Bank, Group) assignment, and the delta actually sent never overshoots that bound.
- **Property class:** Boundedness / numeric correctness
- **Origin:** SPECIFIED — `MAP-BANK-008`, `MAP-BANK-009` (`docs/specs/static-mapping.md` lines 54-55) state this exactly, including the tie-break rule for reversed min/max and the live-vs-estimate preference order.
- **Source evidence:** EARS specs above; `mapping.py` `_process_bank_derived`; git history `81d1397` ("fixed fine tuning to be 0.1 instead of 1 on each midi step"), `f63a84a` ("fixed the pot behvior for micro adjustments").
- **Confidence in intent:** high — fully specified, not inferred.
- **Consequence if false:** axis creeps outside its configured safe range on real motion-control hardware; this exact class of bug has occurred in production before.
- **Downstream dependencies:** none upstream; this is itself close to a leaf numeric-correctness property.
- **Preconditions:** Bank N's fader has a real axis assigned in the active Group; engine is in axis mode.
- **Assumptions:** floating-point arithmetic behaves per IEEE-754 double semantics (Python `float`); not separately verified, treated as trusted-base.
- **Prioritization rationale:** only area in the whole system with a *confirmed* prior production bug; specified, numeric, and directly drives physical hardware position.
- **Priority:** high
- **Approval status:** approved (SPECIFIED, no reconciliation stop needed)
- **Evidence status:** currently Example-tested only (`test_mapping.py`) — no property-based coverage found.
- **Claim type:** boundedness/conservation-style invariant over a large input space (delta sequences × live/estimate interleavings).
- **Evidence selection:** **property-based testing** is the strongest fit — generate random sequences of raw-value deltas (including large jumps, repeated identical values, and alternating live-reading-present/absent) against randomized `[min, max]` ranges (including reversed min>max), assert the invariant holds after every step and that the sent delta never exceeds what's needed to reach the bound. Supporting: keep the existing example-based tests as named regression anchors for the two historical bugs specifically (a property test finding a new violation doesn't replace the record of what broke before).
- **Residual gap:** none identified beyond "write the property test" — this is ready for direct Phase 6 handoff (property-test specification, not LAPS — no proof-worthy universal claim beyond what property testing already covers well).

### MAPS-005: `decode_osc_packet` malformed-bundle robustness

- **Behavioral segment:** `osc_io.py::decode_osc_packet`
- **Claim:** For any byte string presented to `decode_osc_packet` (including malformed `#bundle` framing with non-positive or absurdly large declared `element_size`, or deeply nested bundles), the call either returns a result or raises within bounded time and bounded stack depth — it never hangs and never causes unbounded recursion.
- **Property class:** Boundary/decoder correctness, error/failure semantics, boundedness
- **Origin:** CODE-OBSERVED / INFERRED, confirmed 2026-08-25 — the code's own docstring explicitly disclaims this concern ("No recursion-depth or size-consistency bound is imposed — Dragonframe is a trusted local peer, not untrusted input," citing `OSC-DISCOVER-004`), so the *pre-existing* intent was that this robustness was explicitly out of scope. User confirmed 2026-08-25 that hardening is worth pursuing anyway, overriding that documented framing.
- **Source evidence:** `osc_io.py` `decode_osc_packet` docstring and implementation (lines 110-131); `handle_datagram`'s broad `except Exception` only guards against *raised* exceptions, not a hang from a non-advancing/negative offset.
- **Confidence in intent:** was low pre-reconciliation (MAPS's judgment diverged from the code's stated intent); resolved by user 2026-08-25 in favor of hardening.
- **Consequence if false:** the OSC Listener's background thread hangs or exhausts the stack on a malformed/crafted datagram from any local process (not necessarily malicious — a misbehaving unrelated app binding the wrong port, or Dragonframe itself sending a corrupted packet during a crash, would qualify); both signal indicators go dark with no diagnostic.
- **Downstream dependencies:** axis discovery (MAPS-003 territory), Dragonframe-signal liveness.
- **Preconditions:** any process on the local machine can send to DragonMIDI's listen port; no authentication exists (matches OSC's connectionless design generally).
- **Assumptions:** the "trusted local peer" framing itself is the assumption under scrutiny here.
- **Prioritization rationale:** genuine hang path in a background thread, but requires either a buggy/crashing Dragonframe or another local process sending to the wrong port — not an internet-facing or adversarial-network exposure.
- **Priority:** medium (real but narrow exposure; not safety-relevant the way MAPS-001 is)
- **Approval status:** approved, 2026-08-25 (user confirmed — pursue hardening despite the pre-existing "trusted peer" framing).
- **Evidence status:** Evidence planned.
- **Claim type:** boundary/decoder robustness under malformed input.
- **Evidence selection:** **fuzzing** is the natural fit for "does a decoder ever hang/crash on adversarial bytes" — a short property/fuzz harness feeding `decode_osc_packet` randomized and structurally-malformed byte strings (via `hypothesis`, already a project dependency per the repo's `.hypothesis/` cache dir) with a wall-clock timeout as the oracle. Supporting: a direct code fix (reject non-positive `element_size`, cap recursion depth) plus a regression test for the specific case found.
- **Residual gap:** none beyond scheduling the fuzz harness + fix; ready for Phase 6 handoff.

### MAPS-006: Controller Profile switch state-clear completeness

- **Behavioral segment:** `MappingEngine.set_profile` (`mapping.py:394-409`)
- **Claim:** After `set_profile(new_profile)`, no per-control state tracked under the *previous* profile (dedup values, press state, debounce timestamps, axis positions, Group axis assignments, encoder mode) influences any subsequent `process()`/`process_websocket()`/`process_keystroke()` call under the new profile — even when the old and new profiles reuse the same CC number for semantically different controls.
- **Property class:** Isolation
- **Origin:** SPECIFIED — `MAP-PROFILE-004` states the switch "clears every piece of tracked state, including axis assignments and encoder-mode overrides."
- **Source evidence:** `docs/specs/static-mapping.md` `MAP-PROFILE-004`; `mapping.py::set_profile`/`reset`.
- **Confidence in intent:** high.
- **Consequence if false:** switching from one Controller Profile to another (e.g. via the dropdown, mid-session) leaks stale state — a control on the new profile inherits a dedup baseline or axis position meant for a different physical control on the old profile, producing a wrong first output with no error.
- **Downstream dependencies:** every property that assumes a profile's behavior is self-contained (MAPS-002, MAPS-004).
- **Preconditions:** requires an actual profile switch at runtime — the Phase 4 feature this enables.
- **Assumptions:** `reset()`'s own completeness (it's called from within `set_profile`) — same claim, one level down; not separately registered since they're the same invariant at two call sites.
- **Prioritization rationale:** direct isolation property on the one state machine (`MappingEngine`) every other property depends on being clean.
- **Priority:** medium
- **Approval status:** approved (SPECIFIED)
- **Evidence status:** Example-tested (`test_mapping_profiles.py`, per the assurance map).
- **Claim type:** isolation between two "sessions" (profile A's state, profile B's state) of the same engine instance.
- **Evidence selection:** **property-based testing** is a good fit and currently missing — generate two profiles with deliberately overlapping CC numbers assigned to different roles (fader vs. transport vs. WebSocket-targeted), drive the engine through randomized event sequences under profile A, switch, then assert the *first* event under profile B produces output identical to a fresh `MappingEngine(profile_B)` would produce for the same event (a differential-style oracle against a known-clean instance, cheap since the "reference" is just a fresh object in the same process — not a second implementation, so no independence classification is needed). Supporting: keep existing example-based tests.
- **Residual gap:** none beyond writing the property test; ready for Phase 6 handoff alongside MAPS-004.

## Pending user reconciliation

All properties reconciled as of 2026-08-25. None currently pending.

## Rejected / withdrawn

| Property ID | Reason rejected/withdrawn | Date |
|---|---|---|
| — | none yet | — |
