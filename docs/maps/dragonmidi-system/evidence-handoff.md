# Evidence Handoff

Phase 7 artifact. Concrete next action per approved property. No property in this register calls for formal proof, so there is no LAPS handoff — see `docs/workflow.md § Phase 7` for why: none of the seven are universal semantic claims over a small, cleanly-specifiable domain; property-based testing, fuzzing, and explicit-assumption/manual-verification fit better (rationale in each property's Evidence selection, `property-register.md`).

MAPS does not implement evidence itself — no test file, no fuzz harness, no code fix. Each entry below is either a completed record (target, what was implemented, where the tests live) for a property whose evidence has landed, or a specification handed to **LID** (`linked-intent-dev`) for a property still pending, the same way a `laps-handoff.md` entry hands a proof obligation to LAPS. Every pending entry states its **Gap type** (`checklists/argument-validation.md § 9` taxonomy, matching `property-register.md`'s Gap type field) and **LID entry point**:
- **Missing-evidence gap → LID Phase 5 (tests-first).** Implementation and spec both already exist; only the evidence is thin.
- **Spec ambiguity → LID Phase 2/3 (LLD/EARS update), then Phase 5.** The code has behavior, but no spec confirms it's intended.
- **Design gap → LID Phase 2/3 (LLD/EARS update) as a design-decision handoff, or no test/fuzz/proof spec at all.** Neither the design nor the implementation exists yet.
- **External-assumption verification gap → a manual/operational procedure**, not a LID phase at all.
- **Accepted risk → no action scheduled**, explicit owner and revisit trigger recorded instead.

## MAPS-004 — Knob-nudge clamp bound (complete)

**Target:** `MappingEngine._process_bank_derived`'s knob-nudge path (`mapping.py:636-676`), via `MappingEngine.process()`.

**Implemented:** two property-test groups in `tests/test_mapping.py`, both mutation-verified.
- **In-bounds start** (`test_knob_nudge_sequence_never_leaves_range_at_any_step`, plus a single-nudge property test): randomized `[min, max]` ranges (including reversed), randomized delta sequences, randomized live/estimate interleaving. Asserts the tracked position stays within range after every step, not just the last.
- **Out-of-range start** (`test_knob_nudge_from_out_of_range_start_never_sends_a_position_outside_range`, plus concrete witness tests): the initial live/estimated position is generated outside `[min, max]`. Asserts the resulting position, if a message is sent, is always within range — `MAP-BANK-010`.

No code change was needed for the out-of-range case: `MappingEngine._process_bank_derived`'s existing clamp formula already produces an in-range result unconditionally.

`MAP-BANK-010` was added to `docs/specs/static-mapping.md` and `docs/llds/static-mapping.md` (LID Phase 2/3) before the property test was written (LID Phase 5), since the out-of-range behavior had not previously been confirmed as intended.

## MAPS-006 — Controller Profile switch isolation (complete)

**Target:** `MappingEngine.set_profile` (`mapping.py:394-409`).

**Implemented:** `test_set_profile_full_post_switch_trace_matches_a_fresh_engine` in `tests/test_mapping_profiles.py`, mutation-verified. Drives a synthetic profile (`_COLLIDING_PROFILE`) that reuses Studio's Fader-1 CC for a different control role, through a pre-switch event sequence, then compares the entire output trace of a second post-switch event sequence — every `process()`/`process_websocket()` call, in order — against a freshly constructed `MappingEngine(profile_B)` fed the same sequence.

No LLD/EARS change was needed — `MAP-PROFILE-004` already specifies full state-clear completeness; only the evidence was thin (LID Phase 5 directly).

## MAPS-005 — `decode_osc_packet` robustness (complete)

**Target:** `osc_io.py::decode_osc_packet`.

**Implemented:** `BundleBoundsError` and `MAX_BUNDLE_DEPTH = 8` in `dragonmidi/osc_io.py`, enforced inside `decode_osc_packet` itself. Six deterministic regression tests, two `caplog`-based logging tests, and one `hypothesis` structured-fuzz test in `tests/test_osc_io.py`, all mutation-verified where applicable.

Routed through LID Phase 2/3 first (`docs/llds/osc-io.md`, `docs/specs/osc-io.md` — `OSC-DISCOVER-010/011/012` — including one user decision on debug-level logging on rejection), since the guards were new behavior the code had not previously specified, then Phase 5 (tests, confirmed failing before the guards existed) then Phase 6 (code).

## MAPS-003 — Manual verification procedure (not automatable)

**Gap type / entry point:** **External-assumption verification gap** — not a LID phase at all. Dragonframe is outside this project's control and can't be automated against.

**Owner:** the user (or whoever has hands-on access to a running Dragonframe instance) — MAPS cannot execute this.

**Procedure:**
1. Load a real Dragonframe project with at least 3 axes configured, in an order that is **not** alphabetical and **not** the order the axes were originally created (to rule out coincidental agreement).
2. Launch DragonMIDI, let axis discovery complete (`getAllPosition` round-trip).
3. In the Mapping View, note the discovered axis order.
4. For each discovered axis in turn, trigger the corresponding Solo control (or Cycle, stepping through) and confirm via Dragonframe's debug log (the same `HARD STOP`-style confirmation precedent used for E-Stop, per `docs/high-level-design.md` Success Metrics) which axis actually highlighted.
5. Record the result (pass/fail per axis) in `docs/testing-strategy.md` or equivalent, dated, with the Dragonframe version used — this verification does not self-renew across Dragonframe version changes, so the record should say what version it covers.

**If it fails:** this becomes a live bug (AXn numbering diverges from OSC discovery order for some axis ordering), not just a documentation update — route back through LID for a fix design (e.g. an explicit remapping table) rather than treating it as a MAPS artifact update.

## MAPS-001 — Two-part handoff: transport-readiness + peer-identity

**Gap type / entry point:** **Design gap, both parts → LID Phase 2/3 (design-decision handoff), not a test spec for either.** Neither the transport-readiness indicator nor a peer-identity solution exists or has a ratified design.

**Part A — transport-readiness signal (owner: the user, small implementation + LID nod):**

**Question to resolve:** does DragonMIDI add a third Status UI indicator ("Command channel" or similar) reflecting the WebSocket adapter's bind+connection state, or fold this signal into the existing "Dragonframe signal" indicator (risk: conflates two different channels' health)? This extends the existing `WS-LIFECYCLE-002` bind-observability pattern to also expose ongoing connection state, without claiming anything about E-Stop's real-world efficacy.

**Once that design exists:** the evidence method is straightforward — a lifecycle/integration test over the small enumerable state space (unbound / bound-no-connection / bound-with-connection), matching the existing `WS-LIFECYCLE-*` test style. No property-based testing or formal proof needed.

**Part B — peer-identity assumption (owner: the user; no clean evidence method exists within this codebase's current design):**

**The core limitation:** `WS-CONN-002/003` checks only the connection *path*, not the connecting peer's identity — any local process that connects to `ws://localhost:59177/com.dzed.dragonframe/DragonframeConnection` is accepted and treated as if it were Dragonframe (`WS-CONN-004/005/006`'s supersede logic). Closing this would require Dragonframe itself to participate in some identifying handshake or acknowledgment — outside DragonMIDI's control to implement unilaterally.

**Recommendation:** do not badge Part A's indicator as proof of Part B — document explicitly (in the HLD or the correctness document) that "transport appears ready" is the ceiling of what DragonMIDI can currently claim about E-Stop's availability, and that true end-to-end deliverability remains an accepted, permanent assumption unless a future collaboration with Dragonframe's maintainers changes what's technically possible.

**Not MAPS's call to make:** whether Part A is worth building, and how (or whether) Part B's residual risk gets formally accepted, are product/safety decisions.

## MAPS-002 — No action scheduled (tracked, not handed off)

**Gap type / entry point:** **Accepted risk** — no LID phase entered. Owner: the user. Revisit trigger: contributor base for third-party profiles growing past "a handful of trusted people" (`property-register.md` MAPS-002).

Deliberately deferred per `docs/llds/static-mapping.md`'s existing decision. No evidence work is scheduled. If the user later decides to revisit the deferral, the evidence method is already specified in `property-register.md` (property-based CC-collision generator).

## MAPS-007 — Golden-test specification: Controller Profile migration invariant (awaiting confirmation)

**Gap type / entry point:** **Missing-evidence gap → LID Phase 5** (tests-first), once approved. `build_opinionated_map` already exists and behaves correctly; only the evidence is deficient (circular). No LLD/EARS change needed.

**Not yet approved** — a CODE-OBSERVED finding not yet put to the user for the required reconciliation stop. Specified now so it's ready the moment it's confirmed.

**Target:** `mapping.py::build_opinionated_map`, called with `STUDIO_CONTROLS`/`NANOKONTROL2_CONTROLS`.

**Approach:** known-value/golden test, not property-based or fuzz — the claim is "matches one specific frozen value," which is exactly what a golden test is for.

**Concrete steps:**
1. Capture the current, hand-confirmed output of `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` and `build_opinionated_map(NANOKONTROL2_CONTROLS, has_scene_button=False)` as literal Python dict fixtures, written directly into the test file (not derived by calling the function under test or referencing `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2`, which would reintroduce the same circularity this finding is about).
2. Assert `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True) == <frozen fixture>` and the nanoKONTROL2 equivalent.
3. Optional, non-blocking supporting step: `git show <pre-Phase-5-commit>:dragonmidi/mapping.py` (or equivalent) to diff the actual historical hardcoded literal against today's frozen fixture, to close the retroactive historical-match question rather than only the going-forward one.
