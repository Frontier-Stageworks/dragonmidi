# Assurance Case

The structured traceability counterpart to `correctness-assurance.md`. See `docs/correctness-document.md § assurance-case.md`.

## Traces

### DM-001: OSC bundle-decode robustness

```text
Property (property-register.md):
  At four named boundaries, decode_osc_packet deterministically raises
  BundleBoundsError rather than an unhandled exception. More broadly, no
  unhandled exception has been observed across a bounded fuzz campaign's
  explored space — this broader "any byte input" framing is supported by
  sampling, not established.
        ↓
Preconditions / initial-state domain:
  none — stateless per-call decode
        ↓
Assumptions:
  - Dragonframe is a trusted local peer (DM-EA-001) — these guards are contract
    enforcement, not adversarial hardening
        ↓
Claim dimensions:
  - negative element_size
  - zero element_size
  - element_size exceeding remaining buffer
  - nesting depth at/beyond MAX_BUNDLE_DEPTH
  - arbitrary malformed byte input generally (termination)
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  - negative element_size -> EVID-001, test_decode_osc_packet_raises_on_negative_element_size
  - zero element_size -> EVID-001, test_decode_osc_packet_raises_on_zero_element_size
  - oversized element_size -> EVID-001, test_decode_osc_packet_raises_when_element_size_exceeds_remaining_buffer
  - at-cap accepted -> EVID-001, test_decode_osc_packet_accepts_element_size_exactly_matching_remaining_buffer, test_decode_osc_packet_accepts_nesting_exactly_at_the_depth_cap
  - over-cap rejected -> EVID-001, test_decode_osc_packet_raises_when_nesting_exceeds_the_depth_cap
  - arbitrary malformed input / termination -> EVID-001, test_decode_osc_packet_never_hangs_on_structured_malformed_bundles
    (hypothesis fuzz, robustness evidence purpose — sampled support, not
    deterministic coverage; do not describe as "established" downstream)
        ↓
Enforcement mechanisms:
  - MAX_BUNDLE_DEPTH=8 recursion cap; element_size bounds check — both dimensions
        ↓
Meta-evidence / discrimination:
  - Mutation/reintroduction: removing depth guard fails the over-cap test; removing
    element_size validation fails the corresponding boundary tests. Executed
    2026-08-25; not re-run since.
        ↓
Risk/assumption treatment:
  - Explicit assumption: Dragonframe trusted-peer (DM-EA-001)
        ↓
Current support:
  Established, deterministically, for the four named boundary dimensions. The
  fifth dimension (arbitrary malformed byte input generally) is supported by
  sampled fuzz exploration, not established as a universal claim.
        ↓
Residual gaps:
  none currently identified as an open task — the deterministic/sampled split
  above is an inherent limit of the evidence method, not a closable gap.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: OSC-DISCOVER-010/011/012, confirmed user intent
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested; Property-tested (fuzz); Structural enforcement
    + verification; Supported by multiple complementary layers
  Layering assessment: complementary (structural guard + boundary tests + fuzz;
    no independence argument made or needed)
  Freshness: current as of 2026-08-26 code inspection
  Correctness-assurance.md section: §3.1
```

### DM-002: Controller Profile switch state isolation

```text
Property (property-register.md):
  After set_profile() returns, no dedup state, Group index, axis-target
  assignment, or bank-derived tracked position from the previous profile
  influences any subsequent MIDI event's dispatch.
        ↓
Preconditions / initial-state domain:
  engine may be in any reachable state at the moment set_profile() is called
        ↓
Assumptions:
  - none beyond ordinary single-threaded engine access
        ↓
Claim dimensions:
  n/a — single-instance claim (full post-switch trace)
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  Primary: EVID-002, property test test_set_profile_full_post_switch_trace_matches_a_fresh_engine
  (correctness evidence purpose)
        ↓
Enforcement mechanisms:
  none
        ↓
Meta-evidence / discrimination:
  Oracle strength confirmed by design: full-trace comparison is strictly
  stronger than a first-event-only oracle.
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established.
        ↓
Residual gaps:
  none currently identified.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: MAP-PROFILE-004
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Property-tested
  Layering assessment: single method
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.2
```

### DM-003: Bank-derived knob clamp-to-range

```text
Property (property-register.md):
  For any Bank with a real axis assigned, every derived stepPosition send keeps
  the tracked axis position within [min, max], including recovery from an
  out-of-range starting position.
        ↓
Preconditions / initial-state domain:
  Bank's fader has a real axis name assigned in the active Group; tracked
  position may start anywhere in ℝ (MAP-BANK-010)
        ↓
Assumptions:
  - Dragonframe's reported live position, when available, is itself accurate
    (not separately tracked)
        ↓
Claim dimensions:
  - in-range starting position, ordinary clamp
  - out-of-range starting position, first corrective nudge
  - out-of-range starting position, full multi-step sequence
  - interior (non-boundary) landing, order-independence of the clamp formula
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  - in-range clamp -> EVID-003, test_knob_nudge_reduced_to_reach_the_{lower,upper}_bound_exactly,
    test_knob_nudge_already_at_lower_bound_sends_nothing
  - out-of-range first nudge -> EVID-003, test_knob_nudge_from_{above,below}_range_live_position_moves_toward_bound
  - out-of-range full sequence -> EVID-003, test_knob_nudge_sequence_never_leaves_range_at_any_step,
    test_knob_nudge_from_out_of_range_start_never_sends_a_position_outside_range
  - interior-landing order-independence -> EVID-003, test_knob_clamp_bounds_order_independence_does_not_clamp_an_interior_position
        ↓
Enforcement mechanisms:
  - the clamp formula in _process_bank_derived, all four dimensions — the formula
    itself is the enforcement mechanism (structurally makes an out-of-range send
    impossible when correctly implemented), verified by the tests above
        ↓
Meta-evidence / discrimination:
  Mutation/reintroduction: removing the clamp formula fails 4 tests; removing
  sorted() from the effective-bounds computation fails specifically the
  interior-point test and no other — confirming that test, not the pre-existing
  boundary test, is what discriminates this class of bug. Executed 2026-08-25;
  not re-run since.
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established for all four named dimensions.
        ↓
Residual gaps:
  none currently identified.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: MAP-BANK-008/009/010
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested; Property-tested; Structural enforcement +
    verification; Supported by multiple complementary layers
  Layering assessment: complementary (property test + targeted example tests
    against the same spec/implementation; no independence argument made)
  Freshness: current as of 2026-08-26 code inspection; mutation result last
    executed 2026-08-25
  Correctness-assurance.md section: §3.3
```

### DM-004: `build_opinionated_map`'s static table content correctness, for the two bundled Controller Profiles

```text
Property (property-register.md):
  build_opinionated_map's returned dict has correct key membership and, per
  present key, correct kind/address/args, for the Studio's and nanoKONTROL2's
  declared controls specifically. Explicitly not a claim about runtime
  dispatch behavior (channel-match, send cadence, one-shot enforcement,
  unmapped-event handling — MappingEngine.process()'s concern, not this
  dict's) and not a claim about arbitrary third-party controls: declarations
  — see Residual gaps for both.
        ↓
Preconditions / initial-state domain:
  the Studio's or nanoKONTROL2's declared controls: block
        ↓
Assumptions:
  - none beyond the config schema itself being correctly documented
        ↓
Claim dimensions:
  - fader entries (_fader_entries()) — key membership + kind/address, per profile
  - knob entries (_knob_entries()) — key membership + kind/address, per profile
  - mute entries (_mute_entries()) — key membership + kind/address, per profile
  - transport entries (_transport_entries()) — key membership + kind/address/
    args, per profile, incl. omitted-key absence (MAP-CONFIG-004)
  - Scene-button insertion (build_opinionated_map()'s own has_scene_button
    block, not a helper function) — present/correct for Studio, absent for
    nanoKONTROL2
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  - all five dimensions -> EVID-004, test_studio_opinionated_map_matches_hand_derived_golden_table,
    test_nanokontrol2_opinionated_map_matches_hand_derived_golden_table,
    test_studio_opinionated_map_omits_a_hand_derived_entry_when_that_transport_key_is_absent
    (tests/test_mapping_config_schema.py) — hand-authored golden values derived
    from docs/llds/static-mapping.md's Opinionated Default Map tables +
    MAP-CONFIG-004 + each bundled profile's declared CC list, not from
    build_opinionated_map, OPINIONATED_MAP_STUDIO/_NANOKONTROL2, or git history
    (correctness evidence purpose). All five: A — covered.
        ↓
Enforcement mechanisms:
  none
        ↓
Meta-evidence / discrimination:
  Executed 2026-08-26: deliberately altered _fader_entries()'s, _knob_entries()'s,
  and _mute_entries()'s address formulas, _transport_entries()'s record args, and
  the Scene-button insertion's address, one at a time, in a working copy;
  confirmed each mutation fails the golden tests (the Scene mutation correctly
  failed only the Studio test, not nanoKONTROL2); reverted each and confirmed
  the full suite passes (374 tests; only the pre-existing, unrelated
  test_listener_resends_discovery_query_on_rebind flake fails).
        ↓
Risk/assumption treatment:
  none for the bundled-profile static-content claim — established. Generalization
  to third-party profiles: Defer. Runtime dispatch behavior
  (MAP-TABLE-001/002/003/005): out of scope for this claim entirely, not tracked
  by any property in this pass.
        ↓
Current support:
  Established, for both bundled profiles, by hand-derived golden-value tests
  independent of build_opinionated_map's own code path, mutation-verified. The
  pre-existing test_mapping_config_schema.py:76,81 remains present, still
  regression/change-detection only.
        ↓
Residual gaps:
  - Description: the shared synthesis helpers are the same code path for any
    Controller Profile, but no evidence covers arbitrary third-party
    controls: declarations
    Gap type: evidence missing
    Gap disposition: defer
        ↓
  (Note: MAP-TABLE-001/002/003/005's runtime dispatch behavior is explicitly
  outside this claim, not a residual gap of it — DM-004 was never about
  whether MappingEngine.process() correctly acts on this table. That concern
  is untracked by any property; see correctness-assurance.md § 6.)
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: MAP-CONFIG-004, plus docs/llds/static-mapping.md's
    Opinionated Default Map tables for per-control content
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested (correctness); existing circular test remains,
    regression-only
  Layering assessment: single method (golden-value testing); no independent
    second layer, and none needed — the golden values' independence comes from
    their derivation, not from a second evidence method
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.4
```

### DM-005: Controller Profile config parsing robustness

```text
Property (property-register.md):
  A malformed Controller Profile config file is skipped with a logged warning;
  the remaining valid files still load; the app does not crash.
        ↓
Preconditions / initial-state domain:
  none
        ↓
Assumptions:
  none
        ↓
Claim dimensions:
  - missing required top-level field
  - wrong type for a required field
  - malformed controls: block
  - malformed YAML syntax
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  all four dimensions -> EVID-005, example tests in tests/test_controller_profile_loader.py,
  one targeted fixture per dimension (correctness evidence purpose)
        ↓
Enforcement mechanisms:
  per-file try/except isolation in _load_directory
        ↓
Meta-evidence / discrimination:
  none — each fixture is a minimal, single-violation shape, discriminating by
  construction
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established for all four named dimensions.
        ↓
Residual gaps:
  none currently identified.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: PROFILE-LOAD-002/008/009/010
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested
  Layering assessment: single method (example testing) plus a structural
    isolation mechanism
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.5
```

### DM-006: Preset Store Bank/Group index bounds validation

```text
Property (property-register.md):
  An out-of-range Bank/Group index or malformed entry in a persisted file is
  skipped with a logged warning, not allowed to reach positional resolution.
        ↓
Preconditions / initial-state domain:
  none
        ↓
Assumptions:
  none
        ↓
Claim dimensions:
  - Bank index below/above range
  - Group index below/above range
  - malformed entry shape
  - unreadable/non-JSON file (treated as empty table)
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  all dimensions -> EVID-006, example tests in tests/test_preset_store.py
  (correctness evidence purpose)
        ↓
Enforcement mechanisms:
  _parse_index bounds check (Bank [1,8], Group [1,5]); _validate_entry shape check
        ↓
Meta-evidence / discrimination:
  not independently mutation-tested — guard is a simple range comparison,
  judged low marginal value to mutation-test given Priority: low-medium
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established for the named dimensions; exact-boundary-value coverage (0, 9, -1,
  6 specifically) not independently confirmed.
        ↓
Residual gaps:
  none tracked as blocking — a light, non-blocking confirmation noted in
  evidence-matrix.md EVID-006.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: MAP-STORE-001/002/003
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested
  Layering assessment: single method plus a structural bounds-check mechanism
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.6
```

### DM-007: WebSocket command encode + dispatch

```text
Property (property-register.md):
  A press-transition on a WebSocket-mapped control produces exactly one
  correctly-shaped send when connected, and no send when not connected.
        ↓
Preconditions / initial-state domain:
  a WebSocket connection is currently active (for the send-succeeds half of the
  claim; the no-connection half is its own dimension)
        ↓
Assumptions:
  - at most one Dragonframe client connects at a time (structurally enforced,
    never independently confirmed against Dragonframe's own behavior)
        ↓
Claim dimensions:
  - E-Stop (bare trigger) encode
  - ranged command encode (select-AXn/jog-AXn)
  - delivery when connected
  - no-connection drop
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  all four dimensions -> EVID-007, example tests in
  tests/test_websocket_output.py (correctness evidence purpose), 22/22
  passing under the project's declared environment (.venv, Python 3.11.15,
  websockets==16.1.1 per pyproject.toml). A — covered.
        ↓
Enforcement mechanisms:
  single _connection slot (supersedes on reconnect)
        ↓
Meta-evidence / discrimination:
  not independently mutation-tested; encode tests assert exact JSON shape,
  discriminating by construction
        ↓
Risk/assumption treatment:
  Accept risk: delivery-failure visibility (correctness-assurance.md §6.1) —
  explicit HLD decision, not part of this claim
        ↓
Current support:
  Established for all four named dimensions by an executed, passing test
  suite.
        ↓
Residual gaps:
  none currently identified.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: WS-SEND-001..008, MAP-WS-001..009
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested
  Layering assessment: single method plus a structural connection-slot
    mechanism
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.7
```

### DM-008: Keystroke stuck-modifier release guarantee

```text
Property (property-register.md):
  For a send() call where a modifier press, the main key press, or an
  unrecognized key lookup raises — but not where release() itself raises —
  every modifier already pressed is released, in reverse order.
        ↓
Preconditions / initial-state domain:
  the failure, if any, occurs during a press call or key lookup, not during a
  release() call (explicitly excluded from this claim)
        ↓
Assumptions:
  none beyond the stated precondition
        ↓
Claim dimensions:
  - modifier press failure — covered
  - main-key press failure — covered
  - unrecognized key lookup failure — covered
  - backend release() call itself failing — excluded from this claim, residual gap
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  Primary: EVID-008, example tests in tests/test_keystroke_output.py
  (test_send_still_releases_modifiers_when_key_press_raises,
  test_send_still_releases_remaining_modifiers_when_one_modifier_press_raises,
  test_send_swallows_total_backend_failure_without_raising,
  test_send_swallows_unrecognized_key_lookup_failure) — correctness evidence
  purpose, for the three covered dimensions
        ↓
Enforcement mechanisms:
  finally block releasing pressed modifiers in reverse order
        ↓
Meta-evidence / discrimination:
  none; fake-backend instrumentation directly asserts ordering, discriminating
  by construction
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established for the three covered dimensions. The release()-failure
  dimension is not covered and not claimed — it is excluded by this property's
  own wording, not a silent gap in an unqualified claim.
        ↓
Residual gaps:
  - Description: a doubly-failing release() sequence is excluded from this
    claim's wording and has no evidence
    Gap type: evidence missing
    Gap disposition: defer — judged low-value given Priority: medium; tracked
    in evidence-handoff.md (No action scheduled)
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: KEY-SEND-001..006
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested
  Layering assessment: single method plus a structural finally-block mechanism
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.8
```

### DM-009: Group-switch dispatch precedence and dedup-state discard

```text
Property (property-register.md):
  Group-switch key wins any CC collision; a Group switch discards dedup state
  only for axis-direct-mode Banks; only a Controller Profile switch resets the
  active Group to 1.
        ↓
Preconditions / initial-state domain:
  none
        ↓
Assumptions:
  none
        ↓
Claim dimensions:
  - dispatch-order precedence under CC collision
  - dedup-discard scope
  - Group-index reset scope
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  all dimensions -> existing example tests in tests/test_mapping.py, confirmed
  present by inspection (EVID-009; correctness evidence purpose)
        ↓
Enforcement mechanisms:
  none beyond the dispatch code itself
        ↓
Meta-evidence / discrimination:
  none — EVID-009 concluded "additional evidence: none justified"
        ↓
Risk/assumption treatment:
  none
        ↓
Current support:
  Established via existing coverage; confirmed present by source inspection,
  not independently re-verified in depth.
        ↓
Residual gaps:
  none currently identified.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: MAP-GROUP-005/007/011
  Claim nature: Property
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Example-tested (existing)
  Layering assessment: single method
  Freshness: current as of 2026-08-26
  Correctness-assurance.md section: §3.9
```

### DM-EA-001: Dragonframe trusted-local-peer assumption

```text
Property (property-register.md):
  DragonMIDI's OSC decode path does not defend against a deliberately
  adversarial peer; DM-001's guards are contract enforcement, not a security
  boundary.
        ↓
Preconditions / initial-state domain:
  n/a
        ↓
Assumptions:
  n/a — this entry is itself the assumption
        ↓
Claim dimensions:
  n/a
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  Primary: none — EVID-010 concluded "additional evidence: none justified"
  (an intentional design posture, not an open uncertainty)
        ↓
Enforcement mechanisms:
  none (deliberately)
        ↓
Meta-evidence / discrimination:
  none
        ↓
Risk/assumption treatment:
  Explicit assumption, accepted by design
        ↓
Current support:
  n/a — stated posture, not a testable claim
        ↓
Residual gaps:
  none currently identified — accepted, intentional boundary
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: explicit docstring ("Dragonframe is a trusted local peer")
  Claim nature: External assumption
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: No evidence — by design
  Layering assessment: n/a
  Freshness: n/a
  Correctness-assurance.md section: §5.1
```

### DM-EA-002: AXn axis-identity assumption

```text
Property (property-register.md):
  Dragonframe's internal AXn axis numbering corresponds to DragonMIDI's
  OSC-discovery order, for every project/ordering/version. No available
  evidence method can fully establish this quantifier — only sample it.
        ↓
Preconditions / initial-state domain:
  n/a
        ↓
Assumptions:
  n/a — this entry is itself the assumption
        ↓
Claim dimensions:
  n/a
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  Primary: none realized yet; EVID-011 specifies a manual verification
  procedure (operational validation evidence purpose) — see evidence-handoff.md.
  Scope note: once run, establishes correspondence only for the specific
  version/project/ordering tested, never the general claim.
        ↓
Enforcement mechanisms:
  none — cannot be enforced, only observed
        ↓
Meta-evidence / discrimination:
  Required: the procedure must use a non-alphabetical, non-creation-order axis
  arrangement to rule out coincidental agreement.
        ↓
Risk/assumption treatment:
  Explicit assumption, currently unverified; generalization beyond any single
  tested configuration is accepted as permanently unverifiable by this method
        ↓
Current support:
  NOT established. No evidence exists yet. Even once the manual procedure
  passes, the general claim (every project/ordering/version) remains assumed,
  not established — only the tested configuration would be confirmed.
        ↓
Residual gaps:
  - Description: no automated or manual verification has been performed
    Gap type: external verification unavailable or missing
    Gap disposition: manual/operational verification
  - Description: generalization beyond the tested version/project/ordering
    cannot be closed by a single manual check
    Gap type: external verification unavailable or missing
    Gap disposition: accept risk
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: explicit docstring ("the accepted assumption")
  Claim nature: External assumption
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: No evidence
  Layering assessment: n/a
  Freshness: n/a until run; once run, scoped to the specific version/project/
    ordering tested only — does not generalize
  Correctness-assurance.md section: §5.2
```

### DM-EA-003: nanoKONTROL2 default CC map assumption

```text
Property (property-register.md):
  The bundled nanoKONTROL2 Controller Profile's CC numbers/channel match the
  device's actual factory-default CC-mode assignment.
        ↓
Preconditions / initial-state domain:
  n/a
        ↓
Assumptions:
  n/a — this entry is itself the assumption
        ↓
Claim dimensions:
  n/a
        ↓
Evidence mapped to claim dimensions (evidence-matrix.md):
  Primary: manual verification, 2026-07-21, one physical unit (operational
  validation evidence purpose)
        ↓
Enforcement mechanisms:
  none
        ↓
Meta-evidence / discrimination:
  none — a behavioral confirmation (every control produced expected behavior),
  not a byte-level MIDI-monitor trace
        ↓
Risk/assumption treatment:
  Explicit assumption, partially verified
        ↓
Current support:
  Manually verified as of 2026-07-21, against one physical unit, behaviorally.
        ↓
Residual gaps:
  none currently identified against the verified unit.
        ↓
Disposition / next action:
  Authority: SPECIFIED
  Authority basis: docs/high-level-design.md, confirmed against real hardware
  Claim nature: External assumption
  Lifecycle: Enduring
  Disposition: Approved
  Evidence summary: Manually verified (as of 2026-07-21)
  Layering assessment: n/a
  Freshness: verified as of 2026-07-21 — stale-renewal trigger: a divergence
  report on a different unit/firmware
  Correctness-assurance.md section: §5.3
```

## Coverage check

| Property ID | Has assurance-case trace? | Has correctness-assurance.md claim row? | Discrepancy? |
|---|---|---|---|
| `DM-001` | Yes | Yes (§3.1) | None |
| `DM-002` | Yes | Yes (§3.2) | None |
| `DM-003` | Yes | Yes (§3.3) | None |
| `DM-004` | Yes | Yes (§3.4) | None |
| `DM-005` | Yes | Yes (§3.5) | None |
| `DM-006` | Yes | Yes (§3.6) | None |
| `DM-007` | Yes | Yes (§3.7) | None |
| `DM-008` | Yes | Yes (§3.8) | None |
| `DM-009` | Yes | Yes (§3.9) | None |
| `DM-EA-001` | Yes | Yes (§5.1) | None |
| `DM-EA-002` | Yes | Yes (§5.2) | None |
| `DM-EA-003` | Yes | Yes (§5.3) | None |
