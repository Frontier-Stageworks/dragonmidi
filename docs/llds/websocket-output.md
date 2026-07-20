# WebSocket Output Adapter

## Context and Design Philosophy

A third, narrower output path alongside OSC (`docs/llds/osc-io.md`) and Keystroke (`docs/llds/keystroke-output.md`), for the small set of Dragonframe functions reachable only through Dragonframe's own outbound WebSocket connection — `E-Stop`, `select-AXn`, `jog-AXn` (`docs/high-level-design.md § Problem`).

Unlike the OSC Client and Keystroke Output Adapter, this component is a server, not a sender: Dragonframe initiates the connection, at its own startup, to a fixed well-known port. This component's only job is to accept that connection and, on a mapped MIDI event, send the corresponding `{"input": "<name>"}` JSON command over it. It does not implement the general command/discovery protocol Dragonframe's connection is capable of — no `replaceInputList`/`setInputColor` parsing, no dynamic input list, no multi-client support (`docs/high-level-design.md § Non-Goals`).

## Interface

```python
@dataclass(frozen=True)
class WebSocketCommand:
    input: str
    operation: str = ""
    params: tuple = ()
```

`WebSocketCommand` lives in `events.py` alongside `MidiEvent`/`OscMessage`/`KeyCombo` — a shared data type between the Mapping Engine (producer) and this adapter (consumer).

```python
class WebSocketOutputAdapter:
    def __init__(
        self,
        hosts: tuple[str, ...] = ("127.0.0.1", "::1"),
        port: int = 59177,
        on_bind_result: "Callable[[bool], None] | None" = None,
    ) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def send(self, command: WebSocketCommand) -> None: ...
```

Matches `OscListener`'s start/stop lifecycle shape, not `KeystrokeOutputAdapter`'s (which holds no persistent OS resource) — this component owns a bound server socket for the app's lifetime. `on_bind_result` mirrors `OscListener`'s constructor parameter of the same name and meaning.

## Lifecycle

- **`start()` is synchronous and blocks until the bind attempt is fully known**, matching `OscListener.start()`'s contract exactly — it does not return while binding is still in flight. Internally, `start()` spawns the background thread, then blocks on a `threading.Event` that the thread sets immediately after the bind attempt (both addresses) succeeds or fails; only after that does `start()` return. `on_bind_result(True/False)` is called (from the background thread, before the event is set) with the outcome, the same signal shape `OscListener` already gives its caller.
- **Binding both addresses is all-or-nothing.** `websockets.serve()` is called once with `hosts` as a list, relying on `asyncio`'s own multi-host `create_server` semantics: if one address fails to bind, any socket already opened for the other is closed and the whole attempt is treated as a single failure (`on_bind_result(False)`) — no separate "partially bound" state exists. A degraded state where only one of the two loopback addresses is reachable would depend on how this specific machine resolves `localhost`, an unreliable and undebuggable condition not worth exposing as a distinct outcome.
- **`start()` is idempotent.** Calling it while already started is a no-op (logged, does not attempt a second bind or spawn a second thread) — checked via whether the background thread/loop reference is already set.
- **`stop()` is idempotent.** Calling it when never started, or after a failed `start()`, or a second time after it already ran, is a no-op — checked via the same reference being unset.
- **`stop()` blocks briefly, bounded well under `app.py`'s 5-second shutdown-step budget (`docs/llds/app-ui.md` / `shutdown.py`).** It signals the event loop to close the active connection and stop, then joins the background thread with an internal ~1-second timeout. If that internal join times out, `stop()` logs a warning and returns anyway rather than blocking further — the thread is a daemon thread (like `OscListener`'s), so it cannot prevent process exit even if abandoned; `run_shutdown_sequence`'s own outer timeout-and-isolate behavior is therefore a backstop, not the only protection.
- **`start()`/`stop()` are called only from the app's main (Qt) thread**, the same convention `OscListener`/`MidiInputAdapter` already follow (`app.py`'s `__init__`/`closeEvent`) — stated explicitly here since, unlike `send()`, no cross-thread guard is implemented for these two calls; concurrent `start()`/`stop()` calls from multiple threads is not a supported usage.

## Connection Handling

- Binds both `127.0.0.1` and `::1` on the given port, at `start()` — not `0.0.0.0`. Dragonframe's own outbound connection to `localhost` resolves to the IPv6 loopback address; an IPv4-only bind misses it.
- Accepts a connection only at path `/com.dzed.dragonframe/DragonframeConnection`, enforced via `websockets`' handshake-rejection hook (`process_request`), which returns an HTTP 404 for any other path before a WebSocket connection is ever established. Dragonframe is the only client this component expects. Each rejection is logged once, at debug level, with the requested path and remote address — no spam suppression, since this is a loopback-only server with no realistic exposure to repeated hostile probing.
- **At most one active connection is tracked, held as a single reference mutated only from code running on the adapter's own event loop thread** — the accept handler that assigns a new connection and the `send()` coroutine that reads it both run there; nothing outside that thread touches the reference directly. Because `asyncio` runs one coroutine step at a time on a single thread, and the "become the active connection" assignment is a single statement with no `await` inside it, this reference can never be read mid-update — no lock is needed.
- **A new connection replaces the previously active one, and the old connection is explicitly closed** (not merely dereferenced) at the moment of replacement — matches Dragonframe's own reconnect behavior (it closes its old connection before opening a new one) and avoids leaving a stale server-side connection object open after Dragonframe has already moved on.
- Concurrent handshake attempts are serialized by the same single-threaded event loop that owns the connection reference — only one accept handler body runs at a time, so two near-simultaneous connection attempts (e.g., during a Dragonframe restart) cannot race on which one "wins" as the active connection; whichever's handler completes its replacement statement second is the one left active.
- Every message Dragonframe sends after connecting (`{"status":"ok"}`, `replaceInputList`, `setInputColor` echoes) is received and discarded. This component tracks connection presence only, not message content, matching `docs/high-level-design.md § Non-Goals`.
- No liveness/last-activity signal is derived from this connection for the Status UI — matches the HLD's decision that WebSocket output has no dedicated indicator, silent-fail only.

## Sending a Command

- `send(command)` encodes `command` as newline-delimited JSON and writes it to the currently active connection, if any.
- `operation`/`params` are omitted from the encoded JSON when they hold their defaults (`""`/`()`) — matches the bare `{"input": "<name>"}` shape confirmed for trigger commands; only ranged/incremental commands (`jog-AXn`) need the full three-key shape.
- **`send()` checks, on the calling thread, whether the event loop is currently running before doing anything else.** If it isn't — never started, `start()` failed to bind, or `stop()` has already run — the call is logged and dropped immediately, without touching `asyncio.run_coroutine_threadsafe` at all. This gives pre-start, post-bind-failure, and post-stop calls the identical observable behavior as "started but no client connected yet": logged and dropped, never a different exception shape.
- If the loop is running but there is no active connection, the scheduled coroutine finds none and drops the send the same way — logged, not queued, not retried. Matches Keystroke output's silent-fail precedent (`docs/high-level-design.md § Key Design Decisions`); Dragonframe reconnects on its own when it regains OS focus, outside this component's control.
- A failure during the write itself (connection drops mid-send) is caught and logged the same way, not raised — a failed WebSocket send must not interrupt MIDI/OSC/Keystroke processing for the rest of the app, matching the principle `keystroke-output.md`'s `KEY-SEND-003` establishes for its own output path.
- **A `send()` that arrives after `stop()` has begun (but before the loop is fully torn down) is treated as "loop not running"** — `stop()` flips its own internal flag before initiating shutdown, and `send()`'s pre-check reads that same flag, so a send racing the start of shutdown is dropped cleanly rather than being scheduled against a loop that may close before the write runs.
- **Sends already scheduled before `stop()` began are not explicitly drained or waited on individually.** `stop()` gives the loop a brief window to process anything already queued as part of its own shutdown sequence (closing the connection, canceling remaining tasks) within `stop()`'s internal ~1-second join timeout, but delivery of a send issued right as shutdown begins is not guaranteed — consistent with this component's existing "fire and forget, no retry, no queue" principle.

## Runtime Model

- Uses the `websockets` library (asyncio-based) — hand-rolling the WebSocket handshake and frame format was judged not worth it against one more validated, portable dependency, matching the existing preference (`pynput`, `mido`) over hand-rolled protocol code.
- Runs its own asyncio event loop on a dedicated background **daemon** thread, started in `start()` and stopped in `stop()` — the only component in this app with an asyncio dependency; `OscListener` and `MidiInputAdapter` both use blocking-socket-in-a-thread instead, since neither library requires asyncio. Daemon, matching `OscListener`'s and `run_shutdown_sequence`'s own threads, so an abandoned thread (e.g. a hung `stop()`) cannot block process exit.
- `send()` is called from the Qt UI-tick thread (same as `OscClient.send`/`KeystrokeOutputAdapter.send`) and hands the write off to the adapter's own event loop thread via `asyncio.run_coroutine_threadsafe` — it does not block waiting for the write to complete.
- **If the top-level accept loop itself raises** (the `websockets.serve()` context exits abnormally — distinct from a per-connection handler exception, which the library already isolates per-connection and does not propagate to the server loop), the exception is caught at the top of the background thread's run function, logged, and the thread exits without restarting. This leaves the adapter in a dead-but-quiet state — `send()`'s "is the loop running" check (above) already treats a dead loop the same as "never started," so subsequent sends fail the same clean, logged way rather than throwing. No auto-restart is implemented, matching the "no retry/reconnect machinery" principle already established for this narrow, secondary output path elsewhere in this LLD.
- `stop()` shuts the event loop down cleanly and joins the thread (bounded, see Lifecycle above); added to `app.py`'s `run_shutdown_sequence` alongside `OscListener.stop`.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Library | `websockets` (asyncio) | Hand-rolled WebSocket server on a raw socket | One more validated dependency vs. hand-rolling handshake/framing — matches `pynput`/`mido` precedent |
| Bind addresses | `127.0.0.1` + `::1`, not `0.0.0.0` | Bind `0.0.0.0` only (matches `OscListener`) | Dragonframe's outbound connection to `localhost` resolves to IPv6; an IPv4-only bind misses it |
| Path validation | Accept only `/com.dzed.dragonframe/DragonframeConnection` | Accept any path | Dragonframe is the only expected client; a fixed accepted path is simpler than a general connection-ID parsing scheme |
| Multi-connection handling | New connection replaces the active one, no explicit rejection | Reject a second connection while one is active | Matches Dragonframe's own reconnect behavior (close-then-reopen); no other client is ever expected to connect |
| Incoming message handling | Received and discarded, no parsing | Parse `replaceInputList`/`setInputColor` for future use | Out of scope per the HLD Non-Goal; nothing this component sends depends on any server-originated message |
| Send failure / no connection | Log and drop, not queued or retried | Queue until reconnect | Matches Keystroke output's silent-fail precedent; Dragonframe's reconnect timing is outside this component's control |
| Concurrency model | Dedicated asyncio event loop on its own thread | Blocking-socket-in-thread, like `OscListener` | `websockets`'s public API is asyncio-native; reimplementing it over a raw blocking socket means hand-rolling the protocol this library already provides |
| Port | Fixed constant `59177`, not user-editable | Expose as a Status UI config field, like the OSC ports | Dragonframe's own integration hardcodes this port; making it editable would break the connection, not add flexibility |
| `start()` bind-result reporting | Synchronous — blocks until bind success/failure is known, via `on_bind_result` callback | Return immediately, report bind result asynchronously only | Matches `OscListener.start()`'s existing synchronous contract; an async-only report would leave the caller unable to tell "just started, not connected yet" from "failed to bind" without extra state |
| Partial dual-stack bind | All-or-nothing — one address failing fails the whole bind, relying on `asyncio.create_server`'s built-in cleanup of any already-opened socket | Treat as a degraded-but-working partial success | A one-address-only bind is unreliable and undebuggable (depends on how this machine resolves `localhost`); simpler to treat as one clean failure |
| `start()`/`stop()` idempotency | Both are no-ops when called redundant to current state (already started / never started or already stopped) | Raise on redundant calls | Matches the "narrow secondary path, fail soft" philosophy already used for send failures; a redundant lifecycle call is a harmless no-op, not an error worth crashing over |
| `send()` before `start()` / after `stop()` / while the loop is dead | Same code path as "no active connection": logged and dropped, checked via a loop-running flag before touching `asyncio` at all | Let it raise (e.g. against a closed loop) | One consistent, safe outcome for every "not currently able to send" case, rather than a different exception shape depending on why |
| `stop()` internal timeout | ~1 second, well under `app.py`'s 5-second shutdown-step budget | No internal timeout; rely solely on the outer `run_shutdown_sequence` bound | A short internal bound keeps `stop()` itself well-behaved and gives the outer timeout a wide margin, rather than depending on it as the only backstop |
| Pending sends at shutdown | Not explicitly drained/awaited; best-effort within `stop()`'s brief internal window | Block `stop()` until all scheduled sends complete | Consistent with this component's existing fire-and-forget, no-retry-queue principle for sends in general |
| Active-connection mutation safety | Single reference, touched only from the event loop thread; no lock | Guard with an explicit `asyncio.Lock` or threading lock | `asyncio`'s single-threaded, non-preemptive execution already serializes any code path with no `await` inside the critical section; an explicit lock would be redundant |
| Old connection on replace | Explicitly closed at the moment of replacement | Left to be garbage-collected / closed by the peer | Avoids a stale server-side connection object lingering after Dragonframe has already moved on to a new one |
| Wrong-path connection attempts | Rejected via `websockets`' `process_request` hook (HTTP 404); logged once per attempt at debug level | Silently reject with no logging; or rate-limit/suppress repeated attempts | A loopback-only server has no realistic hostile-probing exposure; simple per-attempt debug logging is enough without added suppression machinery |
| Accept-loop top-level failure | Caught, logged, thread exits — no auto-restart | Restart the loop automatically after a crash | Matches the "no retry/reconnect machinery" principle already used throughout this component; auto-restart would be new resilience machinery none of this app's other components have |
| Background thread daemon flag | Daemon thread, matching `OscListener` | Non-daemon | A non-daemon thread could block process exit if `stop()`'s join times out; daemon matches the existing precedent and `run_shutdown_sequence`'s own thread-isolation design |
| `start()`/`stop()` calling convention | Main (Qt) thread only, stated as an explicit invariant, not lock-enforced | Make `start()`/`stop()` internally thread-safe against concurrent calls | Matches the existing, already-implicit convention for `OscListener`/`MidiInputAdapter`; no evidence this app ever calls lifecycle methods from more than one thread |

## Open Questions & Future Decisions

### Resolved

1. **Which physical controls map to which WebSocket commands** was not decided in this LLD — it belongs to `static-mapping.md`'s territory (mirrors how `keystroke-output.md` doesn't decide the jog wheel binds to `Step Moco Forward`/`Back`; `static-mapping.md`'s `MAP-JOGKEY-*` specs do). Now committed to specific controls in `static-mapping.md`'s WebSocket-Targeted Controls section (`MAP-WS-001` through `MAP-WS-009`).

### Deferred

1. Whether a failed WebSocket send should eventually surface on the Status UI is deferred, matching Keystroke output's identical open question.
2. Whether to detect another process already holding port 59177 ahead of `start()` (rather than only failing the bind) is deferred — out of scope per the HLD's coexistence Non-Goal.

## References

- `docs/high-level-design.md § Approach` and `§ Key Design Decisions` — the decision to add this as a third output path, server/client direction, fixed port, and no-status-indicator scope decisions.
- `docs/llds/keystroke-output.md` — the closest existing precedent for a narrow, secondary output path with silent failure handling.
- `docs/llds/osc-io.md § Listener (Receive)` — the closest existing precedent for a bound-socket server component with a start/stop lifecycle.
- `docs/llds/static-mapping.md § WebSocket-Targeted Controls` — the specific control bindings for the WebSocket commands this adapter serves.
