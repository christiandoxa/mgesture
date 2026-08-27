from __future__ import annotations

import dataclasses
import json
import os
import shutil
import tempfile
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_log_dir

STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    target_fps: int = 30
    mirror: bool = True


@dataclass(frozen=True, slots=True)
class VisionConfig:
    handedness_confidence: float = 0.70
    detection_confidence: float = 0.65
    presence_confidence: float = 0.65
    tracking_confidence: float = 0.65
    model_path: str | None = None
    handedness_mirrored_input: bool = False


@dataclass(frozen=True, slots=True)
class DisplayConfig:
    screen_mode: str = "primary"
    monitor: int = 0
    width: int = 1920
    height: int = 1080


@dataclass(frozen=True, slots=True)
class GestureConfig:
    active_left: float = 0.10
    active_right: float = 0.10
    active_top: float = 0.10
    active_bottom: float = 0.10
    pointer_gain: float = 1.0
    pointer_acceleration: float = 0.0
    dead_zone: float = 0.002
    filter_min_cutoff: float = 1.0
    filter_beta: float = 0.007
    filter_derivative_cutoff: float = 1.0
    pinch_down_threshold: float = 0.45
    pinch_release_threshold: float = 0.60
    debounce_ms: int = 70
    release_debounce_ms: int = 35
    hand_loss_timeout_ms: int = 250
    reacquisition_ms: int = 150
    scroll_entry_ms: int = 180
    scroll_sensitivity: float = 35.0
    scroll_direction: int = 1
    scroll_dead_zone: float = 0.001
    activation_gesture: bool = True
    activation_gesture_ms: int = 1000
    activation_cooldown_ms: int = 1000


@dataclass(frozen=True, slots=True)
class InputConfig:
    backend: str = "auto"
    engine: str = "auto"


@dataclass(frozen=True, slots=True)
class ComputeConfig:
    mode: str = "auto"


@dataclass(frozen=True, slots=True)
class PerformanceConfig:
    profile: str = "balanced"
    target_fps: int = 30
    max_fps: int = 60
    idle_fps: int = 5
    adaptive: bool = True
    preview_fps: int = 30


@dataclass(frozen=True, slots=True)
class AppConfig:
    camera: CameraConfig = CameraConfig()
    vision: VisionConfig = VisionConfig()
    display: DisplayConfig = DisplayConfig()
    gesture: GestureConfig = GestureConfig()
    input: InputConfig = InputConfig()
    compute: ComputeConfig = ComputeConfig()
    performance: PerformanceConfig = PerformanceConfig()
    preview: bool = True
    overlay: bool = True
    log_level: str = "INFO"
    activation_shortcut: str = "ctrl+alt+m"
    armed: bool = False


def config_path() -> Path:
    return Path(user_config_dir("mgesture")) / "config.toml"


def data_dir() -> Path:
    return Path(user_data_dir("mgesture"))


def cache_dir() -> Path:
    return Path(user_cache_dir("mgesture"))


def state_path() -> Path:
    return data_dir() / "state.json"


def log_dir() -> Path:
    candidate = Path(user_log_dir("mgesture"))
    return candidate if candidate.name.casefold() == "mgesture" else candidate.parent


def onboarding_completed() -> bool:
    try:
        raw = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    onboarding = raw.get("onboarding") if isinstance(raw, dict) else None
    return (
        isinstance(raw, dict)
        and raw.get("schema_version") == STATE_SCHEMA_VERSION
        and isinstance(onboarding, dict)
        and onboarding.get("completed") is True
    )


def set_onboarding_completed(completed: bool = True) -> Path:
    target = state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "schema_version": STATE_SCHEMA_VERSION,
                    "onboarding": {"completed": completed},
                },
                handle,
                indent=2,
            )
            handle.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _safe_owned_directory(path: Path) -> Path:
    """Accept only mgesture's app directory or its platform log/cache child."""
    path = path.expanduser()
    app_name = path.name.casefold()
    valid_child = app_name in {"cache", "logs", "log"} and path.parent.name.casefold() == "mgesture"
    if (
        app_name != "mgesture"
        and not valid_child
        or path.parent == path
        or path.is_symlink()
        or path.parent.is_symlink()
    ):
        raise RuntimeError(f"refusing unsafe mgesture data path: {path}")
    return path


def reset_user_data() -> tuple[str, ...]:
    """Remove mgesture user state while retaining installed application assets."""
    removed: list[str] = []
    targets = (
        (config_path().parent, "configuration"),
        (data_dir(), "user data, calibration, tutorial state, and recordings"),
        (cache_dir(), "cached application data"),
        (log_dir(), "application logs"),
    )
    paths: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for raw_path, label in targets:
        path = _safe_owned_directory(raw_path)
        if path in seen:
            continue
        seen.add(path)
        paths.append((path, label))
    for path, label in paths:
        if path.exists():
            shutil.rmtree(path)
            removed.append(label)
    return tuple(removed)


def default_config() -> AppConfig:
    return AppConfig()


def _section(cls: type[Any], values: dict[str, Any] | None) -> Any:
    values = values or {}
    names = {field.name for field in fields(cls)}
    return cls(**{name: values[name] for name in names if name in values})


def load_config(path: Path | None = None) -> AppConfig:
    target = path or config_path()
    if not target.exists():
        return default_config()
    with target.open("rb") as handle:
        raw = tomllib.load(handle)
    return validate(
        AppConfig(
            camera=_section(CameraConfig, raw.get("camera")),
            vision=_section(VisionConfig, raw.get("vision")),
            display=_section(DisplayConfig, raw.get("display")),
            gesture=_section(GestureConfig, raw.get("gesture")),
            input=_section(InputConfig, raw.get("input")),
            compute=_section(ComputeConfig, raw.get("compute")),
            performance=_section(PerformanceConfig, raw.get("performance")),
            preview=bool(raw.get("preview", True)),
            overlay=bool(raw.get("overlay", True)),
            log_level=str(raw.get("log_level", "INFO")),
            activation_shortcut=str(raw.get("activation_shortcut", "ctrl+alt+m")),
            armed=bool(raw.get("armed", False)),
        )
    )


def validate(config: AppConfig) -> AppConfig:
    errors: list[str] = []
    if config.camera.index < 0:
        errors.append("camera.index must be >= 0")
    if config.camera.width < 160 or config.camera.height < 120:
        errors.append("camera width/height are too small")
    if config.camera.target_fps <= 0:
        errors.append("camera.target_fps must be > 0")
    for name in (
        "handedness_confidence",
        "detection_confidence",
        "presence_confidence",
        "tracking_confidence",
    ):
        value = getattr(config.vision, name)
        if not 0.0 <= value <= 1.0:
            errors.append(f"vision.{name} must be between 0 and 1")
    margins = (
        config.gesture.active_left,
        config.gesture.active_right,
        config.gesture.active_top,
        config.gesture.active_bottom,
    )
    if (
        any(not 0.0 <= value < 0.5 for value in margins)
        or sum(margins[:2]) >= 1
        or sum(margins[2:]) >= 1
    ):
        errors.append("gesture active margins must be in [0, 0.5) and leave an active region")
    if config.gesture.pinch_down_threshold >= config.gesture.pinch_release_threshold:
        errors.append("gesture pinch_down_threshold must be below pinch_release_threshold")
    if config.gesture.scroll_direction not in (-1, 1):
        errors.append("gesture.scroll_direction must be -1 or 1")
    if config.display.screen_mode not in ("primary", "virtual"):
        errors.append("display.screen_mode must be primary or virtual")
    if config.display.monitor < 0:
        errors.append("display.monitor must be >= 0")
    if config.display.width <= 0 or config.display.height <= 0:
        errors.append("display width/height must be positive")
    if config.input.engine not in ("auto", "mojo", "python"):
        errors.append("input.engine must be auto, mojo, or python")
    if config.input.backend not in ("auto", "fake", "x11", "wayland", "windows", "macos"):
        errors.append("input.backend is not recognized")
    if config.compute.mode not in ("auto", "gpu", "cpu"):
        errors.append("compute.mode must be auto, gpu, or cpu")
    if config.performance.profile not in ("performance", "balanced", "efficiency"):
        errors.append("performance.profile must be performance, balanced, or efficiency")
    if (
        not 1
        <= config.performance.idle_fps
        <= config.performance.target_fps
        <= config.performance.max_fps
    ):
        errors.append("performance FPS values must satisfy 1 <= idle_fps <= target_fps <= max_fps")
    if errors:
        raise ValueError("Invalid configuration: " + "; ".join(errors))
    return config


def with_overrides(config: AppConfig, **values: Any) -> AppConfig:
    result = config
    for name, value in values.items():
        if value is None:
            continue
        if name in {field.name for field in fields(AppConfig)}:
            result = replace(result, **{name: value})
        elif name in {field.name for field in fields(InputConfig)}:
            result = replace(result, input=replace(result.input, **{name: value}))
        elif name in {field.name for field in fields(ComputeConfig)}:
            result = replace(result, compute=replace(result.compute, **{name: value}))
        elif name in {field.name for field in fields(PerformanceConfig)}:
            result = replace(result, performance=replace(result.performance, **{name: value}))
        elif name in {field.name for field in fields(DisplayConfig)}:
            result = replace(result, display=replace(result.display, **{name: value}))
        elif name in {field.name for field in fields(CameraConfig)}:
            result = replace(result, camera=replace(result.camera, **{name: value}))
    return validate(result)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if value is None:
        return ""
    return str(value)


def config_text(config: AppConfig | None = None) -> str:
    config = config or default_config()
    lines: list[str] = []
    root = dataclasses.asdict(config)
    for key in ("preview", "overlay", "log_level", "activation_shortcut", "armed"):
        lines.append(f"{key} = {_toml_value(root[key])}")
    for section in ("camera", "vision", "display", "gesture", "input", "compute", "performance"):
        lines.append("")
        lines.append(f"[{section}]")
        for key, value in root[section].items():
            if value is not None:
                lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def write_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(config_text(config), encoding="utf-8")
    os.chmod(target, 0o600)
    return target
