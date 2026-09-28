from __future__ import annotations

from typing import Protocol

from app.shared.mapping import MappingReadiness, MappingSnapshot


class MappingProjection(Protocol):
    def publish(self, snapshot: MappingSnapshot) -> None: ...


class MappingReader(Protocol):
    def lock(self) -> None: ...
    def readiness(self) -> MappingReadiness: ...
