from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from mgesture.config import AppConfig, write_config
from mgesture.engine import EngineConfig, PythonGestureEngine
from mgesture.vision import Camera, HandLandmarker, available_model

MIN_CALIBRATION_SAMPLES = 20


def robust_median(values: Sequence[float]) -> float:
    samples = sorted(value for value in values if math.isfinite(value))
    if not samples:
        raise ValueError("calibration needs finite observations")
    if len(samples) < 4:
        return float(statistics.median(samples))
    quartiles = statistics.quantiles(samples, n=4, method="inclusive")
    spread = quartiles[2] - quartiles[0]
    if spread == 0:
        inliers = [value for value in samples if value == statistics.median(samples)]
    else:
        lower, upper = quartiles[0] - 1.5 * spread, quartiles[2] + 1.5 * spread
        inliers = [value for value in samples if lower <= value <= upper]
    return float(statistics.median(inliers or samples))


def calibrated_pinch_thresholds(
    open_samples: Sequence[float], pinch_samples: Sequence[float]
) -> tuple[float, float]:
    open_value = robust_median(open_samples)
    pinch_value = robust_median(pinch_samples)
    gap = open_value - pinch_value
    if gap <= 0.02:
        raise ValueError("open and pinch observations are not sufficiently separated")
    return pinch_value + gap * 0.4, pinch_value + gap * 0.7


def calibrate(
    config: AppConfig,
    output: Path | None = None,
    minimum_samples: int = MIN_CALIBRATION_SAMPLES,
) -> int:
    if minimum_samples < 2:
        raise ValueError("minimum calibration samples must be >= 2")
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("calibration needs OpenCV; run `pixi install`") from exc
    model = (
        available_model(Path(config.vision.model_path))
        if config.vision.model_path
        else available_model()
    )
    if model is None:
        raise RuntimeError("hand model is not installed; run `mgesture model install`")
    print(
        "Calibration is safe: observation only; no real mouse events are emitted. "
        "Hold an open hand, press O, then pinch index or middle, press P. "
        "Press S to save, Q/Esc to cancel."
    )
    observer = PythonGestureEngine(EngineConfig(activation_gesture=False))
    open_samples: list[float] = []
    pinch_samples: list[float] = []
    phase = "open"
    collecting = False
    last_result = -1
    handled_camera_failure = 0
    try:
        with (
            Camera(
                config.camera.index,
                config.camera.width,
                config.camera.height,
                config.camera.target_fps,
            ) as camera,
            HandLandmarker(
                str(model),
                config.vision.detection_confidence,
                config.vision.presence_confidence,
                config.vision.tracking_confidence,
                "cpu",
                config.vision.handedness_mirrored_input,
            ) as landmarker,
        ):
            while True:
                if camera.failure_generation > handled_camera_failure:
                    handled_camera_failure = camera.failure_generation
                    print(
                        camera.last_error
                        or "camera failed during calibration; reconnecting and checking permissions"
                    )
                captured = camera.read_latest(0.5)
                if captured is None:
                    continue
                landmarker.submit(captured.image, captured.timestamp_ms)
                result = landmarker.poll_latest()
                if result is not None and result.timestamp_ms > last_result:
                    last_result = result.timestamp_ms
                    detected = result.hand
                    if (
                        detected is not None
                        and detected.frame.handedness.lower() == "right"
                        and detected.frame.handedness_confidence
                        >= config.vision.handedness_confidence
                    ):
                        observation = observer.observe(detected.frame.landmarks)
                        index_pinch = observation["index_pinch"]
                        middle_pinch = observation["middle_pinch"]
                        if not isinstance(index_pinch, (int, float)) or not isinstance(
                            middle_pinch, (int, float)
                        ):
                            value = None
                        else:
                            value = (float(index_pinch) + float(middle_pinch)) / 2
                        if collecting and value is not None:
                            (open_samples if phase == "open" else pinch_samples).append(value)
                lines = [
                    f"phase={phase} open={len(open_samples)}/{minimum_samples} "
                    f"pinch={len(pinch_samples)}/{minimum_samples}",
                    "O open samples | P pinch samples | S save | Q cancel",
                ]
                if camera.error:
                    lines.append(f"camera: {camera.error}")
                cv2.putText(
                    captured.image,
                    " | ".join(lines),
                    (12, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("mgesture calibration", captured.image)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    return 1
                if key == ord("o"):
                    phase = "open"
                    collecting = True
                elif key == ord("p"):
                    phase = "pinch"
                    collecting = True
                elif key == ord("s"):
                    if len(open_samples) < minimum_samples or len(pinch_samples) < minimum_samples:
                        print("Need more valid right-hand samples before saving.")
                        continue
                    try:
                        down, release = calibrated_pinch_thresholds(open_samples, pinch_samples)
                    except ValueError as exc:
                        print(f"Calibration not saved: {exc}")
                        continue
                    updated = replace(
                        config,
                        gesture=replace(
                            config.gesture,
                            pinch_down_threshold=down,
                            pinch_release_threshold=release,
                        ),
                    )
                    target = write_config(updated, output)
                    print(f"saved {target}: pinch_down={down:.3f}, pinch_release={release:.3f}")
                    return 0
    finally:
        cv2.destroyAllWindows()
