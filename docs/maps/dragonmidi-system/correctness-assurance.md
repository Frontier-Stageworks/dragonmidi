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
- No formal proof exists anywhere in this system, and none is proposed — every property here fits property-based testing, fuzzing, or explicit-assumption treatment better than proof (see `docs/evidence-selection.md`'s rubric; none of the seven properties are universal semantic claims over a small, cleanly-specifiable domain the way formal proof requires).
- No differential testing exists or is proposed — there is no independent second implementation of the OSC/WebSocket protocols or the mapping engine to test against; Dragonframe itself is closed and unscriptable. (The same-process "fresh instance" oracle used by MAPS-006 is a differential-*style* check, not differential testing against an independent implementation — see § 3.2.)
- MAPS-001's end-to-end E-Stop-deliverability question has **no implementation to evidence at all** — it is a design gap, not a testing gap (see § 3.6).
- Fuzzing and property-based testing establish strong, sampled support, not exhaustive/universal proof — Section 3's Assurance Status column says "Fuzz-supported"/"Property-tested," deliberately not a status implying proof, for exactly this reason (see § 3.3, § 3.1).

# 2. System Model

Full system model lives in `docs/high-level-design.md` and `docs/llds/*.md` (LID artifacts) plus `system-assurance-map.md` (this MAPS pass's trust-boundary/chokepoint analysis) — not re-derived here. In brief: one desktop app, one MIDI-in → Mapping-Engine → {OSC, Keystroke, WebSocket} pipeline, driven by a swappable `ControllerProfile` (bundled or user-authored YAML), with a Preset Store persisting per-(Bank, Group) axis assignments. See `system-assurance-map.md §§ Trust boundaries, Semantic chokepoints` for the six trust boundaries and five chokepoints this argument is scoped around.

# 3. Correctness / Assurance Claims

## 3.1 Axis-nudge numeric correctness (MAPS-004)

**Precondition(s):** Bank N's fader has a real axis assigned in the active Group; engine in axis mode. For the in-bounds claim specifically, the initial authoritative position (live or estimated) is itself within the configured range; the out-of-range claim is precisely the complementary case.
**Canonical definition(s):** "in bounds" means the tracked position stays within `[min(min_value, max_value), max(min_value, max_value)]` inclusive, per `MAP-BANK-008`'s explicit tie-break rule for reversed min/max. A live position reading comes from Dragonframe, whose actual axis travel is independent of DragonMIDI's user-entered range — an out-of-range live reading is a realistic input (a too-narrow user-configured range), not a purely pathological one, and is treated as a distinct claim below.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| Given an in-bounds starting position, Knob N's derived `stepPosition` delta never carries the tracked axis position outside its configured range, across any delta sequence and any live/estimate interleaving | Boundedness | `test_mapping.py` (`test_knob_nudge_sequence_never_leaves_range_at_any_step`, `test_knob_nudge_from_out_of_range_start_never_sends_a_position_outside_range`, plus two example tests anchoring `81d1397`/`f63a84a`) | Example-tested + Property-tested, mutation-verified |
| Given an out-of-range starting position (a live reading outside the configured range), the resulting position — if a message is sent — is always within `[low, high]` | Boundedness | `test_mapping.py`, property-based (`MAP-BANK-010`) | Property-tested, mutation-verified |
| The live-reading-preferred-over-estimate rule (`MAP-BANK-009`) is applied correctly at the boundary between "reading available" and "no reading available" | Functional correctness | `test_mapping.py` | Example-tested |

**Coverage notes:** the two example tests anchor the specific scenarios of two prior production bugs (`81d1397`, `f63a84a`); the property tests cover the general delta/range/live-vs-estimate input space, including multi-step sequences (not just single nudges) and out-of-range starting positions. `test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position` is a companion to the existing `test_knob_clamp_bounds_are_order_independent`, covering an interior-point nudge that the original boundary-only test could not distinguish from a broken (unsorted-bounds) clamp formula.

**Accepted / Rejected — floating-point precision:**
- Accepted: ordinary IEEE-754 double rounding error in the position estimate; the code explicitly prefers computing the "no clamping needed" case via the exact delta rather than position-subtraction specifically to avoid *additional* float error (see code comment at `mapping.py:665-669`) — this is evidence the implementation already reasons about this, not evidence the reasoning is exhaustively verified.
- Rejected (out of scope): any claim about `pynput`/OS-level keystroke timing precision — unrelated numeric domain, not part of this claim.

## 3.2 Controller Profile isolation across a runtime switch (MAPS-006)

**Precondition(s):** two or more Controller Profiles loaded; user switches the active profile mid-session via the Status UI dropdown.
**Canonical definition(s):** "no state leak" means every `process()`/`process_websocket()`/`process_keystroke()` call across an entire post-switch event sequence under the new profile — not merely the first call — produces output identical, call-for-call, to what a freshly constructed `MappingEngine(new_profile)` fed only that same sequence would produce.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| `set_profile()` clears dedup/press/debounce/axis-position/Group-axis/encoder-mode state completely, with no delayed leakage across a multi-event post-switch sequence | Isolation | `test_mapping_profiles.py` (`test_set_profile_full_post_switch_trace_matches_a_fresh_engine`, plus first-call example tests) | Example-tested (first-call case) + Property-tested (full trace), mutation-verified |

**Coverage notes:** the property test drives a synthetic profile (`_COLLIDING_PROFILE`) that deliberately reuses Studio's Fader-1 CC (0) for a WebSocket-targeted "stop" role, through a pre-switch event sequence, then compares the entire output trace of a second post-switch sequence (`process()` and `process_websocket()`, every call) against a freshly constructed engine on the same profile.

**Accepted / Rejected — profile switch mid-input:**
- Accepted: a profile switch that occurs while a physical control is mid-gesture (e.g. fader partway through a slide) is not separately modeled — `reset()` clears dedup state unconditionally, so the next physical movement on either profile is always treated as a fresh baseline. This is existing, specified (`MAP-PROFILE-004`) behavior, not a gap this document is scoped to re-litigate.

## 3.3 OSC decoder robustness under malformed input (MAPS-005)

**Precondition(s):** any datagram arrives on DragonMIDI's OSC listen port, from any local process.
**Canonical definition(s):** "robust" means `decode_osc_packet` raises `BundleBoundsError` — a specific, documented failure — for a `#bundle` with a non-positive/overlong `element_size` or nesting beyond `MAX_BUNDLE_DEPTH` (8), rather than relying on Python's slicing semantics or its own interpreter recursion limit for safety. This is a robustness/contract claim, not a claim that a hang is being prevented: direct testing (a 3,000-level nested bundle; negative and zero `element_size` inputs) found the pre-guard code already safe against those specific inputs — a non-positive `element_size` always produces an empty Python slice, which always fails to decode immediately, and uncapped nesting safely raises `RecursionError`, already caught by the existing broad exception handler.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| `decode_osc_packet` explicitly rejects non-positive/inconsistent `element_size` and caps `#bundle` nesting depth at 8, replacing implicit/incidental safety with a documented contract | Error semantics | `dragonmidi/osc_io.py` (`BundleBoundsError`, `MAX_BUNDLE_DEPTH`) | Implemented, Example-tested |
| Six specific malformed-bundle shapes (negative/zero/oversized `element_size`, exact-boundary-still-valid, depth-cap-exact-still-valid, depth-cap-exceeded) each have a dedicated regression test | Error semantics | `test_osc_io.py`, 6 tests | Example-tested, mutation-verified |
| A guard rejection is logged at debug level; an ordinary (non-guard) decode failure is not | Operational (observability) | `test_osc_io.py`, 2 tests (`caplog`-based) | Example-tested |
| Beyond the guarded/anticipated shapes above, `decode_osc_packet` does not raise an unhandled/unexpected exception type under further randomized malformed byte input within a bounded per-example time budget | Error semantics (exploratory) | `test_osc_io.py`, 1 `hypothesis` test, structured malformed-bundle strategy, per-example deadline | Fuzz-supported |
| `handle_datagram`'s broad exception guard prevents a raised decode error from crashing the listener thread | Error semantics | `test_osc_io.py` (example-based) | Example-tested |

**Coverage notes:** the fuzz test uses `hypothesis`'s per-example deadline as its hang oracle rather than a subprocess/watchdog execution-isolation harness — sufficient for this claim's scope, since the guards themselves (not the fuzz layer) are the load-bearing evidence for the bound.

**Accepted / Rejected — threat model:**
- Accepted: the sender is assumed to be non-adversarial in the security sense (no attacker actively crafting packets to exploit DragonMIDI) — this remains a *robustness* claim (tolerate buggy/corrupted input) not a *security* claim (resist deliberate attack). `docs/evidence-selection.md`'s security-properties class, with its explicit-threat-model requirement, is deliberately not invoked here.
- Rejected: any claim that DragonMIDI validates the *sender's identity* before processing — the port has no authentication by design (`docs/high-level-design.md` Non-Goals), and this document does not propose changing that.

## 3.4 WebSocket-targeted controls: Group-offset arithmetic (part of MAPS-003's dependency chain)

**Precondition(s):** Solo N pressed while Group g is active; `key in ws_keys.solos`.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| Solo N sends `select-AX(N + 8·(g-1))`, matching `MAP-WS-002` exactly | Functional correctness | `test_mapping.py` (`MAP-GROUP-*`/`MAP-WS-002` cases, per `system-assurance-map.md`) | Example-tested |
| The resulting `AXn` number corresponds to the axis DragonMIDI itself intends, *given* MAPS-003's assumption holds | Compatibility (conditional) | N/A — depends entirely on MAPS-003 | **External assumption, Unverified** — see § 3.5. This row's assurance status is capped by MAPS-003's Verification state; internal arithmetic correctness does not imply external correctness. |

**Coverage notes:** this section exists specifically to make explicit that "the arithmetic is right" (well-tested) and "the arithmetic targets the axis the operator intended" (unverified assumption) are two different claims, easy to conflate. Section 3.5 formalizes the second.

## 3.5 External assumption: Dragonframe WebSocket AXn ordering (MAPS-003)

**Precondition(s):** none — this is an assumption, not a conditional claim.

**Status model:** this claim tracks two separate axes: **Type** (the permanent nature of the claim — never changes) and **Verification state** (the current confidence — changes when a manual check is actually performed, but never promotes the Type). A successful manual check does not graduate an external assumption to a tested property, because Dragonframe's internal behavior remains outside DragonMIDI's control.

| Claim | Property Type | Type | Verification state | Evidence |
|---|---|---|---|---|
| Dragonframe's internal `AXn` WebSocket numbering matches DragonMIDI's OSC-discovered axis order | Compatibility (external) | **External assumption** (permanent) | **Unverified** (would become "Manually verified against Dragonframe version `<X>`, `<date>`" once run — see `property-register.md` MAPS-003 for the procedure) | None — Dragonframe is closed and unscriptable from outside its own UI/log |

**Coverage notes:** this is not a gap awaiting future test coverage — it is structurally untestable by any automated method available to this project. The correct action is a documented manual verification, which moves the Verification-state column but never the Type column. A future Dragonframe version change would move Verification state back to Unverified-for-that-version; Type stays External assumption indefinitely.

## 3.6 WebSocket E-Stop transport readiness observability (MAPS-001)

**Precondition(s):** none — no implementation exists yet.
**Canonical definition(s):** the claim below is deliberately scoped to *transport* state (server bound + a live peer connection present), not to E-Stop's real-world deliverability to Dragonframe. `WS-CONN-004/005/006` accepts any local process passing the path check with no peer-identity verification, so bind+connection state proves *a* peer is present, not that the peer is Dragonframe — the two claims are stated separately below.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| The operator can distinguish "WebSocket transport appears ready" (bound + connected) from "not ready" (unbound, or bound with no connection), without physically testing it | Operational (state-machine visibility) | None | **Known gap** — no implementation exists yet; once a connection-state signal is added, a lifecycle test in the existing `WS-LIFECYCLE-*` style is sufficient evidence (small, enumerable state space) |
| **The connected peer is actually Dragonframe** (the assumption the row above's practical usefulness depends on) | Trust/identity (external) | None — structurally unestablishable by this adapter as built | **Assumption**, permanent — no evidence method in this codebase's current design applies; would require a handshake/acknowledgment protocol Dragonframe would also need to implement |
| End-to-end: the operator can determine whether pressing E-Stop will actually reach and be acted on by Dragonframe | Operational / safety | None — this is the union of the two rows above, and is only as strong as the weaker one | **Known gap**, capped by the peer-identity assumption above even after the transport-readiness row is fully evidenced |

**Coverage notes:** included in this document specifically so this document doesn't silently omit the highest-consequence property in the register merely because it isn't ready for evidence work. The three-row split above exists so that shipping the transport-readiness indicator (a genuinely achievable, testable near-term improvement) is never later cited as if it had closed the full E-Stop-deliverability question — it narrows the gap, it does not close it.

## 3.7 Controller Profile migration-invariant evidence (MAPS-007)

**Precondition(s):** none.
**Canonical definition(s):** "migration invariant" refers to `MAP-CONFIG-003`'s claim that `build_opinionated_map()` applied to the bundled profiles' `ControlsConfig` reproduces the pre-Phase-5 hardcoded map literals exactly.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| `build_opinionated_map(STUDIO_CONTROLS/NANOKONTROL2_CONTROLS, ...)` matches the historical pre-Phase-5 hardcoded literals | Refinement/equivalence | `test_mapping_config_schema.py:76,81` | **Circular** — the test's "reference" (`OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2`) is itself produced by the identical function call, not an independently-frozen historical value; effectively no regression protection despite the passing assertion |
| Going forward, `build_opinionated_map()`'s output for the two bundled profiles stays stable across future refactors | Refinement/equivalence (forward-looking, narrower than the historical claim) | None yet | **Evidence planned** — a known-value/golden test pinning the current literal output, independent of the function under test (see `property-register.md` MAPS-007) |

**Coverage notes:** this claim is still pending the reconciliation stop `property-register.md`'s Pending user reconciliation table records — no evidence work is scheduled until it clears that stop.

**Accepted / Rejected — historical vs. forward-looking claim:**
- Accepted: pinning current behavior going forward (a golden test) as adequate assurance for future changes, even though it cannot retroactively verify the original historical claim.
- Rejected (for now): re-deriving the true historical claim by diffing against the pre-Phase-5 git commit — offered as optional supporting work in `property-register.md`, not scheduled as required evidence, since `test_mapping.py`'s large example suite already provides some independent behavioral protection against gross regressions even without this specific check.

# 4. Structure of the Assurance Argument

| Evidence Layer | Catches | Does NOT Catch |
|---|---|---|
| Existing example-based unit tests (`test_mapping.py`, `test_osc_io.py`, etc.) | Regressions against specific known scenarios, including the two historical knob-nudge bugs | Input-space coverage outside the chosen examples; adversarial/malformed input the author didn't think to write an example for |
| Property-based tests, MAPS-004 (both sub-claims) and MAPS-006 | Boundary/edge cases across a randomized input space for the axis-clamp and profile-isolation invariants, including multi-step sequences and out-of-range starting positions | Correctness of the invariant *statement* itself if the EARS spec it's drawn from is wrong; still bounded by `hypothesis`'s generation strategy and example budget, not exhaustive |
| Explicit parser guards, MAPS-005 (`BundleBoundsError`, `MAX_BUNDLE_DEPTH`) | Non-positive/inconsistent `element_size`, over-cap bundle nesting — deterministic rejection, the primary evidence for the bound | Any malformed shape the guards don't anticipate — that's what the fuzzing layer below is for |
| Boundary regression tests, MAPS-005 | The specific malformed-bundle shapes this review identified, as named regression anchors | General malformed-input coverage — these are deterministic single cases, not exploratory |
| Fuzz test, MAPS-005 (`hypothesis`, per-example deadline) | Unhandled exceptions in `decode_osc_packet` under malformed byte input the guards above didn't anticipate | Semantic correctness of successfully-decoded messages; a stuck example beyond the per-example deadline in an execution model where the deadline check itself can't run |
| Manual operational verification (MAPS-003, once performed) | Whether the AXn-ordering assumption holds for one specific Dragonframe version/project at one point in time | Regression if a future Dragonframe version changes its internal numbering — this verification does not self-renew; Type stays External assumption regardless |
| Known-value/golden test (MAPS-007, once written) | Future regressions in the two bundled profiles' opinionated map contents | The original historical claim (matches the actual pre-Phase-5 literal) — only a one-time git-history diff could establish that, and it isn't scheduled |
| CI (`ruff` lint + existing test suite) | Syntax/style issues, existing-test regressions on every push | Any of the above gaps — CI green is not evidence for any claim in Section 3 that says "Evidence planned" or "Known gap" |

**Evidence independence note:** not applicable — no differential testing appears in this document (see Section 1). All evidence layers above are testing the same implementation from different angles, not two implementations against each other, so no shared-bug-risk analysis is needed.

# 5. Assumptions

## 5.1 External system behavior (Dragonframe)

- Dragonframe's WebSocket `AXn` numbering matches DragonMIDI's OSC-discovered axis order (MAPS-003) — Type: External assumption (permanent); Verification state: Unverified.
- The peer connected to DragonMIDI's WebSocket server is Dragonframe (MAPS-001) — Type: External/trust assumption (permanent, unestablishable by the adapter's current design); Verification state: not applicable — no verification method exists for this one, unlike MAPS-003's one-time manual check.
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

## 6.1 Safety-relevant gap with no current mitigation path

- MAPS-001 has no implementation and no evidence for either of its two component claims (transport readiness, peer identity). This is the single highest-consequence item in this document and it is currently a **Known gap**, full stop, for the end-to-end deliverability question. The narrower transport-readiness claim is a smaller, achievable near-term ask — but even fully evidenced, it does not close the end-to-end gap, because the peer-identity assumption underneath it is not establishable by this adapter's current design. Closing the full gap requires a design decision (a handshake/acknowledgment protocol Dragonframe would also need to implement, or accepting the risk formally with explicit sign-off) that is outside MAPS's authority. **This document should not be read as claiming E-Stop is safe, nor as claiming a future transport-readiness indicator would make it safe; neither is evidenced.**

## 6.2 Structurally untestable assumption

- MAPS-003's AXn-ordering assumption cannot be closed by any evidence method available to this project (no Dragonframe API, no reference implementation, no way to script Dragonframe's internal state). The best available mitigation is a one-time documented manual check, which itself has no regression protection against a future Dragonframe version changing behavior.

## 6.3 Deliberately deferred gap, tracked but not closed

- MAPS-002 (Controller Profile CC-collision detection) remains an accepted, documented design gap (`docs/llds/static-mapping.md`). This document tracks it per user request but does not propose closing it — doing so would reverse an existing LLD decision, which belongs in LID.

## 6.4 Evidence still pending

- MAPS-007's golden-test fix is specified but not yet approved for implementation — it is a new CODE-OBSERVED finding awaiting the reconciliation stop `property-register.md` records. Until then, `MAP-CONFIG-003`'s migration invariant has no real regression protection despite a passing (circular) test.

## 6.5 Out of scope for this MAPS pass entirely

- UI layout, CI/lint tooling, and the remainder of DragonMIDI's EARS specs not touched by MAPS-001 through MAPS-007 were deliberately not re-examined — `system-assurance-map.md` records a substantial existing example-based test suite as adequate-by-inspection for those areas, not independently re-verified property-by-property, and this document does not assert a specific coverage fraction for it (see § 1).

# 7. Trusted Base

- Python 3 interpreter and standard library (`socket`, `struct`, `threading`, `asyncio`, `json`), including IEEE-754 float semantics.
- Third-party libraries: `mido`+`python-rtmidi` (MIDI), `websockets` (WebSocket server), `PyYAML` (Controller Profile parsing), `pynput` (keystroke synthesis) — none independently audited by this project; all load-bearing for their respective output paths.
- The OS's UDP/TCP networking stack and MIDI driver layer (CoreMIDI on macOS, the Windows MIDI stack).
- `pytest`/`hypothesis` as the testing framework itself — a bug in the test framework could mask a real defect; not independently verified here.
- The physical KORG hardware's MIDI implementation matching its documented/community-confirmed CC behavior (already flagged in `system-assurance-map.md`'s External assumptions as confirmed-once-in-practice for the nanoKONTROL2, not byte-level verified against vendor documentation for either device).

# 8. Summary of Guarantees

- Knob-driven axis nudges are specified (`MAP-BANK-008`/`009`/`010`), example-tested, and property-tested with mutation verification, for both in-bounds starting positions (a full sequence invariant, not just single nudges) and out-of-range starting positions (the resulting position, if a message is sent, is always within range — no stronger claim about which bound it favors is made).
- Controller Profile switching is specified (`MAP-PROFILE-004`) to fully clear per-control engine state, example-tested for the first post-switch event, and property-tested with mutation verification across a full multi-event post-switch trace against a CC-colliding synthetic profile.
- Solo's Group-offset arithmetic (`MAP-WS-002`) is correctly implemented and tested internally — whether it targets the axis Dragonframe itself understands by that number is a permanent, structurally unverifiable external assumption (Type), currently Unverified (Verification state) pending a one-time manual check.
- The OSC decoder now explicitly rejects malformed bundle shapes it previously handled only via incidental Python behavior, and is Example-tested, Fuzz-supported, and mutation-verified against that claim. This is a robustness/contract improvement, not a fix for a hang this project ever reproduced.
- MAPS-001 is two claims, not one: "WebSocket transport appears ready" (bind+connection state — a Known gap, but achievable with a small implementation step) and "the connected peer is Dragonframe" (a permanent, unestablishable assumption given the adapter's current design). Neither is evidenced today, and even both together would not fully close the "operator can trust E-Stop will work" question.
- The `MAP-CONFIG-003` migration invariant's existing test is circular — it compares the function under test to itself, not to an independent historical reference — so despite a passing assertion, no real regression protection currently exists for either bundled profile's opinionated map; a golden-test fix is planned (MAPS-007), pending reconciliation.

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
