from __future__ import annotations

from mgesture.engine import Button, EngineConfig, GestureState, LandmarkFrame, PythonGestureEngine


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
