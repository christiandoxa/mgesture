from __future__ import annotations

import pytest

from mgesture.engine import EngineConfig, EngineUnavailableError, LandmarkFrame, create_engine
from mgesture.engine.synthetic import synthetic_landmarks


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
