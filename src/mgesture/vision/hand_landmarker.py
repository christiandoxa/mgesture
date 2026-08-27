from __future__ import annotations

import threading
import time
from typing import Any

from mgesture.engine.models import LandmarkFrame

from .landmarks import DetectedHand, LandmarkResult


class HandLandmarkerError(RuntimeError):
    pass


class HandLandmarker:
    """Persistent MediaPipe context with bounded async work and newest-result delivery."""

    _MAX_PENDING = 1

    def __init__(
        self,
        model_path: str,
        detection: float,
        presence: float,
        tracking: float,
        compute: str = "cpu",
        handedness_mirrored_input: bool = False,
    ) -> None:
        if compute not in ("cpu", "gpu"):
            raise HandLandmarkerError(f"unsupported MediaPipe compute mode: {compute}")
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
        self._latest_result: LandmarkResult | None = None
        self._last_result_timestamp_ms = -1
        self._last_polled_timestamp_ms = -1
        self._discard_before_timestamp_ms = -1
        self._last_submitted_timestamp_ms = -1
        self._lock = threading.Lock()
        self._submitted: dict[int, int] = {}
        self._image_buffers: dict[int, Any] = {}
        self.submitted_frames = 0
        self.completed_frames = 0
        self.dropped_submissions = 0
        self.dropped_results = 0
        self.last_inference_ms: float | None = None
        self.compute = compute
        self._closed = False
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
        except HandLandmarkerError:
            raise
        except Exception as exc:
            raise HandLandmarkerError(
                f"cannot initialize MediaPipe Hand Landmarker ({compute}): {exc}"
            ) from exc

    def _callback(self, result: Any, _output_image: Any, timestamp_ms: int) -> None:
        with self._lock:
            started = self._submitted.pop(timestamp_ms, None)
            self._image_buffers.pop(timestamp_ms, None)
            if (
                self._closed
                or timestamp_ms
                <= max(
                    self._last_result_timestamp_ms,
                    self._last_polled_timestamp_ms,
                    self._discard_before_timestamp_ms,
                )
                or timestamp_ms < self._last_submitted_timestamp_ms
                or (started is None and timestamp_ms == self._last_submitted_timestamp_ms)
            ):
                self.dropped_results += 1
                return
        if started is not None:
            self.last_inference_ms = (time.perf_counter_ns() - started) / 1_000_000
        detected: DetectedHand | None = None
        if result.hand_landmarks:
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
            detected = DetectedHand(
                LandmarkFrame(timestamp_ms, flat, handedness, confidence), world
            )
        with self._lock:
            if (
                self._closed
                or timestamp_ms
                <= max(
                    self._last_result_timestamp_ms,
                    self._last_polled_timestamp_ms,
                    self._discard_before_timestamp_ms,
                )
                or timestamp_ms < self._last_submitted_timestamp_ms
                or (started is None and timestamp_ms == self._last_submitted_timestamp_ms)
            ):
                self.dropped_results += 1
                return
            self._last_result_timestamp_ms = timestamp_ms
            if self._latest_result is not None:
                self.dropped_results += 1
            self._latest_result = LandmarkResult(timestamp_ms, detected)
            self.completed_frames += 1

    def submit(self, image: Any, timestamp_ms: int) -> bool:
        """Submit newest frame; return false when timestamp/work was already superseded."""
        with self._lock:
            if self._closed or timestamp_ms <= max(
                self._last_submitted_timestamp_ms, self._last_polled_timestamp_ms
            ):
                self.dropped_submissions += 1
                return False
            if len(self._submitted) >= self._MAX_PENDING:
                self.dropped_submissions += 1
                return False
        try:
            rgb = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
            flags = getattr(rgb, "flags", None)
            contiguous = getattr(flags, "c_contiguous", None)
            if contiguous is None and flags is not None:
                try:
                    contiguous = bool(flags["C_CONTIGUOUS"])
                except (KeyError, TypeError):
                    contiguous = True
            if contiguous is False:
                import numpy as np

                rgb = np.ascontiguousarray(rgb)
        except Exception as exc:
            raise HandLandmarkerError(f"MediaPipe frame preprocessing failed: {exc}") from exc
        started = time.perf_counter_ns()
        with self._lock:
            if self._closed or timestamp_ms <= max(
                self._last_submitted_timestamp_ms, self._last_polled_timestamp_ms
            ):
                self.dropped_submissions += 1
                return False
            if len(self._submitted) >= self._MAX_PENDING:
                self.dropped_submissions += 1
                return False
            self._last_submitted_timestamp_ms = timestamp_ms
            self._submitted[timestamp_ms] = started
            self._image_buffers[timestamp_ms] = rgb
            self.submitted_frames += 1
        try:
            self._landmarker.detect_async(
                self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), timestamp_ms
            )
        except Exception as exc:
            with self._lock:
                self._submitted.pop(timestamp_ms, None)
                self._image_buffers.pop(timestamp_ms, None)
            raise HandLandmarkerError(f"MediaPipe frame submission failed: {exc}") from exc
        return True

    def poll_latest(self) -> LandmarkResult | None:
        with self._lock:
            latest, self._latest_result = self._latest_result, None
            if latest is None:
                return None
            self._last_polled_timestamp_ms = latest.timestamp_ms
            return latest

    def latest(self) -> DetectedHand | None:
        result = self.poll_latest()
        return result.hand if result is not None else None

    def diagnostics(self) -> dict[str, object]:
        with self._lock:
            return {
                "compute": self.compute,
                "submitted_frames": self.submitted_frames,
                "completed_frames": self.completed_frames,
                "pending_frames": len(self._submitted),
                "dropped_submissions": self.dropped_submissions,
                "dropped_results": self.dropped_results,
                "last_inference_ms": self.last_inference_ms,
                "last_submitted_timestamp_ms": self._last_submitted_timestamp_ms,
                "last_result_timestamp_ms": self._last_result_timestamp_ms,
                "discard_before_timestamp_ms": self._discard_before_timestamp_ms,
            }

    def discard_pending(self) -> None:
        """Invalidate callbacks for frames captured before an upstream camera failure."""
        with self._lock:
            self._latest_result = None
            self._discard_before_timestamp_ms = max(
                self._discard_before_timestamp_ms, self._last_submitted_timestamp_ms
            )
            self._submitted.clear()
            self._image_buffers.clear()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._submitted.clear()
            self._image_buffers.clear()
        self._landmarker.close()

    def __enter__(self) -> HandLandmarker:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
