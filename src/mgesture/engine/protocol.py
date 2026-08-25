from __future__ import annotations

from typing import Protocol

from .models import ActionBatch, EngineConfig, LandmarkFrame


class GestureEngine(Protocol):
    name: str
    version: str

    def process(self, frame: LandmarkFrame) -> ActionBatch: ...

    def reset(self, reason: str = "reset") -> ActionBatch: ...

    def set_armed(self, armed: bool) -> ActionBatch: ...


def engine_config_from_values(**values: object) -> EngineConfig:
    return EngineConfig(**values)  # type: ignore[arg-type]
