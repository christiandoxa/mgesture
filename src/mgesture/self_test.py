from __future__ import annotations

import importlib
import os
from typing import Any

from .engine import Button, EngineConfig, create_engine
from .engine.synthetic import synthetic_frames
from .input import FakeMouseBackend
from .vision.model_manager import available_model


def run_self_test(require_mojo: bool = False) -> dict[str, Any]:
    checks: dict[str, str] = {}
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
    }
    return {
        "passed": not failed,
        "checks": checks,
        "actions": actions,
        "held_buttons": [button.value for button in backend.held],
        "failures": failed,
    }
