"""Tests for the WebSocket Output Adapter (docs/specs/websocket-output.md).

@spec WS-LIFECYCLE-001, WS-LIFECYCLE-002, WS-LIFECYCLE-003, WS-LIFECYCLE-004
@spec WS-LIFECYCLE-005, WS-LIFECYCLE-006, WS-LIFECYCLE-007, WS-LIFECYCLE-008
@spec WS-CONN-001, WS-CONN-002, WS-CONN-003, WS-CONN-004, WS-CONN-005, WS-CONN-006
@spec WS-SEND-001, WS-SEND-002, WS-SEND-003, WS-SEND-004, WS-SEND-005, WS-SEND-007
@spec WS-RUNTIME-001

Note on scope: WS-RUNTIME-002 (top-level accept-loop crash handling) and
WS-RUNTIME-003 (no auto-reconnect machinery) are exercised structurally by
inspection of `websocket_output.py`'s `run()`/`stop()` control flow, not by an
automated test - genuinely triggering an `asyncio` event-loop-level crash (as
opposed to a per-connection handler exception, which `websockets` already
isolates and which never reaches this code) requires faking internals deep
enough that the test would no longer exercise real behavior.
"""

from __future__ import annotations

import asyncio
import json
import queue
import socket
import threading
import time

import pytest
import websockets.asyncio.client as ws_client

from dragonmidi.events import WebSocketCommand
from dragonmidi.websocket_output import CONNECTION_PATH, WebSocketOutputAdapter, _encode


class _FakeDragonframeClient:
    """A WebSocket client impersonating Dragonframe, running on its own background
    thread/event loop so synchronous test code can trigger adapter sends and then
    inspect what was received.
    """

    def __init__(self, port: int, path: str = CONNECTION_PATH, host: str = "127.0.0.1") -> None:
        self._received: queue.Queue[str] = queue.Queue()
        self._loop = asyncio.new_event_loop()
        self._connected = threading.Event()
        self._closed = threading.Event()
        self._connect_error: list[BaseException] = []
        self._ws = None
        self._main_task: asyncio.Task | None = None
        self._thread = threading.Thread(target=self._run, args=(host, port, path), daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=2.0):
            raise TimeoutError("fake Dragonframe client did not connect in time")
        if self._connect_error:
            raise self._connect_error[0]

    def _run(self, host: str, port: int, path: str) -> None:
        asyncio.set_event_loop(self._loop)
        self._main_task = self._loop.create_task(self._main(host, port, path))
        try:
            self._loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._loop.close()

    async def _main(self, host: str, port: int, path: str) -> None:
        uri_host = f"[{host}]" if ":" in host else host
        try:
            async with ws_client.connect(f"ws://{uri_host}:{port}{path}", open_timeout=2.0) as ws:
                self._ws = ws
                self._connected.set()
                try:
                    async for message in ws:
                        self._received.put(message)
                except asyncio.CancelledError:
                    pass
        except Exception as exc:  # noqa: BLE001 - captured for the constructor to re-raise
            self._connect_error.append(exc)
            self._connected.set()
        finally:
            self._closed.set()

    def wait_for_message(self, timeout: float = 2.0) -> str:
        return self._received.get(timeout=timeout)

    def assert_no_message(self, wait: float = 0.2) -> None:
        with pytest.raises(queue.Empty):
            self._received.get(timeout=wait)

    def wait_closed(self, timeout: float = 2.0) -> bool:
        return self._closed.wait(timeout=timeout)

    def close(self) -> None:
        if self._main_task is not None:
            self._loop.call_soon_threadsafe(self._main_task.cancel)
        self._thread.join(timeout=2.0)

    def send_raw(self, payload: str) -> None:
        """Test-only reach-in: send a raw payload as if Dragonframe sent it."""
        fut = asyncio.run_coroutine_threadsafe(self._ws.send(payload), self._loop)
        fut.result(timeout=2.0)


def _try_connect(port: int, path: str, host: str = "127.0.0.1", timeout: float = 2.0) -> None:
    async def _run() -> None:
        async with ws_client.connect(f"ws://{host}:{port}{path}", open_timeout=timeout):
            pass

    asyncio.run(_run())


# --- WS-SEND-001 / WS-SEND-002: wire encoding ---


# @spec WS-SEND-001
def test_encode_bare_trigger_omits_operation_and_params() -> None:
    payload = _encode(WebSocketCommand("E-Stop"))
    assert json.loads(payload.strip()) == {"input": "E-Stop"}


# @spec WS-SEND-002
def test_encode_ranged_command_includes_operation_and_params() -> None:
    payload = _encode(WebSocketCommand("Jog All", operation="+", params=(-1,)))
    assert json.loads(payload.strip()) == {"input": "Jog All", "operation": "+", "params": [-1]}


# @spec WS-SEND-001
def test_encode_is_newline_terminated() -> None:
    payload = _encode(WebSocketCommand("E-Stop"))
    assert payload.endswith("\n")


# --- WS-LIFECYCLE-001 / 002: synchronous start(), on_bind_result signal ---


# @spec WS-LIFECYCLE-001, WS-LIFECYCLE-002
def test_start_blocks_until_bind_succeeds_and_reports_true(free_tcp_port: int) -> None:
    results: list[bool] = []
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port, on_bind_result=results.append)

    adapter.start()

    assert results == [True]
    adapter.stop()


# @spec WS-LIFECYCLE-001, WS-LIFECYCLE-003
def test_start_reports_false_on_bind_failure_without_raising(free_tcp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", free_tcp_port))
    blocker.listen(1)
    try:
        results: list[bool] = []
        adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port, on_bind_result=results.append)

        adapter.start()  # must not raise

        assert results == [False]
    finally:
        blocker.close()


# @spec WS-LIFECYCLE-003
def test_partial_dual_stack_bind_failure_leaves_no_socket_bound(free_tcp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", free_tcp_port))
    blocker.listen(1)
    try:
        results: list[bool] = []
        adapter = WebSocketOutputAdapter(hosts=("127.0.0.1", "::1"), port=free_tcp_port, on_bind_result=results.append)
        adapter.start()
        assert results == [False]
    finally:
        blocker.close()

    # the IPv6 side must not have been left bound despite the IPv4 side failing
    probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    probe.bind(("::1", free_tcp_port))
    probe.close()


# @spec WS-LIFECYCLE-004
def test_start_called_twice_is_a_no_op(free_tcp_port: int) -> None:
    results: list[bool] = []
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port, on_bind_result=results.append)

    adapter.start()
    adapter.start()  # must not raise, must not attempt a second bind

    assert results == [True]  # on_bind_result only fired once
    adapter.stop()


# @spec WS-LIFECYCLE-005
def test_stop_before_start_is_a_no_op() -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=0)
    adapter.stop()  # must not raise


# @spec WS-LIFECYCLE-005
def test_stop_called_twice_is_a_no_op(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()

    adapter.stop()
    adapter.stop()  # must not raise


# @spec WS-LIFECYCLE-006, WS-LIFECYCLE-008
def test_stop_joins_the_background_thread_and_frees_the_port(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()

    adapter.stop()

    # port must be free again - a fresh bind proves the thread/socket really tore down
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", free_tcp_port))
    probe.close()


# --- WS-CONN-001: dual-stack bind ---


# @spec WS-CONN-001
def test_binds_both_ipv4_and_ipv6_loopback_by_default(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(port=free_tcp_port)
    try:
        adapter.start()
        v4_client = _FakeDragonframeClient(free_tcp_port, host="127.0.0.1")
        v6_client = _FakeDragonframeClient(free_tcp_port, host="::1")
        v4_client.close()
        v6_client.close()
    finally:
        adapter.stop()


# --- WS-CONN-002 / 003: path validation ---


# @spec WS-CONN-002
def test_connection_at_correct_path_is_accepted(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        client = _FakeDragonframeClient(free_tcp_port)  # must not raise
        client.close()
    finally:
        adapter.stop()


# @spec WS-CONN-002
def test_connection_at_wrong_path_is_rejected(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        with pytest.raises(Exception):  # noqa: B017 - websockets.exceptions.InvalidStatus
            _try_connect(free_tcp_port, "/wrong/path")
    finally:
        adapter.stop()


# --- WS-CONN-004 / 005: connection replacement ---


# @spec WS-CONN-004, WS-CONN-005
def test_new_connection_replaces_and_closes_the_previous_one(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        first = _FakeDragonframeClient(free_tcp_port)
        second = _FakeDragonframeClient(free_tcp_port)  # connects while `first` is still open

        assert first.wait_closed(timeout=2.0)  # the first connection was explicitly closed

        # the new connection is the one that receives sends
        adapter.send(WebSocketCommand("E-Stop"))
        message = second.wait_for_message()
        assert json.loads(message.strip()) == {"input": "E-Stop"}

        second.close()
    finally:
        adapter.stop()


# --- WS-CONN-006: incoming messages are received and discarded ---


# @spec WS-CONN-006
def test_messages_sent_by_dragonframe_are_discarded_without_error(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        client = _FakeDragonframeClient(free_tcp_port)
        client.send_raw('{"status":"ok"}')

        # adapter keeps working normally afterward - not crashed, not wedged
        adapter.send(WebSocketCommand("E-Stop"))
        message = client.wait_for_message()
        assert json.loads(message.strip()) == {"input": "E-Stop"}

        client.close()
    finally:
        adapter.stop()


# --- WS-SEND-003: send() with no running loop (never started / already stopped) ---


# @spec WS-SEND-003
def test_send_before_start_is_dropped_without_raising() -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=0)
    adapter.send(WebSocketCommand("E-Stop"))  # must not raise


# @spec WS-SEND-003
def test_send_after_failed_bind_is_dropped_without_raising(free_tcp_port: int) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", free_tcp_port))
    blocker.listen(1)
    try:
        adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
        adapter.start()
        adapter.send(WebSocketCommand("E-Stop"))  # must not raise
    finally:
        blocker.close()


# @spec WS-SEND-003, WS-SEND-007
def test_send_after_stop_is_dropped_without_raising(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    adapter.stop()

    adapter.send(WebSocketCommand("E-Stop"))  # must not raise


# --- WS-SEND-004: send() with a running loop but no active connection ---


# @spec WS-SEND-004
def test_send_with_no_active_connection_is_dropped_without_raising(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        adapter.send(WebSocketCommand("E-Stop"))  # must not raise; no client connected
    finally:
        adapter.stop()


# --- WS-SEND-005: write failure is caught and logged, not raised ---


# @spec WS-SEND-005
def test_send_after_client_disconnects_is_dropped_without_raising(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        client = _FakeDragonframeClient(free_tcp_port)
        client.close()
        client.wait_closed(timeout=2.0)
        time.sleep(0.1)  # let the server-side handler observe the close

        adapter.send(WebSocketCommand("E-Stop"))  # must not raise
    finally:
        adapter.stop()


# --- End-to-end: a full send is actually delivered ---


# @spec WS-SEND-001, WS-CONN-004
def test_send_is_delivered_to_the_connected_client(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        client = _FakeDragonframeClient(free_tcp_port)

        adapter.send(WebSocketCommand("Jog All", operation="+", params=(1,)))

        message = client.wait_for_message()
        assert json.loads(message.strip()) == {"input": "Jog All", "operation": "+", "params": [1]}
        client.close()
    finally:
        adapter.stop()


# --- WS-RUNTIME-001: send() does not block the calling thread ---


# @spec WS-RUNTIME-001
def test_send_returns_promptly_without_waiting_for_delivery(free_tcp_port: int) -> None:
    adapter = WebSocketOutputAdapter(hosts=("127.0.0.1",), port=free_tcp_port)
    adapter.start()
    try:
        client = _FakeDragonframeClient(free_tcp_port)

        start = time.monotonic()
        adapter.send(WebSocketCommand("E-Stop"))
        elapsed = time.monotonic() - start

        assert elapsed < 0.1
        client.wait_for_message()  # delivery still happens, just not waited on by send()
        client.close()
    finally:
        adapter.stop()
