# Evidence Handoff

Phase 7 artifact for every evidence method other than formal proof — no property in this register calls for formal proof, so there is no LAPS handoff. Records the concrete next action per **approved** property whose evidence still needs to be produced. MAPS does not implement any entry itself — no test file, no fuzz harness, no code fix, no mutation/reintroduction check — that work belongs to LID (`docs/integrations/lid.md § MAPS → LID handoff`) for this LID-governed project.

**Not every property needs an entry here.** MAPS-004, MAPS-005, and MAPS-006 have realized, mutation-verified evidence already — see `property-register.md` and `correctness-assurance.md §§ 3.1–3.3` for the record; there is nothing left to hand off, and listing them here would misrepresent completed work as pending.

**MAPS-001 is one property with two independent residual gaps** — each gets its own block below (a design-decision handoff for the achievable transport-readiness gap, and a no-action-scheduled entry for the permanently-accepted peer-identity gap), per `SKILL.md § The property state model`'s rule that a property's Residual gaps is a collection, not a reason to fork the property into two IDs.

**MAPS-007 is Approved, not a Candidate** — `MAP-CONFIG-003` is an existing SHALL requirement (`docs/specs/static-mapping.md`), and this property's earlier CODE-OBSERVED classification was a misclassification (a finding about evidence quality mistakenly applied to Origin, corrected in `property-register.md`). It gets a real golden-test specification below, same as any other approved Evidence-missing gap.

## Gap disposition routing (fill in before choosing a block below)

| Property / gap | Gap disposition | Block used below |
|---|---|---|
| MAPS-001, transport-readiness gap | Resolve through LID/design | Design-decision handoff |
| MAPS-001, peer-identity gap | Accept risk | No action scheduled |
| MAPS-002 (sub-claim b, general CC-collision) | Defer | No action scheduled |
| MAPS-003 | Manual/operational verification | Manual verification procedure |
| MAPS-007 | Produce evidence | Known-value/golden test specification |

## Known-value / golden-test specification

### MAPS-007 — Golden-test specification: Controller Profile migration invariant

**Target:** `mapping.py::build_opinionated_map`, called with `STUDIO_CONTROLS`/`NANOKONTROL2_CONTROLS`.

**Gap type:** Evidence missing — the implementation is believed correct (hand-confirmed at the Phase 5 migration commit); the existing test doesn't actually check it, since its "reference" is the same code path as the value under test.

**Approach:** known-value/golden test, not property-based or fuzz — the claim (`MAP-CONFIG-003`) is "matches one specific frozen value," which is exactly what a golden test is for. **Independence requirement, not optional:** the fixture must be a literal, hand-authored Python dict written directly into the test file — not derived by calling `build_opinionated_map`, and not referencing `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` (both of which are themselves produced by the function under test). Reintroducing either of those would recreate the exact circularity this handoff exists to fix.

**Concrete steps:**
1. Capture the current, hand-confirmed output of `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` and `build_opinionated_map(NANOKONTROL2_CONTROLS, has_scene_button=False)` as literal Python dict fixtures.
2. Assert `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True) == <frozen fixture>` and the nanoKONTROL2 equivalent.
3. Optional, non-blocking supporting step: `git show <pre-Phase-5-commit>:dragonmidi/mapping.py` (or equivalent) to diff the actual historical hardcoded literal against today's frozen fixture, closing the retroactive historical-match question rather than only the going-forward one.

**Mutation/reintroduction requirement:** once built, deliberately change one entry in `_fader_entries()`/`_knob_entries()`/`_mute_entries()`/`_transport_entries()` (e.g. shift one CC's target address) and confirm the golden test fails; revert and confirm it passes again. This is required specifically because the property this test replaces was found non-discriminating — the whole point of this handoff is a test that actually catches a regression, and that claim itself needs verifying, not assuming.

**LID entry point:** Phase 5 (tests-first) — `MAP-CONFIG-003` already exists as an EARS requirement; no LLD/EARS change needed first.

## Design-decision handoff

### MAPS-001 (transport-readiness gap) — Design-decision handoff

**Owner:** the user, typically via a LID pass on `docs/high-level-design.md`.

**Gap type:** Operational observability gap.

**Question to resolve:** does DragonMIDI add a third Status UI indicator ("Command channel" or similar) reflecting the WebSocket adapter's bind+connection state, or fold this signal into the existing "Dragonframe signal" indicator (risk: conflates two different channels' health)? This extends the existing `WS-LIFECYCLE-002` bind-observability pattern to also expose ongoing connection state, without claiming anything about the separate peer-identity residual gap.

**Once a design exists:** the evidence method is a lifecycle/integration test over the small enumerable state space (unbound / bound-no-connection / bound-with-connection), matching the existing `WS-LIFECYCLE-*` test style. No property-based testing or formal proof needed — LID Phase 5 directly, framed as new intent (Phase 2/3 first) since the indicator itself is new behavior.

**Not MAPS's call to make:** which design option is right is a product decision, not an assurance-evidence decision.

## No action scheduled

### MAPS-001 (peer-identity gap) — No action scheduled

**Gap type:** Design missing — no peer-authentication mechanism exists, and none is unilaterally buildable by this project.
**Gap disposition:** Accept risk.
**Owner / sign-off:** the user, tracked as a known, permanent limitation.
**Revisit trigger:** none currently identified — this is not expected to become actionable without Dragonframe-side protocol cooperation, which is outside this project's control to schedule.

Closing MAPS-001's other residual gap (the transport-readiness indicator above), even fully built, must never be read as having made progress on this one — the two gaps are independent, with different causes (`correctness-assurance.md § 3.6`).

### MAPS-002 (sub-claim b) — No action scheduled

**Gap type:** Design missing — the cross-field CC-uniqueness check has no design or implementation.
**Gap disposition:** Defer.
**Revisit trigger:** contributor base for third-party Controller Profiles growing past "a handful of trusted people."

Deliberately deferred per `docs/llds/static-mapping.md`'s existing decision. No evidence work is scheduled. If the deferral is revisited, the evidence method is already specified in `property-register.md` MAPS-002 (property-based CC-collision generator, `detect_cc_collisions()` against a set-cardinality oracle) and can be handed off at that time without redoing the analysis.

## Manual / non-automatable verification procedure

### MAPS-003 — Manual verification procedure (not automatable)

**Owner:** the user (or whoever has hands-on access to a running Dragonframe instance) — MAPS cannot execute this.

**Procedure:**
1. Load a real Dragonframe project with at least 3 axes configured, in an order that is **not** alphabetical and **not** the order the axes were originally created (to rule out coincidental agreement).
2. Launch DragonMIDI, let axis discovery complete (`getAllPosition` round-trip).
3. In the Mapping View, note the discovered axis order.
4. For each discovered axis in turn, trigger the corresponding Solo control (or Cycle, stepping through) and confirm via Dragonframe's debug log (the same `HARD STOP`-style confirmation precedent used for E-Stop, per `docs/high-level-design.md` Success Metrics) which axis actually highlighted.
5. Record the result (pass/fail per axis) in `docs/testing-strategy.md` or equivalent, dated, with the Dragonframe version used.

**Recording:** the dated, version-scoped record above becomes this property's Freshness anchor — Evidence state moves to "Manually verified (as of `<version>`, `<date>`)" and Freshness to "current" once logged.

**Does not self-renew:** a future Dragonframe version change moves Freshness to "stale — renewal needed," not silently "current" — the check must be re-run against the new version, not assumed to still hold.

**If it fails:** this becomes a live bug (AXn numbering diverges from OSC discovery order for some axis ordering), not just a documentation update — route back through LID for a fix design (e.g. an explicit remapping table) rather than treating it as a MAPS artifact update.
