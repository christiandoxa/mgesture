from __future__ import annotations

import importlib
import os
from typing import Any

from .engine import Button, EngineConfig, create_engine
from .engine.synthetic import synthetic_frames
from .input import FakeMouseBackend
from .release import runtime_metadata
from .vision.model_manager import available_model


def run_self_test(require_mojo: bool = False) -> dict[str, Any]:
    checks: dict[str, str] = {}
    metadata = runtime_metadata()
    checks["mojo_source"] = (
        "passed" if metadata.get("mojo_source_available") is True else "not-available"
    )
    native_mojo = metadata.get("native_mojo_engine_available") is True
    if not native_mojo and metadata.get("standalone") is not True:
        try:
            probe = create_engine("mojo", EngineConfig(), armed=False)
        except Exception:
            pass
        else:
            native_mojo = probe.name == "mojo"
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
    try:
        engine = create_engine(
            "mojo" if require_mojo else "python",
            EngineConfig(reacquisition_ms=0, activation_gesture=False),
            armed=True,
        )
        if require_mojo and engine.name != "mojo":
            raise RuntimeError("native Mojo engine was not selected")
    except Exception as exc:
        checks["gesture_engine"] = f"failed: {exc}"
        return {
            "passed": False,
            "checks": checks,
            "actions": 0,
            "held_buttons": [],
            "failures": checks,
        }
    actions = 0
    for frame in synthetic_frames(60):
        batch = engine.process(frame)
        actions += len(batch.actions)
        for action in batch.actions:
            if action.button is Button.LEFT and action.type.value == "button_down":
                backend.button_down(Button.LEFT)
            elif action.button is Button.LEFT and action.type.value == "button_up":
                backend.button_up(Button.LEFT)
    backend.release_all()
    checks["gesture_engine"] = "passed" if actions >= 0 else "failed"
    checks["fake_backend_released"] = "passed" if not backend.held else "failed"
    failed = {
        name: value
        for name, value in checks.items()
        if value != "passed"
        and not (name == "model" and not os.environ.get("MGESTURE_BUNDLE_ROOT"))
        and not (name == "mojo_native_engine" and not require_mojo)
    }
    return {
        "passed": not failed,
        "checks": checks,
        "actions": actions,
        "held_buttons": [button.value for button in backend.held],
        "failures": failed,
    }
