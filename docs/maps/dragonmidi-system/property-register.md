# Property Register

Phase 2/3/4 artifact. Merged with evidence-matrix fields per `docs/workflow.md § Artifact scaling for small tasks` — seven properties, one segment, doesn't warrant a separate `evidence-matrix.md` file.

**Six independent axes, never collapsed.** Origin, Claim nature, Disposition, Evidence state (a *set*), Residual gaps (a *collection* — zero or more, each independently typed and dispositioned), and Freshness are tracked separately per `SKILL.md § The property state model`. "Assumption" never appears as a Disposition or Evidence-state value — it is a Claim nature. **Origin is never changed by a finding about evidence quality** — a SPECIFIED property whose existing test turns out circular or non-discriminating stays SPECIFIED; that finding is a Residual-gap entry (Gap type: Evidence missing), not an Origin downgrade. **A property is never split or merged merely to give a gap its own field** — Residual gaps being a collection is precisely what avoids that pressure; a property is split only when its sub-claims are genuinely separate assurance questions.

Built from `system-assurance-map.md`'s chokepoints and failure paths.

## Register

### MAPS-001: WebSocket E-Stop transport readiness observability

- **Behavioral segment:** WebSocket Output Adapter (`websocket_output.py`), Status UI
- **Claim:** The operator has some way to determine, without physically pressing Stop, whether DragonMIDI's WebSocket server is currently bound *and* has a live peer connection ("transport appears ready") versus unbound or bound-with-no-connection ("transport not ready"). Stated in terms of what is actually observed: **internal state** — the adapter's bind/connection state (`WS-LIFECYCLE-*`, `WS-CONN-*`); **observable proxy exposed** — a proposed Status UI indicator surfacing that internal state; **end-to-end outcome NOT established by this claim** — whether a specific E-Stop command reaches and is acted on by Dragonframe. This is a single property with two independent residual gaps (below), not two properties — the transport-readiness half and the peer-identity half are the same assurance question (can the operator trust E-Stop?) viewed from its two independent causes, and splitting them into separate IDs would only satisfy field cardinality, not represent a genuinely separate claim.
- **Quantifiers in the claim:** for every point in time after the indicator exists, its displayed state matches the adapter's actual bind/connection state at that moment — a small, enumerable state-machine correspondence claim (three states: unbound / bound-no-connection / bound-with-connection), not a large generatable space. The peer-identity dimension is effectively "for every E-Stop send, the connected peer is Dragonframe" — a dimension no current evidence method can reach at all (see the second residual gap below).
- **Canonical definition:** "transport appears ready" = server bound AND an active peer connection present, per the existing `WS-CONN-*` connection model. `WS-CONN-004/005/006`'s connection-supersede logic accepts any local process passing the path check, with no origin or authentication check, so a second connection silently displaces the first — this is why "transport appears ready" and "E-Stop is deliverable" are different claims, not a wording nicety.
- **Valid initial-state domain:** n/a (state-machine visibility claim, not boundedness/isolation/conservation).
- **Property class:** Operational properties (state-machine visibility) + Compatibility/trust-identity (external), for the two dimensions respectively.
- **Origin:** INFERRED — no existing spec states either dimension of this claim. The transport-readiness scoping is a smaller ask than the HLD's Non-Goal ("no third status indicator") rules out, since it extends the existing bind-result observability pattern (`WS-LIFECYCLE-002`); the peer-identity dimension is MAPS surfacing a risk no spec currently addresses (the HLD's E-Stop success metric covers correct behavior under normal single-client operation, not this adversarial-connection scenario).
- **Claim nature:** Property — a claim about DragonMIDI's own adapter and its trust boundary, even though *closing* the peer-identity dimension would require Dragonframe's cooperation. That external-cooperation fact belongs in that gap's Gap disposition, not in Claim nature — DragonMIDI's own design is what's incomplete, not an external system's documented behavior.
- **Source evidence:** `docs/high-level-design.md` Key Design Decisions ("WebSocket output fails silently on bind failure"); `websocket_output.py` `WS-SEND-003`/`WS-RUNTIME-003`, `WS-CONN-002` through `WS-CONN-006`; `system-assurance-map.md` High-consequence failure paths and Trust boundaries.
- **Confidence in intent:** low against the HLD as currently written (which rules out a third indicator) — user has confirmed this should be top priority regardless.
- **Consequence if false:** operator presses physical Stop believing E-Stop fired; motion-control hardware keeps moving with no indication anything is wrong until physically observed. For the peer-identity dimension specifically: an impostor local process could intercept or supersede the WebSocket connection, silently defeating E-Stop with no error and no distinguishing signal.
- **Downstream dependencies:** none.
- **Preconditions:** WebSocket Output Adapter is the only path for E-Stop (`docs/high-level-design.md` Non-Goals: "no command exists" via OSC/keystroke for this).
- **Assumptions:** resolving the peer-identity gap assumes Dragonframe would participate in some future identifying handshake — outside this project's unilateral control.
- **Prioritization rationale:** highest consequence-if-false in the whole system; user-confirmed top priority; the transport-readiness gap is genuinely achievable now, independent of whether the peer-identity gap ever closes.
- **Priority:** high
- **Disposition:** Approved
- **Evidence state (set):** No evidence
- **Residual gaps (collection):**
  - Gap: transport-readiness signal does not exist — no Status UI indicator reflects the WebSocket adapter's bind/connection state. — Type: Operational observability gap — Disposition: Resolve through LID/design — Owner: the user, via a LID pass — Freshness: n/a
  - Gap: connected-peer identity / end-to-end E-Stop delivery is unestablished — the adapter cannot distinguish Dragonframe from any other local process passing the path check, and no unilateral design exists to close this. — Type: Design missing — Disposition: Accept risk (no unilateral resolution path exists without Dragonframe-side protocol cooperation) — Owner/sign-off: the user, tracked as a known, permanent limitation — Freshness: n/a
- **Claim type:** State-machine visibility (transport-readiness dimension) / trust-identity boundary claim (peer-identity dimension).
- **Formalizability:** n/a for both.
- **Executable oracle quality:** strong once the transport-readiness signal is built — small, enumerable state space (3 states), an example-based lifecycle test is a strong oracle for that claim shape. None available for the peer-identity dimension — no evidence method reaches it.
- **Reference category:** n/a (no differential testing for either dimension).
- **Primary evidence method:** transport-readiness — ordinary/lifecycle example testing, once a design exists, matching the existing `WS-LIFECYCLE-*` test style. Peer-identity — none currently viable; `docs/evidence-selection.md`'s "ACCEPT AS EXPLICIT ASSUMPTION" is the only applicable option, tracked as a residual risk, not an evidence method with active work behind it.
- **Supporting evidence:** none for either dimension.
- **Evidence strength tier:** n/a (not a boundedness/resource-safety claim).
- **Quantifier coverage check:** transport-readiness — pre-handoff n/a; the state space is small and fully enumerable, so an example-based test covering all three states and their transitions trivially satisfies the claim's quantifier. Peer-identity — n/a, no evidence plan exists to check.
- **Wording check:** load-bearing for this pass — no artifact anywhere may let the transport-readiness observable be read as establishing the peer-identity/E2E-delivery dimension. Checked across `correctness-assurance.md`, `assurance-case.md`, `evidence-handoff.md`, and this register: confirmed clean.
- **Vacuity check:** n/a — no evidence exists yet for either dimension. Once the transport-readiness signal is built, its evidence must actually flip the underlying adapter state and observe the indicator update, not merely assert a mocked value — record this expectation in the eventual handoff.

### MAPS-002: Controller Profile CC-collision detection

- **Behavioral segment:** Controller Profile config schema / loader (`mapping.py::validate_controls_config`, `controller_profile_loader.py`)
- **Claim (a) — dispatch order under a Group-switch/other-control CC collision:** when a Group-switch key (Previous/Next Track) shares a CC with any other control, `process()` resolves the collision in favor of Group switching, deterministically (`MAP-GROUP-005`).
- **Claim (b) — general cross-field CC-uniqueness:** loading a Controller Profile config file whose `controls:` block assigns the same CC number to two different, non-Group-switch control roles either (a) is rejected at load time with a clear error, or (b) has fully deterministic, documented resolution behavior for every possible collision pair.
- **Quantifiers in the claim:** (a) for the one specific Group-switch-vs-other collision case, dispatch order is fixed — a single-instance claim, not a large space. (b) for every possible cross-field collision pair — unquantified today; no validation logic exists to have a coverage question about.
- **Canonical definition:** n/a.
- **Valid initial-state domain:** n/a (representation-invariant/boundary-decoder class, not boundedness/isolation/conservation).
- **Property class:** (a) State-machine safety (dispatch determinism). (b) Boundary/decoder correctness (validation completeness) + representation invariant (CC-to-role mapping should be injective within a profile).
- **Origin:** (a) SPECIFIED (`MAP-GROUP-005`). (b) **SPECIFIED — as an explicitly accepted, deferred gap**, not a silent oversight: `docs/llds/static-mapping.md` Open Questions #7 states plainly that rejecting duplicate CCs "not yet specified"; `docs/llds/midi-input.md` line 151 documents the closest related case (`match_substring` collisions) as "logged, not refused," a stated project-wide tolerance for this class of authoring mistake.
- **Claim nature:** Property (both sub-claims — DragonMIDI's own config-loading behavior, no external system involved).
- **Source evidence:** `mapping.py::validate_controls_config` (checks only per-field length and jog-wheel presence, no cross-field uniqueness); `docs/llds/static-mapping.md` lines 171, 216, 381 (three places documenting (b) as an accepted gap).
- **Confidence in intent:** high that (b)'s gap is deliberate as currently documented — user asked to track it anyway.
- **Consequence if false (b):** a third-party-authored profile silently double-maps a control (last-dict-write-wins in `build_opinionated_map`'s dict-merge order, or a fader/transport ambiguity) — the contributor gets wrong behavior with no error message pointing at the cause.
- **Downstream dependencies:** every property that assumes a profile's opinionated map is internally consistent (MAPS-004, MAPS-006).
- **Preconditions (b):** only reachable via a user-authored YAML profile — the two bundled profiles are hand-verified and known collision-free.
- **Assumptions:** none.
- **Prioritization rationale:** (b) is the one boundary where non-maintainer content becomes live behavior with zero review gate; user requested tracking despite the documented deferral.
- **Priority:** (a) low — already correct and tested, no action needed. (b) medium — real risk, deliberately deferred.
- **Disposition:** (a) Approved. (b) **Deferred** — acknowledged as real, not pursued now; revisit trigger below.
- **Evidence state (set):** (a) Example-tested (`test_mapping.py`, `MAP-GROUP-005` cases). (b) No evidence.
- **Residual gaps (collection):**
  - (a): none.
  - (b) Gap: no cross-field CC-uniqueness validation exists in the Controller Profile loader. — Type: Design missing — the validation logic itself has no design or implementation; the LLD decision that exists is a decision *not* to build it yet, not a design for the check itself. — Disposition: Defer — per the existing, explicit LLD deferral. — Revisit trigger: contributor base for third-party profiles growing past "a handful of trusted people." — Freshness: n/a.
- **Claim type (b):** representation invariant (if the deferral were reversed).
- **Reference category:** n/a.
- **Primary evidence method (b, if the deferral is ever reversed):** property-based testing — generate randomized `ControlsConfig` instances (including deliberately duplicated CCs across fields) and assert a `detect_cc_collisions()` function's output against a simple set-cardinality oracle.
- **Evidence strength tier (b):** n/a today (no guard exists to evaluate); if reversed, the natural design is Structural enforcement + verification — a validating function paired with boundary tests, not fuzzing alone.
- **Quantifier coverage check / Wording check / Vacuity check:** n/a — no evidence plan is active for (b); this row exists so the analysis isn't lost if the deferral is ever revisited.

### MAPS-003: Dragonframe WebSocket AXn-ordering assumption

- **Behavioral segment:** `MappingEngine.process_websocket()` (Cycle, Group-aware Solo)
- **Claim:** For every axis DragonMIDI discovers via OSC `getAllPosition`, Dragonframe's WebSocket-side `AXn` index for that axis equals DragonMIDI's OSC-discovery-order index for it (used by `select-AXn`).
- **Quantifiers in the claim:** for every discovered axis — a correspondence claim between two fixed numbering schemes for one specific project's axis set, not a claim over a generatable input space (which is exactly why no automated evidence method applies — see Evidence selection below).
- **Canonical definition:** n/a beyond the claim itself.
- **Valid initial-state domain:** n/a.
- **Property class:** External assumption / compatibility property (interop with an external, unverified numbering scheme)
- **Origin:** SPECIFIED as an *assumption* — explicitly written into `process_websocket()`'s own docstring as "the accepted assumption" and cross-referenced from `docs/llds/static-mapping.md`. Not SPECIFIED as a *confirmed fact*.
- **Claim nature:** **External assumption** — a claim about Dragonframe's internal behavior, a system this project does not control. This is the claim's permanent nature, independent of whether it has ever been checked (see Evidence state / Freshness below, which are the axes that actually change).
- **Source evidence:** `mapping.py` `process_websocket()` docstring; `docs/llds/static-mapping.md` WebSocket-Targeted Controls section.
- **Confidence in intent:** the assumption's existence is well-documented; its truth is not — user has confirmed it remains unverified against real Dragonframe.
- **Consequence if false:** Cycle and Solo select the wrong physical axis — silent misdirection (a `select-AXn` command still succeeds, it just targets the wrong axis), with high blast radius on a live rig if noticed late.
- **Downstream dependencies:** MAPS-001's peer-identity gap conceptually (silent-wrong-behavior class) but functionally independent.
- **Preconditions:** only matters once axis discovery has found ≥1 axis and Group/Cycle actually gets used.
- **Assumptions:** this property *is* the assumption; nothing further underlies it.
- **Prioritization rationale:** unverifiable by unit testing (depends on real Dragonframe internal numbering, which DragonMIDI cannot query); high consequence, silent failure mode.
- **Priority:** high (as a documented, unverified assumption — not a code-fix task, since there's no code to fix).
- **Disposition:** Approved (as an assumption to actively track toward verification).
- **Evidence state (set):** No evidence. (Would become `Manually verified (as of <Dragonframe version>, <date>)` once the procedure below is run and logged — Evidence state and Freshness are the axes that move; Claim nature never does.)
- **Residual gaps (collection):**
  - Gap: no verification has occurred against real Dragonframe. — Type: External verification unavailable or missing — Disposition: Manual/operational verification — Owner: the user (or whoever has hands-on Dragonframe access) — Freshness: n/a (no verification has yet occurred to have a freshness state; once first verified, becomes "current," moving to "stale — renewal needed" whenever Dragonframe's version changes).
- **Claim type:** compatibility/interop claim against an external, closed system with no available reference implementation to differential-test against.
- **Formalizability:** n/a.
- **Reference category:** n/a (Dragonframe cannot serve as a scriptable reference for differential testing).
- **Primary evidence method:** an explicit, documented **operational verification procedure**: with a real project loaded in Dragonframe, deliberately create an axis ordering that is *not* alphabetical/creation order (to rule out coincidental agreement), fire `select-AXn` for each discovered axis in turn, and log-confirm via Dragonframe's debug log (the same `HARD STOP`-style precedent used for E-Stop) that the intended axis highlights each time. One-time or per-Dragonframe-version, not automatable.
- **Supporting evidence:** none.
- **Evidence strength tier:** n/a (not a boundedness/resource-safety claim).
- **Quantifier coverage check:** the procedure covers ≥3 axes in a deliberately non-trivial order, closing the "coincidental agreement on a small/ordered set" gap a 1-axis or alphabetically-ordered check would leave open.
- **Wording check:** must never be described as "verified" in `correctness-assurance.md` until the procedure has actually run — checked, clean.
- **Vacuity check:** n/a until the procedure runs; the procedure itself is designed to discriminate (non-trivial ordering rules out a false positive from coincidental agreement), satisfying the pre-handoff reachability requirement.

### MAPS-004: Knob-nudge clamp bound invariant

- **Behavioral segment:** `MappingEngine._process_bank_derived` (`mapping.py:636-676`)
- **Claim (a) — in-bounds start:** for any sequence of Knob N raw-value deltas and any interleaving of live (`axis_positions`) vs. internally-estimated position readings, given the tracked position starts within `[min(min_value, max_value), max(min_value, max_value)]`, it stays within that range after every step, and the sent delta never overshoots the bound.
- **Claim (b) — out-of-range start:** given the tracked position starts *outside* `[low, high]` — a realistic input, since a live reading comes from Dragonframe, whose actual axis limits are independent of DragonMIDI's user-entered `min`/`max` — the resulting position, if a message is sent, is always within `[low, high]`. `MAP-BANK-008`'s clamp formula (`clamped_position = max(low, min(high, current_position + delta))`) applies unconditionally, with no distinct code path; no further guarantee is made about *which* position within range it lands on.
- **Together, (a) and (b) partition the full domain** (position starts in-range or out-of-range — no third case) — the invariant is now stated for every reachable starting state, not silently assuming the happy path.
- **Quantifiers in the claim:** (a) "for any delta sequence, for any live/estimate interleaving, at every step" — full-sequence, not single-nudge. (b) "for any out-of-range starting position, any nonzero delta" — single-step, since the claim is only about the immediate clamp result, not a multi-step recovery trajectory.
- **Canonical definition:** "in bounds" = `[min(min_value, max_value), max(min_value, max_value)]`, per `MAP-BANK-008`'s explicit tie-break rule for reversed min/max.
- **Valid initial-state domain:** (a) position ∈ `[low, high]` at the start of the sequence — stated explicitly, not implicit. (b) position ∉ `[low, high]` — the complementary domain, also explicit.
- **Property class:** Boundedness / numeric correctness
- **Origin:** SPECIFIED — (a) `MAP-BANK-008`, `MAP-BANK-009`; (b) `MAP-BANK-010`.
- **Claim nature:** Property.
- **Source evidence:** EARS specs above; `mapping.py::_process_bank_derived`; git history `81d1397`, `f63a84a` (two historical production bugs, both in-bounds-start scenarios).
- **Confidence in intent:** high — fully specified.
- **Consequence if false:** axis creeps outside its configured safe range on real motion-control hardware; this exact class of bug has occurred in production before.
- **Downstream dependencies:** none upstream.
- **Preconditions:** Bank N's fader has a real axis assigned in the active Group; engine is in axis mode.
- **Assumptions:** floating-point arithmetic behaves per IEEE-754 double semantics (Python `float`) — trusted base, not separately verified.
- **Prioritization rationale:** only area in the whole system with a confirmed prior production bug; specified, numeric, directly drives physical hardware position.
- **Priority:** high
- **Disposition:** Approved (both sub-claims).
- **Evidence state (set):** Example-tested (two named tests anchoring `81d1397`/`f63a84a`); **Property-tested** (single-nudge and full multi-step-sequence properties, in-bounds and out-of-range generator groups); **Supported by multiple complementary layers** (structural enforcement — the clamp formula itself — paired with both example-based and property-based verification of it; not claimed as *independent* layers, since the tests and the production code they verify all derive from the same spec and exercise the same implementation — see Evidence strength tier below for the distinct claim that *is* warranted).
- **Residual gaps (collection):** none currently identified.
- **Freshness:** n/a.
- **Claim type:** boundedness/conservation-style invariant over a large input space (delta sequences × live/estimate interleavings × initial-state domain).
- **Evidence strength tier:** **Structural enforcement + verification.** `clamped_position = max(low, min(high, ...))` is the structural guard — it makes the invariant true by construction for every case, not merely reduces the failure space. `test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position` (added this pass, verified by mutation to distinguish the correct clamp from a broken order-dependent one that the pre-existing boundary-only test could not) plus the property tests are the verification layer confirming the guard fires correctly across randomized inputs, not merely asserted to exist. This is the strongest available tier, not sampled exploration alone — and it is a claim about *strength*, not about *independence*: the guard and its tests are complementary evidence for the same implementation, not two independently-derived checks.
- **Quantifier coverage check:** confirmed by direct inspection of `tests/test_mapping.py` — `test_knob_nudge_sequence_never_leaves_range_at_any_step` reconstructs the tracked position from `process()`'s returned deltas and asserts the invariant after *every* step in a generated sequence of 2–30 values, not just the final one; `test_knob_nudge_from_out_of_range_start_never_sends_a_position_outside_range` generates the starting position outside `[low, high]` explicitly via a dedicated `overshoot`/`starts_above` strategy dimension. Both oracles match their claim's quantifiers.
- **Wording check:** no universal-language overclaim found — the claim's "always"/"any" wording is backed by the enforcement+verification pair above, not sampled evidence alone.
- **Vacuity check:** Precondition witnessed satisfiable — yes, concrete witness tests (`test_knob_nudge_from_above_range_live_position_moves_down_toward_upper_bound` etc.) demonstrate the out-of-range scenario is real and reachable with specific numbers, not merely hypothesis-generated. Oracle reachability — confirmed by inspection: generators include reversed bounds, large deltas relative to span, and both live/estimate paths. **Mutation/reintroduction — actually performed, not merely required:** the `max`/`min` clamp was removed and confirmed to make four tests fail (restored, re-confirmed green); `sorted()` on reversed min/max was dropped separately and confirmed to make the new interior-point test fail while the pre-existing boundary-only test kept passing (the exact gap that motivated adding the interior-point test), then restored. Both results recorded here as the discriminating-evidence record this pass requires.

### MAPS-005: `decode_osc_packet` malformed-bundle robustness

- **Behavioral segment:** `osc_io.py::decode_osc_packet`
- **Claim:** `decode_osc_packet` raises `BundleBoundsError` for a `#bundle` with a non-positive/overlong `element_size` or nesting beyond `MAX_BUNDLE_DEPTH` (8), rather than relying on Python's slicing semantics or its own interpreter recursion limit for safety. This is a robustness/contract claim, not a claim that a hang is being prevented: direct testing (a 3,000-level nested bundle; negative and zero `element_size` inputs) found the pre-guard code already safe against those specific inputs — a non-positive `element_size` always produces an empty Python slice, which always fails to decode immediately, and uncapped nesting safely raises `RecursionError`, already caught by the existing broad exception handler. The guards replace that incidental safety with an explicit, documented one.
- **Quantifiers in the claim:** "for any byte string" is the engineering target the guards are built to satisfy for the specific malformed shapes named above — not a claim that every possible byte string has been exhaustively verified (see Wording check below).
- **Canonical definition:** n/a.
- **Valid initial-state domain:** n/a — `decode_osc_packet` is a pure function of its input bytes, no persistent state to have a starting domain.
- **Property class:** Boundary/decoder correctness, error/failure semantics, boundedness
- **Origin:** **SPECIFIED.** The guards' behavior is now an explicit EARS requirement — `OSC-DISCOVER-010`, `OSC-DISCOVER-011`, `OSC-DISCOVER-012` (`docs/specs/osc-io.md`, all `[x]`) — not a residual CODE-OBSERVED/INFERRED classification carried forward from before those specs existed. The path here matches `docs/property-discovery.md`'s "approving new intent" case directly: the guards did not exist in the code at all before the user's approval (nothing to have "observed"), the user affirmatively decided they should be built, and a LID Phase 2/3 pass subsequently landed real EARS IDs for them — Origin is SPECIFIED on that independent, mechanical basis, not retained as `INFERRED, confirmed <date>`.
- **Claim nature:** Property.
- **Source evidence:** `docs/specs/osc-io.md` `OSC-DISCOVER-010/011/012`; `osc_io.py::decode_osc_packet`; `handle_datagram`'s broad `except Exception`.
- **Confidence in intent:** high — fully specified, and implemented to match.
- **Consequence if false:** an undocumented, implicit reliance on Python's own recursion limit and slicing semantics for safety, plus an unnecessary stack walk on malformed deeply-nested input before failing.
- **Downstream dependencies:** axis discovery (MAPS-003 territory), Dragonframe-signal liveness.
- **Preconditions:** any process on the local machine can send to DragonMIDI's listen port; no authentication exists.
- **Assumptions:** the "trusted local peer" framing this design reverses is documented in `docs/llds/osc-io.md`'s Decisions & Alternatives, not restated here.
- **Prioritization rationale:** explicit guards replace an implicit, refactor-fragile safety property with a documented one, and bound the stack-walk cost of malformed input on a background thread.
- **Priority:** medium
- **Disposition:** Approved and **implemented**.
- **Evidence state (set):** Example-tested (6 deterministic regression tests: negative/zero/oversized `element_size`, exact-boundary-still-valid, depth-cap-exact-still-valid, depth-cap-exceeded, plus 2 logging tests); **Fuzz-supported** (1 `hypothesis` structured-fuzz test, per-example deadline); **Supported by multiple complementary layers** (structural enforcement paired with both deterministic and sampled verification — complementary failure-detection strengths, not an independence claim; the guards and every test that exercises them share the same production implementation).
- **Residual gaps (collection):** none currently identified for the stated claim; see Vacuity check for one recorded scope note (not a gap in what's claimed).
- **Freshness:** n/a.
- **Claim type:** boundary/decoder robustness under malformed input, established via explicit enforcement rather than search evidence alone.
- **Evidence strength tier:** **Structural enforcement + verification.** `BundleBoundsError` and `MAX_BUNDLE_DEPTH = 8` are the structural guards, enforced inside `decode_osc_packet` itself (not only `handle_datagram`'s wrapper). The six deterministic regression tests verify each guard fires at its stated limit — including the two boundary-valid-not-rejected cases (`element_size` exactly matching remaining bytes; nesting exactly at the cap), confirming the guards don't over-reject. The fuzz test is supporting, exploratory evidence for shapes the guards weren't specifically written for, not the primary basis for the claim.
- **Quantifier coverage check:** confirmed by direct inspection of `tests/test_osc_io.py` — the fuzz test (`test_decode_osc_packet_never_hangs_on_structured_malformed_bundles`) generates `declared_size` across the full `int32` range, `nesting_depth` 0–12 (spanning both under and over the 8-level cap), and arbitrary binary payloads, with a per-example deadline as the hang oracle.
- **Wording check:** the claim's universal wording ("for any byte string") is explicitly qualified in the Claim field above as the engineering target the guards satisfy for the named malformed shapes, distinct from a claim that fuzzing alone exhaustively verified arbitrary input — matches `docs/claim-validation.md § 3`'s required split.
- **Vacuity check:** Precondition — n/a (no nontrivial precondition; any byte string is a valid input). Oracle reachability — confirmed by inspection: the fuzz generator explicitly constructs `#bundle`-framed payloads with randomized declared sizes rather than relying on unstructured byte fuzzing to stumble onto the shape. **Mutation/reintroduction — actually performed:** both guards were deliberately removed (reverting `decode_osc_packet` to the pre-guard implementation) and confirmed to make 5 of 7 new deterministic/logging tests fail (the two accept-cases — exact-boundary and exact-depth — correctly kept passing, confirming the guards don't over-reject); restored and the full `test_osc_io.py` suite re-confirmed green. One residual scope note, not a gap in what's claimed: the fuzz test's hang oracle is `hypothesis`'s per-example deadline rather than a subprocess/watchdog execution-isolation harness — sufficient given the underlying hang risk this guards against was itself found not to reproduce in direct testing (see Claim), but recorded here in case that judgment is revisited.

### MAPS-006: Controller Profile switch state-clear completeness

- **Behavioral segment:** `MappingEngine.set_profile` (`mapping.py:394-409`)
- **Claim:** After `set_profile(new_profile)`, no per-control state tracked under the *previous* profile (dedup values, press state, debounce timestamps, axis positions, Group axis assignments, encoder mode) influences any subsequent `process()`/`process_websocket()`/`process_keystroke()` call under the new profile — even when the old and new profiles reuse the same CC number for semantically different controls.
- **Quantifiers in the claim:** "any subsequent" call, across the full post-switch sequence, for all three output paths — not merely the first call after the switch, and not merely two of the three paths.
- **Canonical definition:** "no state leak" = every `process()`/`process_websocket()`/`process_keystroke()` call across an entire post-switch event sequence produces output identical, call-for-call, to what a freshly constructed `MappingEngine(new_profile)` fed only that same sequence would produce.
- **Valid initial-state domain:** n/a in the boundedness sense; the isolation claim's own "before" state (arbitrary prior-profile activity) is exactly what the generator varies, not a fixed precondition to state separately.
- **Property class:** Isolation
- **Origin:** SPECIFIED — `MAP-PROFILE-004` states the switch "clears every piece of tracked state, including axis assignments and encoder-mode overrides."
- **Claim nature:** Property.
- **Source evidence:** `docs/specs/static-mapping.md` `MAP-PROFILE-004`; `mapping.py::set_profile`/`reset`.
- **Confidence in intent:** high.
- **Consequence if false:** switching Controller Profiles mid-session leaks stale state — a control on the new profile inherits a dedup baseline or axis position meant for a different physical control on the old profile, producing a wrong output with no error, possibly several events after the switch.
- **Downstream dependencies:** every property that assumes a profile's behavior is self-contained (MAPS-002, MAPS-004).
- **Preconditions:** requires an actual profile switch at runtime.
- **Assumptions:** `reset()`'s own completeness (called from within `set_profile`) — same invariant one level down, not separately registered.
- **Prioritization rationale:** direct isolation property on the one state machine every other property depends on being clean.
- **Priority:** medium
- **Disposition:** Approved.
- **Evidence state (set):** Example-tested (`test_mapping_profiles.py`, first-call-only example tests, `process()`/`process_websocket()`); **Property-tested** (full post-switch trace, `process()`/`process_websocket()`, verified by direct inspection — see Quantifier coverage check); **Discharged by structural argument** (`process_keystroke()`) — `mapping.py` documents this method as "Stateless — allocates and consults no per-control state," so the claim's isolation requirement holds for it by construction: there is no per-control state for a stale profile to leak into in the first place. This is not an untested exclusion; it is a distinct form of evidence that the claim's full three-output-path scope is satisfied.
- **Residual gaps (collection):** none currently identified — the claim's full scope (all three output paths) is now covered, `process()`/`process_websocket()` by property test and `process_keystroke()` by structural argument.
- **Freshness:** n/a.
- **Claim type:** isolation between two "sessions" (profile A's state, profile B's state) of the same engine instance.
- **Evidence strength tier:** n/a (isolation property, not boundedness/resource-safety — the strength-tier field is scoped to that class).
- **Quantifier coverage check — confirmed by direct inspection of `tests/test_mapping_profiles.py`, not trusted from prior prose:** `test_set_profile_full_post_switch_trace_matches_a_fresh_engine` drives a synthetic profile (`_COLLIDING_PROFILE`, deliberately reusing Studio's Fader-1 CC for a different, WebSocket-targeted control role) through a `hypothesis`-generated pre-switch event sequence (1–15 events), switches, then drives a *second* generated event sequence (1–15 events, not a single event) — feeding it to both the switched engine and a freshly constructed `MappingEngine(profile_B)`, asserting `process()` and `process_websocket()` return identical values call-for-call across the whole second sequence. This exercises dedup state, press/release state, debounce, axis-position estimates, Group assignments, and encoder mode collectively, and CC-overlap across profiles by construction of `_COLLIDING_PROFILE`. `process_keystroke()` is covered separately by the structural argument recorded in Evidence state above, not by this oracle — together the two forms of evidence reach the claim's full stated scope.
- **Wording check:** n/a (no sampled-evidence-as-proof risk; this is a same-process differential check against a known-clean reference object, not a claim resting on fuzz sampling).
- **Vacuity check:** Precondition — witnessed satisfiable (the colliding-profile construction is a concrete, real `ControllerProfile`, not a hypothetical). Oracle reachability — confirmed by inspection, as above. **Mutation/reintroduction — actually performed:** `reset()`'s `_previous_value.clear()` call was deliberately removed and confirmed to make the test fail at the first post-switch event in the hypothesis-discovered falsifying example (a specific `(pre_switch, post_switch)` pair reported in the failure output); restored, and the full suite (`test_mapping.py` + `test_mapping_profiles.py`, 146 tests) re-confirmed green.

### MAPS-007: `MAP-CONFIG-003` migration-invariant evidence is non-discriminating

- **Behavioral segment:** Controller Profile map synthesis (`mapping.py::build_opinionated_map`, `build_profile`)
- **Claim:** `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` and `build_opinionated_map(NANOKONTROL2_CONTROLS, has_scene_button=False)` produce the exact map contents the project's pre-Phase-5 hardcoded literal constants produced, before Phase 5 replaced those literals with values derived from `ControlsConfig`.
- **Quantifiers in the claim:** for both bundled profiles' complete opinionated maps — a fixed, finite comparison, not a generatable space; a known-value/golden test, not property-based testing, is the natural fit (see Evidence selection).
- **Canonical definition:** n/a.
- **Valid initial-state domain:** n/a.
- **Property class:** Refinement/equivalence (migration correspondence)
- **Origin:** **SPECIFIED.** `MAP-CONFIG-003` (`docs/specs/static-mapping.md`, `[x]`) is an explicit SHALL requirement: "The bundled nanoKONTROL Studio and nanoKONTROL2 config files... shall synthesize opinionated maps identical in content to this LLD's pre-Phase-5 `OPINIONATED_MAP_STUDIO` and `OPINIONATED_MAP_NANOKONTROL2` constants." **Correction from an earlier pass: this property's Origin was previously carried as CODE-OBSERVED, which conflated the claim's origin with a finding about its evidence's quality.** The requirement is, and always was, SPECIFIED — what's CODE-OBSERVED is the separate finding that the existing test doesn't actually establish it, which belongs in Residual gaps, not in Origin. See `SKILL.md § The property state model` rule 23.
- **Claim nature:** Property.
- **Source evidence:** `docs/specs/static-mapping.md` `MAP-CONFIG-003`; `test_mapping_config_schema.py:76,81` — `assert build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True) == OPINIONATED_MAP_STUDIO`. `OPINIONATED_MAP_STUDIO` (`mapping.py:321`) is defined as `STUDIO_PROFILE.opinionated_map`, and `STUDIO_PROFILE` is itself built via `build_profile(..., controls=STUDIO_CONTROLS)` → `build_opinionated_map(STUDIO_CONTROLS, has_scene_button=True)` — the identical function called with the identical arguments. The test compares the function under test's output to itself; it is not compared against any independently-frozen historical literal, because that literal no longer exists anywhere in the current codebase. **Shared-bug/independence reasoning (`checklists/differential-independence.md`), applied explicitly:** the "reference" (`OPINIONATED_MAP_STUDIO`) and the "actual" value are not merely correlated — they are provably the same value by construction (same function, same arguments, same call graph), so this is not differential testing with a shared-bug risk to *assess*; it is not differential testing at all. A future golden-test fix must use a literal, hand-authored value with no code path connecting it to `build_opinionated_map`, or the same circularity recurs.
- **Confidence in intent:** high that the requirement itself is intended and correctly worded (it's an explicit SHALL, not inferred); high also that the underlying claim was true *at the moment of the Phase 5 migration commit*; low that today's test provides any ongoing regression protection for it.
- **Consequence if false:** a future change to `build_opinionated_map`/`_fader_entries`/`_knob_entries`/etc. could silently drift both bundled profiles' entire opinionated map away from long-validated behavior, and this specific test would not catch it.
- **Downstream dependencies:** MAPS-002 (assumes the bundled profiles are collision-free and correct), MAPS-006 (assumes profile behavior is well-defined pre-switch).
- **Preconditions:** none.
- **Assumptions:** none.
- **Prioritization rationale:** real audit-trail/regression-protection gap for an explicit SHALL requirement; moderate consequence in practice — `test_mapping.py`'s large example suite exercises `OPINIONATED_MAP_STUDIO`/`NANOKONTROL2` behavior directly, providing some independent behavioral protection against gross regressions even without this specific check.
- **Priority:** medium
- **Disposition:** **Approved.** `MAP-CONFIG-003` is already an approved requirement in the current spec — there is no reconciliation question about whether the *property* should be pursued, only about how to produce discriminating evidence for it, which this entry already specifies.
- **Evidence state (set):** Example-tested, but non-discriminating (circular) — recorded as its own distinct value rather than merged into "No evidence," so the passing-but-non-discriminating test isn't lost from the record, and rather than merged into "Example-tested" unqualified, so it isn't mistaken for real coverage.
- **Residual gaps (collection):**
  - Gap: the existing test does not actually establish `MAP-CONFIG-003` — it is circular, comparing the function under test to itself. — Type: Evidence missing — the implementation is believed correct (hand-confirmed at Phase 5 migration time); what's missing is evidence that would actually catch a future regression. — Disposition: Produce evidence (specifically, independent/golden evidence — a hand-authored fixture with no code path back to `build_opinionated_map`) — Freshness: n/a.
- **Claim type:** refinement/equivalence against a historical reference that itself no longer exists in the codebase to check against.
- **Reference category:** the existing test's "reference" is not a differential-testing reference at all (see Source evidence above) — n/a for `checklists/differential-independence.md` purposes. The proposed golden-test fixture is classified GOLDEN ORACLE / DATA (hand-authored, independent of the code path).
- **Primary evidence method:** known-value/golden test — freeze the current, hand-confirmed opinionated map contents as an explicit literal fixture independent of `build_opinionated_map`'s own code path.
- **Evidence strength tier:** n/a (not a boundedness/resource-safety claim).
- **Quantifier coverage check:** the fixture covers both bundled profiles' complete opinionated maps, matching the claim's full (finite) scope.
- **Wording check:** n/a — no universal/sampled-evidence language in this claim.
- **Vacuity check (for the golden-test fix once implemented):** the proposed fixture avoids the current circularity specifically because it is hand-authored, not derived by calling the function under test — this is the one property in the register whose entire finding *is* a vacuity failure in existing evidence (a non-discriminating equivalence check), so the fix is written to directly repair the specific mechanism that failed, not just add more of the same kind of test. Supporting, non-blocking: a one-time `git show <pre-Phase-5-commit>` diff against the actual historical hardcoded literal would additionally close the *retroactive* historical-match question, which the golden fixture alone (pinning current behavior going forward) does not — offered as optional work, not required for the primary evidence.

## Candidate Disposition

Every candidate/open question `system-assurance-map.md` raises — across its Open Questions, High-consequence failure paths, Important state machines, External assumptions, and Known fragile areas tables — gets exactly one disposition row below. `system-assurance-map.md`'s Trust boundaries, Semantic chokepoints, and Externally visible outputs tables are structural context that fed candidate discovery, not candidates themselves — every concrete risk they surfaced is captured in the tables dispositioned below, so they don't get separate rows.

| Source item (`system-assurance-map.md`) | Disposition | Detail |
|---|---|---|
| Open Questions: Silent E-Stop loss | Registered | MAPS-001 (both the transport-readiness and peer-identity dimensions are residual gaps within this one property, not separate property IDs). |
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
| Important state machines: WebSocket server connection (supersede) | Merged | Same trust gap as MAPS-001's peer-identity residual gap — "no operator-visible signal distinguishing the real Dragonframe from an impostor connection" is one and the same concern. → MAPS-001 |
| External assumptions: AXn numbering matches OSC discovery order | Merged | Same item as the Open Questions row above → MAPS-003 |
| External assumptions: nanoKONTROL2 factory-default CC map | Deferred | Confirmed once against real hardware — a practical smoke check judged sufficient for now, not escalated to a registered property. Revisit if the physical device's firmware/config is suspected to have changed, or a control is reported behaving unexpectedly on that profile. |
| External assumptions: Dragonframe-traffic-as-liveness | Rejected | This is an accepted, explicit HLD design decision (`docs/high-level-design.md` Key Design Decisions), not a gap MAPS should try to independently verify — doing so would require building an independent Dragonframe test double, disproportionate to the risk. |
| External assumptions: `pynput` cross-platform key mapping | Deferred | Real gap, but requires platform-specific CI runners (macOS + Windows) not currently available. Revisit if a keystroke-delivery bug is reported on either platform. |
| External assumptions: Socket close from another thread interrupting `recvfrom()` | Explicitly out of scope | Already tested, found false, and fixed prior to this MAPS pass (bounded 0.5s `settimeout()` poll workaround) — not a live gap, no further MAPS action needed. |
| Known fragile areas: Knob-driven axis nudge scaling | Merged | Same item as the High-consequence failure paths row above → MAPS-004 |
| Known fragile areas: UI layout | Explicitly out of scope | Visual layout is not a correctness property MAPS addresses. |
| Known fragile areas: CI/lint configuration | Explicitly out of scope | Tooling, not system behavior. |

## Pending user reconciliation

None. (MAPS-007 was previously listed here on the basis of an Origin misclassification — the finding that its existing evidence is non-discriminating was mistaken for a reason to treat the *property* as unconfirmed. `MAP-CONFIG-003` is already an approved SHALL requirement; the reconciliation-worthy question was never "should we pursue this," only "how do we evidence it," which is not a user-intent question. See MAPS-007's entry above.)

## Rejected / withdrawn

| Property ID | Reason rejected/withdrawn | Date |
|---|---|---|
| — | none | — |
