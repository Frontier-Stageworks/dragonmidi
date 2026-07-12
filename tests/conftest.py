from __future__ import annotations

import socket

import pytest

from tests.support import FakeClock


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def free_udp_port() -> int:
    """Reserve an ephemeral UDP port number, then release it for the test to bind."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port
