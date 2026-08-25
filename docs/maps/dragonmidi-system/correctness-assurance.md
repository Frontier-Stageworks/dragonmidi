# DragonMIDI Correctness / Assurance Document

**Version:** 2026-08-25, covers the codebase at commit `a491310`-adjacent state (Phases 1–6 of `docs/high-level-design.md` all present in code)
**Scope:** Whole system — MIDI Input Adapter, Mapping Engine, OSC Client/Listener, Keystroke Output Adapter, WebSocket Output Adapter, Controller Profile loading, Preset Store.
**Repository:** `dragonmidi`
**Companion documents:** `property-register.md` (evidence-matrix fields merged in per small-task scaling), `assurance-case.md`

See `docs/correctness-document.md` for the full contract this template implements.

# 1. Purpose and Scope

This document states what can currently be claimed about DragonMIDI's correctness, and — just as importantly — what cannot. It does not claim the system is bug-free. It claims exactly what Section 3's evidence rows support, nothing more.

**What this covers:** the six properties in `property-register.md` (MAPS-001 through MAPS-006), selected from a full-system Phase 1 assurance map as the highest-value candidates — not exhaustive coverage of every EARS spec in `docs/specs/`. Most of DragonMIDI's ~460 EARS requirements have existing example-based test coverage (per `system-assurance-map.md`'s test inventory) that this document does not re-litigate; MAPS was engaged specifically to identify what *beyond* that existing example-based suite would materially increase confidence.

**What this explicitly does NOT claim:**
- No formal proof exists anywhere in this system, and none is proposed — every property here fits property-based testing, fuzzing, or explicit-assumption treatment better than proof (see `docs/evidence-selection.md`'s rubric; none of the six properties are universal semantic claims over a small, cleanly-specifiable domain the way formal proof requires).
- No differential testing exists or is proposed — there is no independent second implementation of the OSC/WebSocket protocols or the mapping engine to test against; Dragonframe itself is closed and unscriptable.
- As of this document's writing, **none of the property-based/fuzz evidence proposed in Section 3 has actually been written yet** — MAPS's role ends at specifying what evidence to produce and why (Phase 6 handoff); this document will overclaim until that work lands and this section is revisited (`docs/correctness-document.md § Maintenance`).
- MAPS-001 (E-Stop observability) has **no implementation to evidence at all** — it is a design gap, not a testing gap, and requires an LID-level decision before any evidence claim is possible.

# 2. System Model

Full system model lives in `docs/high-level-design.md` and `docs/llds/*.md` (LID artifacts) plus `system-assurance-map.md` (this MAPS pass's trust-boundary/chokepoint analysis) — not re-derived here. In brief: one desktop app, one MIDI-in → Mapping-Engine → {OSC, Keystroke, WebSocket} pipeline, driven by a swappable `ControllerProfile` (bundled or user-authored YAML), with a Preset Store persisting per-(Bank, Group) axis assignments. See `system-assurance-map.md §§ Trust boundaries, Semantic chokepoints` for the six trust boundaries and four chokepoints this argument is scoped around.

# 3. Correctness / Assurance Claims

## 3.1 Axis-nudge numeric correctness (MAPS-004)

**Precondition(s):** Bank N's fader has a real axis assigned in the active Group; engine in axis mode.
**Canonical definition(s):** "in bounds" means the tracked position stays within `[min(min_value, max_value), max(min_value, max_value)]` inclusive, per `MAP-BANK-008`'s explicit tie-break rule for reversed min/max.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| Knob N's derived `stepPosition` delta never carries the tracked axis position outside its configured range | Boundedness | `test_mapping.py` (example-based, specific scenarios) | Example-tested — **not yet Property-tested**; property-test evidence planned (MAPS-004), not yet written |
| The live-reading-preferred-over-estimate rule (`MAP-BANK-009`) is applied correctly at the boundary between "reading available" and "no reading available" | Functional correctness | `test_mapping.py` | Example-tested |

**Coverage notes:** existing example tests were written to a spec that itself is a direct response to two prior production bugs (`81d1397`, `f63a84a`) — they cover the specific cases that broke before, not the general delta/range/live-vs-estimate input space. Property-based testing is planned to close that gap (see `property-register.md` MAPS-004).

**Accepted / Rejected — floating-point precision:**
- Accepted: ordinary IEEE-754 double rounding error in the position estimate; the code explicitly prefers computing the "no clamping needed" case via the exact delta rather than position-subtraction specifically to avoid *additional* float error (see code comment at `mapping.py:665-669`) — this is evidence the implementation already reasons about this, not evidence the reasoning is exhaustively verified.
- Rejected (out of scope): any claim about `pynput`/OS-level keystroke timing precision — unrelated numeric domain, not part of this claim.

## 3.2 Controller Profile isolation across a runtime switch (MAPS-006)

**Precondition(s):** two or more Controller Profiles loaded; user switches the active profile mid-session via the Status UI dropdown.
**Canonical definition(s):** "no state leak" means: the first `process()`/`process_websocket()`/`process_keystroke()` call under the new profile produces output identical to what a *freshly constructed* `MappingEngine(new_profile)` would produce for the same input.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| `set_profile()` clears dedup/press/debounce/axis-position/Group-axis/encoder-mode state completely | Isolation | `test_mapping_profiles.py` (example-based) | Example-tested — property-test evidence planned (MAPS-006), not yet written |

**Coverage notes:** the existing tests were not confirmed during this pass to specifically exercise the "old and new profile reuse the same CC number for different roles" adversarial case, which is the one scenario where an incomplete clear would actually be observable (a clean-state clear and a CC-number-coincidence-masked leak look identical on non-colliding profiles). The planned property test targets exactly this case.

**Accepted / Rejected — profile switch mid-input:**
- Accepted: a profile switch that occurs while a physical control is mid-gesture (e.g. fader partway through a slide) is not separately modeled — `reset()` clears dedup state unconditionally, so the next physical movement on either profile is always treated as a fresh baseline. This is existing, specified (`MAP-PROFILE-004`) behavior, not a gap this document is scoped to re-litigate.

## 3.3 OSC decoder robustness under malformed input (MAPS-005)

**Precondition(s):** any datagram arrives on DragonMIDI's OSC listen port, from any local process.
**Canonical definition(s):** "robust" means: returns or raises within bounded wall-clock time and bounded stack depth — does not hang the listener thread, does not exhaust the process stack.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| `decode_osc_packet` terminates (returns or raises) within bounded time/depth for arbitrary byte input | Boundedness / error semantics | None yet | **Evidence planned** — fuzz harness not yet written (MAPS-005) |
| `handle_datagram`'s broad exception guard prevents a *raised* decode error from crashing the listener thread | Error semantics | `test_osc_io.py` (example-based, well-formed-and-a-few-malformed cases) | Example-tested for the raise case; does **not** cover the hang case, which raises nothing to catch |

**Coverage notes:** this is the one claim in this document currently backed by essentially no evidence — flagged as such deliberately rather than citing the existing exception-guard tests as if they covered the hang scenario, which they structurally cannot (a hang never reaches the `except` clause).

**Accepted / Rejected — threat model:**
- Accepted: the sender is assumed to be non-adversarial in the security sense (no attacker actively crafting packets to exploit DragonMIDI) — this remains a *robustness* claim (tolerate buggy/corrupted input) not a *security* claim (resist deliberate attack). `docs/evidence-selection.md`'s security-properties class, with its explicit-threat-model requirement, is deliberately not invoked here.
- Rejected: any claim that DragonMIDI validates the *sender's identity* before processing — the port has no authentication by design (`docs/high-level-design.md` Non-Goals), and this document does not propose changing that.

## 3.4 WebSocket-targeted controls: Group-offset arithmetic (part of MAPS-003's dependency chain)

**Precondition(s):** Solo N pressed while Group g is active; `key in ws_keys.solos`.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| Solo N sends `select-AX(N + 8·(g-1))`, matching `MAP-WS-002` exactly | Functional correctness | `test_mapping.py` (`MAP-GROUP-*`/`MAP-WS-002` cases, per `system-assurance-map.md`) | Example-tested |
| The resulting `AXn` number corresponds to the axis DragonMIDI itself intends, *given* MAPS-003's assumption holds | Compatibility (conditional) | N/A — depends entirely on MAPS-003 | **Assumption** — see 3.5. This row's assurance status is capped by MAPS-003's status; internal arithmetic correctness does not imply external correctness. |

**Coverage notes:** this section exists specifically to make explicit that "the arithmetic is right" (well-tested) and "the arithmetic targets the axis the operator intended" (unverified assumption) are two different claims, easy to conflate. Section 3.5 formalizes the second.

## 3.5 External assumption: Dragonframe WebSocket AXn ordering (MAPS-003)

**Precondition(s):** none — this is an assumption, not a conditional claim.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| Dragonframe's internal `AXn` WebSocket numbering matches DragonMIDI's OSC-discovered axis order | Compatibility (external) | None — Dragonframe is closed and unscriptable from outside its own UI/log | **Assumption** (terminal status — see `property-register.md` MAPS-003 for the recommended one-time manual verification procedure) |

**Coverage notes:** this is not a gap awaiting future test coverage — it is structurally untestable by any method available to this project. The correct terminal action is a documented manual verification, not a pending automation task. Its status is not expected to change to "tested" by future engineering work; only by someone actually performing and logging that manual check.

## 3.6 E-Stop delivery observability (MAPS-001)

**Precondition(s):** none — no implementation exists yet.

| Claim | Property Type | Evidence | Assurance Status |
|---|---|---|---|
| The operator can distinguish "E-Stop is currently deliverable" from "E-Stop is currently non-functional" without physically testing it | Operational / safety | None | **Known gap** — no design exists; this is not an evidence-collection task yet, it's a pending LID decision (see Section 6) |

**Coverage notes:** included in this document specifically so this document doesn't silently omit the highest-consequence property in the register merely because it isn't ready for evidence work. Omitting it would violate this document's own purpose (Section 1).

# 4. Structure of the Assurance Argument

| Evidence Layer | Catches | Does NOT Catch |
|---|---|---|
| Existing example-based unit tests (`test_mapping.py`, `test_osc_io.py`, etc.) | Regressions against specific known scenarios, including the two historical knob-nudge bugs | Input-space coverage outside the chosen examples; adversarial/malformed input the author didn't think to write an example for |
| Planned property-based tests (MAPS-004, MAPS-006, once written) | Boundary/edge cases across a randomized input space for the axis-clamp and profile-isolation invariants | Correctness of the invariant *statement* itself if the EARS spec it's drawn from is wrong; still bounded by `hypothesis`'s generation strategy and example budget, not exhaustive |
| Planned fuzz harness (MAPS-005, once written) | Hangs/crashes/unbounded recursion in `decode_osc_packet` under malformed byte input | Semantic correctness of successfully-decoded messages (a fuzz harness targeting termination doesn't check decoded values are meaningful) |
| Manual operational verification (MAPS-003, once performed) | Whether the AXn-ordering assumption holds for one specific Dragonframe version/project at one point in time | Regression if a future Dragonframe version changes its internal numbering — this verification does not self-renew |
| CI (`ruff` lint + existing test suite) | Syntax/style issues, existing-test regressions on every push | Any of the above gaps — CI green is not evidence for any claim in Section 3 that says "Evidence planned" or "Known gap" |

**Evidence independence note:** not applicable — no differential testing appears in this document (see Section 1, "What this explicitly does NOT claim"). All evidence layers above are testing the same implementation from different angles, not two implementations against each other, so no shared-bug-risk analysis is needed.

# 5. Assumptions

## 5.1 External system behavior (Dragonframe)

- Dragonframe's WebSocket `AXn` numbering matches DragonMIDI's OSC-discovered axis order (MAPS-003) — unverified, terminal assumption.
- Dragonframe treats any UDP traffic to its OSC Output port as evidence of DragonMIDI-side liveness (no heartbeat contract) — accepted per HLD design, not independently verifiable from DragonMIDI's side.
- Dragonframe is the only process that will ever connect to DragonMIDI's WebSocket server on the well-known port/path — explicitly *not* enforced (any local process passing the path check succeeds); accepted per HLD Non-Goals.

## 5.2 Local network/process trust

- The OSC listen port and WebSocket server port are reachable by any local process, not just Dragonframe. Historically treated as "trusted local peer" for the OSC decoder (see Section 3.3); this document narrows that to a robustness claim under review (MAPS-005), not a security claim.

## 5.3 Numerical

- Python `float` (IEEE-754 double) arithmetic behaves per IEEE-754 semantics; not independently verified — trusted base (Section 7).

## 5.4 Library/runtime

- `pynput` correctly maps `alt`/`shift`/`right`/`left` to the OS-level keys Dragonframe's Hot Keys preferences expect, on both target platforms (macOS, Windows) — assumed, not independently verified per-OS in this codebase's CI.
- `mido`/`python-rtmidi`, `websockets`, and `PyYAML` behave per their documented contracts — trusted base, not re-verified by this project.

# 6. Residual Risks and Model Gaps

## 6.1 Safety-relevant gap with no current mitigation path

- MAPS-001 (E-Stop observability) has no implementation and no evidence. This is the single highest-consequence item in this document and it is currently a **Known gap**, full stop. Closing it requires a design decision (does DragonMIDI add a third status indicator, fold the signal into an existing one, or accept the risk formally with explicit sign-off) that is outside MAPS's authority — it revises an HLD Non-Goal. **This document should not be read as claiming E-Stop is safe; it explicitly is not evidenced either way.**

## 6.2 Structurally untestable assumption

- MAPS-003's AXn-ordering assumption cannot be closed by any evidence method available to this project (no Dragonframe API, no reference implementation, no way to script Dragonframe's internal state). The best available mitigation is a one-time documented manual check, which itself has no regression protection against a future Dragonframe version changing behavior.

## 6.3 Deliberately deferred gap, tracked but not closed

- MAPS-002 (Controller Profile CC-collision detection) remains an accepted, documented design gap (`docs/llds/static-mapping.md`). This document tracks it per user request but does not propose closing it — doing so would reverse an existing LLD decision, which belongs in LID.

## 6.4 Evidence-not-yet-produced gap (temporary, by construction)

- MAPS-004, MAPS-005, MAPS-006 all currently rest on example-based test coverage only; the property-based/fuzz evidence this document cites as "planned" does not exist yet. Until it is written, this document's claims for those three properties should be read as "specified and example-tested," not "property-verified."

## 6.5 Out of scope for this MAPS pass entirely

- UI layout, CI/lint tooling, and the ~450+ other EARS specs not touched by MAPS-001 through MAPS-006 were deliberately not re-examined — `system-assurance-map.md` records the existing example-based suite as adequate-by-inspection for those areas, not independently re-verified property-by-property.

# 7. Trusted Base

- Python 3 interpreter and standard library (`socket`, `struct`, `threading`, `asyncio`, `json`), including IEEE-754 float semantics.
- Third-party libraries: `mido`+`python-rtmidi` (MIDI), `websockets` (WebSocket server), `PyYAML` (Controller Profile parsing), `pynput` (keystroke synthesis) — none independently audited by this project; all load-bearing for their respective output paths.
- The OS's UDP/TCP networking stack and MIDI driver layer (CoreMIDI on macOS, the Windows MIDI stack).
- `pytest`/`hypothesis` (once the planned property tests land) as the testing framework itself — a bug in the test framework could mask a real defect; not independently verified here.
- The physical KORG hardware's MIDI implementation matching its documented/community-confirmed CC behavior (already flagged in `system-assurance-map.md`'s External assumptions as confirmed-once-in-practice for the nanoKONTROL2, not byte-level verified against vendor documentation for either device).

# 8. Summary of Guarantees

- Knob-driven axis nudges are specified (`MAP-BANK-008`/`009`) and example-tested against the two specific historical failure modes that previously escaped to production; broader input-space coverage is planned, not yet in place.
- Controller Profile switching is specified (`MAP-PROFILE-004`) to fully clear per-control engine state, and example-tested; the specific CC-reuse-across-profiles adversarial case is not yet confirmed covered.
- Solo's Group-offset arithmetic (`MAP-WS-002`) is correctly implemented and tested *internally* — whether it targets the axis Dragonframe itself understands by that number is an open, structurally unverifiable assumption, not a tested guarantee.
- The OSC decoder's behavior under malformed/adversarial input is **not yet evidenced** in either direction; this is an open item with a specific, agreed evidence plan (fuzzing), not a claim of safety.
- E-Stop's silent-failure behavior is **not yet observable to the operator**, and no guarantee exists that the operator can tell a working E-Stop path from a broken one before needing it.

# 9. Correctness Claim Taxonomy

| Property Type | Definition | Primary Sections |
|---|---|---|
| Boundedness | Resource/value stays within a bound regardless of input | 3.1, 3.3 |
| Isolation | State for one entity (profile) doesn't bleed into another | 3.2 |
| Functional correctness | Computes the specified value | 3.1, 3.4 |
| Compatibility | Correctly interoperates with an external system/protocol | 3.4, 3.5 |
| Error / failure semantics | Well-defined behavior under invalid input or partial failure | 3.3 |
| Operational | Correct behavior under real deployment/observability conditions | 3.6 |
