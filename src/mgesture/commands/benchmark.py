from __future__ import annotations

import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

try:
    import resource
except ImportError:  # pragma: no cover - native Windows
    resource = None  # type: ignore[assignment]

from mgesture.compute import capabilities_dict, detect_hardware, select_compute_plan
from mgesture.engine import EngineConfig, create_engine
from mgesture.engine.synthetic import synthetic_frames
from mgesture.vision.model_manager import available_model


def _usage() -> tuple[float, int]:
    if resource is not None:
        getrusage = getattr(resource, "getrusage", None)
        rusage_self = getattr(resource, "RUSAGE_SELF", None)
        if callable(getrusage) and rusage_self is not None:
            usage = getrusage(rusage_self)
            return usage.ru_utime + usage.ru_stime, usage.ru_maxrss
    return 0.0, 0


def _percentile(values: list[float], fraction: float) -> float:
    return values[min(len(values) - 1, round((len(values) - 1) * fraction))]


def _gpu_observation() -> dict[str, object] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        values = [value.strip() for value in result.stdout.split(",")]
        if result.returncode == 0 and len(values) == 4:
            return {
                "device": values[0],
                "utilization_percent": values[1],
                "memory_used_mb": values[2],
                "memory_total_mb": values[3],
            }
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def benchmark_engine(engine_name: str, frames: int = 3000) -> dict[str, object]:
    engine = create_engine(engine_name, EngineConfig(reacquisition_ms=0), armed=True)
    timings: list[float] = []
    processed = 0
    wall_start = time.perf_counter()
    cpu_start, _ = _usage()
    for frame in synthetic_frames(frames):
        start = time.perf_counter_ns()
        engine.process(frame)
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
        processed += 1
    timings.sort()
    cpu_end, max_rss_kb = _usage()
    wall_seconds = time.perf_counter() - wall_start
    return {
        "engine": getattr(engine, "name", engine_name),
        "engine_version": getattr(engine, "version", "unknown"),
        "frames": processed,
        "median_ms": statistics.median(timings),
        "p95_ms": _percentile(timings, 0.95),
        "p99_ms": _percentile(timings, 0.99),
        "processed_fps": 1000.0 / statistics.mean(timings),
        "os": platform.platform(),
        "cpu": platform.processor(),
        "python": platform.python_version(),
        "cpu_process_seconds": max(0.0, cpu_end - cpu_start),
        "cpu_percent_of_one_core": max(
            0.0, (cpu_end - cpu_start) / max(wall_seconds, 1e-9) * 100.0
        ),
        "max_rss_kb": max_rss_kb,
        "gpu_observation": _gpu_observation(),
    }


def benchmark_mediapipe(compute: str, frames: int = 30) -> dict[str, object]:
    model = available_model()
    hardware = detect_hardware()
    try:
        plan = select_compute_plan(compute, hardware, "python")
    except (RuntimeError, ValueError) as exc:
        return {
            "compute": compute,
            "available": False,
            "error": str(exc),
            "hardware": capabilities_dict(hardware),
        }
    if model is None:
        return {
            "compute": compute,
            "available": False,
            "error": "verified model is not installed; run `mgesture model install`",
        }
    try:
        import cv2
        import mediapipe as mp  # type: ignore[import-untyped]
        from mediapipe.tasks import python  # type: ignore[import-untyped]
        from mediapipe.tasks.python import vision  # type: ignore[import-untyped]

        delegate = (
            python.BaseOptions.Delegate.GPU
            if plan.inference == "mediapipe_gpu"
            else python.BaseOptions.Delegate.CPU
        )
        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(model), delegate=delegate),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
        )
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(
                __import__("numpy").zeros((480, 640, 3), dtype="uint8"), cv2.COLOR_BGR2RGB
            ),
        )
        timings: list[float] = []
        wall_start = time.perf_counter()
        cpu_start, _ = _usage()
        with vision.HandLandmarker.create_from_options(options) as landmarker:
            for _ in range(frames):
                started = time.perf_counter_ns()
                landmarker.detect(image)
                timings.append((time.perf_counter_ns() - started) / 1_000_000)
        timings.sort()
        cpu_end, max_rss_kb = _usage()
        wall_seconds = time.perf_counter() - wall_start
        return {
            "compute": compute,
            "selected_inference": plan.inference,
            "available": True,
            "frames": frames,
            "median_ms": statistics.median(timings),
            "p95_ms": _percentile(timings, 0.95),
            "p99_ms": _percentile(timings, 0.99),
            "fps": 1000.0 / statistics.mean(timings),
            "cpu_process_seconds": max(0.0, cpu_end - cpu_start),
            "cpu_percent_of_one_core": max(
                0.0, (cpu_end - cpu_start) / max(wall_seconds, 1e-9) * 100.0
            ),
            "max_rss_kb": max_rss_kb,
            "gpu_observation": _gpu_observation(),
        }
    except Exception as exc:
        return {
            "compute": compute,
            "available": False,
            "error": f"inference backend initialization/benchmark failed: {exc}",
        }


def run_benchmark(
    engine_name: str = "compare",
    output: Path | None = None,
    compute: str = "cpu",
    compare_compute: bool = False,
) -> dict[str, object]:
    if engine_name == "compare":
        results: dict[str, object] = {}
        for name in ("python", "mojo"):
            try:
                results[name] = benchmark_engine(name)
            except Exception as exc:
                results[name] = {"engine": name, "available": False, "error": str(exc)}
        result: dict[str, object] = {"type": "core", "results": results}
    else:
        result = {"type": "core", "results": {engine_name: benchmark_engine(engine_name)}}
    if compare_compute:
        result["inference"] = {mode: benchmark_mediapipe(mode) for mode in ("cpu", "gpu", "auto")}
    else:
        result["inference"] = {compute: benchmark_mediapipe(compute)}
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def print_benchmark(result: dict[str, object]) -> None:
    print(json.dumps(result, indent=2))
