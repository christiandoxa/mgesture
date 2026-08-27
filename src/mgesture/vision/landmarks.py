from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mgesture.engine.models import LandmarkFrame, PhysicalHand


def canonical_physical_hand(label: object, mirrored_input: bool) -> PhysicalHand:
    """Normalize MediaPipe's selfie-input label to physical left/right."""
    hand = PhysicalHand.coerce(label)
    if mirrored_input or hand is PhysicalHand.UNKNOWN:
        return hand
    return PhysicalHand.LEFT if hand is PhysicalHand.RIGHT else PhysicalHand.RIGHT


@dataclass(frozen=True, slots=True)
class DetectedHand:
    frame: LandmarkFrame
    world_landmarks: Sequence[float] | None = None
    tracking_status: str = "tracked"


@dataclass(frozen=True, slots=True)
class LandmarkResult:
    timestamp_ms: int
    hand: DetectedHand | None
    hand_changed: bool = False
