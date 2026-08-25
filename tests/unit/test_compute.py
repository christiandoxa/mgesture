import pytest

from mgesture.compute import HardwareCapabilities, select_compute_plan
from mgesture.config import PerformanceConfig
from mgesture.vision.scheduler import AdaptivePerformanceController, effective_performance


def capabilities(gpu: bool, media_gpu: bool, mojo: bool = False) -> HardwareCapabilities:
    return HardwareCapabilities(
        "Linux",
        "x86_64",
        "test",
        8,
        4,
        gpu,
        "NVIDIA" if gpu else "unknown",
        "test",
        "test",
        None,
        True,
        mojo,
        "nvidia" if mojo else "unavailable",
        media_gpu,
    )


def test_cpu_compute_never_selects_gpu():
    plan = select_compute_plan("cpu", capabilities(True, True, True), "mojo")
    assert plan.inference == "mediapipe_cpu"
    assert plan.gesture == "mojo_cpu"


def test_gpu_compute_requires_a_usable_candidate():
    with pytest.raises(RuntimeError, match="GPU compute requested"):
        select_compute_plan("gpu", capabilities(True, False), "python")


def test_auto_falls_back_to_cpu_and_keeps_python_complete():
    plan = select_compute_plan("auto", capabilities(False, False), "python")
    assert plan.inference == "mediapipe_cpu"
    assert plan.gesture == "python_cpu"


def test_scheduler_waits_at_idle_rate_and_profiles_are_centralized():
    scheduler = AdaptivePerformanceController(30, 60, 5)
    assert scheduler.should_process(0.0, True, False)
    assert not scheduler.should_process(0.01, True, False)
    assert scheduler.remaining(0.01) > 0.1
    assert effective_performance(PerformanceConfig(profile="efficiency")).target_fps <= 24
