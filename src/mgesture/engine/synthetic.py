from __future__ import annotations

from collections.abc import Iterator

from .models import LandmarkFrame


def synthetic_landmarks(
    index_x: float = 0.45, index_y: float = 0.25, pinch: str | None = None
) -> tuple[float, ...]:
    """Stable synthetic right-hand frames for offline replay and package self-tests."""
    points = [(0.5, 0.7, 0.0)] * 21
    points[0] = (0.5, 0.8, 0.0)
    points[5] = (0.4, 0.55, 0.0)
    points[9] = (0.5, 0.5, 0.0)
    points[13] = (0.58, 0.55, 0.0)
    points[17] = (0.65, 0.6, 0.0)
    points[6] = (0.4, 0.4, 0.0)
    points[10] = (0.5, 0.35, 0.0)
    points[14] = (0.58, 0.47, 0.0)
    points[18] = (0.65, 0.52, 0.0)
    points[8] = (index_x, index_y, 0.0)
    points[12] = (0.55, 0.4, 0.0)
    points[16] = (0.58, 0.5, 0.0)
    points[20] = (0.65, 0.55, 0.0)
    points[4] = (0.25, 0.65, 0.0)
    if pinch == "left":
        points[4] = (index_x + 0.02, index_y + 0.02, 0.0)
    elif pinch == "right":
        points[4] = (points[12][0] + 0.02, points[12][1] + 0.02, 0.0)
    return tuple(value for point in points for value in point)


def synthetic_frames(count: int = 60) -> Iterator[LandmarkFrame]:
    for index in range(count):
        yield LandmarkFrame(
            index * 33, synthetic_landmarks(0.2 + (index % 100) / 125, 0.45), "Right", 0.99
        )
