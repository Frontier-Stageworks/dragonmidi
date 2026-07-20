# WebSocket Output Adapter — EARS Specs

Traces to `docs/llds/websocket-output.md`.

## Lifecycle

- [x] **WS-LIFECYCLE-001**: When `start()` is called on an adapter that is not already started, the system shall block until the bind attempt on all configured addresses has fully succeeded or failed before returning.
- [x] **WS-LIFECYCLE-002**: When a bind attempt completes, the system shall invoke the `on_bind_result` callback, if provided, with `True` on success or `False` on failure.
- [x] **WS-LIFECYCLE-003**: If any one of the configured bind addresses fails to bind, the system shall treat the entire bind attempt as failed and shall close any socket already opened for another address.
- [x] **WS-LIFECYCLE-004**: If `start()` is called while the adapter is already started, the system shall treat the call as a no-op, without attempting a second bind or spawning a second background thread.
- [x] **WS-LIFECYCLE-005**: If `stop()` is called on an adapter that was never started, failed to bind, or is already stopped, the system shall treat the call as a no-op.
- [x] **WS-LIFECYCLE-006**: When `stop()` is called on a running adapter, the system shall signal the event loop to close the active connection and stop, then join the background thread with an internal timeout bounded well under the app's overall shutdown-step timeout.
- [x] **WS-LIFECYCLE-007**: If the background thread does not terminate within `stop()`'s internal timeout, the system shall log a warning and return from `stop()` without blocking further.
- [x] **WS-LIFECYCLE-008**: The system shall run the WebSocket server's background thread as a daemon thread, so that an abandoned thread cannot block process exit.

## Connection Handling

- [x] **WS-CONN-001**: The system shall bind the configured addresses (default `127.0.0.1` and `::1`) rather than a wildcard address.
- [x] **WS-CONN-002**: The system shall accept an incoming connection only at the path `/com.dzed.dragonframe/DragonframeConnection`; a connection attempt at any other path shall be rejected at the WebSocket handshake with an HTTP 404 response.
- [x] **WS-CONN-003**: When a connection attempt is rejected for path mismatch, the system shall log the requested path and remote address at debug level.
- [x] **WS-CONN-004**: The system shall track at most one connection as active at a time.
- [x] **WS-CONN-005**: When a new connection is accepted while a previous connection is active, the system shall explicitly close the previous connection and replace it with the new one as the active connection.
- [x] **WS-CONN-006**: The system shall receive and discard every message sent by Dragonframe over the connection (including `{"status":"ok"}`, `replaceInputList`, and `setInputColor` messages), without parsing or acting on their content.
- [x] **WS-CONN-007**: The system shall not derive any liveness or last-activity signal from this connection for the Status UI.

## Sending a Command

- [x] **WS-SEND-001**: When `send(command)` is called, the system shall encode `command` as a single newline-delimited JSON object and write it to the currently active connection, if one exists.
- [x] **WS-SEND-002**: The system shall omit the `operation` and `params` keys from the encoded JSON when they hold their default values (`""` and `()` respectively), producing a bare `{"input": "<name>"}` object for trigger commands.
- [x] **WS-SEND-003**: If `send()` is called while the event loop is not currently running (never started, failed to bind, already stopped, or dead after an unhandled accept-loop failure), the system shall log and drop the call without attempting to schedule it on the event loop.
- [x] **WS-SEND-004**: If `send()` is called while the event loop is running but no connection is currently active, the system shall log and drop the command.
- [x] **WS-SEND-005**: If writing a command to the active connection fails, the system shall catch and log the failure rather than raise it, and shall not interrupt MIDI, OSC, or Keystroke processing elsewhere in the app.
- [x] **WS-SEND-006**: The system shall not queue or retry a dropped or failed send.
- [x] **WS-SEND-007**: If `send()` is called after `stop()` has begun but before the background thread has fully terminated, the system shall treat the call identically to `WS-SEND-003` (loop not running), rather than scheduling it against a closing event loop.
- [x] **WS-SEND-008**: The system shall not guarantee delivery of a command whose `send()` call was scheduled before `stop()` began.

## Runtime Model

- [x] **WS-RUNTIME-001**: `send()` shall not block the calling thread waiting for the write to complete; the write is handed off to the adapter's own event loop thread.
- [x] **WS-RUNTIME-002**: If the top-level accept loop raises an exception outside of a single connection handler, the system shall catch it, log it, and terminate the background thread without automatically restarting the server.
- [x] **WS-RUNTIME-003**: The system shall not implement automatic reconnection or accept-loop restart machinery of any kind — including after a bind failure, a connection drop, or an accept-loop crash.

## References

- `docs/llds/websocket-output.md`
