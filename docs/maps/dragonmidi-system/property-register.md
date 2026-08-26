# Property Register

Phase 2/3/4 artifact. Merged with evidence-matrix fields per `docs/workflow.md § Artifact scaling for small tasks` — seven properties, one segment, doesn't warrant a separate `evidence-matrix.md` file.

Built from `system-assurance-map.md`'s chokepoints and failure paths.

## Register

### MAPS-001: WebSocket E-Stop transport readiness observability

- **Behavioral segment:** WebSocket Output Adapter (`websocket_output.py`), Status UI
- **Claim:** The operator has some way to determine, without physically pressing Stop, whether DragonMIDI's WebSocket server is currently bound *and* has a live peer connection ("transport appears ready") versus unbound or bound-with-no-connection ("transport not ready"). This claim is deliberately scoped to transport state only — it does not claim, and a passing test for it would not establish, that E-Stop is actually deliverable to Dragonframe end-to-end. A bound-and-connected state proves *a* peer is talking to the WebSocket server; it does not prove that peer is Dragonframe, since `_handler()`'s connection-supersede logic (`WS-CONN-004/005/006`) accepts any local process passing the path check, with no origin/auth check.
- **Property class:** Operational properties / error-failure semantics (state-machine visibility)
- **Origin:** INFERRED — no existing spec states this claim. The transport-readiness scoping is a smaller ask than the HLD's Non-Goal ("no third status indicator") rules out, since it extends the existing bind-result observability pattern (`WS-LIFECYCLE-002`) rather than claiming anything about E-Stop's real-world efficacy.
- **Source evidence:** `docs/high-level-design.md` Key Design Decisions ("WebSocket output fails silently on bind failure"); `websocket_output.py` `WS-SEND-003`/`WS-RUNTIME-003` (drop-silently-on-not-running, no reconnection machinery); `WS-CONN-004/005/006` (connection supersede, no peer auth); `system-assurance-map.md` High-consequence failure paths and Trust boundaries.
- **Confidence in intent:** low against the HLD as currently written (which rules out a third indicator) — user has confirmed this should be top priority regardless.
- **Consequence if false (i.e., if the gap stays closed):** operator presses physical Stop believing E-Stop fired; motion-control hardware keeps moving with no indication anything is wrong until physically observed.
- **Downstream dependencies:** none — this is a leaf UI/observability property, doesn't gate other claims.
- **Preconditions:** WebSocket Output Adapter is the only path for E-Stop (`docs/high-level-design.md` Non-Goals: "no command exists" via OSC/keystroke for this).
- **Assumptions:** **the connected peer is Dragonframe.** Not established by the adapter as built — `WS-CONN-002/003` checks only the connection *path*, not the peer's identity, and any local process passing that check can hold the connection. This is the reason the claim above is capped at "transport appears ready," not "E-Stop is deliverable." Strengthening this assumption would require new design work (e.g. a handshake/acknowledgment protocol Dragonframe would also need to implement, which is outside DragonMIDI's control).
- **Prioritization rationale:** highest consequence-if-false in the whole system (safety-relevant, silent, hard to notice mid-shoot); user-confirmed top priority; the transport-readiness half is genuinely evidenceable now, without waiting on a full E-Stop-delivery design decision.
- **Priority:** high
- **Approval status:** approved for the transport-readiness claim. Still requires a small implementation step (exposing connection-state, not just bind-state, to the Status UI) — a much less contested design ask than "prove E-Stop works," since it extends an existing observability pattern rather than reversing the HLD's E-Stop Non-Goal outright. See Phase 7 handoff (`evidence-handoff.md`).
- **Evidence status:** Known gap for the transport-readiness signal itself — no implementation exists yet. Structurally out of reach for the peer-identity assumption — see Residual gap.
- **Claim type:** state-machine visibility (a UI-observable state must correctly reflect the WebSocket adapter's bind/connection state) — once implemented.
- **Evidence selection:** for the transport-readiness claim, once a connection-state signal is added: a **lifecycle/integration test** (state-machine safety class, small state space: unbound / bound-no-connection / bound-with-connection) matching the existing `WS-LIFECYCLE-*` test style — example-based is sufficient, the state space is small and enumerable. For the peer-identity assumption: no evidence method applies within this codebase's current design; it remains an explicit, permanent assumption unless Dragonframe gains some way to authenticate itself.
- **Residual gap:** even with the transport-readiness indicator built and tested, end-to-end E-Stop deliverability to Dragonframe specifically remains unestablished — that would require either a design capable of identifying/acknowledging the Dragonframe peer specifically (LID's territory, not MAPS's), or an explicit, permanent, documented acceptance that peer identity is unverifiable and out of scope. Flagged for handoff, not resolved here.
- **Gap type (`checklists/argument-validation.md § 9` taxonomy):** **Design gap** for both parts — the transport-readiness signal has no implementation and the design itself (third indicator vs. folded-in vs. other) is undecided; the peer-identity part has no implementation and no viable design currently exists at all within DragonMIDI's unilateral control. Per rule #9, neither part gets a ready-to-implement test specification — `evidence-handoff.md`'s MAPS-001 entry is a design-decision handoff for the first, and a permanent-limitation note for the second.

### MAPS-002: Controller Profile CC-collision detection

- **Behavioral segment:** Controller Profile config schema / loader (`mapping.py::validate_controls_config`, `controller_profile_loader.py`)
- **Claim:** Loading a Controller Profile config file whose `controls:` block assigns the same CC number to two different control roles (e.g. a fader CC reused as a transport CC) either (a) is rejected at load time with a clear error, or (b) has fully deterministic, documented resolution behavior for every possible collision pair.
- **Property class:** Boundary/decoder correctness (validation completeness) + representation invariant (CC-to-role mapping should be injective within a profile)
- **Origin:** **SPECIFIED — as an explicitly accepted, deferred gap**, not a silent oversight. `docs/llds/static-mapping.md` Open Questions #7: "rejecting duplicate CCs reused across two different controls on the same device... not yet specified." `docs/llds/midi-input.md` line 151 documents the *closest* related case (`match_substring` collisions) as "logged, not refused," matching a stated project-wide tolerance for this class of authoring mistake.
- **Source evidence:** `mapping.py::validate_controls_config` (checks only per-field length and jog-wheel presence, no cross-field uniqueness); `docs/llds/static-mapping.md` lines 171, 216, 381 (three separate places documenting this as an accepted gap).
- **Confidence in intent:** high that the gap is *deliberate* as currently documented — user asked to track it anyway.
- **Consequence if false (gap exploited):** a third-party-authored profile silently double-maps a control (last-dict-write-wins in `build_opinionated_map`'s dict-merge order, or a fader/transport ambiguity) — the contributor gets wrong behavior with no error message pointing at the cause.
- **Downstream dependencies:** every property that assumes a profile's opinionated map is internally consistent (MAPS-004, MAPS-006 below).
- **Preconditions:** only reachable via a user-authored YAML profile — the two bundled profiles are hand-verified and known collision-free.
- **Assumptions:** none.
- **Prioritization rationale:** the one boundary where non-maintainer content becomes live behavior with zero review gate; user requested tracking despite the documented deferral.
- **Priority:** medium — real risk, but deliberately deferred by an existing design decision; not silently overridden here.
- **Approval status:** approved for **tracking** — **not** approved for closing the gap; that would reverse `docs/llds/static-mapping.md`'s explicit deferral and belongs in LID, not decided unilaterally by MAPS.
- **Evidence status:** Known gap for the general cross-field case. **Example-tested** for the one collision case that *is* specified: `MAP-GROUP-005`'s Track-vs-jog-wheel dispatch order is deterministic and covered.
- **Claim type:** representation invariant (if the deferral were reversed).
- **Evidence selection (if the deferral is ever reversed):** property-based testing is the natural fit — generate randomized `ControlsConfig` instances (including deliberately duplicated CCs across fields) and assert a `detect_cc_collisions()` function's output against a simple set-cardinality oracle. Cheap, strong exploration, no need for formal proof (the invariant is a straightforward uniqueness check, not a subtle universal claim).
- **Residual gap:** stays open by design. Recommend re-raising with the user as an explicit HLD/LLD revision proposal if the contributor base for third-party profiles grows past "a handful of trusted people."
- **Gap type:** **Accepted risk** — known, real, deliberately not being closed right now (`docs/llds/static-mapping.md`'s existing deferral). Owner: the user. Revisit trigger: contributor base growth past "a handful of trusted people."

### MAPS-003: Dragonframe WebSocket AXn-ordering assumption

- **Behavioral segment:** `MappingEngine.process_websocket()` (Cycle, Group-aware Solo)
- **Claim:** Dragonframe's WebSocket-side `AXn` numbering (used by `select-AXn`) matches the axis ordering DragonMIDI discovers via OSC `getAllPosition` responses.
- **Property class:** External assumption / compatibility property (interop with an external, unverified numbering scheme)
- **Origin:** SPECIFIED as an *assumption* — explicitly written into `process_websocket()`'s own docstring as "the accepted assumption" and cross-referenced from `docs/llds/static-mapping.md`. Not SPECIFIED as a *confirmed fact*.
- **Source evidence:** `mapping.py` `process_websocket()` docstring; `docs/llds/static-mapping.md` WebSocket-Targeted Controls section.
- **Confidence in intent:** the assumption's existence is well-documented; its truth is not — user has confirmed it remains unverified against real Dragonframe.
- **Consequence if false:** Cycle and Solo select the wrong physical axis — silent misdirection (a `select-AXn` command still succeeds, it just targets the wrong axis), with high blast radius on a live rig if noticed late.
- **Downstream dependencies:** MAPS-001 territory conceptually (silent-wrong-behavior class) but functionally independent.
- **Preconditions:** only matters once axis discovery has found ≥1 axis and Group/Cycle actually gets used.
- **Assumptions:** this property *is* the assumption — no further assumption underlies it.
- **Prioritization rationale:** unverifiable by unit testing (depends on real Dragonframe internal numbering, which DragonMIDI cannot query); high consequence, silent failure mode; already flagged by the code itself as the shakiest external assumption in the system.
- **Priority:** high (as a documented, unverified assumption — not as a code-fix task, since there's no code to fix)
- **Approval status:** approved as an **open assumption requiring operational verification**.
- **Claim nature vs. verification state:** two separate axes, not one field, so that verifying the assumption once doesn't get conflated with the assumption itself becoming a tested property.
  - **Type:** External assumption. This does not change, ever — even a successful manual check does not promote this to a tested/proved property, because Dragonframe's internal behavior remains outside DragonMIDI's control and could change in a future Dragonframe version with no notice to this project.
  - **Verification state:** **Unverified.** Would change to **Manually verified against Dragonframe version `<X>`, `<date>`** once the procedure below is run and logged — the Type stays External assumption regardless; only the Verification state field moves.
- **Evidence status:** Assumption, Unverified.
- **Claim type:** compatibility/interop claim against an external, closed system (Dragonframe) with no available reference implementation to differential-test against.
- **Evidence selection:** no unit/property/formal method applies — Dragonframe is not observable or scriptable from outside its own UI/log. The only viable evidence is an **explicit, documented operational verification procedure**: with a real project loaded in Dragonframe, deliberately create an axis ordering where discovery order is *not* alphabetical/creation order (to distinguish coincidental agreement from a real correspondence), fire `select-AXn` for each discovered axis in turn, and log-confirm (Dragonframe's debug log, per the HLD's existing verification precedent for `E-Stop`/`HARD STOP`) that the *intended* axis highlights each time. This is a one-time or per-Dragonframe-version manual check, not automatable — recommend adding it to the project's README/testing-strategy as a documented manual verification step, so it isn't silently forgotten.
- **Residual gap:** the Type stays External assumption permanently. The Verification state moves from Unverified to Manually verified (version-scoped) once the procedure is run and logged — and moves back to Unverified-for-that-version if Dragonframe is ever upgraded, since a manual check has no regression protection across Dragonframe versions.
- **Gap type:** **External-assumption verification gap** — the claim depends on a system (Dragonframe) outside this project's control and can't be automated. Routes to a manual/operational verification procedure, not a test/fuzz/proof spec.

### MAPS-004: Knob-nudge clamp bound invariant

- **Behavioral segment:** `MappingEngine._process_bank_derived` (`mapping.py:636-676`)
- **Claim (in-bounds-start sub-claim):** For any sequence of Knob N raw-value deltas and any interleaving of live (`axis_positions`) vs. internally-estimated position readings, given the tracked position starts within `[min(min_value, max_value), max(min_value, max_value)]`, the tracked position after each nudge always stays within that range, and the delta actually sent never overshoots that bound.
- **Claim (out-of-range-start sub-claim):** If the tracked position starts outside `[low, high]` — a realistic input, since a live reading comes from Dragonframe, whose actual axis limits are independent of DragonMIDI's user-entered `min`/`max` scaling range, and a user could configure a narrower range than Dragonframe's real travel — the resulting position, if a message is sent, is always within `[low, high]`. This is `MAP-BANK-008`'s clamping formula applied unconditionally, with no distinct code path: `clamped_position = max(low, min(high, current_position + delta))` forces the result into range regardless of the starting position. Which position within `[low, high]` a given out-of-range-start nudge lands on — an interior point, or exactly one bound — is whatever `current_position + delta` clamps to; no further guarantee about which bound it favors exists beyond landing in range.
- **Property class:** Boundedness / numeric correctness
- **Origin:** the in-bounds sub-claim is SPECIFIED — `MAP-BANK-008`, `MAP-BANK-009` (`docs/specs/static-mapping.md`) state it exactly, including the tie-break rule for reversed min/max and the live-vs-estimate preference order. The out-of-range sub-claim is now SPECIFIED as `MAP-BANK-010`.
- **Source evidence:** EARS specs above; `mapping.py` `_process_bank_derived`; git history `81d1397` ("fixed fine tuning to be 0.1 instead of 1 on each midi step"), `f63a84a` ("fixed the pot behvior for micro adjustments").
- **Confidence in intent:** high — fully specified, not inferred.
- **Consequence if false:** axis creeps outside its configured safe range on real motion-control hardware; this exact class of bug has occurred in production before.
- **Downstream dependencies:** none upstream; this is itself close to a leaf numeric-correctness property.
- **Preconditions:** Bank N's fader has a real axis assigned in the active Group; engine is in axis mode. The in-bounds sub-claim additionally requires the initial authoritative position (live or estimated) to itself be within `[low, high]`; the out-of-range sub-claim is precisely the complementary case.
- **Assumptions:** floating-point arithmetic behaves per IEEE-754 double semantics (Python `float`); not separately verified, treated as trusted-base.
- **Prioritization rationale:** only area in the whole system with a *confirmed* prior production bug; specified, numeric, and directly drives physical hardware position.
- **Priority:** high
- **Approval status:** approved (SPECIFIED, no reconciliation stop needed)
- **Evidence status:** Example-tested (two named tests anchoring the historical bug scenarios) + **Property-tested** (a single-nudge property over randomized ranges/deltas/live-or-estimate, and a multi-step sequence property asserting the invariant holds after every step) for the in-bounds sub-claim; **Property-tested** for the out-of-range sub-claim. Both mutation-verified.
- **Claim type:** boundedness/conservation-style invariant over a large input space (delta sequences × live/estimate interleavings, and out-of-range starting positions).
- **Evidence selection:** property-based testing, in two generator groups: (1) **in-bounds-start** — initial position constrained to `[low, high]`, random sequences of raw-value deltas (large jumps, repeated identical values, alternating live-reading-present/absent) against randomized `[min, max]` ranges (including reversed min>max); asserts the invariant holds after every step, and the sent delta never exceeds what's needed to reach the bound. (2) **out-of-range-start** — initial live/estimated position deliberately generated outside `[low, high]` (both above `high` and below `low`); asserts the resulting position, if a message is sent, is always within `[low, high]`. Both keep the existing example-based tests as named regression anchors for the two historical bugs.
- **Residual gap:** none.
- **Gap type:** **Missing-evidence gap** for both sub-claims — implementation and spec exist for both; the evidence has been produced. Both route through LID Phase 5.

### MAPS-005: `decode_osc_packet` malformed-bundle robustness

- **Behavioral segment:** `osc_io.py::decode_osc_packet`
- **Claim:** For any byte string presented to `decode_osc_packet`, the call either returns a result or raises `BundleBoundsError` for a `#bundle` with a non-positive/overlong `element_size` or nesting beyond `MAX_BUNDLE_DEPTH` (8). The guards replace two behaviors this function previously relied on implicitly: Python's own slicing semantics (a non-positive-length slice is always empty) and the interpreter's own recursion limit — with an explicit, documented, fast-failing contract. A background thread walking Python's default ~1000-frame recursion limit on a malformed deeply-nested datagram, before these guards existed, was also a real if narrow cost this change removes.
- **Property class:** Boundary/decoder correctness, error/failure semantics, boundedness
- **Origin:** CODE-OBSERVED / INFERRED — the code's docstring explicitly disclaimed this concern ("No recursion-depth or size-consistency bound is imposed — Dragonframe is a trusted local peer, not untrusted input," citing `OSC-DISCOVER-004`), so the pre-existing intent was that this robustness was explicitly out of scope. User confirmed hardening was worth pursuing anyway, overriding that documented framing — the listening port accepts traffic from any local process, not only a well-behaved Dragonframe.
- **Source evidence:** `osc_io.py` `decode_osc_packet` implementation; `handle_datagram`'s broad `except Exception`.
- **Confidence in intent:** resolved by the user in favor of hardening.
- **Consequence if false:** an undocumented, implicit reliance on Python's own recursion limit and slicing semantics for safety, plus an unnecessary stack walk on malformed deeply-nested input before failing. Both signal indicators go dark momentarily on such a datagram, matching ordinary malformed-packet handling, with no diagnostic beyond the debug-level logging this work added (`OSC-DISCOVER-012`).
- **Downstream dependencies:** axis discovery (MAPS-003 territory), Dragonframe-signal liveness.
- **Preconditions:** any process on the local machine can send to DragonMIDI's listen port; no authentication exists (matches OSC's connectionless design generally).
- **Assumptions:** the "trusted local peer" framing itself is the assumption under scrutiny here.
- **Prioritization rationale:** explicit guards replace an implicit, refactor-fragile safety property with a documented one, and bound the stack-walk cost of malformed input on a background thread.
- **Priority:** medium
- **Approval status:** approved and **implemented** (`dragonmidi/osc_io.py`).
- **Evidence status:** **Example-tested** (6 deterministic regression tests: negative/zero/oversized `element_size`, exact-boundary-still-valid, depth-cap-exact-still-valid, depth-cap-exceeded) **+ Fuzz-supported** (1 `hypothesis` property test, structured malformed-bundle strategy, per-example deadline) **+ mutation-verified**: guards were deliberately removed and confirmed to make the new deterministic/logging tests fail (the accept-cases correctly kept passing); restored and re-confirmed against the full suite.
- **Claim type:** boundary/decoder robustness under malformed input, established via explicit enforcement rather than search evidence alone.
- **Evidence selection:** three parts. (1) Explicit parser guards (`BundleBoundsError`, `MAX_BUNDLE_DEPTH = 8`) inside `decode_osc_packet` itself, not only `handle_datagram`'s wrapper — the guards are the load-bearing evidence for the bound, not the tests. (2) Six deterministic boundary regression tests anchoring the specific malformed shapes. (3) One `hypothesis`-based structured-fuzz test (`st.binary()` payload plus randomized declared size and nesting depth, with a per-example deadline) as supporting, exploratory evidence for shapes the guards weren't specifically written for.
- **Residual gap:** the fuzz test uses `hypothesis`'s per-example deadline rather than a subprocess/watchdog execution-isolation harness; sufficient for this claim's scope, revisit only if that judgment changes. A guard rejection is logged at debug level (`OSC-DISCOVER-012`); every other decode failure stays silent, matching prior behavior.
- **Gap type:** **Missing-evidence gap**, resolved. Routed through LID Phase 2/3 (`docs/llds/osc-io.md`, `docs/specs/osc-io.md`, including one user decision on debug-level logging) before Phase 5 (tests) and Phase 6 (code), since the guards were new behavior not previously specified anywhere.

### MAPS-006: Controller Profile switch state-clear completeness

- **Behavioral segment:** `MappingEngine.set_profile` (`mapping.py:394-409`)
- **Claim:** After `set_profile(new_profile)`, no per-control state tracked under the *previous* profile (dedup values, press state, debounce timestamps, axis positions, Group axis assignments, encoder mode) influences any subsequent `process()`/`process_websocket()`/`process_keystroke()` call under the new profile — even when the old and new profiles reuse the same CC number for semantically different controls.
- **Property class:** Isolation
- **Origin:** SPECIFIED — `MAP-PROFILE-004` states the switch "clears every piece of tracked state, including axis assignments and encoder-mode overrides."
- **Source evidence:** `docs/specs/static-mapping.md` `MAP-PROFILE-004`; `mapping.py::set_profile`/`reset`.
- **Confidence in intent:** high.
- **Consequence if false:** switching from one Controller Profile to another (e.g. via the dropdown, mid-session) leaks stale state — a control on the new profile inherits a dedup baseline or axis position meant for a different physical control on the old profile, producing a wrong output with no error, possibly several events after the switch.
- **Downstream dependencies:** every property that assumes a profile's behavior is self-contained (MAPS-002, MAPS-004).
- **Preconditions:** requires an actual profile switch at runtime.
- **Assumptions:** `reset()`'s own completeness (it's called from within `set_profile`) — same claim, one level down; not separately registered since they're the same invariant at two call sites.
- **Prioritization rationale:** direct isolation property on the one state machine (`MappingEngine`) every other property depends on being clean.
- **Priority:** medium
- **Approval status:** approved (SPECIFIED)
- **Evidence status:** Example-tested (`test_mapping_profiles.py`, first-call case) + **Property-tested** (full post-switch trace, mutation-verified).
- **Claim type:** isolation between two "sessions" (profile A's state, profile B's state) of the same engine instance.
- **Evidence selection:** the claim quantifies over *any subsequent* call, not just the first — a plan that only compares the first post-switch event would miss delayed effects (a knob's dedup baseline that only diverges on a second nudge; encoder-mode and Group-axis interactions that take several steps to manifest; a debounce timestamp that only matters if a second press lands inside a stale window). The property test drives a synthetic profile with a CC number deliberately reused across a different control role than Studio's, through a pre-switch event sequence, switches, then drives a second randomized event sequence under the new profile — feeding the same sequence to both the switched engine and a freshly constructed `MappingEngine(profile_B)` — and asserts the entire output trace (every `process()`/`process_websocket()`/`process_keystroke()` return value, in order) is identical between the two. This is a same-process differential check against a known-clean reference object, not a second implementation, so no independence classification is needed.
- **Residual gap:** none.
- **Gap type:** **Missing-evidence gap**, resolved. Implementation and spec both existed (`MAP-PROFILE-004`); the evidence has been produced. Routed through LID Phase 5.

### MAPS-007: MAP-CONFIG-003 migration-invariant evidence is circular

- **Behavioral segment:** Controller Profile map synthesis (`mapping.py::build_opinionated_map`, `build_profile`)
- **Claim:** `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` and `build_opinionated_map(NANOKONTROL2_CONTROLS, has_scene_button=False)` produce the exact map contents the project's pre-Phase-5 hardcoded literal constants produced, before Phase 5 replaced those literals with values derived from `ControlsConfig`.
- **Property class:** Refinement/equivalence (migration correspondence)
- **Origin:** CODE-OBSERVED, by direct inspection — not yet put to the user as a reconciliation question, see Approval status.
- **Source evidence:** `test_mapping_config_schema.py:76,81` — `assert build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True) == OPINIONATED_MAP_STUDIO`. `OPINIONATED_MAP_STUDIO` (`mapping.py:321`) is defined as `STUDIO_PROFILE.opinionated_map`, and `STUDIO_PROFILE` (`mapping.py:299-307`) is itself built via `build_profile(..., controls=STUDIO_CONTROLS)` → `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` — the identical function called with the identical arguments. The test compares the function under test's output to itself; it is not compared against any independently-frozen historical literal, because that literal no longer exists anywhere in the current codebase.
- **Confidence in intent:** high that the underlying claim was true *at the moment of the Phase 5 migration commit* (presumably verified by an actual diff against the real pre-migration literal at that time, per the comment's confident phrasing); low that today's test provides any ongoing regression protection for it, since there is nothing independent left to compare against.
- **Consequence if false:** a future change to `build_opinionated_map`/`_fader_entries`/`_knob_entries`/etc. could silently drift both bundled profiles' entire opinionated map away from long-validated behavior, and this specific test would not catch it — the "reference" moves in lockstep with the code under test by construction.
- **Downstream dependencies:** MAPS-002 (assumes the bundled profiles are collision-free and correct), MAPS-006 (assumes profile behavior is well-defined pre-switch).
- **Preconditions:** none.
- **Assumptions:** none.
- **Prioritization rationale:** real audit-trail/regression-protection gap, but moderate consequence in practice — `test_mapping.py`'s large example suite exercises `OPINIONATED_MAP_STUDIO`/`NANOKONTROL2` behavior directly (not framed as "the migration invariant," but still providing some independent behavioral protection against gross regressions).
- **Priority:** medium
- **Approval status:** candidate — **not yet put to the user for confirmation**; a CODE-OBSERVED finding subject to the same reconciliation-before-approval rule as any other candidate. Listed in Pending user reconciliation below.
- **Evidence status:** Example-tested, but circular — effectively equivalent to Known gap for the specific "matches history" claim, despite a passing test existing.
- **Claim type:** refinement/equivalence against a historical reference that itself no longer exists in the codebase to check against.
- **Evidence selection:** **known-value/golden test** — freeze the current, hand-confirmed opinionated map contents (both bundled profiles) as an explicit literal fixture independent of `build_opinionated_map`'s own code path, and assert the function's output equals that frozen fixture. This provides real going-forward regression protection, even though it cannot retroactively re-verify byte-identity to the actual pre-Phase-5 code. Supporting, non-blocking: a one-time git-history diff against the pre-Phase-5 commit, if the user wants the original historical claim itself checked rather than just going-forward stability pinned.
- **Residual gap:** the true historical claim ("matches what shipped before Phase 5") is not recoverable through the current codebase alone; only through git history, and only as a one-time check, not an ongoing one.
- **Gap type:** **Missing-evidence gap** — the implementation exists and behaves correctly; only the evidence is deficient. Routes to a golden-test specification, LID Phase 5, once approved — gated on the reconciliation stop below, not on any design decision.

## Candidate Disposition

Every candidate/open question `system-assurance-map.md` raises — across its Open Questions, High-consequence failure paths, Important state machines, External assumptions, and Known fragile areas tables — gets exactly one disposition row below: **registered** (cites the property ID), **merged** (cites the target property ID), **rejected** (rationale given), **deferred** (rationale + revisit trigger given), or **explicitly out of scope** (reason given). `system-assurance-map.md`'s Trust boundaries, Semantic chokepoints, and Externally visible outputs tables are structural context that fed candidate discovery, not candidates themselves — every concrete risk they surfaced is captured in the tables dispositioned below, so they don't get separate rows.

| Source item (`system-assurance-map.md`) | Disposition | Detail |
|---|---|---|
| Open Questions: Silent E-Stop loss | Registered | MAPS-001 |
| Open Questions: CC-collision validation gap | Registered | MAPS-002 |
| Open Questions: AXn ordering assumption | Registered | MAPS-003 |
| Open Questions: `MAP-CONFIG-003` migration-invariant test coverage | Registered | MAPS-007 |
| High-consequence failure paths: Silent E-Stop loss | Merged | Same item as the Open Questions row above → MAPS-001 |
| High-consequence failure paths: Colliding CC numbers | Merged | → MAPS-002 |
| High-consequence failure paths: `decode_osc_packet` malformed/adversarial bundle | Registered | MAPS-005 |
| High-consequence failure paths: Knob-nudge clamp arithmetic drift | Registered | MAPS-004 |
| High-consequence failure paths: `MAP-CONFIG-003` migration-invariant regression | Merged | → MAPS-007 |
| Important state machines: `MappingEngine` fader mode (axis ⇄ encoder) | Deferred | Already specified (`MAP-AXIS-*`) and unit-tested; no confirmed bug history unlike the knob-nudge path (MAPS-004); no distinct assurance gap identified beyond what MAPS-004/006's tests incidentally exercise. Revisit if a fader-mode-switch bug is ever reported. |
| Important state machines: Active Group (1–5) | Deferred | Already specified (`MAP-GROUP-*`) and unit-tested including the wrap case; Solo's Group-offset arithmetic is covered as a downstream dependency inside MAPS-003 (`correctness-assurance.md § 3.4`), but the Group state machine itself wasn't judged to need a standalone property. Revisit if Group-switching bugs are reported. |
| Important state machines: Controller Profile switch | Registered | MAPS-006 |
| Important state machines: WebSocket server connection (supersede) | Merged | Same trust gap as MAPS-001's peer-identity assumption — "no operator-visible signal distinguishing the real Dragonframe from an impostor connection" is one and the same concern. → MAPS-001 |
| External assumptions: AXn numbering matches OSC discovery order | Merged | Same item as the Open Questions row above → MAPS-003 |
| External assumptions: nanoKONTROL2 factory-default CC map | Deferred | Confirmed once against real hardware — a practical smoke check judged sufficient for now, not escalated to a registered property. Revisit if the physical device's firmware/config is suspected to have changed, or a control is reported behaving unexpectedly on that profile. |
| External assumptions: Dragonframe-traffic-as-liveness | Rejected | This is an accepted, explicit HLD design decision (`docs/high-level-design.md` Key Design Decisions), not a gap MAPS should try to independently verify — doing so would require building an independent Dragonframe test double, disproportionate to the risk (an operational/UX liveness signal, not the safety category MAPS-001 addresses). |
| External assumptions: `pynput` cross-platform key mapping | Deferred | Real gap, but requires platform-specific CI runners (macOS + Windows) not currently available. Revisit if a keystroke-delivery bug is reported on either platform. |
| External assumptions: Socket close from another thread interrupting `recvfrom()` | Explicitly out of scope | Already tested, found false, and fixed prior to this MAPS pass (bounded 0.5s `settimeout()` poll workaround) — not a live gap, no further MAPS action needed. |
| Known fragile areas: Knob-driven axis nudge scaling | Merged | Same item as the High-consequence failure paths row above → MAPS-004 |
| Known fragile areas: UI layout | Explicitly out of scope | Visual layout is not a correctness property MAPS addresses. |
| Known fragile areas: CI/lint configuration | Explicitly out of scope | Tooling, not system behavior. |

## Pending user reconciliation

| Property ID | Origin | Claim (short) | Why MAPS believes it might matter |
|---|---|---|---|
| MAPS-007 | CODE-OBSERVED | `MAP-CONFIG-003`'s existing test proves the migration invariant only tautologically (compares the function under test to itself); no independent regression protection exists for either bundled profile's opinionated map | A future refactor of `build_opinionated_map`/`_fader_entries`/etc. could silently change both bundled profiles' behavior with no test catching it, despite `test_mapping_config_schema.py` appearing to cover exactly this case |

## Rejected / withdrawn

| Property ID | Reason rejected/withdrawn | Date |
|---|---|---|
| — | none | — |
