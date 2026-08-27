from __future__ import annotations

import json
import time
from pathlib import Path

from mgesture.config import AppConfig
from mgesture.vision import Camera, HandLandmarker, available_model


def record_landmarks(
    config: AppConfig,
    output: Path,
    seconds: float = 10.0,
    maximum_frames: int | None = None,
    camera_index: int | None = None,
) -> int:
    if seconds <= 0:
        raise ValueError("recording duration must be > 0")
    if maximum_frames is not None and maximum_frames <= 0:
        raise ValueError("maximum recorded frames must be > 0")
    try:
        import cv2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("landmark recording needs OpenCV; run `pixi install`") from exc
    model = (
        available_model(Path(config.vision.model_path))
        if config.vision.model_path
        else available_model()
    )
    if model is None:
        raise RuntimeError("hand model is not installed; run `mgesture model install`")
    output.parent.mkdir(parents=True, exist_ok=True)
    camera = Camera(
        config.camera.index if camera_index is None else camera_index,
        config.camera.width,
        config.camera.height,
        config.camera.target_fps,
    )
    recorded = 0
    deadline = time.monotonic() + seconds
    last_result = -1
    handled_camera_failure = 0
    with (
        camera,
        HandLandmarker(
            str(model),
            config.vision.detection_confidence,
            config.vision.presence_confidence,
            config.vision.tracking_confidence,
            "cpu",
            config.vision.handedness_mirrored_input,
        ) as landmarker,
    ):
        with output.open("x", encoding="utf-8") as handle:
            print(f"Recording landmarks only to {output}; no images or mouse input are used.")
            while time.monotonic() < deadline:
                if camera.failure_generation > handled_camera_failure:
                    handled_camera_failure = camera.failure_generation
                    print(
                        camera.last_error
                        or "camera failed during recording; reconnecting and checking permissions"
                    )
                captured = camera.read_latest(0.25)
                if captured is None:
                    continue
                landmarker.submit(captured.image, captured.timestamp_ms)
                result = landmarker.poll_latest()
                if result is None or result.timestamp_ms <= last_result or result.hand is None:
                    continue
                last_result = result.timestamp_ms
                hand = result.hand
                handle.write(
                    json.dumps(
                        {
                            "timestamp_ms": result.timestamp_ms,
                            "landmarks": list(hand.frame.landmarks),
                            "world_landmarks": (
                                list(hand.world_landmarks)
                                if hand.world_landmarks is not None
                                else None
                            ),
                            "handedness": hand.frame.handedness,
                            "handedness_confidence": hand.frame.handedness_confidence,
                            "width": captured.width,
                            "height": captured.height,
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                handle.flush()
                recorded += 1
                if maximum_frames is not None and recorded >= maximum_frames:
                    break
    print(f"recorded {recorded} landmark frames")
    return 0
