from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mgesture.engine.models import LandmarkFrame


@dataclass(frozen=True, slots=True)
class DetectedHand:
    frame: LandmarkFrame
    world_landmarks: Sequence[float] | None = None
    tracking_status: str = "tracked"


@dataclass(frozen=True, slots=True)
class LandmarkResult:
    timestamp_ms: int
    hand: DetectedHand | None
