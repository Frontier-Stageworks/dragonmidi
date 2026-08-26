# DragonMIDI Correctness / Assurance Document

**Version:** current `main` (fresh MAPS pass, 2026-08-26)
**Scope:** Whole system — OSC I/O, MIDI input, mapping engine, Controller Profile loading, Preset Store, keystroke output, WebSocket output. App UI layout/rendering excluded except where it affects an assurance claim.
**Repository:** `/Users/markstalzer/github/dragonmidi`
**Companion documents:** `property-register.md`, `evidence-matrix.md`, `assurance-case.md`

## 1. Purpose and Scope

This document states what can currently be claimed about DragonMIDI's correctness, on what basis, and where confidence stops. There is no formal proof or model-checked component anywhere in this system — every claim below rests on tests (example, property-based, or fuzz), structural enforcement paired with boundary verification, or explicit manual verification. No claim in this document should be read as "formally verified."

Existing test coverage is substantial (a large example-test suite across every module) but requirement-to-test traceability has not been measured — this document says "substantial existing test coverage" where that's what was actually checked, not a coverage-fraction claim.

This document does not claim DragonMIDI is hardened against a deliberately adversarial Dragonframe peer (§5.1), does not claim `E-Stop`/WebSocket command delivery is observable when it fails (§6.1), and does not claim the synthesized opinionated map is correct against the current spec (§3.4 is evidence-pending, not established).

## 2. System Model

See `docs/high-level-design.md` and `docs/llds/*.md` for the full architecture; not re-derived here. In brief: MIDI input → Mapping Engine → one of three output adapters (OSC Client, Keystroke Output, WebSocket Output), plus an OSC Listener receiving Dragonframe's own traffic and a Preset Store persisting (Bank, Group) axis assignments. Controller Profiles (bundled or third-party YAML config files) parameterize the Mapping Engine's behavior. See `system-assurance-map.md` for trust boundaries, chokepoints, and failure paths.

## 3. Correctness / Assurance Claims

### 3.1 OSC Bundle Decoding

**Precondition(s):** none — `decode_osc_packet` is called on every received UDP datagram.
**Canonical definition(s):** "malformed bundle framing" = a declared `element_size` that is non-positive or exceeds the remaining buffer, or `#bundle` nesting depth at or beyond `MAX_BUNDLE_DEPTH` (8).
**Valid initial-state domain:** n/a — stateless per-call decode.

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| `decode_osc_packet` raises `BundleBoundsError` (not an unhandled exception, not silent corruption) for non-positive/oversized `element_size` or over-depth nesting, and decodes correctly at exactly the stated boundary | Boundedness; Error/failure semantics | `EVID-001` | Established for the named boundary conditions and for the general malformed-input space explored by the realized fuzz campaign; not a claim of exhaustive proof over all byte inputs. |

**Property being asserted:** `decode_osc_packet` never raises an unhandled exception, for any byte input.
**Evidence produced:** deterministic verification at the named boundaries (structural enforcement + verification), plus broad but deadline-bounded, sampled exploration of the general malformed-byte space (fuzz) — strong supporting evidence, not exhaustive proof over all byte inputs.

**Coverage notes:** all five claim dimensions (negative/zero/oversized `element_size`, at/over-depth nesting, general malformed-byte termination) are individually covered — see `EVID-001`'s per-dimension discharge. Structural enforcement (`MAX_BUNDLE_DEPTH`, `element_size` check) is paired with deterministic below/at/above-boundary tests, plus a hypothesis fuzz campaign with a 500ms deadline as supporting exploration. Mutation/reintroduction verified 2026-08-25 (removing either guard fails its corresponding boundary test); not re-executed since.

**Accepted / Rejected — bundle nesting depth:**
- Accepted: nesting exactly at `MAX_BUNDLE_DEPTH` (8) decodes normally.
- Rejected: nesting at depth 9 raises `BundleBoundsError` before attempting to decode the offending level.

### 3.2 Controller Profile Switch State Isolation

**Precondition(s):** `MappingEngine.set_profile()` is called with a new `ControllerProfile`.
**Canonical definition(s):** "post-switch trace" = every dispatch-relevant engine field (dedup state, Group index, per-(Bank,Group) axis targets, bank-derived tracked positions) as observed by subsequent `process()`/`process_websocket()`/`process_keystroke()` calls.
**Valid initial-state domain:** n/a — claim concerns the state immediately after the call, from any reachable prior engine state.

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| After `set_profile()` returns, the full post-switch dispatch trace is indistinguishable from a freshly-constructed engine's trace | Isolation; State-machine safety | `EVID-002` | Established — the realized property test compares the *entire* trace, not merely the first post-switch event, closing the narrower oracle that would have understated this claim. |

**Coverage notes:** oracle quantifier ("any subsequent operation") matches the claim's own wording, confirmed by inspecting the test itself, not merely the property-register description.

### 3.3 Bank-Derived Knob Clamp-to-Range

**Precondition(s):** Bank N's fader has a real axis name assigned in the active Group.
**Canonical definition(s):** "effective bounds" = the lower and higher of the two configured `min`/`max` values, regardless of which is named which.
**Valid initial-state domain:** the tracked position may start anywhere in ℝ, not only within `[min, max]` — recovery from an out-of-range start is part of this claim, not a separate one (`MAP-BANK-010`).

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| Every derived `stepPosition` send keeps the tracked axis position within `[min, max]`, for any starting position (in- or out-of-range) and any nudge sequence | Boundedness; Numeric correctness | `EVID-003` | Established for the four named dimensions (in-range clamp, out-of-range first nudge, out-of-range full sequence, interior-landing order-independence). |

**Property being asserted:** the clamp holds for arbitrary nudge sequences of arbitrary length.
**Evidence produced:** property-based testing across generated sequences plus targeted named-scenario examples — strong sampled evidence, not a universality proof.

**Evidence strength tier:** Structural enforcement + verification — the clamp formula in `_process_bank_derived` is itself the enforcement mechanism, paired with boundary/sequence/interior-point tests as its verification.

**Coverage notes:** mutation/reintroduction (2026-08-25) found and closed a real gap — a pre-existing boundary-only test could not distinguish a correct order-independent clamp formula from one missing its `sorted()` call, because a boundary-landing nudge reproduces the correct output by coincidence either way. The added interior-point test specifically discriminates this case.

**Accepted / Rejected — out-of-range recovery:**
- Accepted: a tracked position starting outside `[min, max]` is corrected toward the nearer bound on the first nudge, and every subsequent nudge behaves as the ordinary in-range case.
- Rejected: a tracked position landing exactly on the far bound on a large single nudge is not itself evidence of a defect — `MAP-BANK-008`'s reduced-delta rule permits this.

### 3.4 Opinionated Map Synthesis

**Precondition(s):** a syntactically valid `controls:` declaration for the profile.
**Canonical definition(s):** "matches the spec" = every synthesized entry's target OSC address/action, channel-match condition, and continuous-vs-one-shot framing matches what `MAP-TABLE-001/002/003/005` and `MAP-CONFIG-004/005/006/007/008` require for the profile's declared CC/channel values.
**Valid initial-state domain:** n/a — pure synthesis function.

| Dimension | Discharge |
|---|---|
| fader entries | residual gap — evidence planned |
| knob entries | residual gap — evidence planned |
| mute entries | residual gap — evidence planned |
| shared button entries (incl. Scene-button override) | residual gap — evidence planned |
| absent-key handling (`MAP-CONFIG-004`) | residual gap — evidence planned |

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| `build_opinionated_map`'s output matches the Opinionated Table/Config specs for any profile's declared controls | Functional correctness; Refinement/equivalence | `EVID-004` | **Not currently established.** The existing test (`test_mapping_config_schema.py:76,81`) compares the function's output to constants that are themselves produced by the same function call — regression/change-detection evidence only, not correctness evidence (`docs/evidence-selection.md § Self-derived snapshots are not correctness evidence`). This is the system's highest-blast-radius chokepoint with the weakest current evidence. |

**Coverage notes:** a hand-authored, spec-derived golden table is specified in `evidence-handoff.md` as the evidence plan. Until built, no dimension above is covered by evidence; this section must not be read as claiming correctness.

### 3.5 Controller Profile Config Parsing

**Precondition(s):** a `.yaml`/`.yml` file discovered in the bundled or user-local Controller Profile folder.
**Canonical definition(s):** n/a
**Valid initial-state domain:** n/a

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| A malformed config file (missing field, wrong type, malformed `controls:`, malformed YAML) is skipped with a logged warning; discovery of remaining valid files is unaffected | Error/failure semantics; Deployment/configuration safety | `EVID-005` | Established for all four named malformed-shape dimensions. |

**Coverage notes:** each dimension has its own targeted fixture (one violation at a time), confirmed discriminating by construction.

### 3.6 Preset Store Index Validation

**Precondition(s):** a persisted `~/Documents/DragonMIDI/configurations/<profile>.json` file exists and is read.
**Canonical definition(s):** valid Bank index range `[1, 8]`; valid Group index range `[1, 5]`.
**Valid initial-state domain:** n/a

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| An out-of-range Bank/Group index or malformed entry is skipped with a logged warning, rather than reaching positional Bank/Group resolution | Boundedness; Error/failure semantics | `EVID-006` | Established for the named malformed-shape dimensions; boundary-value coverage (exact `0`/`9`/`-1`/`6`, not merely clearly-invalid values) not independently confirmed — noted as a light, non-blocking check, not a tracked gap given low exposure. |

**Coverage notes:** the guard's stated purpose — closing a specific negative-indexing risk where an unvalidated `0` Bank index would resolve via Python negative indexing to the *last* Bank — is the claim's actual motivation, confirmed present in the code by direct inspection.

### 3.7 WebSocket Command Dispatch

**Precondition(s):** a control mapped to a WebSocket target undergoes a press-transition.
**Canonical definition(s):** "correctly-shaped send" = a `{"input": ...}` JSON payload matching `WS-SEND-001/002`'s encoding rules.
**Valid initial-state domain:** n/a

| Dimension | Discharge |
|---|---|
| `E-Stop` (bare trigger) encode | property test |
| ranged command encode (`select-AXn`/`jog-AXn`) | property test |
| delivery when connected | property test |
| no-connection drop | property test |

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| A press-transition on a WebSocket-mapped control sends exactly one correctly-shaped command when connected, and no send when not connected | Functional correctness; Determinism | `EVID-007` | Established for all four named dimensions, by direct inspection of `tests/test_websocket_output.py`'s content and assertions. **The test suite currently cannot be executed in this development environment** (`websockets` module not installed) — content confirmed correct by inspection, not by a passing run. |

**Coverage notes:** `E-Stop` specifically is the motion-control emergency-stop function named in the HLD's Success Metrics — this claim is what makes that function's *dispatch* trustworthy; it does not cover delivery-failure *visibility* (§6.1, a separate, deliberately-unaddressed concern).

### 3.8 Keystroke Output Stuck-Modifier Safety

**Precondition(s):** `KeystrokeOutputAdapter.send()` is called with a `KeyCombo`.
**Canonical definition(s):** n/a
**Valid initial-state domain:** n/a

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| Every modifier already pressed for a given `send()` call is released, in reverse order, even if a later press/release call in the same sequence raises | Error/failure semantics; Safety | `EVID-008` | Established for the failure points directly tested (a modifier press failing, the main key press failing, an unrecognized key lookup failing). A doubly-failing sequence (the release itself also raising) is not separately asserted — recorded as a low-priority residual gap, not blocking this claim's overall support. |

**Coverage notes:** the code's own reasoning names the consequence directly — a stuck modifier "would corrupt every subsequent real keystroke until manually cleared," worse than one missed send — this claim exists specifically to hold that guarantee to evidence.

### 3.9 Group-Switch Dispatch Precedence

**Precondition(s):** a CC collision between a Group-switch key and another control, or an ordinary Group switch/Controller Profile switch/MIDI reconnect.
**Canonical definition(s):** n/a
**Valid initial-state domain:** n/a

| Claim | Property Type | Evidence IDs | Current support |
|---|---|---|---|
| A Group-switch key wins any CC collision (`MAP-GROUP-005`); a Group switch discards dedup state only for axis-direct-mode Banks (`MAP-GROUP-011`); only a Controller Profile switch resets the active Group to 1 (`MAP-GROUP-007`) | State-machine safety; Determinism | `EVID-009` | Established via existing example-test coverage; no additional evidence judged justified (`EVID-009`). |

## 4. Structure of the Assurance Argument

| Role | Item | Catches / enforces / treats | Does NOT establish |
|---|---|---|---|
| Direct evidence | Example tests (all properties) | Specific named scenarios and boundary conditions | Behavior outside the tested cases |
| Direct evidence | Property-based tests (`DM-001`–`003`) | Broad sampled coverage of generated input/sequence spaces | Universality — sampled evidence, not proof |
| Direct evidence | Hypothesis fuzz campaign (`DM-001`) | Unstructured/adversarially-shaped malformed input, deadline-bounded | Guaranteed termination proof; bounded by the deadline and generator strategy |
| Direct evidence | Manual verification, once run (`DM-EA-002`, `DM-EA-003`) | Real-hardware/real-Dragonframe behavior no code-level test can reach | Behavior across untested hardware/firmware/Dragonframe versions |
| Enforcement mechanism | `MAX_BUNDLE_DEPTH` cap, `element_size` validation (`DM-001`) | Reduces the reachable malformed-framing failure space structurally | Correctness of the guard's boundary — that's the paired verification's job, not the guard alone |
| Enforcement mechanism | Bank/Group index bounds check (`DM-006`) | Reduces reachable negative-indexing/out-of-range failure space | Correctness of every other Preset Store field (e.g. `axis_name` referring to a real axis) |
| Meta-evidence | Mutation testing (`DM-001`, `DM-003`) | Confirms the paired tests actually discriminate correct from broken behavior | Nothing about baseline correctness by itself — discrimination only |
| Risk/assumption treatment | Explicit assumption (`DM-EA-001`, `DM-EA-002`, `DM-EA-003`) | Names what's assumed and on what basis | Nothing beyond the stated assumption — not a substitute for evidence |
| Risk/assumption treatment | Accept risk (E-Stop delivery-failure visibility, no frontmost-window check — §6.1, §6.2) | Names a known, already-decided limitation | Nothing — deliberately unaddressed by design |

**Evidence independence note:** no claim in this document currently relies on differential testing against a second implementation, so no shared-bug-risk analysis is required by `docs/evidence-selection.md § Shared-bug-risk analysis`. `DM-004`'s planned golden-table evidence is a known-value comparison against a hand-derived spec value, not a second implementation — its independence rests on the golden table never being derived from `build_opinionated_map`'s own code path (stated explicitly in `evidence-matrix.md`'s `EVID-004`), not on a differential-independence argument.

## 5. Assumptions

### 5.1 Network / Peer Trust

- Dragonframe is assumed to be a trusted local peer, not a deliberately adversarial OSC sender. `DM-001`'s guards are robustness/contract enforcement against accidental malformation, not a security boundary. **Assumption, not enforced** — Evidence state: No evidence, by design (`DM-EA-001`).

### 5.2 External System Behavior

- Dragonframe's internal `AXn` axis numbering corresponds to DragonMIDI's OSC-discovery order. **Assumption, not currently verified** — Evidence state: No evidence; a manual verification procedure is specified but not yet run (`DM-EA-002`).
- The bundled nanoKONTROL2 default CC map matches real hardware factory defaults. **Assumption, partially verified** — Evidence state: Manually verified as of 2026-07-21 against one physical unit, behaviorally (not a byte-level MIDI trace) (`DM-EA-003`).
- At most one Dragonframe client connects to the WebSocket server at a time. **Enforced within DragonMIDI's own code** (a new connection supersedes any existing `_connection`), but Dragonframe's own connection behavior is never independently confirmed to actually honor this — a minor, unregistered assumption folded into `DM-007`.

### 5.3 Operating Environment

- A synthesized keystroke is delivered to whichever application currently holds OS focus. **Not enforced at all** — no frontmost-window check exists; explicitly accepted (§6.2).

## 6. Residual Risks and Model Gaps

### 6.1 E-Stop / WebSocket delivery has no operator-visible failure signal

If the WebSocket Output Adapter fails to bind, has no active connection, or a send raises, a control mapped to `E-Stop` (or any WebSocket target) silently does nothing — logged, but with no Status UI indicator. This is a deliberate, already-made project decision (HLD: "fails silently, not as a new status indicator... deferred, not ruled out"), not a gap this document proposes to fix. Recorded here because `E-Stop` is explicitly the safety-relevant function named in the HLD's own Success Metrics.

### 6.2 No frontmost-window detection before a synthesized keystroke

A keystroke-mapped control (the jog wheel's Arc Motion Control stepping) can affect an unrelated foreground application if Dragonframe isn't OS-focused. Explicit HLD Non-Goal; accepted risk, mirrors how a physical keypress behaves.

### 6.3 Opinionated map synthesis correctness is currently unestablished

`DM-004` (§3.4) is this document's most significant open gap — the highest-blast-radius chokepoint in the mapping layer has no correctness evidence yet, only a self-referential regression check. Evidence is planned (`evidence-handoff.md`); until it lands, this document does not claim the synthesized map is correct for any profile, bundled or third-party.

### 6.4 AXn axis-identity assumption is unverified

`DM-EA-002` (§5.2) has no evidence at all yet — a wrong assumption here would silently target the wrong physical axis via `select-AXn`/`jog-AXn`/Solo, with no error. A manual verification procedure is specified (`evidence-handoff.md`) but requires hands-on access to a running Dragonframe instance and has not been executed.

### 6.5 WebSocket test evidence cannot currently be re-executed in this environment

`tests/test_websocket_output.py` (backing `DM-007`, §3.7) fails to import in this development environment because the `websockets` package is not installed. Its content is confirmed correct by direct inspection, but it cannot currently be re-run to confirm it's still green after any future change to `websocket_output.py`. Not a code defect; an environment gap.

### 6.6 Pre-existing test flake, unrelated to any claim in this document

`test_listener_resends_discovery_query_on_rebind` was observed flaky and confirmed (via `git stash`) to fail identically on the unmodified codebase — out of scope for this MAPS pass, but noted so a future reader doesn't mistake it for evidence against any claim above.

## 7. Trusted Base

- **Python runtime, `mido`/`python-rtmidi`, `pynput`, `websockets`, `PySide6`** — this document does not independently verify these libraries' own correctness; a defect in any of them could invalidate a claim that depends on it (e.g., `mido`'s MIDI parsing underlies every claim about correct dispatch).
- **Operating system (macOS/Windows) keyboard/accessibility APIs** — `DM-008`'s claim assumes the OS itself correctly delivers press/release calls to the intended target once `pynput` issues them.
- **Local network/UDP stack** — `DM-001`'s and `DM-EA-001`'s scope assumes ordinary OS-level UDP delivery semantics, not an attacker positioned to spoof or flood at the network layer.
- **`hypothesis`** (property-based/fuzz testing library) — `DM-001`'s and `DM-003`'s property/fuzz evidence relies on its generator/shrinking correctness.

## 8. Summary of Guarantees

- OSC bundle decoding rejects malformed framing (non-positive/oversized `element_size`, over-depth nesting) via a well-typed error, verified at and around the stated boundaries, with supporting fuzz exploration (§3.1).
- A Controller Profile switch fully isolates subsequent dispatch from the previous profile's state, verified across a full post-switch trace, not just the first event (§3.2).
- Bank-derived knob nudges keep the tracked axis position within its configured range, including recovery from an out-of-range starting position, verified by property tests and mutation-confirmed to actually discriminate a broken clamp formula (§3.3).
- **Opinionated map synthesis correctness is not currently established** — this document does not claim `build_opinionated_map`'s output is correct against the spec for any profile (§3.4, §6.3).
- Malformed Controller Profile config files and malformed Preset Store entries are rejected without affecting other valid data (§3.5, §3.6).
- WebSocket-targeted commands (including `E-Stop`) encode and dispatch correctly when connected, and are dropped (not queued or errored) when not — but a delivery failure produces no operator-visible signal (§3.7, §6.1).
- Keystroke synthesis releases every pressed modifier even on a mid-sequence failure, for the failure points directly tested (§3.8).
- Group-switch dispatch precedence and dedup-discard rules hold per existing coverage (§3.9).
- Dragonframe is trusted as a local peer, not defended against as adversarial (§5.1); AXn axis identity is assumed but unverified (§5.2, §6.4); the nanoKONTROL2 default CC map is verified once, behaviorally, against one physical unit (§5.2).

## 9. Correctness Claim Taxonomy

| Property Type | Definition | Primary Sections |
|---|---|---|
| Safety | Something bad never happens | §3.8 |
| Boundedness | Resource usage / a tracked value doesn't grow without bound / leave its range | §3.1, §3.3, §3.6 |
| Isolation | State for one entity doesn't bleed into another | §3.2 |
| State-machine safety | Transitions/dispatch precedence behave as specified | §3.9 |
| Determinism | Same input always produces same output | §3.7, §3.9 |
| Functional correctness | Output matches the specified behavior for given input | §3.4, §3.7 |
| Refinement/Equivalence | A derived artifact matches its specification | §3.4 |
| Error/failure semantics | Malformed input produces the specified failure behavior, not undefined behavior | §3.1, §3.5, §3.6, §3.8 |
| Deployment/configuration safety | External configuration input can't corrupt the running system | §3.5 |
