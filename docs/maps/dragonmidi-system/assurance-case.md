# Assurance Case

Structured traceability counterpart to `correctness-assurance.md`. One trace per property in `property-register.md`.

## Traces

### MAPS-001: WebSocket E-Stop transport readiness observability

Property (property-register.md):
  The operator has some way to determine whether DragonMIDI's WebSocket
  server is bound AND has a live peer connection ("transport appears
  ready"), without physically testing it. Deliberately does not claim
  E-Stop is end-to-end deliverable to Dragonframe — peer identity is a
  separate, unestablishable assumption (see below).
        ↓
Evidence (property-register.md, merged evidence-matrix fields):
  Primary:    none — no implementation exists (transport-readiness signal
              not yet built)
  Supporting: none

Assumptions:
  - The connected peer is Dragonframe. Permanent, unestablishable by this
    adapter's current design — not a placeholder for future test coverage.

Remaining gap / residual risk:
  Transport-readiness half is an open but achievable design/implementation
  gap (extends existing WS-LIFECYCLE-002 bind-observability pattern, does
  not itself reverse the HLD's E-Stop Non-Goal). Peer-identity half is a
  permanent assumption with no evidence method available in this
  codebase's current design. Even with both addressed, end-to-end
  E-Stop-deliverability remains the union, capped by the weaker
  (peer-identity) half. Highest-consequence item in the register, least
  evidenced. See correctness-assurance.md § 6.1.

Assurance status: Known gap (transport-readiness signal); Assumption,
permanent (peer identity) — see correctness-assurance.md § 3.6's three-row
split for the full breakdown.
Correctness-assurance.md section: § 3.6

### MAPS-002: Controller Profile CC-collision detection

Property (property-register.md):
  Loading a profile with a duplicate CC across two control roles either
  rejects at load time or has fully deterministic, documented resolution.
        ↓
Evidence (property-register.md):
  Primary:    Example-tested for the one specified sub-case (MAP-GROUP-005,
              Track-vs-jog-wheel dispatch order) — test_mapping.py
  Supporting: none for the general cross-field case

Assumptions:
  - None beyond the deliberate LLD decision to defer general validation
    (docs/llds/static-mapping.md, Open Questions #7).

Remaining gap / residual risk:
  General CC-collision validation stays an accepted, documented gap by
  design — not scheduled for closure by this MAPS pass, per user request.
  See correctness-assurance.md § 6.3.

Assurance status: Known gap (explicit, by design) for the general case;
Example-tested for the one specified dispatch-order sub-case.
Correctness-assurance.md section: § 6.3 (general case not in § 3 — no claim row exists for an intentionally-unaddressed property)

### MAPS-003: Dragonframe WebSocket AXn-ordering assumption

Property (property-register.md):
  Dragonframe's WebSocket AXn numbering matches DragonMIDI's OSC-discovered
  axis order.
        ↓
Evidence (property-register.md):
  Primary:    none — structurally untestable by automation (Dragonframe is
              closed and unscriptable)
  Supporting: a documented one-time manual verification procedure
              (specified in property-register.md, not yet performed)

Assumptions:
  - This claim *is* the assumption; nothing further underlies it.

Status model — Type vs. Verification state, tracked as two separate axes:
  - Type: External assumption — permanent, never changes, even after a
    successful manual check (Dragonframe's behavior stays outside
    DragonMIDI's control and could change without notice).
  - Verification state: Unverified. Would become "Manually verified
    against Dragonframe version <X>, <date>" once the procedure in
    property-register.md is run and logged — that action moves this field
    only, never the Type above.

Remaining gap / residual risk:
  No automated evidence will ever apply here. Manual verification, once
  performed and logged, moves Verification state only; it will not
  self-renew against future Dragonframe version changes (a version bump
  would move Verification state back to Unverified-for-that-version).

Assurance status: Assumption (Type: External, permanent) / Unverified
(Verification state)
Correctness-assurance.md section: § 3.5

### MAPS-004: Knob-nudge clamp bound invariant

Property (property-register.md):
  Two sub-claims. (a) In-bounds-start: given the tracked axis position
  starts within the configured [min, max] range, it stays within that
  range across any nudge sequence, and the sent delta never overshoots the
  bound. (b) Out-of-range-start: given the tracked position starts outside
  [min, max] (a realistic input, since a live Dragonframe reading can fall
  outside a user-configured range narrower than the axis's real travel),
  the resulting position, if a message is sent, is always within
  [min, max].
        ↓
Evidence (property-register.md):
  Primary:    (a) Example-tested (test_mapping.py, anchoring two historical
              bug scenarios) + property-tested (single-nudge and full
              multi-step-sequence properties over randomized ranges/deltas/
              live-or-estimate interleavings).
              (b) Property-tested (randomized out-of-range starting
              positions, both above and below the range).
  Supporting: git history of two prior fixes (81d1397, f63a84a) as named
              regression anchors for (a).

Assumptions:
  - Python float (IEEE-754 double) arithmetic behaves per IEEE-754
    semantics (correctness-assurance.md § 5.3, trusted base).

Remaining gap / residual risk:
  None. Both sub-claims are mutation-verified.

Assurance status: (a) Example-tested + Property-tested, mutation-verified.
(b) Property-tested, mutation-verified.
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
  Primary:    (1) Explicit parser guards (BundleBoundsError,
              MAX_BUNDLE_DEPTH = 8) inside decode_osc_packet itself — the
              load-bearing evidence for the bound.
              (2) Six deterministic boundary regression tests for the
              specific malformed shapes this review identified.
  Supporting: (3) hypothesis-based structured-fuzz test with a per-example
              deadline, exploring beyond the guarded/anticipated shapes.
              Existing except-Exception guard in handle_datagram (covers
              the raise case; pre-existing).

Assumptions:
  - Sender is non-adversarial in the security sense; this is a robustness
    claim, not a security claim (correctness-assurance.md § 3.3).

Remaining gap / residual risk:
  The fuzz test uses hypothesis's per-example deadline rather than a
  subprocess/watchdog execution-isolation harness — sufficient for this
  claim's scope, since the guards (not the fuzz layer) are the load-bearing
  evidence.

Assurance status: Implemented, Example-tested + Fuzz-supported,
mutation-verified.
Correctness-assurance.md section: § 3.3

### MAPS-006: Controller Profile switch state-clear completeness

Property (property-register.md):
  After set_profile(), no state from the previous profile influences any
  subsequent processing under the new profile — not merely the first call
  — even under CC-number reuse across profiles.
        ↓
Evidence (property-register.md):
  Primary:    Example-tested (test_mapping_profiles.py, first-call case) +
              property-tested: a second randomized event sequence is
              driven post-switch, and the entire output trace, call-for-
              call, is compared against a freshly constructed
              MappingEngine(profile_B) fed the same sequence, using a
              synthetic profile with a CC number deliberately reused
              across a different control role than Studio's.
  Supporting: MAP-PROFILE-004's explicit spec of set_profile's clearing
              behavior.

Assumptions:
  - reset()'s completeness, called from within set_profile — same
    invariant one level down, not separately registered.

Remaining gap / residual risk:
  None.

Assurance status: Example-tested (first-call case) + Property-tested
(full post-switch trace), mutation-verified.
Correctness-assurance.md section: § 3.2

### MAPS-007: MAP-CONFIG-003 migration-invariant evidence is circular

Property (property-register.md):
  build_opinionated_map() applied to the bundled profiles' ControlsConfig
  reproduces the pre-Phase-5 hardcoded map literals exactly.
        ↓
Evidence (property-register.md):
  Primary:    test_mapping_config_schema.py:76,81 — but circular: the
              "reference" (OPINIONATED_MAP_STUDIO/_NANOKONTROL2) is itself
              produced by the identical function call with identical
              arguments, not an independently-frozen historical literal.
  Supporting: none independent of the above.

Assumptions:
  - None.

Remaining gap / residual risk:
  No real regression protection currently exists despite a passing
  assertion. Planned fix: a known-value/golden test pinning the current
  literal output independently of build_opinionated_map's own code path.
  The true historical claim (matches pre-Phase-5 code) is separately
  unrecoverable except via a one-time git-history diff, offered as
  optional supporting work, not scheduled. Not yet put to the user for
  confirmation — listed in property-register.md's Pending user
  reconciliation table.

Assurance status: Circular (effectively Known gap despite a passing test)
→ Evidence planned (Known-value/golden test, once approved and written)
Correctness-assurance.md section: § 3.7

## Coverage check

| Property ID | Has assurance-case trace? | Has correctness-assurance.md claim row? | Discrepancy? |
|---|---|---|---|
| MAPS-001 | Yes | Yes (§ 3.6, three-row split) | None |
| MAPS-002 | Yes | Partial — general case discussed only in § 6.3, not a § 3 claim row (deliberate: an intentionally-deferred gap has no claim to make a row for) | None (expected asymmetry, explained above) |
| MAPS-003 | Yes | Yes (§ 3.5) | None |
| MAPS-004 | Yes | Yes (§ 3.1, two-row split) | None |
| MAPS-005 | Yes | Yes (§ 3.3, five-row split) | None |
| MAPS-006 | Yes | Yes (§ 3.2) | None |
| MAPS-007 | Yes | Yes (§ 3.7) | None — but note: MAPS-007 itself is still an unconfirmed candidate (see property-register.md Pending user reconciliation), unlike MAPS-001–006 which are all approved |
