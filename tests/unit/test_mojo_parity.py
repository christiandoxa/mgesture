from __future__ import annotations

import math

import pytest

from mgesture.engine import (
    EngineConfig,
    EngineUnavailableError,
    HandSelection,
    LandmarkFrame,
    create_engine,
)
from mgesture.engine.synthetic import synthetic_landmarks


def _ambiguous_landmarks():
    values = list(synthetic_landmarks())
    values[12:15] = (0.50, 0.325, 0.0)
    return tuple(values)


def test_mojo_and_python_match_pointer_and_button_contract():
    try:
        config = EngineConfig(reacquisition_ms=0, activation_gesture=False, dead_zone=0.0)
        python_engine = create_engine("python", config, armed=True)
        mojo_engine = create_engine("mojo", config, armed=True)
    except EngineUnavailableError as exc:
        pytest.skip(str(exc))
    frames = [
        LandmarkFrame(0, synthetic_landmarks(0.4, 0.4), "Right", 0.99),
        LandmarkFrame(200, synthetic_landmarks(0.4, 0.4), "Right", 0.99),
        LandmarkFrame(280, synthetic_landmarks(0.4, 0.4, "left"), "Right", 0.99),
        LandmarkFrame(360, synthetic_landmarks(0.4, 0.4, "left"), "Right", 0.99),
        LandmarkFrame(400, synthetic_landmarks(0.4, 0.4), "Right", 0.99),
        LandmarkFrame(440, synthetic_landmarks(0.4, 0.4), "Right", 0.99),
    ]
    python_actions = [
        action
        for frame in frames
        for action in python_engine.process(frame).actions
        if action.type.value != "state"
    ]
    mojo_actions = [
        action
        for frame in frames
        for action in mojo_engine.process(frame).actions
        if action.type.value != "state"
    ]
    assert [(action.type.value, action.button) for action in mojo_actions if action.button] == [
        (action.type.value, action.button) for action in python_actions if action.button
    ]
    python_moves = [action for action in python_actions if action.type.value == "move_absolute"]
    mojo_moves = [action for action in mojo_actions if action.type.value == "move_absolute"]
    assert len(mojo_moves) == len(python_moves)
    for mojo_move, python_move in zip(mojo_moves, python_moves, strict=True):
        assert abs((mojo_move.x or 0.0) - (python_move.x or 0.0)) < 80.0
        assert abs((mojo_move.y or 0.0) - (python_move.y or 0.0)) < 80.0


def test_mojo_and_python_match_safety_and_arbitration_edges():
    try:
        config = EngineConfig(
            reacquisition_ms=100,
            hand_loss_timeout_ms=100,
            activation_gesture=False,
            dead_zone=0.0,
        )
        python_engine = create_engine("python", config, armed=True)
        mojo_engine = create_engine("mojo", config, armed=True)
    except EngineUnavailableError as exc:
        pytest.skip(str(exc))
    ambiguous = _ambiguous_landmarks()
    invalid = list(synthetic_landmarks())
    invalid[0] = math.nan
    frames = [
        LandmarkFrame(0, synthetic_landmarks(pinch="left"), "Right", 0.99),
        LandmarkFrame(120, synthetic_landmarks(pinch="left"), "Right", 0.99),
        LandmarkFrame(200, synthetic_landmarks(pinch="left"), "Right", 0.99),
        LandmarkFrame(220, tuple(invalid), "Right", 0.99),
        LandmarkFrame(330, tuple(invalid), "Right", 0.99),
        LandmarkFrame(360, ambiguous, "Right", 0.99),
        LandmarkFrame(360, ambiguous, "Right", 0.99),
        LandmarkFrame(460, ambiguous, "Right", 0.99),
        LandmarkFrame(540, ambiguous, "Right", 0.99),
        LandmarkFrame(580, synthetic_landmarks(), "Right", 0.99),
        LandmarkFrame(620, synthetic_landmarks(), "Right", 0.99),
    ]
    for frame in frames:
        python_batch = python_engine.process(frame)
        mojo_batch = mojo_engine.process(frame)
        assert [
            (action.type.value, action.button, action.state) for action in mojo_batch.actions
        ] == [(action.type.value, action.button, action.state) for action in python_batch.actions]


def test_mojo_and_python_match_left_hand_selection():
    try:
        config = EngineConfig(
            hand_selection=HandSelection.LEFT,
            reacquisition_ms=0,
            activation_gesture=False,
            dead_zone=0.0,
        )
        python_engine = create_engine("python", config, armed=True)
        mojo_engine = create_engine("mojo", config, armed=True)
    except EngineUnavailableError as exc:
        pytest.skip(str(exc))
    frames = [
        LandmarkFrame(0, synthetic_landmarks(0.4, 0.4), "Left", 0.99),
        LandmarkFrame(200, synthetic_landmarks(0.4, 0.4), "Left", 0.99),
        LandmarkFrame(280, synthetic_landmarks(0.4, 0.4, "left"), "Left", 0.99),
        LandmarkFrame(360, synthetic_landmarks(0.4, 0.4, "left"), "Left", 0.99),
        LandmarkFrame(440, synthetic_landmarks(0.4, 0.4), "Left", 0.99),
        LandmarkFrame(500, synthetic_landmarks(0.4, 0.4), "Left", 0.99),
    ]

    for frame in frames:
        python_batch = python_engine.process(frame)
        mojo_batch = mojo_engine.process(frame)
        assert [
            (action.type.value, action.button, action.state) for action in mojo_batch.actions
        ] == [(action.type.value, action.button, action.state) for action in python_batch.actions]


def test_mojo_and_python_release_on_hand_switch():
    try:
        config = EngineConfig(
            hand_selection=HandSelection.EITHER,
            reacquisition_ms=0,
            activation_gesture=False,
        )
        python_engine = create_engine("python", config, armed=True)
        mojo_engine = create_engine("mojo", config, armed=True)
    except EngineUnavailableError as exc:
        pytest.skip(str(exc))
    frames = (
        LandmarkFrame(0, synthetic_landmarks(pinch="left"), "Right", 0.99),
        LandmarkFrame(80, synthetic_landmarks(pinch="left"), "Right", 0.99),
        LandmarkFrame(120, synthetic_landmarks(pinch="left"), "Left", 0.99),
    )

    for frame in frames:
        python_batch = python_engine.process(frame)
        mojo_batch = mojo_engine.process(frame)
        assert [
            (action.type.value, action.button, action.state) for action in mojo_batch.actions
        ] == [(action.type.value, action.button, action.state) for action in python_batch.actions]
