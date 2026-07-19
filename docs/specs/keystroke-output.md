# Keystroke Output Adapter — EARS Specs

Traces to `docs/llds/keystroke-output.md`.

## Sending a Combo

- [x] **KEY-SEND-001**: When `KeystrokeOutputAdapter.send(combo)` is called, the system shall press each modifier in `combo.modifiers`, then press and release `combo.key`, then release each modifier, reproducing the press/release shape of a real keyboard chord.
- [x] **KEY-SEND-002**: If pressing or releasing the key, or any modifier, raises an exception during `send()`, the system shall still release every modifier that was pressed, via a cleanup path that runs regardless of where the failure occurred.
- [x] **KEY-SEND-003**: If sending a combo fails for any reason (backend exception, unrecognized modifier or key name, or any other error), the system shall catch and log the failure rather than raise it out of `send()`, and shall not crash or interrupt other MIDI or OSC processing.
- [x] **KEY-SEND-004**: The system shall not debounce or deduplicate calls to `send()` — each call performs its full press/release sequence independent of timing since the previous call or whether the combo is identical to the previous one.
- [x] **KEY-SEND-005**: The system shall not verify that Dragonframe, or any specific application, is the OS-focused application before calling the backend to send a combo.
- [x] **KEY-SEND-006**: The system shall not attempt to detect or pre-validate OS-level input permission (e.g. macOS Accessibility access) before calling `send()`; a permission failure is handled solely via `KEY-SEND-003`.

## Backend

- [x] **KEY-BACKEND-001**: The system shall abstract keystroke sending behind a `KeystrokeBackend` protocol with a swappable concrete implementation, enabling a fake backend to be substituted in tests without touching real OS input.

## References

- `docs/llds/keystroke-output.md`
