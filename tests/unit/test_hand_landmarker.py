from __future__ import annotations

import threading
import time
from types import SimpleNamespace

from mgesture.vision.hand_landmarker import HandLandmarker


def _bare_landmarker() -> HandLandmarker:
    landmarker = object.__new__(HandLandmarker)
    landmarker._handedness_mirrored_input = False
    landmarker._latest_result = None
    landmarker._last_result_timestamp_ms = -1
    landmarker._last_polled_timestamp_ms = -1
    landmarker._discard_before_timestamp_ms = -1
    landmarker._last_submitted_timestamp_ms = -1
    landmarker._lock = threading.Lock()
    landmarker._submitted = {}
    landmarker._image_buffers = {}
    landmarker.submitted_frames = 0
    landmarker.completed_frames = 0
    landmarker.dropped_submissions = 0
    landmarker.dropped_results = 0
    landmarker.last_inference_ms = None
    landmarker._closed = False
    return landmarker


def _result(with_hand: bool) -> SimpleNamespace:
    if not with_hand:
        return SimpleNamespace(hand_landmarks=[], handedness=[], hand_world_landmarks=[])
    points = [SimpleNamespace(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    category = SimpleNamespace(category_name="Right", score=0.99)
    return SimpleNamespace(
        hand_landmarks=[points], handedness=[[category]], hand_world_landmarks=[]
    )


def test_landmarker_drops_out_of_order_results() -> None:
    landmarker = _bare_landmarker()
    landmarker._submitted = {100: time.perf_counter_ns(), 200: time.perf_counter_ns()}

    landmarker._callback(_result(True), None, 100)
    landmarker._callback(_result(True), None, 200)
    landmarker._callback(_result(True), None, 150)

    result = landmarker.poll_latest()
    assert result is not None
    assert result.timestamp_ms == 200
    assert result.hand is not None
    assert landmarker.dropped_results == 2


def test_landmarker_delivers_no_hand_as_a_timestamped_result() -> None:
    landmarker = _bare_landmarker()
    landmarker._submitted = {300: time.perf_counter_ns()}

    landmarker._callback(_result(False), None, 300)

    result = landmarker.poll_latest()
    assert result is not None
    assert result.timestamp_ms == 300
    assert result.hand is None


def test_landmarker_drops_result_older_than_newest_submission() -> None:
    landmarker = _bare_landmarker()
    landmarker._last_submitted_timestamp_ms = 200
    landmarker._submitted = {100: time.perf_counter_ns()}

    landmarker._callback(_result(True), None, 100)

    assert landmarker.poll_latest() is None
    assert landmarker.dropped_results == 1


def test_landmarker_discards_pending_results_after_camera_failure() -> None:
    landmarker = _bare_landmarker()
    landmarker._last_submitted_timestamp_ms = 200
    landmarker._submitted = {200: time.perf_counter_ns()}
    landmarker._image_buffers = {200: object()}

    landmarker.discard_pending()
    landmarker._callback(_result(True), None, 200)

    assert landmarker.poll_latest() is None
    assert landmarker._submitted == {}
    assert landmarker._image_buffers == {}
