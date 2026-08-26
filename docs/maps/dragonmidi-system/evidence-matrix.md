# Evidence Matrix

Phase 4 artifact. For each approved property, records why a given evidence method was chosen — not merely which one. See `docs/evidence-selection.md`.

**Six independent axes, never collapsed:** Discovery source, Authority, Claim nature, Lifecycle, Disposition, Evidence records/summary, Residual gaps, and Freshness are tracked separately for every property — see `SKILL.md § The property state model`. This file adds the evidence-design and evidence-selection reasoning on top of what `property-register.md` already carries.

## Phase 3 — Prioritization

| Property | Priority | Rationale (2–3 driving factors) |
|---|---|---|
| `DM-004` | Highest | Highest blast-radius chokepoint in the mapping layer (every control on the two bundled profiles derives from it); silent-wrong-output failure mode; existing evidence is regression-only, not correctness — this is a real, currently-open gap, not bookkeeping. |
| `DM-003` | High | Physical/motion-control safety consequence (an out-of-range axis command); common usage path (every knob nudge on an axis-assigned Bank); already has low-cost realized evidence to re-verify. |
| `DM-007` | High | `E-Stop` is an explicit safety-relevant function (motion-control emergency stop); narrower exposure than the mapping-wide chokepoints, but consequence-if-false is not merely cosmetic. |
| `DM-EA-002` | Medium-high | Silent-wrong-axis failure mode (no crash, no error) with no automated verification path available — Dragonframe's own AXn assignment isn't queryable; manual verification is the only method, moderate cost, worth doing given consequence. |
| `DM-001` | Medium | Chokepoint for all OSC traffic; high likelihood ordinary tests miss malformed-framing edge cases; consequence bounded by the trusted-peer assumption (`DM-EA-001`), so not maximal; already has low-cost realized evidence to re-verify. |
| `DM-002` | Medium | Silent-failure risk on every profile switch (a common operation for anyone using more than one controller); already has low-cost realized evidence to re-verify. |
| `DM-005` | Medium | Moderate blast radius (one malformed third-party file could theoretically affect discovery of others); defensive code and per-file isolation already in place with existing example coverage. |
| `DM-008` | Medium | High consequence-if-false (a stuck modifier corrupts all subsequent keyboard input system-wide) but only reachable via an already-rare backend-failure path; existing example tests already target the `finally`-block guarantee directly. |
| `DM-006` | Low-medium | Guard already in place and tested; low exposure in practice (Preset Store files are normally only written by the app itself, not hand-edited). |
| `DM-009` | Low | Dense existing spec + example-test coverage; no gap identified during Phase 1 mapping. |
| `DM-EA-003` | Low | Already manually verified in practice (2026-07-21); no further evidence action needed absent a divergence report. |
| `DM-EA-001` | n/a — not an evidence-task candidate | Intentional, accepted threat-model boundary; not something Phase 4A should propose evidence for. |

## Phase 4A — Evidence design, and Phase 4B — Selection

### EVID-001 — DM-001, OSC bundle-decode robustness

- **Remaining uncertainty:** at the five named boundary conditions, does `decode_osc_packet` deterministically raise `BundleBoundsError` and nothing else? Separately, and more weakly: across the broader space of malformed byte layouts a fuzz campaign can reach, is no unhandled exception observed? These are two different questions with two different evidence strengths — see Claim-dimension discharge.
- **What passing would establish:** for the four deterministic boundary dimensions, that the guard code's behavior matches its own stated contract exactly. For the general "arbitrary malformed byte input" dimension, that no unhandled exception occurred within the fuzz campaign's explored distribution — this supports, but does not prove, the broader claim.
- **Oracle authority:** the expected outcome (`BundleBoundsError` raised, or a well-formed decode) is derived directly from the guard's own stated bounds (`MAX_BUNDLE_DEPTH`, `element_size` vs. remaining buffer) — authoritative by construction, since the guard *is* the spec for this claim.
- **Oracle independence:** the property-test oracle re-derives the expected pass/fail from the same bound constants the guard checks, not from re-implementing the guard's logic independently — this is a coverage/robustness check on the guard's own stated contract, not an independent correctness reference. Recorded honestly rather than overstated.
- **Additional confidence:** the existing hypothesis fuzz test (`test_decode_osc_packet_never_hangs_on_structured_malformed_bundles`) explores this space; the guard code, the specific boundary example tests (`_raises_on_negative_element_size`, `_at_the_depth_cap`, `_exceeds_the_depth_cap`, etc.), and the fuzz test are all present in the codebase and match the claim as registered (confirmed by source inspection).
- **What wrong implementation could still pass:** an implementation that checked `element_size` but not nesting depth (or vice versa) would fail the existing boundary tests — confirmed by direct inspection that both dimensions have dedicated tests, not just one.
- **Evidence purpose:** correctness (boundary tests against the guard's own stated contract) + robustness (fuzz campaign).
- **Selected evidence — Primary:** Structural enforcement + verification (guard + deterministic below/at/above-boundary tests, already realized). **Supporting:** Fuzzing (hypothesis, deadline-bounded).
- **Claim-dimension discharge:** negative `element_size` → `test_decode_osc_packet_raises_on_negative_element_size` (**A — covered, deterministic**); zero → `test_..._raises_on_zero_element_size` (**A — covered, deterministic**); oversized → `test_..._raises_when_element_size_exceeds_remaining_buffer` (**A — covered, deterministic**); at-cap accepted → `test_..._accepts_element_size_exactly_matching_remaining_buffer`, `test_..._accepts_nesting_exactly_at_the_depth_cap` (**A — covered, deterministic**); over-cap rejected → `test_..._raises_when_nesting_exceeds_the_depth_cap` (**A — covered, deterministic**); arbitrary malformed input / termination → `test_decode_osc_packet_never_hangs_on_structured_malformed_bundles` (fuzz) (**A — covered, but by sampled exploration, not deterministic proof — do not describe this dimension as "established for arbitrary input" in any downstream artifact**).
- **Vacuity / discrimination:** boundary tests are deterministic below/at/above-boundary by construction (discriminating by design). Mutation/reintroduction: removing the depth guard causes `test_..._raises_when_nesting_exceeds_the_depth_cap` to fail; removing `element_size` validation causes the corresponding boundary tests to fail. Result executed 2026-08-25; not re-executed since (see Freshness).
- **Evidence state (set):** Example-tested; Property-tested (fuzz); Structural enforcement + verification; Supported by multiple complementary layers.
- **Residual gaps:** none currently identified.
- **Freshness:** current as of 2026-08-26 code inspection; the mutation/reintroduction result was last executed 2026-08-25 — cheap to re-run, and should be re-run the next time `osc_io.py` changes.
- **Correctness-assurance.md row:** `§3.1`

### EVID-002 — DM-002, profile-switch state isolation

- **Remaining uncertainty:** does `set_profile()` clear every piece of per-control state (dedup, Group index, axis targets, bank-derived tracked positions) such that a full trace of every control type, immediately after a switch, is indistinguishable from a freshly-constructed engine?
- **What passing would establish:** the *entire* post-switch trace matches a fresh engine's trace — not just the first event after switching.
- **Oracle authority:** the oracle is a fresh `MappingEngine` instance's own behavior — authoritative by definition, since "indistinguishable from fresh" is exactly what the claim asserts.
- **Oracle independence:** independent of `set_profile()`'s own code path (a freshly-constructed engine never calls `set_profile()`).
- **Additional confidence:** the realized test (`test_set_profile_full_post_switch_trace_matches_a_fresh_engine`) checks the full post-switch trace, closing a narrower, first-event-only oracle that would have understated the claim's own "any subsequent operation" quantifier.
- **What wrong implementation could still pass:** a `set_profile()` that cleared everything except (say) one Bank's dedup state would fail this full-trace comparison but could pass a narrower "first event only" oracle — confirming the broader oracle is doing real work, not redundant with a weaker check.
- **Evidence purpose:** correctness.
- **Selected evidence — Primary:** Property-based testing (full post-switch trace against a fresh-engine oracle).
- **Claim-dimension discharge:** n/a — single-instance claim; **A — covered**.
- **Vacuity / discrimination:** the full-trace oracle is a strictly stronger check than a first-event-only oracle by construction; discriminating power confirmed by design, not separately mutation-tested.
- **Evidence state (set):** Property-tested.
- **Residual gaps:** none currently identified.
- **Freshness:** current as of 2026-08-26 code inspection.
- **Correctness-assurance.md row:** `§3.2`

### EVID-003 — DM-003, Bank-derived clamp-to-range

- **Remaining uncertainty:** does the clamp formula keep the tracked position within `[min, max]` across arbitrary nudge sequences, including ones that start outside the range, and does it treat an interior (non-boundary) landing correctly — not merely reproduce a boundary-only formula that happens to match on boundary cases alone?
- **What passing would establish:** clamp correctness across in-range and out-of-range starting positions, multi-step sequences, and interior (non-boundary) landings specifically.
- **Oracle authority:** derived directly from `MAP-BANK-008/009/010`'s stated formula (effective-bounds-ordering-independent clamp; reduced-delta-to-boundary rule).
- **Oracle independence:** the property-test oracle computes expected clamped output from the spec's formula independently of `_process_bank_derived`'s implementation, not by calling it.
- **Additional confidence:** mutation testing found a genuine, previously-uncovered gap — removing the `sorted()` call in the effective-bounds computation was *not* caught by the pre-existing boundary-only test (`test_knob_clamp_bounds_are_order_independent`), because that test's nudge always lands exactly on a boundary, which a broken order-independence formula can still reproduce by coincidence. The new interior-point test (`test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position`) closes that.
- **What wrong implementation could still pass:** an implementation that only clamped at exact boundaries, or that recovered from an out-of-range start only on the *first* nudge but not a subsequent one, would fail the full-sequence and recovery-then-second-nudge tests specifically.
- **Evidence purpose:** correctness.
- **Evidence strength tier:** Structural enforcement + verification — `_process_bank_derived`'s clamp formula is itself the enforcement mechanism (it structurally makes an out-of-range send impossible when the formula is implemented correctly, the same class of guarantee as `DM-001`'s depth cap), paired with the boundary/sequence/interior-point tests as its verification. Not merely sampled search evidence.
- **Selected evidence — Primary:** Structural enforcement + verification (clamp formula + property-based testing). **Supporting:** targeted example tests for named boundary/recovery scenarios.
- **Claim-dimension discharge:** in-range clamp → `test_knob_nudge_reduced_to_reach_the_{lower,upper}_bound_exactly`, `test_knob_nudge_already_at_lower_bound_sends_nothing`; out-of-range first nudge → `test_knob_nudge_from_{above,below}_range_live_position_moves_toward_bound`; out-of-range full sequence → `test_knob_nudge_sequence_never_leaves_range_at_any_step`, `test_knob_nudge_from_out_of_range_start_never_sends_a_position_outside_range`; interior-landing order-independence → `test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position`. All dimensions: **A — covered**.
- **Vacuity / discrimination:** mutation/reintroduction — removing the clamp formula fails 4 tests; removing `sorted()` fails specifically the new interior-point test and no other, confirming that test (not the pre-existing boundary test) is what discriminates this mutation class. Result executed 2026-08-25; not re-executed since.
- **Evidence state (set):** Example-tested; Property-tested; Structural enforcement + verification; Supported by multiple complementary layers.
- **Residual gaps:** none currently identified.
- **Freshness:** current as of 2026-08-26 code inspection; mutation result last executed 2026-08-25.
- **Correctness-assurance.md row:** `§3.3`

### EVID-004 — DM-004, static opinionated-table content correctness for the two bundled profiles

- **Remaining uncertainty:** does `build_opinionated_map`'s returned dict, for the Studio's and nanoKONTROL2's declared `controls:` values specifically, have the correct key membership and correct per-key `_MapEntry` (`kind`, `address`, `args`) — independent of what the function itself currently produces? This is scoped strictly to the static table's content. It does **not** cover runtime dispatch behavior (`MAP-TABLE-001/002/003/005` — channel-match gating, send cadence, one-shot enforcement, unmapped-event handling), which is enacted by `MappingEngine.process()`, not by this dict; nor `MAP-CONFIG-002/005/006/007/008`, which govern input-schema validation (`validate_controls_config`), WebSocket-key sourcing (`build_websocket_keys`), or Bank membership (`build_bank_membership`) — different functions and different data structures entirely. This evidence design covers only the two bundled profiles' concrete declared values — it does not, and is not intended to, establish the same claim for arbitrary third-party `controls:` declarations. See `property-register.md` `DM-004`'s second residual gap for that separately-tracked domain.
- **What passing would establish:** for the two bundled profiles' concrete declarations only, every key present (or correctly absent) in the returned dict, and each present entry's `kind`/`address`/`args`, matches a value hand-computed from `docs/llds/static-mapping.md`'s Opinionated Default Map tables and `MAP-CONFIG-004`.
- **Oracle authority:** high — the expected table is hand-derived from the LLD's Opinionated Default Map tables (Studio and nanoKONTROL2 sections) plus each profile's declared CC numbers and `MAP-CONFIG-004`'s omission rule, not from running `build_opinionated_map`, not from `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` (which are themselves its output), and not from git history (`SKILL.md § Repository history is not an ordinary MAPS input`).
- **Oracle independence:** high — no code path shared with the implementation under test.
- **Additional confidence:** this is the first evidence for this claim that could actually fail if the implementation were wrong; the existing `test_mapping_config_schema.py:76,81` assertions cannot, since they compare the function's output to constants derived from the identical function call (confirmed by source inspection).
- **What important wrong implementation could still pass:** any implementation that reproduces its own prior output would pass the *existing* test; a hand-derived table closes that for every entry it actually includes. A hand table that got a Scene entry's `kind`/`address` wrong (e.g. `"absolute"` instead of `"press"`, or the wrong OSC action) or that omitted the absent-`transport`-key case (`MAP-CONFIG-004`) would still leave those specific dimensions uncovered — named explicitly below so they aren't silently missed.
- **Evidence purpose:** correctness (explicitly not regression — the expected values are spec/LLD-derived, not implementation-derived; `docs/evidence-selection.md § Evidence purpose`).
- **Selected evidence — Primary:** Known-value/golden testing, hand-authored fixture. **Supporting:** none required beyond the existing large example-test suite's incidental coverage of `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2` runtime behavior (noted, not relied on as primary, and not evidence for the runtime-dispatch specs this property explicitly excludes).
- **Reference classification:** GOLDEN ORACLE / DATA (hand-computed, not derived from either implementation under comparison).
- **Claim-dimension discharge (realized):**
  - fader entries (`_fader_entries()`) → `test_studio_opinionated_map_matches_hand_derived_golden_table`, `test_nanokontrol2_opinionated_map_matches_hand_derived_golden_table`. **A — covered.**
  - knob entries (`_knob_entries()`) → same two tests. **A — covered.**
  - mute entries (`_mute_entries()`) → same two tests. **A — covered.**
  - transport entries (`_transport_entries()`) → same two tests, plus `test_studio_opinionated_map_omits_a_hand_derived_entry_when_that_transport_key_is_absent` for the absent-key case (`MAP-CONFIG-004`). **A — covered.**
  - Scene-button insertion (`build_opinionated_map()`'s own `if has_scene_button:` block) → `test_studio_opinionated_map_matches_hand_derived_golden_table` (present) and `test_nanokontrol2_opinionated_map_matches_hand_derived_golden_table` (absent). **A — covered.**
- **Vacuity / discrimination (realized):** mutation/reintroduction executed 2026-08-26 against a working copy of `mapping.py` — deliberately altered `_fader_entries()`'s address formula, `_knob_entries()`'s address formula, `_mute_entries()`'s address formula, `_transport_entries()`'s `record` args, and the Scene-button insertion's address; each mutation was confirmed to fail the golden tests (the Scene mutation correctly failed only the Studio test, not nanoKONTROL2, which has no Scene entry); each was reverted and confirmed to restore a passing full suite (374 tests, only the pre-existing unrelated `test_listener_resends_discovery_query_on_rebind` flake failing). This establishes the golden tests discriminate; the golden values' correctness itself rests on the hand-derivation from the LLD tables and `MAP-CONFIG-004`, not on this check.
- **Evidence state (set):** Example-tested (correctness — golden values hand-derived independent of `build_opinionated_map`'s own code path); the pre-existing `test_mapping_config_schema.py:76,81` remains present, still regression/change-detection only.
- **Residual gaps:** generalization to arbitrary third-party `controls:` declarations is not covered by this evidence at all — Type: Evidence missing. Disposition: Defer (see `property-register.md` `DM-004`). Note: runtime dispatch behavior (`MAP-TABLE-001/002/003/005`) is not a residual gap of this claim — `DM-004` was never about it. It remains an untracked concern; see `correctness-assurance.md § 6`.
- **Freshness:** current as of 2026-08-26 (evidence realized and mutation-verified this date).
- **Freshness:** n/a until evidence lands.
- **Correctness-assurance.md row:** `§3.4` (evidence pending)

### EVID-005 — DM-005, Controller Profile parsing robustness

- **Remaining uncertainty:** does every named malformed-file shape actually get skipped-with-warning rather than crashing discovery of the remaining files?
- **What passing would establish:** per-malformed-shape isolation, confirmed by direct test rather than inferred from the `try`/`except` block's presence alone.
- **Oracle authority:** derived from `PROFILE-LOAD-002/008/009/010`'s stated behavior (skip-and-warn, not crash).
- **Oracle independence:** test fixtures are literal malformed YAML content, independent of the parser's own code.
- **Additional confidence:** confirms the isolation claim across each named malformed-shape dimension individually, not just one representative case.
- **What wrong implementation could still pass:** a version that let one malformed-shape category propagate (e.g. malformed `controls:` structure, but not a missing top-level field) would fail only that dimension's test — confirming per-dimension coverage actually distinguishes them.
- **Evidence purpose:** correctness.
- **Selected evidence — Primary:** Example testing, one test per malformed-shape dimension (realized in `tests/test_controller_profile_loader.py`, confirmed present by source inspection).
- **Claim-dimension discharge:** all four dimensions listed in `property-register.md` → existing example tests, confirmed present. **A — covered.**
- **Vacuity / discrimination:** each test's fixture is a minimal, targeted malformed shape (one violation at a time) — discriminating by construction (a fixture missing exactly one required field can only fail that field's check).
- **Evidence state (set):** Example-tested.
- **Residual gaps:** none currently identified.
- **Freshness:** current as of 2026-08-26 inspection.
- **Correctness-assurance.md row:** `§3.5`

### EVID-006 — DM-006, Preset Store bounds validation

- **Remaining uncertainty:** does every out-of-range index and malformed-entry shape actually get skipped rather than reaching the positional Bank/Group resolution downstream?
- **What passing would establish:** per-malformed-shape isolation, matching `_parse_index`'s and `_validate_entry`'s stated behavior.
- **Oracle authority:** derived from `MAP-STORE-001/002/003` and the guard's own stated bounds (`_MIN_BANK_INDEX`..`_MAX_BANK_INDEX`, `_MIN_GROUP_INDEX`..`_MAX_GROUP_INDEX`).
- **Oracle independence:** test fixtures are literal malformed JSON content.
- **Additional confidence:** low marginal value beyond existing coverage — the guard's logic is simple range checks, already exercised by `tests/test_preset_store.py` (confirmed by source inspection).
- **What wrong implementation could still pass:** an off-by-one in the range check (e.g. accepting Bank index `0` or `9`) would fail a boundary-value test if one exists — confirm this specifically rather than assuming general coverage suffices.
- **Evidence purpose:** correctness.
- **Selected evidence — Primary:** Example testing (already realized).
- **Claim-dimension discharge:** all five dimensions in `property-register.md` → existing example tests, confirmed present by file inspection. **A — covered**; exact-boundary-value coverage (`0`, `9`, `-1`, `6` specifically, not just clearly-out-of-range values) not independently confirmed — a light, non-blocking check, not a tracked gap given low consequence/exposure (Phase 3).
- **Vacuity / discrimination:** not independently mutation-tested; the guard is simple enough (direct range comparison) that the existing example tests are judged sufficient without a dedicated mutation campaign.
- **Evidence state (set):** Example-tested.
- **Residual gaps:** none currently identified as blocking.
- **Freshness:** current as of 2026-08-26 inspection.
- **Correctness-assurance.md row:** `§3.6`

### EVID-007 — DM-007, WebSocket command encode + dispatch

- **Remaining uncertainty:** does a press-transition on a WebSocket-mapped control produce exactly one correctly-shaped send when connected, and no send (not a queued/errored one) when not connected?
- **What passing would establish:** encode-shape correctness plus connected/not-connected dispatch behavior, per target name.
- **Oracle authority:** derived from `WS-SEND-001..008` and the JSON shape Dragonframe's WebSocket channel is documented to accept (`{"input": ...}`, optional `operation`/`params`).
- **Oracle independence:** test assertions check the literal JSON produced, independent of `_encode`'s own code (fixtures are hand-specified expected dicts).
- **Additional confidence:** confirms both the encode shape and the connection-state-gated dispatch, not just one or the other.
- **What wrong implementation could still pass:** an implementation that sent twice per press, or sent even with no connection, would fail `test_send_with_no_active_connection_is_dropped_without_raising` / a double-send-detecting assertion — confirmed the latter exists by inspection (`test_send_is_delivered_to_the_connected_client`).
- **Evidence purpose:** correctness.
- **Selected evidence — Primary:** Example testing, executed (`tests/test_websocket_output.py`, 22/22 passing under the project's declared environment).
- **Claim-dimension discharge:** `E-Stop`/bare-trigger encode → `test_encode_bare_trigger_omits_operation_and_params`; ranged command encode → `test_encode_ranged_command_includes_operation_and_params`; delivery when connected → `test_send_is_delivered_to_the_connected_client`; no-connection drop → `test_send_with_no_active_connection_is_dropped_without_raising`, `test_send_before_start_is_dropped_without_raising`, `test_send_after_stop_is_dropped_without_raising`, `test_send_after_client_disconnects_is_dropped_without_raising`. All four dimensions: **A — covered**, confirmed by a passing execution.
- **Vacuity / discrimination:** not independently mutation-tested; encode tests assert exact JSON shape (discriminating by construction — any wrong field value fails the equality assertion).
- **Evidence state (set):** Example-tested.
- **Residual gaps:** none currently identified. (Prior finding — this suite "fails to import, `websockets` not installed" — was an artifact of running with the bare macOS system Python interpreter rather than the project's own `.venv`; `websockets==16.1.1` is declared in `pyproject.toml` and installed in `.venv`. No environment change was needed.)
- **Freshness:** current as of 2026-08-26, executed and passing under `.venv` (Python 3.11.15).
- **Correctness-assurance.md row:** `§3.7`

### EVID-008 — DM-008, keystroke stuck-modifier release guarantee (press/lookup failures only)

- **Remaining uncertainty:** is every already-pressed modifier released, in reverse order, when a modifier press, the main key press, or an unrecognized key lookup raises? (Explicitly not: when a `release()` call itself raises — that is a separate, uncovered dimension, tracked as a residual gap below, not part of this claim.)
- **What passing would establish:** the `finally`-block release guarantee holds for each of the three covered failure points (a modifier press, the main key press, an unrecognized key lookup).
- **Oracle authority:** derived from `KEY-SEND-001..006` and the code's own stated invariant (every pressed modifier is released, reverse order, even on failure).
- **Oracle independence:** test uses a fake backend whose `press`/`release` calls are independently instrumented, not the real `pynput` backend.
- **Additional confidence:** confirms the guarantee holds at each of the three distinct failure points independently, not just one representative failure.
- **What wrong implementation could still pass:** an implementation missing the `finally` block, or releasing in forward rather than reverse order, would fail `test_send_still_releases_modifiers_when_key_press_raises` / `_still_releases_remaining_modifiers_when_one_modifier_press_raises` respectively — confirmed both exist by inspection.
- **Evidence purpose:** correctness.
- **Selected evidence — Primary:** Example testing (already realized, `tests/test_keystroke_output.py`).
- **Claim-dimension discharge:** modifier press failure, main-key press failure, unrecognized key lookup failure → **A — covered** by `test_send_still_releases_modifiers_when_key_press_raises`, `test_send_still_releases_remaining_modifiers_when_one_modifier_press_raises`, `test_send_swallows_total_backend_failure_without_raising`, `test_send_swallows_unrecognized_key_lookup_failure`. Backend `release()` call itself failing → **C — residual gap, explicitly excluded from the claim's own wording**, not merely untested.
- **Vacuity / discrimination:** the fake backend's instrumented press/release calls directly assert ordering — discriminating by construction, for the three covered dimensions.
- **Evidence state (set):** Example-tested (for the three covered dimensions only).
- **Residual gaps:** a `release()` call that itself fails is not tested and not covered by the claim as worded (would still be swallowed by the surrounding `try`/`except`, but the *ordering* guarantee for a doubly-failing sequence is neither asserted nor claimed). Type: Evidence missing. Disposition: Defer — judged low-value given Priority: medium; tracked in `evidence-handoff.md` (No action scheduled).
- **Freshness:** current as of 2026-08-26 inspection.
- **Correctness-assurance.md row:** `§3.8`

### EVID-009 — DM-009, Group-switch dispatch precedence

- **Additional evidence: none justified.**
- **Reason:** Phase 1/3 found dense existing spec (`MAP-GROUP-005/007/011`) and corresponding example-test coverage in `tests/test_mapping.py` (confirmed by source inspection), with no identified gap and no history of defects in this area. The four evidence-design questions were asked: remaining uncertainty is low (behavior is a small enumerable state space, already exercised); an authoritative oracle would simply restate the spec's own dispatch-order rule; additional confidence over existing coverage is marginal. Recording this explicitly rather than defaulting to a handoff by inertia (`SKILL.md § Evidence design`).
- **Evidence state (set):** Example-tested (existing).
- **Residual gaps:** none currently identified.
- **Correctness-assurance.md row:** `§3.9`

### EVID-010 — DM-EA-001, Dragonframe trusted-peer assumption

- **Additional evidence: none justified.**
- **Reason:** this is a stated, intentional threat-model boundary (`osc_io.py` docstring), not an open uncertainty — DragonMIDI is explicitly not designed to defend against an adversarial local peer beyond the robustness guards already covered by `DM-001`. Manufacturing evidence for "Dragonframe is trustworthy" would misrepresent an accepted design posture as a verifiable claim.
- **Evidence state (set):** No evidence — by design.
- **Residual gaps:** none currently identified — recorded as an accepted, explicit boundary, not a gap.
- **Correctness-assurance.md row:** `§5.1`

### EVID-011 — DM-EA-002, AXn axis-identity assumption (evidence design for a manual procedure)

- **Remaining uncertainty:** does Dragonframe's own internal `AXn` axis numbering actually correspond to the order DragonMIDI discovers axis names via `getAllPosition`, for a real project with a non-trivial (non-alphabetical, non-creation-order) axis ordering?
- **What passing would establish:** for at least one real Dragonframe project, triggering each discovered axis's Solo/Cycle control highlights the axis DragonMIDI believes it corresponds to, confirmed via Dragonframe's own debug log.
- **Oracle authority:** Dragonframe's own debug log, which reports which axis was actually affected — authoritative because it's the ground truth the claim is about, not a derived proxy.
- **Oracle independence:** fully independent — Dragonframe's debug log is produced by Dragonframe itself, with no code path shared with DragonMIDI.
- **Additional confidence:** this would be the first evidence of any kind for this claim; currently "no evidence" (per `property-register.md`). Even after it lands, it confirms correspondence only for the one project/ordering/version tested — see the scope note below.
- **What wrong implementation could still pass:** an ordering assumption that happens to be correct for alphabetically-named or creation-ordered axes but wrong for others would pass a naive same-order test — the procedure specifically requires a non-alphabetical, non-creation-order axis arrangement to rule that out.
- **Evidence purpose:** operational validation (this is a real-hardware/real-software manual check, not a code-level test).
- **Scope of what this evidence can establish (mandatory note — do not overstate downstream):** the property's claim quantifies over "every discovered axis, in every axis ordering, on every project, on every Dragonframe version." A single manual check, however carefully designed, can only ever confirm correspondence **for the specific version/project/ordering exercised in that run**. It cannot establish the general claim. Do not describe a passing manual check as having verified the property in general in any downstream artifact — describe it as verified for the tested configuration, with the general claim remaining assumed.
- **Selected evidence — Primary:** Manual/operational verification. Not automatable — no code-level substitute exists (Dragonframe's AXn assignment isn't queryable over OSC or WebSocket). Inherently a sampling method for this claim shape, not a path to universal coverage.
- **Claim-dimension discharge:** n/a — single-instance claim; **C — residual gap** until the procedure is run, and **a second, permanent residual gap remains even after it passes** — see Residual gaps.
- **Vacuity / discrimination requirement:** the non-alphabetical/non-creation-order axis arrangement requirement above is itself the discrimination design — without it, agreement could be coincidental.
- **Evidence state (set):** No evidence currently; procedure specified (see `evidence-handoff.md`).
- **Residual gaps:** (1) no verification performed yet — Type: External verification unavailable or missing. Disposition: Manual/operational verification. Routed to `evidence-handoff.md`. (2) generalization beyond the tested version/project/ordering is not established and cannot be closed by a single manual check — Type: External verification unavailable or missing. Disposition: Accept risk (see `property-register.md` `DM-EA-002`).
- **Freshness:** n/a until run; once run, Freshness anchors to the specific Dragonframe version *and* the specific project/axis-ordering tested — a different project, axis count, or ordering is not covered by the same result and does not inherit its Freshness.
- **Correctness-assurance.md row:** `§5.2` (evidence pending)

### EVID-012 — DM-EA-003, nanoKONTROL2 CC map assumption

- **Additional evidence: none justified, at this time.**
- **Reason:** already manually verified in practice (HLD, 2026-07-21) against a real unit — every control produced expected behavior. Re-verifying now would not add confidence beyond what's already recorded; the honest remaining risk is unit/firmware drift over time, which Freshness (not a new evidence task) is the correct mechanism for tracking.
- **Evidence state (set):** Manually verified (as of 2026-07-21, in-practice behavioral confirmation, one physical unit).
- **Residual gaps:** none currently identified against the verified unit.
- **Freshness:** verified as of 2026-07-21 — stale-renewal trigger: a future report of a nanoKONTROL2 unit or firmware behaving differently than the bundled default map expects.
- **Correctness-assurance.md row:** `§5.3`

## Properties with no active evidence work (Deferred / Accept risk)

No property's *primary* claim has a Defer or Accept-risk disposition — every property above either has realized evidence for its primary claim, a specified evidence plan routed to `evidence-handoff.md`, or an explicit "Additional evidence: none justified" conclusion. Three properties carry a secondary Defer/Accept-risk gap without it affecting their primary claim's status: `DM-004`'s third-party-Controller-Profile generalization gap (Defer), `DM-008`'s doubly-failing-`release()` ordering (Defer), and `DM-EA-002`'s generalization-beyond-the-tested-configuration gap (Accept risk) — all three tracked in `evidence-handoff.md`/`property-register.md`, none listed here as a whole-property no-active-evidence-work case.
