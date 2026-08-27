from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from mgesture.engine import HandSelection, PhysicalHand
from mgesture.vision.hand_landmarker import HandLandmarker


def _bare_landmarker(
    hand_selection: HandSelection | None = None, mirrored_input: bool = False
) -> HandLandmarker:
    landmarker = object.__new__(HandLandmarker)
    landmarker._handedness_mirrored_input = mirrored_input
    if hand_selection is not None:
        landmarker.hand_selection = hand_selection
        landmarker._locked_hand = None
        landmarker._switch_candidate = None
        landmarker._switch_candidate_frames = 0
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


def _result(labels: bool | str | tuple[str, ...]) -> SimpleNamespace:
    if labels is False:
        return SimpleNamespace(hand_landmarks=[], handedness=[], hand_world_landmarks=[])
    if labels is True:
        labels = ("Right",)
    elif isinstance(labels, str):
        labels = (labels,)
    points = [
        [SimpleNamespace(x=0.5 + index * 0.01, y=0.5, z=0.0) for _ in range(21)]
        for index, _label in enumerate(labels)
    ]
    categories = [[SimpleNamespace(category_name=label, score=0.99)] for label in labels]
    return SimpleNamespace(hand_landmarks=points, handedness=categories, hand_world_landmarks=[])


def _deliver(landmarker: HandLandmarker, timestamp_ms: int, labels: bool | str | tuple[str, ...]):
    landmarker._submitted = {timestamp_ms: time.perf_counter_ns()}
    landmarker._last_submitted_timestamp_ms = timestamp_ms
    landmarker._callback(_result(labels), None, timestamp_ms)
    return landmarker.poll_latest()


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


@pytest.mark.parametrize(
    ("mirrored_input", "label", "expected"),
    (
        (True, "Right", PhysicalHand.RIGHT),
        (True, "Left", PhysicalHand.LEFT),
        (False, "Right", PhysicalHand.LEFT),
        (False, "Left", PhysicalHand.RIGHT),
    ),
)
def test_landmarker_normalizes_mediapipe_label_to_physical_hand(
    mirrored_input: bool, label: str, expected: PhysicalHand
) -> None:
    landmarker = _bare_landmarker(HandSelection.EITHER, mirrored_input)

    result = _deliver(landmarker, 1, label)

    assert result is not None and result.hand is not None
    assert result.hand.frame.handedness is expected
    assert len(result.hands) == 1


def test_landmarker_can_recalibrate_input_orientation_without_second_inference() -> None:
    landmarker = _bare_landmarker(HandSelection.EITHER, mirrored_input=False)

    first = _deliver(landmarker, 1, "Right")
    landmarker.set_handedness_mirrored_input(True)
    second = _deliver(landmarker, 2, "Right")

    assert first is not None and first.hand is not None
    assert second is not None and second.hand is not None
    assert first.hand.frame.physical_hand is PhysicalHand.LEFT
    assert second.hand.frame.physical_hand is PhysicalHand.RIGHT


def test_landmarker_locks_auto_selection_when_result_order_changes() -> None:
    landmarker = _bare_landmarker(HandSelection.AUTO, mirrored_input=True)

    first = _deliver(landmarker, 1, ("Right", "Left"))
    reordered = _deliver(landmarker, 2, ("Left", "Right"))
    waiting_one = _deliver(landmarker, 3, ("Left",))
    waiting_two = _deliver(landmarker, 4, ("Left",))
    switched = _deliver(landmarker, 5, ("Left",))

    assert first is not None and first.hand is not None
    assert first.hand.frame.handedness is PhysicalHand.RIGHT
    assert reordered is not None and reordered.hand is not None
    assert reordered.hand.frame.handedness is PhysicalHand.RIGHT
    assert waiting_one is not None and waiting_one.hand is None
    assert waiting_two is not None and waiting_two.hand is None
    assert switched is not None and switched.hand is not None
    assert switched.hand.frame.handedness is PhysicalHand.LEFT
    assert switched.hand_changed is True
