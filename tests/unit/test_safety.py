import random

from mgesture.engine import Button, EngineConfig, LandmarkFrame, PythonGestureEngine
from mgesture.engine.synthetic import synthetic_landmarks
from mgesture.input import FakeMouseBackend


def test_fake_backend_release_all_is_idempotent():
    backend = FakeMouseBackend()
    backend.button_down(Button.LEFT)
    backend.button_down(Button.RIGHT)
    backend.release_all()
    backend.release_all()
    assert backend.held == set()
    assert [event.kind for event in backend.events] == [
        "button_down",
        "button_down",
        "button_up",
        "button_up",
    ]


def test_engine_reset_releases_held_button():
    engine = PythonGestureEngine(
        EngineConfig(reacquisition_ms=0, activation_gesture=False), armed=True
    )
    engine._held = Button.LEFT
    batch = engine.reset("test")
    assert [action.button for action in batch.actions if action.type.value == "button_up"] == [
        Button.LEFT
    ]


def test_randomized_sequences_never_leave_python_engine_held_after_reset():
    rng = random.Random(7)
    engine = PythonGestureEngine(
        EngineConfig(reacquisition_ms=0, activation_gesture=False), armed=True
    )
    for index in range(100):
        first = rng.random()
        second = rng.random()
        pose = "left" if first < 0.25 else "right" if second < 0.25 else None
        engine.process(LandmarkFrame(index * 40, synthetic_landmarks(pinch=pose), "Right", 0.99))
    engine.reset("randomized cleanup")
    assert engine._held is None
