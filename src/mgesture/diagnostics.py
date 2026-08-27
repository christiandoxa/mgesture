from __future__ import annotations

import importlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .compute import capabilities_dict, detect_hardware, select_compute_plan
from .config import (
    AppConfig,
    config_path,
    effective_handedness_mirror,
    effective_preview_mirror,
    validate,
)
from .engine import EngineConfig, EngineUnavailableError, create_engine
from .engine.mojo_engine import NativeMojoGestureEngine, native_library_name
from .input import create_backend
from .release import runtime_metadata
from .self_test import run_self_test
from .vision.camera import probe_camera
from .vision.hand_landmarker import HandLandmarker
from .vision.model_manager import available_model, model_cache_path


class DoctorCode:
    OK = 0
    OPTIONAL_ACCELERATION = 2
    CAMERA = 3
    MODEL = 4
    POINTER = 5
    CONFIG = 6


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    remediation: str = ""
    required: bool = True
    data: dict[str, object] | None = None


def _version(module_name: str, distribution: str | None = None) -> str:
    try:
        module = importlib.import_module(module_name)
        value = getattr(module, "__version__", None)
        return str(value or importlib.metadata.version(distribution or module_name))
    except Exception as exc:
        return f"unavailable ({exc})"


def _mojo_version() -> str:
    command = shutil.which("mojo")
    if not command:
        return "unavailable"
    result = subprocess.run(
        [command, "--version"], capture_output=True, text=True, timeout=5, check=False
    )
    return (result.stdout or result.stderr).strip() or "unavailable"


def _engine_capabilities(
    metadata: dict[str, object], requested: str, probe: bool
) -> dict[str, object]:
    requested = requested.lower()
    nested = metadata.get("mojo")
    nested_mojo = nested if isinstance(nested, dict) else {}
    source_available = metadata.get("mojo_source_available") is True or (
        nested_mojo.get("source_available") is True
    )
    native_available = metadata.get("native_mojo_engine_available") is True or (
        nested_mojo.get("native_engine_available") is True
    )
    native_loaded = metadata.get("native_mojo_engine_loaded") is True or (
        nested_mojo.get("native_engine_loaded") is True
    )
    if probe and requested != "python":
        native_available = False
        native_loaded = False
        if os.environ.get("MGESTURE_ENGINE", "auto").lower() != "python":
            try:
                engine = create_engine("mojo", EngineConfig(), armed=False)
            except EngineUnavailableError:
                pass
            else:
                native_available = isinstance(engine, NativeMojoGestureEngine)
                native_loaded = native_available
                if native_available:
                    close = getattr(engine, "close", None)
                    if callable(close):
                        close()
    python_available = metadata.get("python_engine_available", True) is True
    if requested == "python":
        native_loaded = False
    source_hash = metadata.get("mojo_source_sha256") or nested_mojo.get("source_sha256")
    library_hash = metadata.get("mojo_library_sha256") or nested_mojo.get("library_sha256")
    library_arch = nested_mojo.get("library_arch") or (
        metadata.get("architecture") if native_available else None
    )
    active = (
        "python"
        if requested == "python" or (requested == "auto" and not native_loaded)
        else "mojo"
        if native_loaded
        else "unavailable"
    )
    return {
        "mojo_source_available": source_available,
        "native_mojo_engine_available": native_available,
        "native_mojo_engine_loaded": native_loaded,
        "python_engine_available": python_available,
        "active_engine": active,
        "mojo_abi_version": (
            metadata.get("mojo_abi_version")
            or nested_mojo.get("abi_version")
            or (1 if native_loaded else None)
        ),
        "mojo_library": (
            metadata.get("mojo_library")
            or nested_mojo.get("library")
            or (native_library_name() if native_loaded else None)
        ),
        "mojo_source_sha256": source_hash,
        "mojo_library_sha256": library_hash,
        "mojo_library_arch": library_arch,
        "mojo_build_target": nested_mojo.get("build_target"),
    }


def _camera_check(index: int, width: int = 640, height: int = 480, target_fps: int = 30) -> Check:
    try:
        info = probe_camera(index, width, height, target_fps)
        return Check(
            "camera",
            bool(info.opened and info.readable),
            info.detail,
            "Run `mgesture list-cameras`, check camera permissions, and close other camera users.",
            data=info.as_dict(),
        )
    except Exception as exc:
        return Check("camera", False, str(exc), "Install OpenCV with `pixi install`.")


def collect_checks(
    config: AppConfig, check_camera: bool = True, check_input: bool = True
) -> tuple[list[Check], int]:
    checks: list[Check] = []
    try:
        validate(config)
        checks.append(Check("configuration", True, str(config_path())))
    except ValueError as exc:
        checks.append(
            Check(
                "configuration",
                False,
                str(exc),
                "Run `mgesture config show` and fix the TOML file.",
            )
        )

    session = (
        "Windows"
        if sys.platform == "win32"
        else "macOS"
        if sys.platform == "darwin"
        else (
            "WAYLAND"
            if os.environ.get("WAYLAND_DISPLAY")
            else os.environ.get("XDG_SESSION_TYPE", "unknown").upper()
        )
    )
    mojo_version = _mojo_version()
    hardware = detect_hardware()
    engine_request = os.environ.get("MGESTURE_ENGINE", config.input.engine)
    metadata = runtime_metadata()
    engine_status = _engine_capabilities(metadata, engine_request, probe=True)
    compute_request = os.environ.get("MGESTURE_COMPUTE", config.compute.mode)
    try:
        compute_plan = select_compute_plan(compute_request, hardware, config.input.engine)
        compute_detail = f"request={compute_request}, inference={compute_plan.inference}, gesture={compute_plan.gesture}, reason={compute_plan.reason}"
        compute_ok = True
        compute_fix = ""
    except (RuntimeError, ValueError) as exc:
        compute_detail = str(exc)
        compute_ok = False
        compute_fix = "Use `--compute auto` or install a supported MediaPipe GPU runtime."
    model = (
        available_model(Path(config.vision.model_path))
        if config.vision.model_path
        else available_model()
    )
    gpu_runtime_ok = compute_ok and compute_plan.inference != "mediapipe_gpu"
    gpu_runtime_detail = "not selected"
    if compute_ok and compute_plan.inference == "mediapipe_gpu":
        if model is None:
            gpu_runtime_detail = "cannot initialize without a model"
        else:
            try:
                probe = HandLandmarker(
                    str(model),
                    config.vision.detection_confidence,
                    config.vision.presence_confidence,
                    config.vision.tracking_confidence,
                    "gpu",
                    effective_handedness_mirror(config.vision),
                    config.vision.hand_selection,
                )
                probe.close()
                gpu_runtime_ok = True
                gpu_runtime_detail = "delegate initialized"
            except Exception as exc:
                gpu_runtime_detail = str(exc)
        if not gpu_runtime_ok and compute_request == "auto":
            compute_plan = select_compute_plan("cpu", hardware, config.input.engine)
            compute_detail = f"request=auto, inference={compute_plan.inference}, gesture={compute_plan.gesture}, reason=GPU initialization failed; CPU fallback selected"
            compute_ok = True
    checks.extend(
        [
            Check(
                "operating system",
                True,
                f"{platform.system()} {platform.release()} ({platform.machine()})",
            ),
            Check("session", True, session),
            Check("python", True, sys.version.split()[0]),
            Check(
                "mojo",
                mojo_version != "unavailable",
                mojo_version,
                "Install stable Mojo 1.0.0 on Linux/macOS; Windows uses Python.",
                required=False,
            ),
            Check(
                "mediapipe",
                not _version("mediapipe").startswith("unavailable"),
                _version("mediapipe"),
                "Run `pixi install`.",
                required=False,
            ),
            Check(
                "opencv",
                not _version("cv2").startswith("unavailable"),
                _version("cv2", "opencv-contrib-python"),
                "Run `pixi install`.",
                required=False,
            ),
        ]
    )
    checks.append(
        Check(
            "gesture engines",
            True,
            "requested="
            f"{engine_request}; Mojo source={'available' if engine_status['mojo_source_available'] else 'unavailable'}; "
            f"Mojo native runtime={'available' if engine_status['native_mojo_engine_available'] else 'unavailable'}; "
            f"loaded={'yes' if engine_status['native_mojo_engine_loaded'] else 'no'}; "
            f"Python engine={'available' if engine_status['python_engine_available'] else 'unavailable'}; "
            f"active={engine_status['active_engine']}",
        )
    )
    checks.append(
        Check(
            "hand tracking",
            True,
            f"selection={config.vision.hand_selection.value}; "
            f"camera handedness mirror={'on' if effective_handedness_mirror(config.vision) else 'off'}; "
            f"preview mirror={'on' if effective_preview_mirror(config.camera) else 'off'}",
            required=False,
        )
    )
    checks.append(
        Check(
            "compute plan",
            compute_ok,
            compute_detail,
            compute_fix,
            required=compute_request == "gpu",
        )
    )
    checks.append(
        Check(
            "GPU",
            hardware.gpu_detected,
            f"{hardware.gpu_vendor} {hardware.gpu_device}; driver={hardware.driver}; memory_mb={hardware.gpu_memory_mb}",
            "Install a supported driver/runtime, or use `--compute cpu`.",
            required=False,
        )
    )
    checks.append(
        Check(
            "MediaPipe GPU API",
            hardware.mediapipe_gpu_api,
            "delegate available" if hardware.mediapipe_gpu_api else "delegate unavailable",
            "The selected MediaPipe package does not expose a GPU delegate on this platform.",
            required=False,
        )
    )
    checks.append(
        Check(
            "model",
            model is not None,
            str(model or model_cache_path()),
            "Run `mgesture model install` or set vision.model_path to a readable task file.",
        )
    )
    checks.append(
        Check(
            "MediaPipe GPU runtime",
            gpu_runtime_ok,
            gpu_runtime_detail,
            "Use `--compute cpu` or fix the GPU delegate/driver; auto mode falls back once.",
            required=compute_request == "gpu",
        )
    )
    if check_camera:
        checks.append(
            _camera_check(
                config.camera.index,
                config.camera.width,
                config.camera.height,
                config.camera.target_fps,
            )
        )
    if check_input:
        backend = None
        input_error: Exception | None = None
        input_detail = ""
        try:
            backend = create_backend(
                config.input.backend, config.display.width, config.display.height
            )
            layout = backend.get_screen_layout()
            if not layout.monitors:
                raise RuntimeError("input backend reported no monitors")
            coordinate_mode = "absolute" if backend.absolute_coordinates else "relative-only"
            input_detail = (
                f"{backend.name}; monitors={len(layout.monitors)}; "
                f"virtual bounds {layout.x},{layout.y} {layout.width}x{layout.height}; "
                f"coordinates={coordinate_mode}"
            )
            if backend.dpi_aware is not None:
                input_detail += f"; dpi_aware={backend.dpi_aware}"
        except Exception as exc:
            input_error = exc
        finally:
            if backend is not None:
                try:
                    backend.close()
                except Exception as exc:
                    if input_error is None:
                        input_error = exc
        if input_error is None:
            checks.append(Check("input backend", True, input_detail))
        else:
            if session == "X11":
                remediation = "Check DISPLAY, xrandr, and pynput/XTest access."
            elif session == "WAYLAND":
                remediation = "Check /dev/uinput existence and user read/write permission."
            elif session == "macOS":
                remediation = "Grant Camera and Accessibility permissions to the terminal/app."
            elif session == "Windows":
                remediation = (
                    "Run on native Windows with per-monitor DPI support; WSL is unsupported."
                )
            else:
                remediation = (
                    "Use `--backend fake` for replay, or select the native backend explicitly."
                )
            checks.append(Check("input backend", False, str(input_error), remediation))
    if session == "WAYLAND":
        from .input.linux_wayland_backend import uinput_status

        uinput, uinput_detail = uinput_status()
        checks.append(
            Check(
                "/dev/uinput",
                uinput,
                uinput_detail,
                "Run `scripts/setup_linux_wayland.py` and re-login; review its udev rule.",
                required=False,
            )
        )
    if sys.platform == "darwin":
        try:
            quartz = importlib.import_module("Quartz")
            access_check = getattr(quartz, "CGPreflightPostEventAccess", None)
            if not callable(access_check):
                raise RuntimeError("Quartz Accessibility preflight is unavailable")
            accessibility = bool(access_check())
            checks.append(
                Check(
                    "macOS Accessibility",
                    accessibility,
                    "post-event access granted" if accessibility else "post-event access denied",
                    "Grant Accessibility access to the terminal/app in System Settings.",
                )
            )
        except Exception as exc:
            checks.append(
                Check(
                    "macOS Accessibility",
                    False,
                    str(exc),
                    "Grant Accessibility access to the terminal/app in System Settings.",
                )
            )
    if compute_ok:
        checks.append(
            Check(
                "compute layers",
                True,
                f"camera=CPU; preprocessing=CPU; inference={compute_plan.inference}; gesture={compute_plan.gesture}; preview=CPU; input=platform backend",
            )
        )

    required_failures = [check for check in checks if check.required and not check.ok]
    if required_failures:
        names = {check.name for check in required_failures}
        if "configuration" in names:
            return checks, DoctorCode.CONFIG
        if "camera" in names:
            return checks, DoctorCode.CAMERA
        if "model" in names:
            return checks, DoctorCode.MODEL
        return checks, DoctorCode.POINTER
    if not any(check.ok for check in checks if check.name == "mojo"):
        return checks, DoctorCode.OPTIONAL_ACCELERATION
    return checks, DoctorCode.OK


def report_json(config: AppConfig, checks: list[Check], runtime: bool = False) -> dict[str, object]:
    hardware = detect_hardware()
    request = os.environ.get("MGESTURE_COMPUTE", config.compute.mode)
    engine_request = os.environ.get("MGESTURE_ENGINE", config.input.engine)
    metadata = runtime_metadata()
    try:
        plan = select_compute_plan(request, hardware, config.input.engine)
        plan_data: dict[str, object] = {
            "requested": plan.requested,
            "inference": plan.inference,
            "preprocessing": plan.preprocessing,
            "gesture": plan.gesture,
            "preview": plan.preview,
            "reason": plan.reason,
        }
    except (RuntimeError, ValueError) as exc:
        plan_data = {"requested": request, "error": str(exc)}
    engine_status = _engine_capabilities(
        metadata,
        engine_request,
        probe=True,
    )
    camera_data: dict[str, object] = {
        "index": config.camera.index,
        "requested_width": config.camera.width,
        "requested_height": config.camera.height,
        "requested_fps": config.camera.target_fps,
    }
    camera_check = next((check for check in checks if check.name == "camera"), None)
    if camera_check is not None and camera_check.data is not None:
        camera_data = dict(camera_check.data)
    elif not runtime:
        try:
            camera_data = probe_camera(
                config.camera.index,
                config.camera.width,
                config.camera.height,
                config.camera.target_fps,
            ).as_dict()
        except Exception as exc:
            camera_data["error"] = str(exc)
    result: dict[str, object] = {
        "checks": [
            {"name": check.name, "ok": check.ok, "detail": check.detail, "required": check.required}
            for check in checks
        ],
        "hardware": capabilities_dict(hardware),
        "compute": {"mode": request, "plan": plan_data},
        "camera": camera_data,
        "gesture_engine": {
            "requested": engine_request,
            **engine_status,
        },
        "hand_tracking": {
            "selection": config.vision.hand_selection.value,
            "camera_handedness_mirror": effective_handedness_mirror(config.vision),
            "preview_mirror": effective_preview_mirror(config.camera),
            "active_hand": None,
        },
        "model": str(
            available_model(Path(config.vision.model_path))
            if config.vision.model_path
            else available_model() or model_cache_path()
        ),
        "configuration": str(config_path()),
    }
    if runtime:
        runtime_metadata_value = dict(metadata)
        runtime_metadata_value.update(
            {
                "mojo_source_available": engine_status["mojo_source_available"],
                "native_mojo_engine_available": engine_status["native_mojo_engine_available"],
                "native_mojo_engine_loaded": engine_status["native_mojo_engine_loaded"],
                "python_engine_available": engine_status["python_engine_available"],
            }
        )
        nested_runtime = runtime_metadata_value.get("mojo")
        if isinstance(nested_runtime, dict):
            runtime_metadata_value["mojo"] = {
                **nested_runtime,
                "native_engine_available": engine_status["native_mojo_engine_available"],
                "native_engine_loaded": engine_status["native_mojo_engine_loaded"],
            }
        result["runtime"] = runtime_metadata_value
        result["self_test"] = run_self_test()
    return result


def print_report(checks: list[Check]) -> None:
    for check in checks:
        marker = "OK" if check.ok else "FAIL"
        print(f"[{marker:4}] {check.name}: {check.detail}")
        if not check.ok and check.remediation:
            print(f"       fix: {check.remediation}")
