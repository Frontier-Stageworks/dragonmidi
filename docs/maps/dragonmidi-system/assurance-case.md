# Assurance Case

Structured traceability counterpart to `correctness-assurance.md`. One trace per property in `property-register.md`.

## Traces

### MAPS-001: WebSocket E-Stop transport readiness and peer-identity/end-to-end delivery

Property (property-register.md):
  The operator has some way to determine whether DragonMIDI's WebSocket
  server is bound AND has a live peer connection ("transport appears
  ready"), without physically testing it. Internal state observed:
  adapter bind/connection state. Observable proxy exposed (once built): a
  Status UI indicator. End-to-end outcome NOT established by either
  residual gap: whether E-Stop reaches Dragonframe. This is one property
  with two independent residual gaps, not two properties.
        ↓
Evidence (property-register.md):
  Primary:    none for either residual gap — no implementation exists
  Supporting: none

Assumptions:
  - Resolving the peer-identity gap would require Dragonframe's own
    cooperation in a future identifying protocol — outside this project's
    unilateral control.

Claim nature: Property
Disposition: Approved
Evidence state (set): No evidence
Residual gaps (collection):
  - Gap: transport-readiness signal does not exist — Type: Operational
    observability gap — Disposition: Resolve through LID/design — Owner:
    the user, via a LID pass
  - Gap: connected-peer identity / end-to-end E-Stop delivery is
    unestablished — Type: Design missing — Disposition: Accept risk (no
    unilateral resolution path exists)
Freshness: n/a
Correctness-assurance.md section: § 3.6

### MAPS-002: Controller Profile CC-collision detection

Property (property-register.md):
  (a) A Group-switch-vs-other-control CC collision resolves deterministically
  in favor of Group switching. (b) Loading a profile with a duplicate CC
  across two other control roles either rejects at load time or has fully
  deterministic, documented resolution.
        ↓
Evidence (property-register.md):
  Primary:    (a) Example-tested (MAP-GROUP-005, test_mapping.py)
  Supporting: (b) none for the general cross-field case

Assumptions:
  - None beyond the deliberate LLD decision to defer general validation
    (docs/llds/static-mapping.md, Open Questions #7).

Claim nature: Property (both sub-claims)
Disposition: (a) Approved. (b) Deferred
Evidence state (set): (a) Example-tested. (b) No evidence
Residual gaps (collection):
  - (a): none.
  - (b) Gap: no cross-field CC-uniqueness validation exists — Type:
    Design missing — Disposition: Defer — Revisit trigger: contributor
    base for third-party profiles growing past "a handful of trusted
    people."
Freshness: n/a
Correctness-assurance.md section: § 6.3 (general case not in § 3 — no claim row exists for an intentionally-deferred property)

### MAPS-003: Dragonframe WebSocket AXn-ordering assumption

Property (property-register.md):
  For every axis DragonMIDI discovers, Dragonframe's WebSocket AXn index
  for it equals DragonMIDI's OSC-discovery-order index.
        ↓
Evidence (property-register.md):
  Primary:    none — structurally untestable by automation (Dragonframe is
              closed and unscriptable)
  Supporting: a documented one-time manual verification procedure
              (specified in property-register.md, not yet performed)

Assumptions:
  - This claim *is* the assumption; nothing further underlies it.

Claim nature: External assumption (permanent — this is the claim's type,
never an Evidence state or Disposition value)
Disposition: Approved (as an assumption to actively track toward
verification)
Evidence state (set): No evidence
Residual gaps (collection):
  - Gap: no verification has occurred against real Dragonframe — Type:
    External verification unavailable or missing — Disposition:
    Manual/operational verification
Freshness: n/a (would become "current" once first verified, "stale —
renewal needed" once Dragonframe's version moves on)
Correctness-assurance.md section: § 3.5

### MAPS-004: Knob-nudge clamp bound invariant

Property (property-register.md):
  (a) In-bounds start: tracked axis position after any nudge sequence
  always stays within the configured [min, max] range; sent delta never
  overshoots the bound. (b) Out-of-range start: given the position starts
  outside [min, max], the resulting position, if a message is sent, is
  always within range. (a) and (b) partition the full domain explicitly.
        ↓
Evidence (property-register.md):
  Primary:    Structural enforcement (clamped_position = max(low,
              min(high, ...))) for both sub-claims, paired with:
              (a) 2 example tests (81d1397, f63a84a) + 2 property tests
              (single-nudge, full sequence).
              (b) 1 property test (out-of-range-start generator group).
  Supporting: none beyond the above.

Assumptions:
  - Python float (IEEE-754 double) arithmetic behaves per IEEE-754
    semantics (correctness-assurance.md § 5.3, trusted base).

Claim nature: Property
Disposition: Approved
Evidence state (set): Example-tested; Property-tested; Supported by
multiple complementary layers (not "independent" — the guard and every
test share the same spec and the same production code path; see
correctness-assurance.md § 1)
Residual gaps (collection): none currently identified
Freshness: n/a
Evidence strength tier: Structural enforcement + verification (the
strongest tier — the clamp formula is the guard, the property/example
tests are the boundary verification, not sampled exploration alone)
Vacuity/mutation record: actually performed, not merely required —
removing the max/min clamp made 4 tests fail; dropping sorted() on
reversed min/max made the new interior-point test fail specifically
(while the pre-existing boundary-only test kept passing); both restored
and re-confirmed green.
Correctness-assurance.md section: § 3.1

### MAPS-005: decode_osc_packet malformed-bundle robustness

Property (property-register.md):
  decode_osc_packet raises BundleBoundsError for a #bundle with a
  non-positive/overlong element_size or nesting beyond MAX_BUNDLE_DEPTH
  (8), rather than relying on Python's slicing semantics or its own
  interpreter recursion limit for safety. A robustness/contract claim, not
  a claim that a hang is being prevented — direct testing found the
  pre-guard code already safe against these specific inputs.
        ↓
Evidence (property-register.md):
  Primary:    Structural enforcement (BundleBoundsError, MAX_BUNDLE_DEPTH
              = 8) inside decode_osc_packet itself, paired with 6
              deterministic boundary regression tests (including the two
              boundary-valid-not-rejected cases).
  Supporting: 1 hypothesis structured-fuzz test with a per-example
              deadline; 2 caplog-based logging tests; pre-existing
              except-Exception guard in handle_datagram.

Assumptions:
  - Sender is non-adversarial in the security sense; this is a robustness
    claim, not a security claim (correctness-assurance.md § 3.3).

Claim nature: Property
Disposition: Approved and implemented
Evidence state (set): Example-tested; Fuzz-supported; Supported by
multiple complementary layers (not "independent" — see
correctness-assurance.md § 1)
Residual gaps (collection): none currently identified for the stated
claim (one recorded scope note on the fuzz harness, not a gap in what's
claimed)
Freshness: n/a

**Origin note:** this property's Origin is SPECIFIED — `OSC-DISCOVER-010/
011/012` are explicit, implemented EARS requirements. An earlier pass
carried this as CODE-OBSERVED/INFERRED, which was correct only before
those spec IDs existed; once the user approved the hardening and a LID
pass landed the spec IDs, Origin became SPECIFIED on that independent,
mechanical basis (SKILL.md § The property state model, rule 23).

Evidence strength tier: Structural enforcement + verification
Vacuity/mutation record: actually performed — both guards removed,
confirmed to make 5 of 7 new tests fail while the two accept-cases
correctly kept passing; restored and the full suite re-confirmed green.
Correctness-assurance.md section: § 3.3

### MAPS-006: Controller Profile switch state-clear completeness

Property (property-register.md):
  After set_profile(), no state from the previous profile influences any
  subsequent process()/process_websocket()/process_keystroke() call under
  the new profile — not merely the first call — even under CC-number reuse
  across profiles.
        ↓
Evidence (property-register.md):
  Primary:    process()/process_websocket() — example-tested (first-call
              case) + property-tested: a second randomized event sequence
              is driven post-switch, and the entire output trace,
              call-for-call, is compared against a freshly constructed
              MappingEngine(profile_B) fed the same sequence, using a
              synthetic profile with a CC number deliberately reused
              across a different control role than Studio's.
              process_keystroke() — discharged by structural argument:
              mapping.py documents it as allocating and consulting no
              per-control state, so no leak into it is possible by
              construction.
  Supporting: MAP-PROFILE-004's explicit spec of set_profile's clearing
              behavior.

Assumptions:
  - reset()'s completeness, called from within set_profile — same
    invariant one level down, not separately registered.

Claim nature: Property
Disposition: Approved
Evidence state (set): Example-tested; Property-tested; Discharged by
structural argument (process_keystroke() specifically)
Residual gaps (collection): none currently identified — the claim's full
three-output-path scope is now covered, process()/process_websocket() by
property test and process_keystroke() by structural argument
Freshness: n/a
Vacuity/mutation record: actually performed (on the process()/
process_websocket() portion) — reset()'s _previous_value.clear() removed,
confirmed to make the test fail at the first post-switch event in the
hypothesis-discovered falsifying example; restored, full 146-test suite
re-confirmed green.
Correctness-assurance.md section: § 3.2

### MAPS-007: MAP-CONFIG-003 migration-invariant evidence is non-discriminating

Property (property-register.md):
  build_opinionated_map() applied to the bundled profiles' ControlsConfig
  reproduces the pre-Phase-5 hardcoded map literals exactly (MAP-CONFIG-003,
  an explicit, implemented SHALL requirement).
        ↓
Evidence (property-register.md):
  Primary:    test_mapping_config_schema.py:76,81 — but circular: the
              "reference" (OPINIONATED_MAP_STUDIO/_NANOKONTROL2) is
              provably the same code path as the value under test (same
              function, same arguments), not an independent implementation
              or hand-authored value. Not differential testing at all,
              despite structural resemblance — there is no independence
              to assess.
  Supporting: none independent of the above.

Assumptions:
  - None.

**Origin/Disposition correction from an earlier pass:** MAP-CONFIG-003 is,
and always was, SPECIFIED (docs/specs/static-mapping.md, an explicit `[x]`
SHALL requirement) — this property's Origin was previously carried as
CODE-OBSERVED, which conflated the claim's origin with the separate
finding that its existing evidence is non-discriminating. The finding
about evidence quality belongs in Residual gaps, not in Origin (SKILL.md
§ The property state model, rule 23). There is accordingly no open
reconciliation question about whether this property should be pursued.

Claim nature: Property
Disposition: **Approved**
Evidence state (set): Example-tested, but non-discriminating (circular) —
recorded as its own value, distinct from both "No evidence" and an
unqualified "Example-tested"
Residual gaps (collection):
  - Gap: the existing test does not actually establish MAP-CONFIG-003; it
    is circular — Type: Evidence missing — Disposition: Produce evidence
    (specifically, independent/golden evidence)
Freshness: n/a
Correctness-assurance.md section: § 3.7

## Coverage check

| Property ID | Has assurance-case trace? | Has correctness-assurance.md claim row? | Discrepancy? |
|---|---|---|---|
| MAPS-001 | Yes | Yes (§ 3.6, two-residual-gap split within one property) | None |
| MAPS-002 | Yes | Partial — sub-claim (b) discussed only in § 6.3, not a § 3 claim row (deliberate: a Deferred property has no active claim to make a row for) | None (expected asymmetry, explained above) |
| MAPS-003 | Yes | Yes (§ 3.5) | None |
| MAPS-004 | Yes | Yes (§ 3.1, two-row split) | None |
| MAPS-005 | Yes | Yes (§ 3.3, four-row split) | None |
| MAPS-006 | Yes | Yes (§ 3.2, two-row split: tested paths + structurally-discharged path) | None |
| MAPS-007 | Yes | Yes (§ 3.7) | None — approved, evidence-missing gap only, no reconciliation blocker |
