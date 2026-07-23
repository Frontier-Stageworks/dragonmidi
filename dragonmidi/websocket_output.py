from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import websockets.asyncio.server as ws_server

from .events import WebSocketCommand

if TYPE_CHECKING:
    from websockets.asyncio.server import Server, ServerConnection
    from websockets.http11 import Request, Response

logger = logging.getLogger(__name__)

CONNECTION_PATH = "/com.dzed.dragonframe/DragonframeConnection"
DEFAULT_HOSTS: tuple[str, ...] = ("127.0.0.1", "::1")
DEFAULT_PORT = 59177
STOP_JOIN_TIMEOUT = 1.0


def _encode(command: WebSocketCommand) -> str:
    """@spec WS-SEND-001, WS-SEND-002"""
    if command.operation == "" and command.params == ():
        message = {"input": command.input}
    else:
        message = {"input": command.input, "operation": command.operation, "params": list(command.params)}
    return json.dumps(message) + os.linesep


class WebSocketOutputAdapter:
    """Serves Dragonframe's outbound WebSocket connection and forwards mapped
    controls as Dragonframe WebSocket commands.

    A third, narrower output path alongside OSC and Keystroke. Dragonframe is the
    connecting client; this adapter is the server. Runs its own asyncio event loop
    on a dedicated background thread, since `websockets`'s API is asyncio-native.

    @spec WS-LIFECYCLE-001, WS-LIFECYCLE-002, WS-LIFECYCLE-003, WS-LIFECYCLE-004
    @spec WS-LIFECYCLE-005, WS-LIFECYCLE-006, WS-LIFECYCLE-007, WS-LIFECYCLE-008
    @spec WS-CONN-001, WS-CONN-002, WS-CONN-003, WS-CONN-004, WS-CONN-005
    @spec WS-CONN-006, WS-CONN-007
    @spec WS-SEND-003, WS-SEND-004, WS-SEND-005, WS-SEND-006, WS-SEND-007, WS-SEND-008
    @spec WS-RUNTIME-001, WS-RUNTIME-002, WS-RUNTIME-003
    """

    def __init__(
        self,
        hosts: tuple[str, ...] = DEFAULT_HOSTS,
        port: int = DEFAULT_PORT,
        on_bind_result: Callable[[bool], None] | None = None,
    ) -> None:
        self._hosts = hosts
        self._port = port
        self._on_bind_result = on_bind_result
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: Server | None = None
        self._connection: ServerConnection | None = None
        self._stopping = False

    def start(self) -> None:
        """@spec WS-LIFECYCLE-001, WS-LIFECYCLE-002, WS-LIFECYCLE-003, WS-LIFECYCLE-004"""
        if self._loop is not None:
            logger.warning("WebSocketOutputAdapter.start() called while already started; ignoring")
            return

        self._stopping = False
        ready = threading.Event()
        bind_ok: list[bool] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server = loop.run_until_complete(self._bind())
            except OSError:
                logger.warning(
                    "WebSocketOutputAdapter failed to bind %r on port %d; WebSocket-mapped controls will not fire",
                    self._hosts,
                    self._port,
                )
                bind_ok.append(False)
                ready.set()
                loop.close()
                return

            self._loop = loop
            self._server = server
            bind_ok.append(True)
            ready.set()
            try:
                loop.run_forever()
            except BaseException:  # top-level accept-loop crash, WS-RUNTIME-002
                logger.exception("WebSocketOutputAdapter accept loop crashed")
            finally:
                self._loop = None
                self._server = None
                self._connection = None

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait()
        ok = bind_ok[0] if bind_ok else False
        if not ok:
            self._thread = None
        if self._on_bind_result is not None:
            self._on_bind_result(ok)

    async def _bind(self) -> Server:
        return await ws_server.serve(
            self._handler,
            self._hosts,
            self._port,
            process_request=self._process_request,
        )

    def _process_request(self, connection: ServerConnection, request: Request) -> Response | None:
        """@spec WS-CONN-002, WS-CONN-003"""
        if request.path != CONNECTION_PATH:
            logger.debug(
                "WebSocketOutputAdapter: rejected connection at path %r from %s",
                request.path,
                connection.remote_address,
            )
            return connection.respond(404, "not found")
        return None

    async def _handler(self, connection: ServerConnection) -> None:
        """@spec WS-CONN-004, WS-CONN-005, WS-CONN-006"""
        previous = self._connection
        self._connection = connection
        if previous is not None:
            try:
                await previous.close()
            except Exception:  # best-effort teardown of the superseded connection
                logger.debug("WebSocketOutputAdapter: error closing superseded connection", exc_info=True)
        try:
            async for _ in connection:
                pass  # discard every message Dragonframe sends - WS-CONN-006
        except Exception:  # connection dropped/errored, nothing to act on
            pass
        finally:
            if self._connection is connection:
                self._connection = None

    def stop(self) -> None:
        """@spec WS-LIFECYCLE-005, WS-LIFECYCLE-006, WS-LIFECYCLE-007, WS-LIFECYCLE-008"""
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        self._stopping = True

        async def shutdown() -> None:
            if self._connection is not None:
                try:
                    await self._connection.close()
                except Exception:  # best-effort close during shutdown
                    pass
                self._connection = None
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()
            loop.stop()

        try:
            asyncio.run_coroutine_threadsafe(shutdown(), loop)
        except RuntimeError:
            pass  # loop already stopped/closed - nothing left to shut down
        thread.join(timeout=STOP_JOIN_TIMEOUT)
        if thread.is_alive():
            logger.warning("WebSocketOutputAdapter.stop() timed out waiting for background thread")
        self._thread = None

    def send(self, command: WebSocketCommand) -> None:
        """@spec WS-SEND-003, WS-SEND-004, WS-SEND-005, WS-SEND-006, WS-SEND-007, WS-SEND-008
        @spec WS-RUNTIME-001
        """
        loop = self._loop
        if loop is None or self._stopping:
            logger.debug("WebSocketOutputAdapter.send() dropped, not running: %r", command)
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_async(command), loop)
        except RuntimeError:
            logger.debug("WebSocketOutputAdapter.send() dropped, loop not accepting new work: %r", command)

    async def _send_async(self, command: WebSocketCommand) -> None:
        connection = self._connection
        if connection is None:
            logger.debug("WebSocketOutputAdapter: no active connection, dropping %r", command)
            return
        try:
            await connection.send(_encode(command))
        except Exception:  # a failed send must not interrupt other output paths
            logger.exception("WebSocketOutputAdapter: send failed for %r", command)
