# Evidence Handoff

Phase 6 artifact. Concrete next action per approved property. No property in this register calls for formal proof, so there is no LAPS handoff — see `docs/workflow.md § Phase 6` for why: none of the six are universal semantic claims over a small, cleanly-specifiable domain; property-based testing, fuzzing, and explicit-assumption/manual-verification fit better (rationale in each property's Evidence selection, `property-register.md`).

## MAPS-004 — Property-test specification: knob-nudge clamp bound

**Target:** `MappingEngine._process_bank_derived`'s knob-nudge path (`mapping.py:636-676`), via `MappingEngine.process()`.

**Framework:** `hypothesis` (already a project dependency — `.hypothesis/` cache present).

**Generators:**
- `min_value`, `max_value`: floats, including the reversed case (`min_value > max_value`) — `MAP-BANK-008` explicitly requires correct behavior here.
- A sequence of raw MIDI knob values (`event.raw_value`, 0-127) as consecutive deltas, including repeats (delta=0) and large jumps (e.g. 0→127 in one step).
- Optional presence/absence of a live `axis_positions` reading per step, and, when present, an independently-generated float for it (not derived from the internal estimate) to exercise `MAP-BANK-009`'s live-preferred-over-estimate rule under divergence between the two.

**Invariant (the oracle):** after every simulated knob event, the engine's resulting `_axis_position[fader_key]` (or the position implied by the cumulative sent deltas, whichever is easier to assert against) is within `[min(min_value, max_value), max(min_value, max_value)]` inclusive. Additionally: if the invariant required clamping, the returned `OscMessage`'s delta argument, when applied to the pre-event position, lands exactly on the bound — never past it, never short of it by more than one representable float step.

**Shrinking strategy:** `hypothesis` default shrinking is sufficient — the invariant is a simple bound check, and a minimal failing case (shortest delta sequence, simplest range) is what a fix needs.

**Regression anchors to keep:** the existing example tests covering `81d1397`/`f63a84a`'s specific historical scenarios stay as named tests alongside the new property test, not replaced by it.

## MAPS-006 — Property-test specification: Controller Profile switch isolation

**Target:** `MappingEngine.set_profile` (`mapping.py:394-409`).

**Framework:** `hypothesis`.

**Generators:**
- Two `ControllerProfile` instances (can reuse `STUDIO_PROFILE`/`NANOKONTROL2_PROFILE` plus at least one synthetic profile built via `build_profile()` with a deliberately colliding CC assignment against one of the bundled profiles, to force the adversarial case identified in `correctness-assurance.md § 3.2`).
- A randomized sequence of `MidiEvent`s under profile A (fader moves, knob nudges, button presses, Group switches) to populate engine state before the switch.
- A single `MidiEvent` to fire immediately after `set_profile(profile_B)`, chosen so its key exists under profile B.

**Invariant (the oracle):** `engine.process(post_switch_event, ...)` (and the `_websocket`/`_keystroke` variants) on the switched engine produces output identical to calling the same method on a **freshly constructed** `MappingEngine(profile_B)` fed only that one event. This is a same-process differential check against a known-clean reference object, not a second implementation — no independence classification is needed (`docs/evidence-selection.md`'s reference-classification requirement applies to differential testing against an *external* reference implementation, not this kind of internal freshness check).

**Shrinking strategy:** default; a minimal failing case is the shortest pre-switch event sequence that leaves detectable state.

## MAPS-005 — Fuzz-target specification: `decode_osc_packet` robustness

**Target:** `osc_io.py::decode_osc_packet` (and transitively `decode_osc_message`, `_read_padded_string`).

**Framework:** `hypothesis`'s `st.binary()` strategy is sufficient for a first pass (no need for a dedicated fuzzer like `atheris` given the target is pure Python and the property is "terminates," not "doesn't crash on a C extension boundary").

**Oracle:** call `decode_osc_packet(data)` inside a wall-clock timeout (e.g. `pytest-timeout` or a simple `signal.alarm`/thread-based watchdog, since this needs to bound *hangs*, not just exceptions) and a recursion-depth-safe call path (run in a subprocess or with `sys.setrecursionlimit` lowered for the test, so a stack-exhaustion case fails the test cleanly instead of crashing the test runner). Assert: the call either returns a `list[tuple[str, tuple]]` or raises within the timeout — it never hangs.

**Structured malformed-bundle strategy (in addition to pure `st.binary()`):** specifically construct `#bundle\0` framed payloads with a `hypothesis`-generated `element_size` field that is negative, zero, or larger than the remaining buffer, and with nested-bundle depth up to a few hundred — this targets the two concrete failure modes identified in `system-assurance-map.md` (non-advancing offset, unbounded recursion) directly rather than relying on unstructured fuzzing to stumble onto them.

**Fix scope (once a failing case is found):** reject non-positive `element_size` explicitly (raise, matching `decode_osc_message`'s existing `ValueError` precedent for unsupported type tags) and cap recursion depth on nested bundles with an explicit, documented constant — both changes localized to `decode_osc_packet`, no wider blast radius.

## MAPS-003 — Manual verification procedure (not automatable)

**Owner:** the user (or whoever has hands-on access to a running Dragonframe instance) — MAPS cannot execute this.

**Procedure:**
1. Load a real Dragonframe project with at least 3 axes configured, in an order that is **not** alphabetical and **not** the order the axes were originally created (to rule out coincidental agreement).
2. Launch DragonMIDI, let axis discovery complete (`getAllPosition` round-trip).
3. In the Mapping View, note the discovered axis order.
4. For each discovered axis in turn, trigger the corresponding Solo control (or Cycle, stepping through) and confirm via Dragonframe's debug log (the same `HARD STOP`-style confirmation precedent used for E-Stop, per `docs/high-level-design.md` Success Metrics) which axis actually highlighted.
5. Record the result (pass/fail per axis) in `docs/testing-strategy.md` or equivalent, dated, with the Dragonframe version used — this verification does not self-renew across Dragonframe version changes, so the record should say what version it covers.

**If it fails:** this becomes a live bug (AXn numbering diverges from OSC discovery order for some axis ordering), not just a documentation update — route back through LID for a fix design (e.g. an explicit remapping table) rather than treating it as a MAPS artifact update.

## MAPS-001 — Design-decision handoff (not an evidence task)

**Owner:** the user, via a LID pass on `docs/high-level-design.md`.

**Question to resolve:** does DragonMIDI add a third Status UI indicator ("Command channel" or similar) reflecting the WebSocket adapter's bind+connection state, fold this signal into the existing "Dragonframe signal" indicator (risk: conflates two different channels' health), or formally accept the current silent-failure behavior with explicit safety sign-off recorded somewhere durable (this document, or the HLD itself)?

**Once a design exists:** the evidence method is straightforward — a lifecycle/integration test over the small enumerable state space (unbound / bound-no-connection / bound-with-connection), matching the existing `WS-LIFECYCLE-*` test style. No property-based testing or formal proof needed; this note is here so the eventual evidence work isn't blocked on rediscovering that.

**Not MAPS's call to make:** which of the three options above is right is a product/safety decision, not an assurance-evidence decision — flagged for the user's LID pass, not decided here.

## MAPS-002 — No action scheduled (tracked, not handed off)

Deliberately deferred per `docs/llds/static-mapping.md`'s existing decision. No evidence work is scheduled. If the user later decides to revisit the deferral, the evidence method is already specified in `property-register.md` (property-based CC-collision generator) and can be handed off at that time without redoing this analysis.
