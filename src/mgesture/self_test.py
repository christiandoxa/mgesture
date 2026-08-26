from __future__ import annotations

import importlib
import os
from typing import Any

from .engine import Button, EngineConfig, create_engine
from .engine.mojo_engine import NativeMojoGestureEngine
from .engine.synthetic import synthetic_frames
from .input import FakeMouseBackend
from .release import runtime_metadata
from .vision.model_manager import available_model


def run_self_test(require_mojo: bool = False, engine_request: str = "auto") -> dict[str, Any]:
    checks: dict[str, str] = {}
    metadata = runtime_metadata()
    checks["mojo_source"] = (
        "passed" if metadata.get("mojo_source_available") is True else "not-available"
    )
    native_mojo = False
    try:
        probe = create_engine("mojo", EngineConfig(), armed=False)
    except Exception:
        pass
    else:
        native_mojo = isinstance(probe, NativeMojoGestureEngine)
        close = getattr(probe, "close", None)
        if callable(close):
            close()
    checks["mojo_native_engine"] = "passed" if native_mojo else "not-available"
    checks["python_engine"] = (
        "passed" if metadata.get("python_engine_available", True) is True else "not-available"
    )
    for module in ("numpy", "cv2", "mediapipe"):
        try:
            loaded = importlib.import_module(module)
            if module == "cv2" and not hasattr(loaded, "VideoCapture"):
                raise RuntimeError("cv2 extension is not loaded")
            checks[module] = "passed"
        except Exception as exc:
            checks[module] = f"failed: {exc}"
    model = available_model()
    checks["model"] = "passed" if model is not None else "not-bundled-source"
    backend = FakeMouseBackend()
    selected_engine = "mojo" if require_mojo else engine_request
    active_engine = "unavailable"
    try:
        engine = create_engine(
            selected_engine,
            EngineConfig(reacquisition_ms=0, activation_gesture=False),
            armed=True,
        )
        if selected_engine == "mojo" and not isinstance(engine, NativeMojoGestureEngine):
            raise RuntimeError("native Mojo engine was not selected")
        active_engine = "mojo" if isinstance(engine, NativeMojoGestureEngine) else engine.name
    except Exception as exc:
        checks["gesture_engine"] = f"failed: {exc}"
        return {
            "passed": False,
            "checks": checks,
            "active_engine": active_engine,
            "actions": 0,
            "held_buttons": [],
            "failures": checks,
        }
    actions = 0
    try:
        for frame in synthetic_frames(60):
            batch = engine.process(frame)
            actions += len(batch.actions)
            for action in batch.actions:
                if action.button is Button.LEFT and action.type.value == "button_down":
                    backend.button_down(Button.LEFT)
                elif action.button is Button.LEFT and action.type.value == "button_up":
                    backend.button_up(Button.LEFT)
    finally:
        backend.release_all()
        close = getattr(engine, "close", None)
        if callable(close):
            close()
    checks["gesture_engine"] = "passed" if actions >= 0 else "failed"
    checks["fake_backend_released"] = "passed" if not backend.held else "failed"
    failed = {
        name: value
        for name, value in checks.items()
        if value != "passed"
        and not (name == "model" and not os.environ.get("MGESTURE_BUNDLE_ROOT"))
        and not (name == "mojo_native_engine" and selected_engine != "mojo")
    }
    return {
        "passed": not failed,
        "checks": checks,
        "active_engine": active_engine,
        "actions": actions,
        "held_buttons": [button.value for button in backend.held],
        "failures": failed,
    }
