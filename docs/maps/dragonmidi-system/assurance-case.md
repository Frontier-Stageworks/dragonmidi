# Assurance Case

Structured traceability counterpart to `correctness-assurance.md`. One trace per property in `property-register.md`.

## Traces

### MAPS-001: E-Stop delivery observability

Property (property-register.md):
  The operator has some way to determine whether the WebSocket E-Stop path is
  currently deliverable, without physically testing it.
        ↓
Evidence (property-register.md, merged evidence-matrix fields):
  Primary:    none — no implementation exists
  Supporting: none

Assumptions:
  - None yet applicable — no design exists to state assumptions against.

Remaining gap / residual risk:
  Entire property is an open design gap. Requires an LID-level decision
  (revise HLD Non-Goal "no third status indicator") before any evidence
  method can be selected. Highest-consequence item in the register, least
  evidenced. See correctness-assurance.md § 6.1.

Assurance status: Known gap
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
  design — not scheduled for closure by this MAPS pass. Tracked per user
  request 2026-08-25, not unilaterally closed (would reverse an existing
  LLD decision). See correctness-assurance.md § 6.3.

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

Remaining gap / residual risk:
  Terminal — no automated evidence will ever apply here. Manual
  verification, once performed and logged, is the correct terminal action;
  it will not self-renew against future Dragonframe version changes.

Assurance status: Assumption
Correctness-assurance.md section: § 3.5

### MAPS-004: Knob-nudge clamp bound invariant

Property (property-register.md):
  Tracked axis position after any nudge sequence always stays within the
  configured [min, max] range; sent delta never overshoots the bound.
        ↓
Evidence (property-register.md):
  Primary:    Example-tested today (test_mapping.py); property-based test
              planned (generated delta sequences × live/estimate
              interleavings × reversed min/max ranges) — not yet written
  Supporting: git history of two prior fixes (81d1397, f63a84a) as named
              regression anchors

Assumptions:
  - Python float (IEEE-754 double) arithmetic behaves per IEEE-754
    semantics (correctness-assurance.md § 5.3, trusted base).

Remaining gap / residual risk:
  Until the property test is written, coverage is limited to the specific
  scenarios past bugs already revealed — not the general input space.
  Ready for direct Phase 6 handoff (property-test spec), no LAPS
  involvement needed.

Assurance status: Example-tested; Evidence planned (Property-tested, once written)
Correctness-assurance.md section: § 3.1

### MAPS-005: decode_osc_packet malformed-bundle robustness

Property (property-register.md):
  decode_osc_packet terminates (returns or raises) within bounded time and
  stack depth for arbitrary byte input.
        ↓
Evidence (property-register.md):
  Primary:    none yet — fuzz harness (hypothesis-based) planned, not
              written
  Supporting: existing except-Exception guard in handle_datagram (covers
              the raise case only, not the hang case)

Assumptions:
  - Sender is non-adversarial in the security sense; this is a robustness
    claim, not a security claim (correctness-assurance.md § 3.3).

Remaining gap / residual risk:
  Currently the least-evidenced approved property in the register — flagged
  explicitly rather than citing existing exception-guard tests as if they
  covered a case they structurally cannot reach. Approved for hardening
  2026-08-25 (overrides the code's own prior "trusted peer" framing).

Assurance status: Known gap → Evidence planned
Correctness-assurance.md section: § 3.3

### MAPS-006: Controller Profile switch state-clear completeness

Property (property-register.md):
  After set_profile(), no state from the previous profile influences
  subsequent processing under the new profile, even under CC-number reuse
  across profiles.
        ↓
Evidence (property-register.md):
  Primary:    Example-tested today (test_mapping_profiles.py); property-
              based test planned (adversarial CC-collision profile pairs,
              differential-against-a-fresh-instance oracle) — not yet
              written
  Supporting: MAP-PROFILE-004's explicit spec of set_profile's clearing
              behavior

Assumptions:
  - reset()'s completeness, called from within set_profile — same
    invariant one level down, not separately registered.

Remaining gap / residual risk:
  Not confirmed whether existing tests specifically exercise the
  CC-number-reuse-across-profiles adversarial case, which is the only
  scenario where an incomplete clear is actually observable. Planned
  property test targets exactly this case. Ready for Phase 6 handoff
  alongside MAPS-004.

Assurance status: Example-tested; Evidence planned (Property-tested, once written)
Correctness-assurance.md section: § 3.2

## Coverage check

| Property ID | Has assurance-case trace? | Has correctness-assurance.md claim row? | Discrepancy? |
|---|---|---|---|
| MAPS-001 | Yes | Yes (§ 3.6) | None |
| MAPS-002 | Yes | Partial — general case discussed only in § 6.3, not a § 3 claim row (deliberate: an intentionally-deferred gap has no claim to make a row for) | None (expected asymmetry, explained above) |
| MAPS-003 | Yes | Yes (§ 3.5) | None |
| MAPS-004 | Yes | Yes (§ 3.1) | None |
| MAPS-005 | Yes | Yes (§ 3.3) | None |
| MAPS-006 | Yes | Yes (§ 3.2) | None |
