from __future__ import annotations

import importlib
import os
from typing import Any

from .engine import Button, EngineConfig, create_engine
from .engine.mojo_engine import NativeMojoGestureEngine
from .engine.synthetic import synthetic_frames
from .input import FakeMouseBackend, GlobalShortcutListener, create_backend
from .release import runtime_metadata
from .vision.model_manager import available_model

_PLATFORM_INPUT_MODULES = (
    "mgesture.input.hotkey",
    "mgesture.input.pynput_backend",
    "mgesture.input.linux_x11_backend",
    "mgesture.input.linux_wayland_backend",
    "mgesture.input.macos_backend",
    "mgesture.input.windows_backend",
)


def platform_input_checks() -> dict[str, str]:
    """Probe packaged input code without emitting pointer events."""
    checks: dict[str, str] = {}
    module_errors: list[str] = []
    for module_name in _PLATFORM_INPUT_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            module_errors.append(f"{module_name}: {exc}")
    checks["input_modules"] = (
        "passed" if not module_errors else "failed: " + "; ".join(module_errors)
    )

    listener: GlobalShortcutListener | None = None
    try:
        listener = GlobalShortcutListener("ctrl+alt+m")
        listener.start()
        checks["keyboard_listener"] = "passed"
    except Exception as exc:
        checks["keyboard_listener"] = f"failed: {exc}"
    finally:
        if listener is not None:
            try:
                listener.stop()
            except Exception as exc:
                checks["keyboard_listener"] = f"failed: {exc}"

    backend: Any = None
    try:
        backend = create_backend()
        layout = backend.get_screen_layout()
        if not layout.monitors:
            raise RuntimeError("input backend reported no monitors")
        checks["mouse_backend"] = "passed"
    except Exception as exc:
        checks["mouse_backend"] = f"failed: {exc}"
    finally:
        if backend is not None:
            try:
                backend.close()
            except Exception as exc:
                checks["mouse_backend"] = f"failed: {exc}"
    return checks


def run_self_test(
    require_mojo: bool = False,
    engine_request: str = "auto",
    check_platform_input: bool = False,
) -> dict[str, Any]:
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
    if check_platform_input:
        checks.update(platform_input_checks())
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
