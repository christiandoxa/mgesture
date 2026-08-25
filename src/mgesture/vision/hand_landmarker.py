from __future__ import annotations

import threading
import time
from typing import Any

from mgesture.engine.models import LandmarkFrame

from .landmarks import DetectedHand


class HandLandmarkerError(RuntimeError):
    pass


class HandLandmarker:
    def __init__(
        self,
        model_path: str,
        detection: float,
        presence: float,
        tracking: float,
        compute: str = "cpu",
        handedness_mirrored_input: bool = False,
    ) -> None:
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except ImportError as exc:
            raise HandLandmarkerError(
                "MediaPipe Tasks is not installed; run `pixi install`"
            ) from exc
        self._mp = mp
        self._cv2 = cv2
        self._handedness_mirrored_input = handedness_mirrored_input
        self._latest: DetectedHand | None = None
        self._lock = threading.Lock()
        self._submitted: dict[int, int] = {}
        self.last_inference_ms: float | None = None
        try:
            delegate = python.BaseOptions.Delegate.CPU
            if compute == "gpu":
                delegate = getattr(python.BaseOptions.Delegate, "GPU", None)
                if delegate is None:
                    raise HandLandmarkerError(
                        "GPU compute requested, but this MediaPipe package exposes no GPU delegate"
                    )
            base_options = python.BaseOptions(model_asset_path=model_path, delegate=delegate)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.LIVE_STREAM,
                num_hands=1,
                min_hand_detection_confidence=detection,
                min_hand_presence_confidence=presence,
                min_tracking_confidence=tracking,
                result_callback=self._callback,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            self.compute = "gpu" if compute == "gpu" else "cpu"
        except Exception as exc:
            raise HandLandmarkerError(
                f"cannot initialize MediaPipe Hand Landmarker: {exc}"
            ) from exc

    def _callback(self, result: Any, _output_image: Any, timestamp_ms: int) -> None:
        started = self._submitted.pop(timestamp_ms, None)
        if started is not None:
            self.last_inference_ms = (time.perf_counter_ns() - started) / 1_000_000
        if not result.hand_landmarks:
            with self._lock:
                self._latest = None
            return
        handedness = "Unknown"
        confidence = 0.0
        if result.handedness and result.handedness[0]:
            category = result.handedness[0][0]
            handedness = str(category.category_name or "Unknown")
            confidence = float(category.score or 0.0)
            if not self._handedness_mirrored_input and handedness.lower() in ("left", "right"):
                handedness = "Left" if handedness.lower() == "right" else "Right"
        image_landmarks = result.hand_landmarks[0]
        flat = tuple(
            value
            for landmark in image_landmarks
            for value in (float(landmark.x), float(landmark.y), float(landmark.z))
        )
        world: tuple[float, ...] | None = None
        if result.hand_world_landmarks:
            world = tuple(
                value
                for landmark in result.hand_world_landmarks[0]
                for value in (float(landmark.x), float(landmark.y), float(landmark.z))
            )
        detected = DetectedHand(LandmarkFrame(timestamp_ms, flat, handedness, confidence), world)
        with self._lock:
            self._latest = detected

    def submit(self, image: Any, timestamp_ms: int) -> None:
        try:
            if len(self._submitted) >= 8:
                self._submitted.pop(next(iter(self._submitted)))
            rgb = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
            mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            self._submitted[timestamp_ms] = time.perf_counter_ns()
            self._landmarker.detect_async(mp_image, timestamp_ms)
        except Exception as exc:
            raise HandLandmarkerError(f"MediaPipe frame submission failed: {exc}") from exc

    def latest(self) -> DetectedHand | None:
        with self._lock:
            latest, self._latest = self._latest, None
            return latest

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> HandLandmarker:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
