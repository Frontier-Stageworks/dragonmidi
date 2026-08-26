# DragonMIDI Correctness / Assurance Document

**Version:** covers the codebase at commit `a491310`-adjacent state (Phases 1–6 of `docs/high-level-design.md` all present in code).
**Scope:** Whole system — MIDI Input Adapter, Mapping Engine, OSC Client/Listener, Keystroke Output Adapter, WebSocket Output Adapter, Controller Profile loading, Preset Store.
**Repository:** `dragonmidi`
**Companion documents:** `property-register.md` (evidence-matrix fields merged in per small-task scaling), `assurance-case.md`

See `docs/correctness-document.md` for the full contract this template implements.

# 1. Purpose and Scope

This document states what can currently be claimed about DragonMIDI's correctness, and — just as importantly — what cannot. It does not claim the system is bug-free. It claims exactly what Section 3's evidence rows support, nothing more.

**What this covers:** the seven properties in `property-register.md` (MAPS-001 through MAPS-007), selected from a full-system Phase 1 assurance map as the highest-value candidates — not exhaustive coverage of every EARS spec in `docs/specs/`. `system-assurance-map.md`'s test inventory documents a substantial existing example-based unit-test suite across the codebase; this document does not re-litigate that suite's contents, and — absent an actual requirement-by-requirement traceability count — does not claim a specific fraction of DragonMIDI's EARS requirements it covers.

**What this explicitly does NOT claim:**
- No formal proof exists anywhere in this system, and none is proposed — every property here fits property-based testing, fuzzing, structural enforcement, or explicit-assumption treatment better than proof.
- No differential testing exists or is proposed — there is no independent second implementation of the OSC/WebSocket protocols or the mapping engine to test against; Dragonframe itself is closed and unscriptable. (The same-process "fresh instance" oracle used by MAPS-006 is a differential-*style* check, not differential testing against an independent implementation — see § 3.2. MAPS-007's existing test is explicitly *not* differential testing at all, despite structural resemblance — its "reference" is provably the same code path as what it checks, not an independent implementation; see § 3.7.)
- MAPS-001's peer-identity/end-to-end-delivery residual gap has **no implementation to evidence at all**, and structurally cannot be evidenced by this project unilaterally — it is a design-missing gap accepted as risk, not a testing gap (see § 3.6).
- Fuzzing and property-based testing establish strong, sampled support, not exhaustive/universal proof. Where a claim's evidence includes structural enforcement (MAPS-004, MAPS-005), that enforcement — paired with a boundary test verifying it — is the load-bearing basis, not the supporting fuzz/property layer.
- **Using more than one evidence method for a claim is not, by itself, a claim of independence.** MAPS-004 and MAPS-005 are each backed by multiple *complementary* layers (structural enforcement, example tests, property tests, mutation checks) — different failure-detection strengths applied to the same specification and the same production implementation. None of this document's Evidence State entries claims "multiple independent layers" for any property in this register; that stronger status is reserved for cases with an explicit, argued reduction in shared-bug risk (separate derivations, implementations, or authors), which none of these properties currently has. Mutation-testing a layer shows that layer discriminates; it does not make it independent of the others.

# 2. System Model

Full system model lives in `docs/high-level-design.md` and `docs/llds/*.md` (LID artifacts) plus `system-assurance-map.md` (this MAPS pass's trust-boundary/chokepoint analysis) — not re-derived here. In brief: one desktop app, one MIDI-in → Mapping-Engine → {OSC, Keystroke, WebSocket} pipeline, driven by a swappable `ControllerProfile` (bundled or user-authored YAML), with a Preset Store persisting per-(Bank, Group) axis assignments. See `system-assurance-map.md §§ Trust boundaries, Semantic chokepoints` for the six trust boundaries and five chokepoints this argument is scoped around.

# 3. Correctness / Assurance Claims

## 3.1 Axis-nudge numeric correctness (MAPS-004)

**Precondition(s):** Bank N's fader has a real axis assigned in the active Group; engine in axis mode.
**Canonical definition(s):** "in bounds" means the tracked position stays within `[min(min_value, max_value), max(min_value, max_value)]` inclusive, per `MAP-BANK-008`'s explicit tie-break rule for reversed min/max.
**Valid initial-state domain:** two sub-claims partition the full domain explicitly — (a) starts in-range: position ∈ `[low, high]`; (b) starts out-of-range: position ∉ `[low, high]`, a realistic input since a live Dragonframe reading is independent of DragonMIDI's user-entered range. No third case exists.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| (a) Given an in-bounds starting position, Knob N's derived `stepPosition` delta never carries the tracked axis position outside its configured range, across any delta sequence and any live/estimate interleaving | Boundedness | Structural enforcement (`clamped_position = max(low, min(high, ...))`) + `test_mapping.py` (2 example tests anchoring `81d1397`/`f63a84a`, 2 property tests: single-nudge and full multi-step sequence) | Example-tested; Property-tested; Supported by multiple complementary layers |
| (b) Given an out-of-range starting position (a live reading outside the configured range), the resulting position — if a message is sent — is always within `[low, high]` | Boundedness | Structural enforcement (same formula, applied unconditionally) + `test_mapping.py`, property-based (`MAP-BANK-010`) | Property-tested; Supported by multiple complementary layers |

**Property being asserted vs. evidence produced:** the claim's "never"/"always" wording is backed by structural enforcement (the clamp formula makes the invariant true by construction for every input, not merely for sampled ones), with property-based tests as the verification layer confirming the formula fires correctly at randomized boundaries — not sampled evidence alone standing in for a universal claim.

**On "complementary" vs. "independent":** the structural guard, the example tests, and the property tests here are complementary — they catch different failure shapes (an off-by-one at a literal boundary, a multi-step drift, an order-dependent bug) — but they are not independent evidence in the stricter sense: all of them derive from `MAP-BANK-008`/`009`/`010` and exercise the same `_process_bank_derived` implementation. A shared misunderstanding of the spec, or a bug in a helper all three paths call, could evade all of them simultaneously. This document does not claim otherwise.

**Coverage notes:** the two example tests anchor the specific scenarios of two prior production bugs. The property tests cover the general delta/range/live-vs-estimate input space, including multi-step sequences (not just single nudges) and the out-of-range-start sub-claim's own domain. `test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position` is a companion to the existing `test_knob_clamp_bounds_are_order_independent`, added this pass after inspection found the original test only exercised a boundary-landing nudge — which a broken (unsorted-bounds) clamp formula reproduces by coincidence — while an interior-point nudge distinguishes correct from broken behavior. **Vacuity/mutation check, actually performed and recorded:** the `max`/`min` clamp was removed, confirmed to make four tests fail, restored; `sorted()` on reversed min/max was dropped separately, confirmed to make the new interior-point test fail specifically (while the pre-existing boundary-only test kept passing), restored. Both runs re-confirmed the full suite green.

**Accepted / Rejected — floating-point precision:**
- Accepted: ordinary IEEE-754 double rounding error in the position estimate; the code explicitly prefers computing the "no clamping needed" case via the exact delta rather than position-subtraction specifically to avoid *additional* float error (see code comment at `mapping.py:665-669`) — this is evidence the implementation already reasons about this, not evidence the reasoning is exhaustively verified.
- Rejected (out of scope): any claim about `pynput`/OS-level keystroke timing precision — unrelated numeric domain, not part of this claim.

## 3.2 Controller Profile isolation across a runtime switch (MAPS-006)

**Precondition(s):** two or more Controller Profiles loaded; user switches the active profile mid-session via the Status UI dropdown.
**Canonical definition(s):** "no state leak" means every `process()`/`process_websocket()`/`process_keystroke()` call across an entire post-switch event sequence under the new profile — not merely the first call, and across all three output paths — produces output identical, call-for-call, to what a freshly constructed `MappingEngine(new_profile)` fed only that same sequence would produce (for `process()`/`process_websocket()`), or holds trivially by construction (for `process_keystroke()` — see below).
**Valid initial-state domain:** n/a in the boundedness sense — the "before" state (arbitrary prior-profile activity) is exactly what the property test's generator varies.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| `set_profile()` clears dedup/press/debounce/axis-position/Group-axis/encoder-mode state completely, with no delayed leakage across a multi-event post-switch sequence, for `process()` and `process_websocket()` | Isolation | `test_mapping_profiles.py` (first-call example tests; `test_set_profile_full_post_switch_trace_matches_a_fresh_engine`, full-trace property test) | Example-tested; Property-tested |
| The same claim, restricted to `process_keystroke()` | Isolation | `mapping.py`'s own documentation: `process_keystroke()` "allocates and consults no per-control state" | Discharged by structural argument |

**Coverage notes:** confirmed by direct inspection of the test code — the property test drives a synthetic profile (`_COLLIDING_PROFILE`) reusing Studio's Fader-1 CC for a different, WebSocket-targeted control role, through a pre-switch event sequence, then compares the entire output trace of a *second* generated post-switch sequence against a freshly constructed engine on the same profile, across both `process()` and `process_websocket()`. **`process_keystroke()` is not exercised by that property test, and does not need to be:** it is documented as stateless, so a state-isolation claim about it is discharged by that structural fact rather than by running a test — a distinct, legitimate form of evidence, not an unaddressed exclusion. Together, the property test and the structural argument cover the claim's full three-output-path scope. **Mutation check, actually performed (on the `process()`/`process_websocket()` portion):** `reset()`'s `_previous_value.clear()` call was removed, confirmed to make the test fail at the first post-switch event in the hypothesis-discovered falsifying example, restored; the full suite (146 tests across `test_mapping.py` + `test_mapping_profiles.py`) re-confirmed green.

**Accepted / Rejected — profile switch mid-input:**
- Accepted: a profile switch that occurs while a physical control is mid-gesture (e.g. fader partway through a slide) is not separately modeled — `reset()` clears dedup state unconditionally, so the next physical movement on either profile is always treated as a fresh baseline. This is existing, specified (`MAP-PROFILE-004`) behavior, not a gap this document is scoped to re-litigate.

## 3.3 OSC decoder robustness under malformed input (MAPS-005)

**Precondition(s):** any datagram arrives on DragonMIDI's OSC listen port, from any local process.
**Canonical definition(s):** "robust" means `decode_osc_packet` raises `BundleBoundsError` — a specific, documented failure — for a `#bundle` with a non-positive/overlong `element_size` or nesting beyond `MAX_BUNDLE_DEPTH` (8), rather than relying on Python's slicing semantics or its own interpreter recursion limit for safety. This is a robustness/contract claim, not a claim that a hang is being prevented: direct testing (a 3,000-level nested bundle; negative and zero `element_size` inputs) found the pre-guard code already safe against those specific inputs.
**Valid initial-state domain:** n/a — `decode_osc_packet` is a pure function of its input bytes.
**Origin note:** this claim is SPECIFIED — `OSC-DISCOVER-010/011/012` are explicit, implemented EARS requirements (`docs/specs/osc-io.md`), landed via a LID Phase 2/3 pass before implementation. It is not carried forward as CODE-OBSERVED or INFERRED; those labels applied only before the user's approval and the resulting spec IDs existed.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| `decode_osc_packet` explicitly rejects non-positive/inconsistent `element_size` and caps `#bundle` nesting depth at 8, replacing implicit/incidental safety with a documented contract | Error semantics | Structural enforcement (`BundleBoundsError`, `MAX_BUNDLE_DEPTH`) + 6 deterministic regression tests verifying each guard fires at its stated limit, including the two boundary-valid-not-rejected cases | Example-tested; Supported by multiple complementary layers |
| A guard rejection is logged at debug level; an ordinary (non-guard) decode failure is not | Operational (observability) | `test_osc_io.py`, 2 tests (`caplog`-based) | Example-tested |
| Beyond the guarded/anticipated shapes above, `decode_osc_packet` does not raise an unhandled/unexpected exception type under further randomized malformed byte input within a bounded per-example time budget | Error semantics (exploratory) | `test_osc_io.py`, 1 `hypothesis` structured-fuzz test, per-example deadline | Fuzz-supported |
| `handle_datagram`'s broad exception guard prevents a raised decode error from crashing the listener thread | Error semantics | `test_osc_io.py` (example-based) | Example-tested |

**Property being asserted vs. evidence produced:** the claim's "for any byte string" wording names the engineering target the guards satisfy for the specific malformed shapes identified — it is not a claim that the fuzz campaign alone exhaustively verified arbitrary input. The guards (structural enforcement), paired with the six deterministic boundary tests (verification), are the primary evidence for the bound; the fuzz test is supporting, exploratory evidence for shapes the guards weren't specifically written for, not the primary basis. The regression tests, fuzz test, and guards are complementary, not independent, layers — all target the same implementation.

**Coverage notes:** confirmed by direct inspection of `tests/test_osc_io.py` — the fuzz test generates `declared_size` across the full `int32` range, `nesting_depth` 0–12 (spanning both under and over the cap), and arbitrary binary payloads via a structured `#bundle`-framed strategy, not unstructured byte fuzzing alone. **Mutation check, actually performed:** both guards were removed (reverting to the pre-guard implementation), confirmed to make 5 of 7 new tests fail while the two accept-cases (exact-boundary, exact-depth) correctly kept passing — confirming the guards don't over-reject — restored, and the full `test_osc_io.py` suite re-confirmed green. One recorded scope note: the fuzz test's hang oracle is `hypothesis`'s per-example deadline rather than a subprocess/watchdog execution-isolation harness, judged sufficient given the underlying hang risk was itself found not to reproduce in direct testing.

**Accepted / Rejected — threat model:**
- Accepted: the sender is assumed to be non-adversarial in the security sense (no attacker actively crafting packets to exploit DragonMIDI) — this remains a *robustness* claim (tolerate buggy/corrupted input) not a *security* claim (resist deliberate attack).
- Rejected: any claim that DragonMIDI validates the *sender's identity* before processing — the port has no authentication by design (`docs/high-level-design.md` Non-Goals), and this document does not propose changing that.

## 3.4 WebSocket-targeted controls: Group-offset arithmetic (part of MAPS-003's dependency chain)

**Precondition(s):** Solo N pressed while Group g is active; `key in ws_keys.solos`.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| Solo N sends `select-AX(N + 8·(g-1))`, matching `MAP-WS-002` exactly | Functional correctness | `test_mapping.py` (`MAP-GROUP-*`/`MAP-WS-002` cases, per `system-assurance-map.md`) | Example-tested |
| The resulting `AXn` number corresponds to the axis DragonMIDI itself intends, *given* MAPS-003's assumption holds | Compatibility (conditional) | N/A — depends entirely on MAPS-003 | No evidence (capped by MAPS-003's Evidence state; internal arithmetic correctness does not imply external correctness) |

**Coverage notes:** this section exists specifically to make explicit that "the arithmetic is right" (well-tested) and "the arithmetic targets the axis the operator intended" (unverified external assumption) are two different claims, easy to conflate. Section 3.5 formalizes the second.

## 3.5 External assumption: Dragonframe WebSocket AXn ordering (MAPS-003)

**Precondition(s):** none — this is an assumption, not a conditional claim.
**Claim nature note:** this claim's nature is **External assumption**, permanently — not an Evidence state or a Disposition value. Its Evidence state and Freshness are the axes that actually move as verification work happens; the nature itself never changes, even after a successful manual check, because Dragonframe's internal behavior remains outside DragonMIDI's control.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| Dragonframe's internal `AXn` WebSocket numbering matches DragonMIDI's OSC-discovered axis order, for every discovered axis | Compatibility (external) | None — Dragonframe is closed and unscriptable from outside its own UI/log; only a manual operational verification procedure applies (`property-register.md` MAPS-003) | No evidence (would become "Manually verified (as of `<Dragonframe version>`, `<date>`)" once the procedure runs — Freshness would then read "current," moving to "stale — renewal needed" whenever Dragonframe's version changes) |

**Coverage notes:** this is not a gap awaiting future test coverage — it is structurally untestable by any automated method available to this project. The correct action is the documented manual verification, which moves Evidence state and Freshness, never Claim nature.

## 3.6 WebSocket E-Stop transport readiness and peer-identity/end-to-end delivery (MAPS-001)

**Precondition(s):** none — no implementation exists for either residual gap.
**Canonical definition(s):** this is **one property with two independent residual gaps**, not two properties — see `property-register.md` MAPS-001 for why splitting it would satisfy field cardinality rather than represent a genuinely separate claim. `WS-CONN-004/005/006` accepts any local process passing the path check with no peer-identity verification, so bind+connection state proves *a* peer is present, not that the peer is Dragonframe.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| The operator can distinguish "WebSocket transport appears ready" (bound + connected) from "not ready" (unbound, or bound with no connection), without physically testing it | Operational (state-machine visibility) | None | No evidence — Residual gap: transport-readiness signal doesn't exist (Type: Operational observability gap; Disposition: Resolve through LID/design) |
| The connected peer is actually Dragonframe, so that a specific E-Stop send reaches and is acted on by Dragonframe | Trust/identity (external) | None — structurally unestablishable by this adapter as built | No evidence — Residual gap: no peer-authentication mechanism exists (Type: Design missing; Disposition: Accept risk — no unilateral resolution path exists) |
| End-to-end (not a separately-evidenced claim — the conjunction of the two rows above): the operator can determine whether pressing E-Stop will actually reach and be acted on by Dragonframe | Operational / safety | None — the union of the two rows above, only as strong as the weaker one | No evidence, capped permanently by the peer-identity gap even once the transport-readiness gap is closed |

**Coverage notes:** included in this document specifically so it doesn't silently omit the highest-consequence property in the register merely because neither residual gap is ready for evidence work. The three-row split exists so that closing the transport-readiness gap (a genuinely achievable, testable near-term improvement) is never later cited as if it had closed the peer-identity gap too — it narrows one, it does not close the other, and the two have different causes: an observability gap that's resolvable through design work, versus a design-missing gap this project cannot unilaterally resolve.

## 3.7 Controller Profile migration-invariant evidence (MAPS-007)

**Precondition(s):** none.
**Canonical definition(s):** "migration invariant" refers to `MAP-CONFIG-003`'s claim that `build_opinionated_map()` applied to the bundled profiles' `ControlsConfig` reproduces the pre-Phase-5 hardcoded map literals exactly. **This property is Approved** — `MAP-CONFIG-003` is an existing, explicit SHALL requirement (`docs/specs/static-mapping.md`), not an unconfirmed candidate. What's open is the evidence for it, recorded below, not whether the requirement itself is wanted.

| Claim | Property Type | Evidence | Evidence State |
|---|---|---|---|
| `build_opinionated_map(STUDIO_CONTROLS/NANOKONTROL2_CONTROLS, ...)` matches the historical pre-Phase-5 hardcoded literals (`MAP-CONFIG-003`) | Refinement/equivalence | `test_mapping_config_schema.py:76,81` — but circular: the test's "reference" is provably the same code path as the value under test (same function, same arguments), not an independent implementation or a hand-authored value | Example-tested, but non-discriminating (circular) |

**Coverage notes:** this is not differential testing with a shared-bug risk to weigh — the "reference" and the "actual" value are the same value by construction, so there is no independence to assess at all. The planned golden-test fix avoids this specifically by using a hand-authored literal fixture with no code path connecting it to `build_opinionated_map`.

**Accepted / Rejected — historical vs. forward-looking claim:**
- Accepted: pinning current behavior going forward (a golden test) as adequate assurance for future changes, even though it cannot retroactively verify the original historical claim.
- Rejected (for now): re-deriving the true historical claim by diffing against the pre-Phase-5 git commit — offered as optional supporting work, not scheduled as required evidence.

# 4. Structure of the Assurance Argument

| Evidence Layer | Catches | Does NOT Catch |
|---|---|---|
| Existing example-based unit tests (`test_mapping.py`, `test_osc_io.py`, etc.) | Regressions against specific known scenarios, including the two historical knob-nudge bugs | Input-space coverage outside the chosen examples; adversarial/malformed input the author didn't think to write an example for |
| Structural enforcement (`clamped_position = max(low, min(high, ...))` in MAPS-004; `BundleBoundsError`/`MAX_BUNDLE_DEPTH` in MAPS-005) | Makes the relevant violation impossible by construction for every input, not merely reduces its likelihood | Whether the guard itself is correctly implemented — that's what the paired boundary tests below catch |
| Boundary tests verifying structural enforcement (MAPS-004, MAPS-005) | Off-by-one and similar errors in the guards themselves, at their stated limits | Anything the guard wasn't designed to bound in the first place |
| Property-based tests (MAPS-004, MAPS-006) | Boundary/edge cases across a randomized input space, including multi-step sequences and out-of-range starting positions | Correctness of the invariant *statement* itself if the EARS spec it's drawn from is wrong; still bounded by `hypothesis`'s generation strategy and example budget, not exhaustive |
| Fuzz test (MAPS-005, `hypothesis`, per-example deadline) | Unhandled exceptions in `decode_osc_packet` under malformed byte input the guards above didn't anticipate | Semantic correctness of successfully-decoded messages; a stuck example beyond the per-example deadline in an execution model where the deadline check itself can't run |
| Structural argument (MAPS-006, `process_keystroke()`) | Discharges the isolation claim for a code path that provably has no state to leak, without needing a test | Anything about a code path that *does* have state — this only applies where the "no state" premise is independently true |
| Manual operational verification (MAPS-003, once performed) | Whether the AXn-ordering assumption holds for one specific Dragonframe version/project at one point in time | Regression if a future Dragonframe version changes its internal numbering — this verification does not self-renew |
| Known-value/golden test (MAPS-007, planned) | Future regressions in the two bundled profiles' opinionated map contents, once built | The original historical claim (matches the actual pre-Phase-5 literal) — only a one-time git-history diff could establish that |
| CI (`ruff` lint + existing test suite) | Syntax/style issues, existing-test regressions on every push | Any of the above gaps — CI green is not an Evidence-state value on any axis |

**Evidence independence note:** not applicable — no differential testing appears in this document (see Section 1). All evidence layers above are testing the same implementation from different angles, not two implementations against each other, so no shared-bug-risk analysis is needed. (MAPS-007's existing test resembles differential testing structurally but is explicitly not — see § 3.7.) Where this document says a property is "Supported by multiple complementary layers," that phrase is deliberate — it is not a claim that those layers are independent in the shared-bug-risk sense; see § 1.

# 5. Assumptions

## 5.1 External system behavior (Dragonframe)

- Dragonframe's WebSocket `AXn` numbering matches DragonMIDI's OSC-discovered axis order (MAPS-003) — Claim nature: External assumption (permanent); Evidence state: No evidence; Freshness: n/a (would become current/stale once first manually verified).
- The peer connected to DragonMIDI's WebSocket server is Dragonframe (MAPS-001, peer-identity residual gap) — Claim nature: Property (about DragonMIDI's own trust boundary, though unilaterally unresolvable); Evidence state: No evidence; Gap disposition: Accept risk.
- Dragonframe treats any UDP traffic to its OSC Output port as evidence of DragonMIDI-side liveness (no heartbeat contract) — accepted per HLD design, not independently verifiable from DragonMIDI's side.
- Dragonframe is the only process that will ever connect to DragonMIDI's WebSocket server on the well-known port/path — explicitly *not* enforced (any local process passing the path check succeeds); accepted per HLD Non-Goals.

## 5.2 Local network/process trust

- The OSC listen port and WebSocket server port are reachable by any local process, not just Dragonframe. The OSC decoder's bounds (MAPS-005) are a robustness claim under this trust model, not a security claim.

## 5.3 Numerical

- Python `float` (IEEE-754 double) arithmetic behaves per IEEE-754 semantics; not independently verified — trusted base (Section 7).

## 5.4 Library/runtime

- `pynput` correctly maps `alt`/`shift`/`right`/`left` to the OS-level keys Dragonframe's Hot Keys preferences expect, on both target platforms (macOS, Windows) — assumed, not independently verified per-OS in this codebase's CI.
- `mido`/`python-rtmidi`, `websockets`, and `PyYAML` behave per their documented contracts — trusted base, not re-verified by this project.

# 6. Residual Risks and Model Gaps

## 6.1 Safety-relevant gap with no unilateral resolution path

- MAPS-001's peer-identity residual gap has no implementation and no evidence, and its Gap type (Design missing, requiring external cooperation) means no evidence method available to this project alone would close it. This is the single highest-consequence item in this document. MAPS-001's transport-readiness gap, even fully closed, does not close this one — they are independent residual gaps on the same property, with different causes. **This document should not be read as claiming E-Stop is safe, nor as claiming a future transport-readiness indicator would make it safe; neither residual gap is evidenced, and the peer-identity gap specifically is accepted as a permanent limitation, not a pending task.**

## 6.2 Structurally untestable assumption

- MAPS-003's AXn-ordering assumption cannot be closed by any evidence method available to this project (no Dragonframe API, no reference implementation, no way to script Dragonframe's internal state). The best available mitigation is a one-time documented manual check, which itself has no regression protection against a future Dragonframe version changing behavior.

## 6.3 Deliberately deferred gap, tracked but not closed

- MAPS-002(b) (general Controller Profile CC-collision detection) remains a Design-missing gap with a Defer disposition (`docs/llds/static-mapping.md`'s existing deferral). This document tracks it per user request but does not propose closing it — doing so would reverse an existing LLD decision, which belongs in LID.

## 6.4 Evidence pending for an already-approved requirement

- MAPS-007's golden-test fix is specified and approved — `MAP-CONFIG-003` is an existing SHALL requirement, not an unconfirmed candidate. Until the golden test is built, `MAP-CONFIG-003`'s migration invariant has no real regression protection despite a passing (circular) test. This is an ordinary Evidence-missing gap with a Produce-evidence disposition, not a reconciliation question.

## 6.5 Out of scope for this MAPS pass entirely

- UI layout, CI/lint tooling, and the remainder of DragonMIDI's EARS specs not touched by MAPS-001 through MAPS-007 were deliberately not re-examined — `system-assurance-map.md` records a substantial existing example-based test suite as adequate-by-inspection for those areas, not independently re-verified property-by-property, and this document does not assert a specific coverage fraction for it (see § 1).

# 7. Trusted Base

- Python 3 interpreter and standard library (`socket`, `struct`, `threading`, `asyncio`, `json`), including IEEE-754 float semantics.
- Third-party libraries: `mido`+`python-rtmidi` (MIDI), `websockets` (WebSocket server), `PyYAML` (Controller Profile parsing), `pynput` (keystroke synthesis) — none independently audited by this project; all load-bearing for their respective output paths.
- The OS's UDP/TCP networking stack and MIDI driver layer (CoreMIDI on macOS, the Windows MIDI stack).
- `pytest`/`hypothesis` as the testing framework itself — a bug in the test framework could mask a real defect; not independently verified here.
- The physical KORG hardware's MIDI implementation matching its documented/community-confirmed CC behavior (already flagged in `system-assurance-map.md`'s External assumptions as confirmed-once-in-practice for the nanoKONTROL2, not byte-level verified against vendor documentation for either device).

# 8. Summary of Guarantees

- Knob-driven axis nudges are specified (`MAP-BANK-008`/`009`/`010`), and evidenced by structural enforcement paired with complementary example-based and property-based verification, mutation-checked, for both in-bounds starting positions (a full sequence invariant) and out-of-range starting positions (the resulting position, if a message is sent, is always within range — no stronger claim about which bound it favors is made).
- Controller Profile switching is specified (`MAP-PROFILE-004`) to fully clear per-control engine state for `process()`/`process_websocket()` (example-based and property-based, mutation-checked, covering the full post-switch trace); `process_keystroke()`'s share of the same claim is discharged by the structural fact that it holds no per-control state, not by a test.
- Solo's Group-offset arithmetic (`MAP-WS-002`) is correctly implemented and tested internally — whether it targets the axis Dragonframe itself understands by that number is a permanent External assumption (MAPS-003) with no current evidence, pending a one-time manual check.
- The OSC decoder now explicitly rejects malformed bundle shapes it previously handled only via incidental Python behavior — a specified, implemented requirement (`OSC-DISCOVER-010/011/012`) evidenced by structural enforcement paired with complementary regression tests and fuzzing, mutation-checked. This is a robustness/contract improvement, not a fix for a hang this project ever reproduced.
- MAPS-001 carries two independent residual gaps, not one: "WebSocket transport appears ready" (an achievable, currently-unbuilt observability gap) and "the connected peer is Dragonframe" (a permanent, unilaterally-unresolvable design gap, accepted as risk). Neither is evidenced today, and closing the first does not close the second.
- The `MAP-CONFIG-003` migration invariant is an approved, existing requirement whose only existing test is circular — it compares the function under test to itself, not to an independent historical reference — so despite a passing assertion, no real regression protection currently exists for either bundled profile's opinionated map. A golden-test fix is specified and ready to build; nothing about whether `MAP-CONFIG-003` itself is wanted remains open.

# 9. Correctness Claim Taxonomy

| Property Type | Definition | Primary Sections |
|---|---|---|
| Boundedness | Resource/value stays within a bound regardless of input | 3.1, 3.3 |
| Isolation | State for one entity (profile) doesn't bleed into another | 3.2 |
| Functional correctness | Computes the specified value | 3.1, 3.4 |
| Compatibility | Correctly interoperates with an external system/protocol | 3.4, 3.5 |
| Error / failure semantics | Well-defined behavior under invalid input or partial failure | 3.3 |
| Operational | Correct behavior under real deployment/observability conditions | 3.6 |
| Trust / identity (external) | A claim about a counterparty's identity that the system cannot itself establish | 3.6 |
| Refinement / equivalence | An implementation matches a reference (historical literal or forward-pinned golden value) | 3.7 |
