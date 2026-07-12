from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .osc_io import (
    DEFAULT_DRAGONFRAME_HOST,
    DEFAULT_DRAGONFRAME_PORT,
    DEFAULT_LISTEN_PORT,
    validate_ports,
)


@dataclass(frozen=True)
class EndpointConfig:
    host: str = DEFAULT_DRAGONFRAME_HOST
    dragonframe_port: int = DEFAULT_DRAGONFRAME_PORT
    listen_port: int = DEFAULT_LISTEN_PORT


class ConfigController:
    """Pending-vs-applied host/port state behind an explicit Apply action.

    @spec UI-CONFIG-001
    """

    def __init__(self, initial: EndpointConfig, on_apply: Callable[[EndpointConfig, bool], None]) -> None:
        self.pending = initial
        self.applied = initial
        self._on_apply = on_apply

    def edit(self, **changes: object) -> None:
        self.pending = replace(self.pending, **changes)

    def apply(self) -> None:
        validate_ports(self.pending.dragonframe_port, self.pending.listen_port)
        listen_port_changed = self.pending.listen_port != self.applied.listen_port
        self.applied = self.pending
        self._on_apply(self.applied, listen_port_changed)
