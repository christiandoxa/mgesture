from __future__ import annotations

import threading
import time
from typing import Any

from mgesture.engine.models import HandSelection, LandmarkFrame, PhysicalHand

from .landmarks import DetectedHand, LandmarkResult, canonical_physical_hand


class HandLandmarkerError(RuntimeError):
    pass


class HandLandmarker:
    """Persistent MediaPipe context with bounded async work and hand selection."""

    _MAX_PENDING = 1
    _HAND_SWITCH_MS = 120

    def __init__(
        self,
        model_path: str,
        detection: float,
        presence: float,
        tracking: float,
        compute: str = "cpu",
        handedness_mirrored_input: bool = False,
        hand_selection: HandSelection | str = HandSelection.RIGHT,
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
        self.hand_selection = HandSelection.coerce(hand_selection)
        self._locked_hand: PhysicalHand | None = None
        self._switch_candidate: PhysicalHand | None = None
        self._switch_candidate_since_ms: int | None = None
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
                num_hands=2,
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
        hands: list[DetectedHand] = []
        image_results = getattr(result, "hand_landmarks", ()) or ()
        handedness_results = getattr(result, "handedness", ()) or ()
        world_results = getattr(result, "hand_world_landmarks", ()) or ()
        for index, image_landmarks in enumerate(image_results):
            label = "Unknown"
            confidence = 0.0
            categories = handedness_results[index] if index < len(handedness_results) else ()
            if categories:
                category = categories[0]
                label = str(getattr(category, "category_name", None) or "Unknown")
                confidence = float(getattr(category, "score", None) or 0.0)
            physical_hand = canonical_physical_hand(label, self._handedness_mirrored_input)
            flat = tuple(
                value
                for landmark in image_landmarks
                for value in (float(landmark.x), float(landmark.y), float(landmark.z))
            )
            world: tuple[float, ...] | None = None
            if index < len(world_results):
                world = tuple(
                    value
                    for landmark in world_results[index]
                    for value in (float(landmark.x), float(landmark.y), float(landmark.z))
                )
            hands.append(
                DetectedHand(LandmarkFrame(timestamp_ms, flat, physical_hand, confidence), world)
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
            detected, hand_changed = self._select_hand(hands, timestamp_ms)
            self._last_result_timestamp_ms = timestamp_ms
            if self._latest_result is not None:
                self.dropped_results += 1
            self._latest_result = LandmarkResult(timestamp_ms, detected, hand_changed, tuple(hands))
            self.completed_frames += 1

    def _select_hand(
        self, hands: list[DetectedHand], timestamp_ms: int
    ) -> tuple[DetectedHand | None, bool]:
        """Select one physical hand and retain it while both hands are visible."""
        selection = getattr(self, "hand_selection", None)
        if selection is None:
            return (hands[0] if hands else None), False
        selection = HandSelection.coerce(selection)
        eligible = [hand for hand in hands if selection.accepts(hand.frame.handedness)]
        locked = getattr(self, "_locked_hand", None)
        if locked is not None:
            current = next(
                (hand for hand in eligible if PhysicalHand.coerce(hand.frame.handedness) is locked),
                None,
            )
            if current is not None:
                self._switch_candidate = None
                self._switch_candidate_since_ms = None
                return current, False
        if not eligible:
            self._switch_candidate = None
            self._switch_candidate_since_ms = None
            return None, False
        candidate = max(eligible, key=lambda hand: hand.frame.handedness_confidence)
        candidate_hand = PhysicalHand.coerce(candidate.frame.handedness)
        if locked is None:
            self._locked_hand = candidate_hand
            return candidate, False
        if self._switch_candidate is not candidate_hand:
            self._switch_candidate = candidate_hand
            self._switch_candidate_since_ms = timestamp_ms
        else:
            if self._switch_candidate_since_ms is None:
                self._switch_candidate_since_ms = timestamp_ms
        if (
            self._switch_candidate_since_ms is None
            or timestamp_ms - self._switch_candidate_since_ms < self._HAND_SWITCH_MS
        ):
            return None, False
        self._locked_hand = candidate_hand
        self._switch_candidate = None
        self._switch_candidate_since_ms = None
        return candidate, True

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
                "handedness_mirrored_input": self._handedness_mirrored_input,
                "hand_selection": HandSelection.coerce(
                    getattr(self, "hand_selection", HandSelection.RIGHT)
                ).value,
                "locked_hand": (
                    self._locked_hand.value if getattr(self, "_locked_hand", None) else None
                ),
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
            self._locked_hand = None
            self._switch_candidate = None
            self._switch_candidate_since_ms = None
            self._discard_before_timestamp_ms = max(
                self._discard_before_timestamp_ms, self._last_submitted_timestamp_ms
            )
            self._submitted.clear()
            self._image_buffers.clear()

    def set_handedness_mirrored_input(self, mirrored: bool) -> None:
        """Change the one-time input-orientation interpretation and clear hand continuity."""
        with self._lock:
            self._handedness_mirrored_input = mirrored
            self._locked_hand = None
            self._switch_candidate = None
            self._switch_candidate_since_ms = None
            self._latest_result = None
            self._discard_before_timestamp_ms = max(
                self._discard_before_timestamp_ms, self._last_submitted_timestamp_ms
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._locked_hand = None
            self._switch_candidate = None
            self._switch_candidate_since_ms = None
            self._submitted.clear()
            self._image_buffers.clear()
        self._landmarker.close()

    def __enter__(self) -> HandLandmarker:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()
