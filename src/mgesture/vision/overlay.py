from __future__ import annotations

from typing import Any

from mgesture.engine.models import ActionBatch


def draw_overlay(
    image: Any,
    landmarks: tuple[float, ...] | None,
    batch: ActionBatch,
    lines: list[str],
    active_region: tuple[float, float, float, float] | None = None,
) -> Any:
    try:
        import cv2
    except ImportError:
        return image
    output = image.copy()
    height, width = output.shape[:2]
    if active_region is not None:
        left, top, right, bottom = active_region
        cv2.rectangle(
            output,
            (int(left * width), int(top * height)),
            (int(right * width), int(bottom * height)),
            (255, 180, 0),
            2,
        )
    if landmarks:
        points = [
            (int(landmarks[index * 3] * width), int(landmarks[index * 3 + 1] * height))
            for index in range(21)
        ]
        connections = (
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
            (0, 5),
            (5, 6),
            (6, 7),
            (7, 8),
            (5, 9),
            (9, 10),
            (10, 11),
            (11, 12),
            (9, 13),
            (13, 14),
            (14, 15),
            (15, 16),
            (13, 17),
            (17, 18),
            (18, 19),
            (19, 20),
            (0, 17),
        )
        for first, second in connections:
            cv2.line(output, points[first], points[second], (0, 220, 0), 2)
        for point in points:
            cv2.circle(output, point, 4, (0, 120, 255), -1)
    y = 24
    for line in lines:
        cv2.putText(
            output, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA
        )
        y += 22
    return output
