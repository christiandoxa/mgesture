from __future__ import annotations

from pathlib import Path

from mgesture.config import AppConfig, write_config
from mgesture.engine import EngineConfig, PythonGestureEngine
from mgesture.vision import Camera, HandLandmarker, available_model


def calibrate(config: AppConfig, output: Path | None = None) -> int:
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
        "Calibration is safe: no real mouse events are emitted. Press S to save, Q/Esc to cancel."
    )
    engine = PythonGestureEngine(EngineConfig(activation_gesture=False))
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
                captured = camera.read_latest(0.5)
                if captured is None:
                    continue
                landmarker.submit(captured.image, captured.timestamp_ms)
                detected = landmarker.latest()
                lines = ["Camera OK | S save defaults | Q cancel"]
                if detected is None:
                    lines.append("hand: not detected")
                else:
                    measurements = engine._measure(detected.frame.landmarks)
                    lines.extend(
                        [
                            f"hand: {detected.frame.handedness} confidence={detected.frame.handedness_confidence:.2f}",
                            f"thumb-index={measurements.index_pinch:.3f} thumb-middle={measurements.middle_pinch:.3f}",
                        ]
                    )
                for index, line in enumerate(lines):
                    cv2.putText(
                        captured.image,
                        line,
                        (12, 30 + index * 28),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 255, 0),
                        2,
                    )
                cv2.imshow("mgesture calibration", captured.image)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    return 1
                if key == ord("s"):
                    target = write_config(config, output)
                    print(f"saved {target}")
                    return 0
    finally:
        cv2.destroyAllWindows()
