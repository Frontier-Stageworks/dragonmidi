# Evidence Handoff

Phase 7 artifact. The downstream implementer is LID (`CLAUDE.md` declares `## LID Mode: Full`) — MAPS specifies; it does not implement.

**Not every approved property appears here.** `DM-001`, `DM-002`, `DM-003`, `DM-005`, `DM-006`, `DM-EA-003` have realized evidence with no open residual gap requiring action — see `property-register.md`/`evidence-matrix.md`. `DM-009` and `DM-EA-001` concluded "additional evidence: none justified" (`evidence-matrix.md` `EVID-009`, `EVID-010`) — that conclusion lives there, not here.

## Gap disposition routing

| Property / gap | Gap disposition | Block used below |
|---|---|---|
| `DM-004` | Produce evidence | Generic evidence-work specification (known-value/golden testing) |
| `DM-007`, environment-platform validation gap | Resolve through LID/design | Design-decision handoff (light — dependency install, not a design choice) |
| `DM-008`, doubly-failing-`release()` gap | Defer | No action scheduled |
| `DM-EA-002` | Manual/operational verification | Manual verification procedure |

## Generic evidence-work specification

### DM-004 — Known-value/golden testing specification: Opinionated map synthesis

```text
Evidence purpose: correctness
Evidence ID: EVID-004
Claim / uncertainty addressed: does build_opinionated_map's output, for a
  profile's declared controls, actually match what MAP-TABLE-001/002/003/005
  and MAP-CONFIG-004/005/006/007/008 require — independent of what the
  function itself currently produces?
Oracle: a hand-authored golden table, one per bundled profile (Studio,
  nanoKONTROL2), derived directly from the spec text above and each profile's
  own declared CC/channel numbers.
Oracle authority: high — computed by a human from the current specification,
  never from build_opinionated_map, OPINIONATED_MAP_STUDIO/_NANOKONTROL2 (both
  produced by the function under test), or git history (repository history is
  opt-in only per SKILL.md § Repository history, and this claim does not
  depend on any historical fact — the current spec text is the authority).
Important blind spot: any Opinionated Table requirement not represented in
  the hand-derived table stays uncovered even after this evidence lands —
  the claim-dimension list below must be complete, not merely plausible.
Expected assurance gain: this becomes the first evidence for this claim that
  could actually fail if the implementation were wrong; the existing test
  (test_mapping_config_schema.py:76,81) cannot, by construction.
```

**Direct-evidence method:** Known-value/golden testing.

**Target and environment:** `mapping.py::build_opinionated_map`, called with `STUDIO_CONTROLS`/`has_scene_button=True` and `NANOKONTROL2_CONTROLS`/`has_scene_button=False`.

**Procedure:**
1. From `docs/specs/static-mapping.md`'s Opinionated Table and Bank Derivation sections plus each profile's declared `controls:` CC/channel values, hand-derive the complete expected mapping table for both bundled profiles: all 8 fader entries, all 8 knob entries, all 8 mute entries, and every shared-button/transport entry (including the Studio's Scene-button override). Write these as literal Python dicts directly in the test file — never by calling `build_opinionated_map`, and never by importing `OPINIONATED_MAP_STUDIO`/`_NANOKONTROL2`.
2. Add a dedicated case for `MAP-CONFIG-004` (absent-key handling): a synthetic minimal `controls:` declaration omitting one optional key (e.g. `next_track`), asserting no row is produced for it.
3. Assert `build_opinionated_map(...)` equals the corresponding hand-derived table, for each bundled profile.

**Decision criterion:** exact dict equality between `build_opinionated_map`'s output and the hand-derived table, for both profiles and the absent-key case.

**Artifact/result to record:** the new golden-table test file/function names, plus a note in `property-register.md`'s `DM-004` entry once evidence lands.

**Freshness/revalidation trigger:** re-derive the golden table whenever `MAP-TABLE-*`, `MAP-CONFIG-004..008`, or either bundled profile's declared `controls:` values change.

**Discrimination / anti-vacuity challenge (required — high-value claim):** deliberately alter one entry in each of `_fader_entries()`, `_knob_entries()`, `_mute_entries()`, `_shared_button_entries()` (e.g. shift a target CC/address by one) and confirm the golden test fails; revert and confirm it passes again. This establishes the golden test discriminates a broken implementation from a correct one — it does not, by itself, establish the golden values were correct in the first place; that rests on the hand-derivation in step 1, not on this challenge.

**LID entry point:** Phase 5 (tests-first) — `MAP-CONFIG-004`, `MAP-TABLE-001/002/003/005` already exist as EARS requirements; no LLD/EARS change needed first.

## Design-decision handoff

### DM-007 — Design-decision handoff (dependency, not a design choice)

**Owner:** whoever maintains the dev environment / CI configuration for this repository.

**Gap type:** Environment-platform validation gap.

**Question to resolve:** `tests/test_websocket_output.py` fails to import in this development environment because the `websockets` package is not installed. Install/pin `websockets` as a declared dev dependency (or confirm it already is one and the environment is out of sync) so the test suite backing `DM-007` can actually be executed, not merely inspected.

**Once resolved:** re-run `tests/test_websocket_output.py` to confirm it's still green; update `DM-007`'s Freshness in `property-register.md`/`evidence-matrix.md` from "stale — renewal needed" to "current," and remove this residual gap.

**Not MAPS's call to make:** this is dev-environment/dependency-management housekeeping, not an assurance-argument decision — recorded here only because it currently blocks re-executing `DM-007`'s evidence.

## No action scheduled

### DM-008 — No action scheduled (doubly-failing-`release()` ordering)

**Gap type:** Evidence missing.
**Gap disposition:** Defer.
**Owner / sign-off (Accept risk only):** n/a — this is Defer, not Accept risk.
**Revisit trigger:** a real-world report of a stuck-modifier incident, or `KeystrokeOutputAdapter.send()`'s `finally`-block logic being touched for an unrelated reason (at which point re-verifying this ordering is cheap to add to the same change).

**Disposition:** Defer.
**Basis:** `DM-008`'s primary claim (release on a *single* failing call) is already established; this gap concerns only a doubly-failing sequence (the release itself also raising), judged low-value given the property's overall Priority: medium and the backend-failure path already being rare.
**Owner / revisit trigger:** see above.
**Future direct-evidence plan:** if revisited, extend `FakeKeystrokeBackend` (`tests/test_keystroke_output.py`) to fail on both press and release for the same key, and assert the remaining modifiers still release in order.

## Manual / non-automatable verification procedure

### DM-EA-002 — Manual verification procedure (not automatable)

```text
Evidence purpose: operational
Evidence ID: EVID-011
Claim / uncertainty addressed: does Dragonframe's internal AXn axis numbering
  correspond to DragonMIDI's OSC-discovery order, for a real project with a
  non-trivial axis ordering?
Oracle: Dragonframe's own debug log, reporting which axis was actually
  affected by a triggered Solo/Cycle control.
Oracle authority: fully independent — produced by Dragonframe itself, no code
  path shared with DragonMIDI.
Important blind spot: a passing result confirms correspondence for the one
  project/axis-ordering tested, not for every possible ordering going forward
  — see "Does not self-renew" below.
Expected assurance gain: this would be the first evidence of any kind for
  this claim; currently no evidence exists.
```

**Owner:** the user, or whoever has hands-on access to a running Dragonframe instance — MAPS cannot execute this.

**Procedure:**
1. Load a real Dragonframe project with at least 3 axes configured, in an order that is **not** alphabetical and **not** the order the axes were originally created (to rule out coincidental agreement).
2. Launch DragonMIDI, let axis discovery complete (`getAllPosition` round-trip).
3. In the Mapping View, note the discovered axis order.
4. For each discovered axis in turn, trigger the corresponding Solo control (or Cycle, stepping through) and confirm via Dragonframe's debug log which axis actually highlighted.
5. Record the result (pass/fail per axis) in `docs/testing-strategy.md` or equivalent, dated, with the Dragonframe version used.

**Recording:** the dated, version-scoped record above becomes this property's Freshness anchor — Evidence state moves to "Manually verified (as of `<version>`, `<date>`)" and Freshness to "current" once logged.

**Does not self-renew:** a future Dragonframe version change moves Freshness to "stale — renewal needed," not silently "current" — the check must be re-run against the new version.

**If it fails:** this becomes a live bug (AXn numbering diverges from OSC discovery order for some axis ordering), not just a documentation update — route back through LID for a fix design (e.g. an explicit remapping table) rather than treating it as a MAPS artifact update.
