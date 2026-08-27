from __future__ import annotations

import math
import random

from mgesture.engine import (
    Button,
    EngineConfig,
    GestureState,
    HandSelection,
    LandmarkFrame,
    PythonGestureEngine,
)
from mgesture.engine.python_engine import OneEuroFilter


def hand(index=(0.45, 0.25), pinch=None, scroll=False, open_palm=False):
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
    points[8] = (*index, 0.0)
    points[12] = (0.55, 0.2 if scroll or open_palm else 0.4, 0.0)
    points[16] = (0.58, 0.5 if not open_palm else 0.2, 0.0)
    points[20] = (0.65, 0.55 if not open_palm else 0.25, 0.0)
    points[4] = (0.25, 0.65, 0.0)
    if pinch == "left":
        points[4] = (index[0] + 0.02, index[1] + 0.02, 0.0)
    elif pinch == "right":
        points[4] = (points[12][0] + 0.02, points[12][1] + 0.02, 0.0)
    if open_palm:
        points[12] = (0.55, 0.2, 0.0)
        points[16] = (0.58, 0.2, 0.0)
        points[20] = (0.65, 0.25, 0.0)
        points[4] = (0.25, 0.65, 0.0)
    return tuple(value for point in points for value in point)


def frame(timestamp, points, handedness="Right", confidence=0.99):
    return LandmarkFrame(timestamp, points, handedness, confidence)


def engine(**overrides):
    values = {"reacquisition_ms": 0, "activation_gesture": False}
    values.update(overrides)
    return PythonGestureEngine(EngineConfig(**values), armed=True)


def _scale_hand(points, factor):
    values = list(points)
    for point in range(21):
        offset = point * 3
        values[offset] = 0.5 + (values[offset] - 0.5) * factor
        values[offset + 1] = 0.5 + (values[offset + 1] - 0.5) * factor
        values[offset + 2] *= factor
    return tuple(values)


def _ambiguous_hand():
    values = list(hand())
    values[12:15] = (0.50, 0.325, 0.0)
    return tuple(values)


def _palm_offset(points, offset):
    values = list(points)
    for point in (0, 5, 9, 13, 17):
        values[point * 3 + 1] += offset
    return tuple(values)


def _scroll_hand(index_y=0.25, ring_y=0.50, pinky_y=0.55):
    values = list(hand(scroll=True, index=(0.45, index_y)))
    values[16 * 3 + 1] = ring_y
    values[20 * 3 + 1] = pinky_y
    return tuple(values)


def _translate_hand(points, dx=0.0, dy=0.0):
    values = list(points)
    for point in range(21):
        values[point * 3] += dx
        values[point * 3 + 1] += dy
    return tuple(values)


def test_center_mapping_and_negative_desktop_bounds():
    gesture = PythonGestureEngine(
        EngineConfig(
            screen_x=-1920,
            screen_y=-100,
            screen_width=3840,
            screen_height=1200,
            reacquisition_ms=0,
            activation_gesture=False,
        ),
        armed=True,
    )
    batch = gesture.process(frame(0, hand(index=(0.5, 0.5))))
    move = next(action for action in batch.actions if action.type.value == "move_absolute")
    assert -1920 <= move.x <= 1920
    assert -100 <= move.y <= 1099


def test_left_pinch_has_one_down_and_one_up():
    gesture = engine()
    for timestamp in (0, 40, 80):
        batch = gesture.process(frame(timestamp, hand(pinch="left")))
    assert [action.button for action in batch.actions if action.type.value == "button_down"] == [
        Button.LEFT
    ]
    gesture.process(frame(100, hand()))
    batch = gesture.process(frame(140, hand()))
    assert [action.button for action in batch.actions if action.type.value == "button_up"] == [
        Button.LEFT
    ]


def test_left_physical_hand_uses_canonical_gesture_mapping():
    gesture = engine(hand_selection=HandSelection.LEFT)
    actions = []
    for timestamp, pose in ((0, "left"), (80, "left"), (100, None), (140, None)):
        actions.extend(gesture.process(frame(timestamp, hand(pinch=pose), "Left")).actions)

    assert [(action.type.value, action.button) for action in actions if action.button] == [
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
    ]


def test_left_and_right_hands_share_pointer_mapping():
    right = engine(hand_selection=HandSelection.RIGHT).process(
        frame(0, hand(index=(0.2, 0.3)), "Right")
    )
    left = engine(hand_selection=HandSelection.LEFT).process(
        frame(0, hand(index=(0.2, 0.3)), "Left")
    )

    right_move = next(action for action in right.actions if action.type.value == "move_absolute")
    left_move = next(action for action in left.actions if action.type.value == "move_absolute")
    assert (left_move.x, left_move.y) == (right_move.x, right_move.y)


def test_either_hand_switch_releases_old_button_before_new_hand():
    gesture = engine(hand_selection=HandSelection.EITHER)
    gesture.process(frame(0, hand(pinch="left"), "Right"))
    gesture.process(frame(80, hand(pinch="left"), "Right"))

    switched = gesture.process(frame(120, hand(pinch="left"), "Left"))

    assert [(action.type.value, action.button) for action in switched.actions if action.button] == [
        ("button_up", Button.LEFT)
    ]
    assert switched.diagnostics["hand_switched"] is True
    assert gesture._held is None


def test_sustained_left_pinch_holds_while_moving():
    gesture = engine()
    gesture.process(frame(0, hand(pinch="left", index=(0.45, 0.25))))
    gesture.process(frame(80, hand(pinch="left", index=(0.45, 0.25))))
    assert Button.LEFT in gesture._held
    batch = gesture.process(frame(120, hand(pinch="left", index=(0.75, 0.75))))
    assert Button.LEFT in gesture._held
    assert not any(action.type.value == "button_up" for action in batch.actions)


def test_two_cycles_make_two_pairs():
    gesture = engine()
    actions = []
    for timestamp, pose in (
        (0, "left"),
        (80, "left"),
        (100, None),
        (140, None),
        (200, "left"),
        (280, "left"),
        (300, None),
        (340, None),
    ):
        actions.extend(gesture.process(frame(timestamp, hand(pinch=pose))).actions)
    buttons = [(action.type.value, action.button) for action in actions if action.button]
    assert buttons == [
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
    ]


def test_right_pinch_never_emits_left():
    gesture = engine()
    actions = []
    for timestamp in (0, 80, 120):
        actions.extend(gesture.process(frame(timestamp, hand(pinch="right"))).actions)
    assert any(action.button is Button.RIGHT for action in actions)
    assert not any(action.button is Button.LEFT for action in actions)


def test_hand_loss_releases_held_button():
    gesture = engine()
    gesture.process(frame(0, hand(pinch="left")))
    gesture.process(frame(80, hand(pinch="left")))
    gesture.process(frame(400, hand(), "Left", 0.99))
    batch = gesture.process(frame(700, hand(), "Left", 0.99))
    assert any(
        action.type.value == "button_up" and action.button is Button.LEFT
        for action in batch.actions
    )
    assert gesture._held is None


def test_low_confidence_and_left_hand_are_ignored():
    gesture = engine()
    for timestamp in (0, 80, 160):
        batch = gesture.process(frame(timestamp, hand(pinch="left"), "Left", 0.99))
        assert not any(action.button for action in batch.actions)
        batch = gesture.process(frame(timestamp + 1, hand(pinch="left"), "Right", 0.2))
        assert not any(action.button for action in batch.actions)


def test_scroll_requires_stable_pose_and_accumulates_vertical_steps():
    gesture = engine(scroll_entry_ms=100, scroll_sensitivity=20)
    gesture.process(frame(0, hand(scroll=True)))
    batch = gesture.process(frame(120, hand(scroll=True)))
    assert batch.state is GestureState.SCROLL
    moved = list(hand(scroll=True))
    for landmark in (0, 5, 9, 13, 17):
        moved[landmark * 3 + 1] += 0.1
    batch = gesture.process(frame(160, tuple(moved)))
    assert any(action.type.value == "scroll" and action.dy != 0 for action in batch.actions)


def test_scroll_accepts_bent_index_and_relaxed_fingers_with_progress():
    points = _scroll_hand(index_y=0.36, ring_y=0.43, pinky_y=0.50)
    gesture = engine(scroll_entry_ms=100)

    first = gesture.process(frame(0, points))
    halfway = gesture.process(frame(50, points))
    active = gesture.process(frame(100, points))

    assert first.diagnostics["scroll_fingers_ready"] is True
    assert halfway.state is GestureState.ARMED
    assert halfway.diagnostics["scroll_entry_progress"] == 0.5
    assert active.state is GestureState.SCROLL
    assert active.diagnostics["scroll_active"] is True


def test_scroll_pose_jitter_and_open_fingers_never_enter():
    gesture = engine(scroll_entry_ms=100)
    actions = []
    for index in range(30):
        points = (
            _scroll_hand(index_y=0.36, ring_y=0.43, pinky_y=0.50)
            if index % 2
            else _scroll_hand(index_y=0.38, ring_y=0.43, pinky_y=0.50)
        )
        actions.extend(gesture.process(frame(index * 33, points)).actions)

    assert gesture.state is GestureState.ARMED
    assert not [action for action in actions if action.type.value == "scroll"]


def test_scroll_open_palm_jitter_never_enters():
    gesture = engine(scroll_entry_ms=100)
    actions = []
    for index in range(30):
        points = (
            _scroll_hand(index_y=0.36, ring_y=0.20, pinky_y=0.20)
            if index % 2
            else hand(open_palm=True)
        )
        actions.extend(gesture.process(frame(index * 33, points)).actions)

    assert gesture.state is GestureState.ARMED
    assert not [action for action in actions if action.type.value == "scroll"]


def test_scroll_positive_landmark_jitter_stays_active_without_wheel_noise():
    rng = random.Random(20260827)
    gesture = engine(
        scroll_entry_ms=100,
        scroll_exit_grace_ms=80,
        scroll_dead_zone=0.002,
        scroll_sensitivity=1000,
    )
    points = _scroll_hand(index_y=0.36, ring_y=0.43, pinky_y=0.50)
    actions = []
    for index in range(60):
        jittered = _translate_hand(points, dy=rng.uniform(-0.0006, 0.0006))
        actions.extend(gesture.process(frame(index * 33, jittered)).actions)

    assert gesture.state is GestureState.SCROLL
    assert not [action for action in actions if action.type.value == "scroll"]


def test_scroll_active_survives_brief_landmark_dropout_and_rebases_anchor():
    gesture = engine(scroll_entry_ms=0, scroll_exit_grace_ms=80, scroll_sensitivity=20)
    points = _scroll_hand(index_y=0.36, ring_y=0.43, pinky_y=0.50)

    entered = gesture.process(frame(0, points))
    dropout = gesture.process(frame(40, (0.0,) * 63))
    recovered = gesture.process(frame(80, _translate_hand(points, dy=0.04)))
    moved = gesture.process(frame(120, _translate_hand(points, dy=0.10)))

    assert entered.state is GestureState.SCROLL
    assert dropout.state is GestureState.SCROLL
    assert dropout.diagnostics["scroll_exit_grace"] is True
    assert recovered.state is GestureState.SCROLL
    assert not [action for action in recovered.actions if action.type.value == "scroll"]
    assert any(action.type.value == "scroll" for action in moved.actions)

    gesture.process(frame(220, (0.0,) * 63))
    expired = gesture.process(frame(320, (0.0,) * 63))
    assert expired.state is GestureState.ARMED


def test_scroll_active_hysteresis_tolerates_thumb_drift_without_clicking():
    gesture = engine(scroll_entry_ms=0, scroll_exit_grace_ms=80)
    points = list(_scroll_hand())
    points[4 * 3 : 4 * 3 + 3] = (0.45, 0.40, 0.0)

    entered = gesture.process(frame(0, _scroll_hand()))
    drifted = gesture.process(frame(40, tuple(points)))

    assert entered.state is GestureState.SCROLL
    assert drifted.state is GestureState.SCROLL
    assert drifted.diagnostics["scroll_pinch_clear"] is False
    assert drifted.diagnostics["scroll_active_pinch_clear"] is True
    assert not [action for action in drifted.actions if action.button]


def test_scroll_direction_and_fractional_accumulator_are_stable():
    gesture = engine(
        scroll_entry_ms=0,
        scroll_sensitivity=20,
        scroll_dead_zone=0.01,
    )
    points = _scroll_hand()
    actions = [gesture.process(frame(0, points))]
    for timestamp, offset in ((33, 0.02), (66, 0.04), (99, 0.06), (132, -0.06)):
        actions.append(gesture.process(frame(timestamp, _translate_hand(points, dy=offset))))

    scroll_values = [
        action.dy for batch in actions for action in batch.actions if action.type.value == "scroll"
    ]
    assert scroll_values == [-1.0, 2.0]

    inverted = engine(
        scroll_entry_ms=0,
        scroll_sensitivity=20,
        scroll_dead_zone=0.01,
        scroll_direction=-1,
    )
    inverted.process(frame(0, points))
    batch = inverted.process(frame(33, _translate_hand(points, dy=0.06)))
    assert [action.dy for action in batch.actions if action.type.value == "scroll"] == [1.0]


def test_scroll_never_preempts_pinch_or_drag():
    gesture = engine(scroll_entry_ms=0)

    def left_scroll_pinch(index=(0.45, 0.25)):
        values = list(hand(scroll=True, pinch="left", index=index))
        values[12 * 3 + 1] = 0.10
        return tuple(values)

    gesture.process(frame(0, left_scroll_pinch()))
    down = gesture.process(frame(80, left_scroll_pinch()))
    drag = gesture.process(frame(120, left_scroll_pinch((0.75, 0.75))))

    assert any(action.button is Button.LEFT for action in down.actions)
    assert not [action for action in drag.actions if action.type.value == "scroll"]
    assert gesture._held is Button.LEFT


def test_pause_releases_every_button_and_is_idempotent():
    gesture = engine()
    gesture.process(frame(0, hand(pinch="left")))
    gesture.process(frame(80, hand(pinch="left")))
    batch = gesture.set_armed(False)
    assert any(action.type.value == "button_up" for action in batch.actions)
    assert gesture.set_armed(False).actions == ()


def test_reacquisition_suppresses_first_pointer_frame():
    gesture = engine(reacquisition_ms=100)
    first = gesture.process(frame(0, hand(index=(0.2, 0.2))))
    assert not any(action.type.value == "move_absolute" for action in first.actions)
    second = gesture.process(frame(120, hand(index=(0.2, 0.2))))
    assert any(action.type.value == "move_absolute" for action in second.actions)


def test_one_euro_adapts_to_frame_interval():
    responses = []
    for interval in (1 / 60, 1 / 30, 1 / 15):
        smoother = OneEuroFilter(1.0, 0.007, 1.0)
        smoother.filter(0.0, 0.0, 0.0)
        responses.append(smoother.filter(1.0, 1.0, interval)[0])
    assert responses[0] < responses[1] < responses[2]


def test_generated_cursor_jitter_stays_inside_dead_zone():
    rng = random.Random(20260827)
    gesture = engine(dead_zone=0.002)
    moves = []
    for index in range(120):
        points = hand(index=(0.45 + rng.uniform(-0.001, 0.001), 0.25 + rng.uniform(-0.001, 0.001)))
        batch = gesture.process(frame((index // 2) * 33, points))
        moves.extend(action for action in batch.actions if action.type.value == "move_absolute")
    assert len(moves) == 1


def test_generated_scaled_pinches_keep_one_click_pair():
    for factor in (0.5, 1.0, 2.0):
        gesture = engine()
        points = _scale_hand(hand(pinch="left"), factor)
        actions = []
        for timestamp, pinch_points in (
            (0, points),
            (80, points),
            (100, _scale_hand(hand(), factor)),
            (140, _scale_hand(hand(), factor)),
        ):
            actions.extend(gesture.process(frame(timestamp, pinch_points)).actions)
        assert [(action.type.value, action.button) for action in actions if action.button] == [
            ("button_down", Button.LEFT),
            ("button_up", Button.LEFT),
        ]


def test_zero_time_debounce_still_emits_one_press_and_release():
    gesture = engine(debounce_ms=0, release_debounce_ms=0)
    down = gesture.process(frame(0, hand(pinch="left")))
    up = gesture.process(frame(0, hand()))
    assert [action.button for action in down.actions if action.type.value == "button_down"] == [
        Button.LEFT
    ]
    assert [action.button for action in up.actions if action.type.value == "button_up"] == [
        Button.LEFT
    ]


def test_generated_short_pinch_pulses_emit_no_false_clicks():
    rng = random.Random(20260827)
    gesture = engine()
    actions = []
    timestamp = 0
    for _ in range(24):
        for _ in range(rng.choice((1, 2))):
            actions.extend(gesture.process(frame(timestamp, hand(pinch="left"))).actions)
            timestamp += 30
        for _ in range(2):
            actions.extend(gesture.process(frame(timestamp, hand())).actions)
            timestamp += 30
    assert not [action for action in actions if action.button]


def test_generated_double_click_and_release_jitter_emit_no_duplicates():
    rng = random.Random(11)
    gesture = engine()
    actions = []
    timestamp = 0
    for _ in range(2):
        actions.extend(gesture.process(frame(timestamp, hand(pinch="left"))).actions)
        timestamp += 80 + rng.choice((0, 10))
        actions.extend(gesture.process(frame(timestamp, hand(pinch="left"))).actions)
        timestamp += 10
        actions.extend(gesture.process(frame(timestamp, hand())).actions)
        timestamp += 10
        actions.extend(gesture.process(frame(timestamp, hand(pinch="left"))).actions)
        timestamp += 10
        actions.extend(gesture.process(frame(timestamp, hand())).actions)
        timestamp += 35 + rng.choice((5, 10))
        actions.extend(gesture.process(frame(timestamp, hand())).actions)
        timestamp += 50
    assert [(action.type.value, action.button) for action in actions if action.button] == [
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
    ]


def test_generated_drag_moves_while_held_and_releases_once():
    gesture = engine()
    actions = []
    actions.extend(gesture.process(frame(0, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(80, hand(pinch="left"))).actions)
    for index in range(1, 7):
        actions.extend(
            gesture.process(
                frame(
                    80 + index * 35,
                    hand(index=(0.45 + index * 0.04, 0.25 + index * 0.04), pinch="left"),
                )
            ).actions
        )
    actions.extend(gesture.process(frame(330, hand())).actions)
    actions.extend(gesture.process(frame(340, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(360, hand())).actions)
    actions.extend(gesture.process(frame(400, hand())).actions)
    button_events = [(action.type.value, action.button) for action in actions if action.button]
    assert button_events == [
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
    ]
    assert sum(action.type.value == "move_absolute" for action in actions) >= 3


def test_generated_scroll_jitter_stays_in_dead_zone():
    gesture = engine(scroll_entry_ms=0, scroll_sensitivity=1000, scroll_dead_zone=0.001)
    actions = []
    for index in range(120):
        offset = 0.0008 if index % 2 else -0.0008
        actions.extend(
            gesture.process(frame(index * 33, _palm_offset(hand(scroll=True), offset))).actions
        )
    assert not [action for action in actions if action.type.value == "scroll"]


def test_invalid_landmarks_cancel_pending_click_and_release_held_button():
    gesture = engine(hand_loss_timeout_ms=100, reacquisition_ms=100)
    gesture.process(frame(0, hand(pinch="left")))
    gesture.process(frame(120, hand(pinch="left")))
    gesture.process(frame(200, hand(pinch="left")))
    invalid = list(hand())
    invalid[8 * 3] = math.nan
    first = gesture.process(frame(220, tuple(invalid)))
    second = gesture.process(frame(330, tuple(invalid)))
    assert not [action for action in first.actions if action.button]
    assert [action.button for action in second.actions if action.type.value == "button_up"] == [
        Button.LEFT
    ]
    assert gesture._held is None
    reacquired = gesture.process(frame(360, hand()))
    assert not [action for action in reacquired.actions if action.type.value == "move_absolute"]


def test_generated_brief_hand_loss_reacquires_without_duplicate_click():
    gesture = engine(hand_loss_timeout_ms=250, reacquisition_ms=100)
    actions = []
    actions.extend(gesture.process(frame(0, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(120, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(200, hand(pinch="left"))).actions)
    for timestamp in (220, 320):
        actions.extend(gesture.process(frame(timestamp, hand(), "Left", 0.99)).actions)
    actions.extend(gesture.process(frame(340, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(440, hand(pinch="left"))).actions)
    actions.extend(gesture.process(frame(460, hand())).actions)
    actions.extend(gesture.process(frame(500, hand())).actions)
    assert [(action.type.value, action.button) for action in actions if action.button] == [
        ("button_down", Button.LEFT),
        ("button_up", Button.LEFT),
    ]


def test_generated_ambiguous_pinch_always_selects_right():
    gesture = engine()
    ambiguous = _ambiguous_hand()
    actions = []
    for timestamp, points in (
        (0, ambiguous),
        (80, ambiguous),
        (120, ambiguous),
        (160, hand()),
        (200, hand()),
    ):
        actions.extend(gesture.process(frame(timestamp, points)).actions)
    assert [(action.type.value, action.button) for action in actions if action.button] == [
        ("button_down", Button.RIGHT),
        ("button_up", Button.RIGHT),
    ]
