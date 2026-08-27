import pytest

from mgesture.commands.calibrate import calibrated_pinch_thresholds, robust_median
from mgesture.engine import EngineConfig, PythonGestureEngine
from mgesture.engine.synthetic import synthetic_landmarks


def test_robust_median_rejects_extreme_observation() -> None:
    assert robust_median([0.42, 0.43, 0.42, 0.41, 9.0]) == pytest.approx(0.42)


def test_calibrated_thresholds_stay_between_open_and_pinch_observations() -> None:
    down, release = calibrated_pinch_thresholds([0.8, 0.81, 0.79], [0.2, 0.21, 0.19])
    assert 0.2 < down < release < 0.8


def test_observation_reuses_engine_measurement_without_state_change() -> None:
    engine = PythonGestureEngine(EngineConfig(activation_gesture=False))
    before = engine.state

    observation = engine.observe(synthetic_landmarks())

    assert observation["index_pinch"] is not None
    assert engine.state is before
    assert engine._held is None
