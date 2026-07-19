# Keystroke Output Adapter

## Context and Design Philosophy

A narrow, secondary output path alongside OSC (`docs/llds/osc-io.md`'s Client), for the small set of Dragonframe functions the Mapping Engine needs to drive that have no OSC message at all — confirmed for Arc Motion Control's frame stepping ("Step Moco Forward"/"Step Moco Back"), reachable only through Dragonframe's own Hot Keys preferences (`docs/high-level-design.md § Problem`).

This component's only job is: given a key combination, synthesize the equivalent OS-level keystroke. It does not know why a given combo was chosen, does not track Dragonframe's actual configured Hot Key bindings, and does not verify Dragonframe is the OS-focused application before sending — synthesizing a keystroke behaves exactly like a real keypress in that respect, landing wherever OS focus currently is (`docs/high-level-design.md § Non-Goals`).

## Interface

```python
@dataclass(frozen=True)
class KeyCombo:
    modifiers: frozenset[str]  # e.g. frozenset({"alt", "shift"})
    key: str                   # e.g. "right", "left"
```

`KeyCombo` lives in `events.py` alongside `MidiEvent`/`OscMessage`, since it's a shared data type between the Mapping Engine (producer) and this adapter (consumer) — mirroring how `OscMessage` is shared between the Mapping Engine and the OSC Client.

```python
class KeystrokeBackend(Protocol):
    def press(self, key: str) -> None: ...
    def release(self, key: str) -> None: ...

class KeystrokeOutputAdapter:
    def __init__(self, backend: KeystrokeBackend) -> None: ...
    def send(self, combo: KeyCombo) -> None: ...
```

`KeystrokeBackend` is deliberately low-level (single `press`/`release` per key, matching `pynput.keyboard.Controller`'s own shape) rather than one opaque `press_combo(modifiers, key)` call — the press-order and guaranteed-modifier-release sequencing described below lives in `KeystrokeOutputAdapter.send()` itself, not duplicated inside every backend implementation, so it can be verified against a plain recording fake without needing `pynput` present or any real OS input in tests.

A `Protocol` + concrete-backend split, matching `midi-input.md`'s `MidiBackend`/`MidoBackend` pattern — keeps the domain logic (which combo to send, when) decoupled from the OS-level library, and swappable for a fake backend in tests.

**No lifecycle/shutdown method.** Unlike `MidiInputAdapter`/`OscClient`/`OscListener`, this adapter holds no persistent OS resource (no open socket or port) — each `send()` is a self-contained, fire-and-forget sequence of OS key events through `pynput.keyboard.Controller`. It is not part of `app.py`'s shutdown sequence and needs no `close()`/`disconnect()` counterpart.

## Sending a Combo

- **Press order**: all modifiers down (in `modifiers` iteration order — order has no observable effect for the modifier sets this app produces, since OS key-chord semantics don't depend on modifier press order), then the key down, then the key up, then all modifiers up (reverse order). This is the standard chord shape a real keyboard produces for a shortcut like Option+Shift+Right.
- **Modifiers are always released, even if the key press fails.** The modifier-down and key-down/up steps are wrapped so that a failure partway through (the key press raising, or the backend disappearing) still runs the modifier-up steps in a `finally` — the alternative, leaving a modifier "stuck" down at the OS level, would silently corrupt every subsequent real keystroke the user makes until they manually tap the stuck modifier, a far worse failure mode than a single missed synthesized shortcut.
- **Failures are caught and logged, not raised.** A missing macOS Accessibility grant, a missing Windows permission, an unrecognized modifier/key string the real backend doesn't know how to translate, or any other backend failure is swallowed the same way `midi-input.md`'s Native Mode SysEx sends already are — this is a narrow, secondary output path and one failed send must not crash the app or interrupt MIDI/OSC processing. Per the HLD's decision, this does not yet surface as a Status UI indicator; it is logged only.
- **No debounce or dedup at this layer.** `send()` performs the full press/release sequence on every call, independent of how recently it was last called or whether the combo is identical to the previous one — mirroring `static-mapping.md`'s `MAP-JOG-004` (the jog wheel's OSC output has no debounce/dedup either), so a fast spin of the jog wheel produces one keystroke per detent in lockstep with one OSC message per detent, not a throttled subset of either.
- **Synchronous, on the same thread as the OSC send.** Called from the same MIDI-event-drain tick that already sends the OSC message for the same physical event (see `app.py`'s `_process_midi_event`, which will call both `MappingEngine.process()` and `MappingEngine.process_keystroke()` for the same event). No new thread or queue — `press`/`release` are expected to return promptly, the same assumption already made about OSC's `sendto`.

## Backend

- **`pynput`**, chosen over hand-written per-OS code (`Quartz`/`CGEvent` on macOS, `SendInput` via `ctypes` on Windows) — one dependency covers both target platforms, matching the project's existing preference for validated, portable libraries (`docs/high-level-design.md § Key Design Decisions`).
- The real backend wraps `pynput.keyboard.Controller`, translating this component's string-named modifiers/keys (`"alt"`, `"shift"`, `"right"`, `"left"`) into `pynput.keyboard.Key` members and calling the Controller's own `.press`/`.release`. The string-keyed domain model exists so `mapping.py` and this adapter's tests don't need to import or know about `pynput` types directly — only the real backend implementation does. An unrecognized string (not one of the names this app produces) is a backend-level lookup failure, caught by `send()`'s existing failure handling like any other backend error.
- **No permission-check or pre-flight.** This component does not attempt to detect whether macOS Accessibility access (or the Windows equivalent) has been granted before calling `press`/`release` — it simply calls the backend and catches whatever failure results, per the "failures are caught and logged" rule above. Detecting the permission state ahead of time would require its own platform-specific code for a benefit already covered by graceful failure.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Library | `pynput` | Native `Quartz`/`CGEvent` (macOS) + `SendInput` via `ctypes` (Windows) | One dependency, one code path, for both target platforms — matches the existing MIDI/UI library choices' rationale |
| Domain model | String-named `KeyCombo` (modifiers + key), translated to `pynput` types only inside the real backend | Pass `pynput.keyboard.Key` objects directly through the Mapping Engine | Keeps the Mapping Engine and its tests free of a hard `pynput` dependency, mirroring `MidiEvent`'s independence from `mido` types |
| Backend abstraction | `Protocol` + swappable backend, real (`pynput`) and fake (tests) | Call `pynput` directly from `KeystrokeOutputAdapter` | Matches `MidiBackend`/`MidoBackend`; needed for deterministic tests that don't touch real OS input |
| Failure handling | Catch and log; never raise out of `send()` | Propagate the exception | This is a narrow secondary output path (HLD); a failure here must not interrupt MIDI/OSC processing for the rest of the app |
| Stuck-modifier prevention | Modifier-up steps run in a `finally`, unconditionally | Best-effort press/release with no failure handling | A stuck modifier corrupts every subsequent real keystroke until manually cleared — a much worse failure than one missed synthesized shortcut |
| Permission pre-flight | None | Detect Accessibility/permission state before sending, surface a dedicated warning | No platform API queried is simpler than one that is; graceful failure on the actual `press_combo` call already covers the "it didn't work" case, just without advance warning |
| Frontmost-app check | None — matches the HLD's Non-Goal | Query the OS for the focused app and skip sending if it isn't Dragonframe | Decided at the HLD level: mirrors how a real keypress already behaves, and avoids new per-OS focus-detection code for a self-evident, narrow risk |
| Threading | Synchronous call on the MIDI-event-drain tick, no new thread/queue | A dedicated keystroke-send thread/queue | `press`/`release` are expected to return promptly, same assumption as the OSC Client's `sendto`; no evidence yet that it needs its own concurrency model |
| Backend granularity | Low-level `press(key)`/`release(key)`, sequencing owned by `KeystrokeOutputAdapter` | One opaque `press_combo(modifiers, key)` call per backend | Keeps the ordering and guaranteed-cleanup logic (`KEY-SEND-001`/`002`) in one place, testable against a plain recording fake, instead of duplicated inside every backend implementation |

## Open Questions & Future Decisions

### Deferred

1. Whether a failed keystroke send should eventually surface on the Status UI (a third indicator, or folded into an existing one) is deferred per the HLD's decision — revisit if more mapping entries come to depend on keystroke output and silent failure becomes a real support problem.
2. Whether to detect and warn about missing OS-level input permissions ahead of the first send (rather than only failing silently on use) is deferred — not needed for the single jog-wheel use case in this phase.

## References

- `docs/high-level-design.md § Approach` and `§ Key Design Decisions` — the decision to add this as a secondary output path, library choice, and the no-status-indicator / no-frontmost-check scope decisions.
- `docs/llds/midi-input.md` — source of the `Backend` Protocol + concrete-adapter pattern this LLD reuses.
- `docs/llds/static-mapping.md § Jog Wheel Frame Stepping` — the first (and, in this phase, only) consumer of this component.
