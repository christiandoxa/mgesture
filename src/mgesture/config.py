from __future__ import annotations

import dataclasses
import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir


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
