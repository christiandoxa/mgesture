from __future__ import annotations

import dataclasses
import json
import os
import stat
import sys
import tempfile
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_log_dir

from .engine.models import HandSelection

STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ResetTarget:
    label: str
    path: Path
    legacy_install_entry: bool = False


@dataclass(frozen=True, slots=True)
class CameraConfig:
    index: int = 0
    width: int = 640
    height: int = 480
    target_fps: int = 30
    # Legacy compatibility field; preview_mirror is the canonical setting.
    mirror: bool = True
    preview_mirror: str = "auto"


@dataclass(frozen=True, slots=True)
class VisionConfig:
    handedness_confidence: float = 0.70
    detection_confidence: float = 0.65
    presence_confidence: float = 0.65
    tracking_confidence: float = 0.65
    model_path: str | None = None
    # Legacy compatibility field; handedness_mirror is canonical.
    handedness_mirrored_input: bool = False
    handedness_mirror: str = "auto"
    hand_selection: HandSelection = HandSelection.AUTO

    def __post_init__(self) -> None:
        try:
            selection = HandSelection.coerce(self.hand_selection)
        except ValueError as exc:
            raise ValueError("vision.hand_selection must be right, left, either, or auto") from exc
        object.__setattr__(self, "hand_selection", selection)


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
    pointer_mirror: bool = True
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
    scroll_exit_grace_ms: int = 120
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


def effective_preview_mirror(camera: CameraConfig) -> bool:
    return camera.mirror if camera.preview_mirror == "auto" else camera.preview_mirror == "on"


def effective_handedness_mirror(vision: VisionConfig) -> bool:
    if vision.handedness_mirror == "on":
        return True
    if vision.handedness_mirror == "off":
        return False
    return vision.handedness_mirrored_input


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


def _absolute(path: Path) -> Path:
    return path.expanduser().absolute()


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise RuntimeError(f"cannot validate mgesture reset path: {path}") from exc


def _looks_like_bundle_root(path: Path) -> bool:
    return (
        (path / "bin" / "mgesture").is_file() or (path / "bin" / "mgesture.exe").is_file()
    ) and (path / "share" / "mgesture" / "release-metadata.json").is_file()


def _installation_roots() -> tuple[Path, ...]:
    """Find installed bundle roots without treating a source checkout as one."""
    roots: set[Path] = set()
    for value in (os.environ.get("MGESTURE_INSTALL_DIR"), os.environ.get("MGESTURE_BUNDLE_ROOT")):
        if value:
            candidate = _resolved(Path(value))
            roots.add(candidate.parent if candidate.name.casefold() == "current" else candidate)
    executable = _resolved(Path(sys.executable))
    for ancestor in (executable, *executable.parents):
        if ancestor.name.casefold() == "current":
            roots.add(ancestor.parent)
        if ancestor.parent.name.casefold() == "releases":
            roots.add(ancestor.parent.parent)
        if _looks_like_bundle_root(ancestor):
            roots.add(ancestor)
        if (ancestor / "current").exists() and (ancestor / "releases").is_dir():
            roots.add(ancestor)
    return tuple(sorted(roots))


def _legacy_install_root(path: Path) -> Path | None:
    resolved = _resolved(path)
    for root in _installation_roots():
        if resolved == root:
            return root
    return None


def _protected_paths() -> tuple[Path, ...]:
    home = _resolved(Path.home())
    candidates = {
        home,
        _resolved(Path(sys.executable)),
        _resolved(Path(os.path.abspath(os.sep))),
    }
    for value in (
        os.environ.get("MGESTURE_INSTALL_DIR"),
        os.environ.get("MGESTURE_BUNDLE_ROOT"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("LOCALAPPDATA"),
    ):
        if value:
            candidates.add(_resolved(Path(value)))
    candidates.update(
        _resolved(home / suffix)
        for suffix in (".local", ".local/bin", ".local/share", ".config", ".cache")
    )
    if os.name != "nt":
        candidates.update(_resolved(Path(value)) for value in ("/usr", "/usr/local"))
    return tuple(candidates)


def _is_descendant(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_reset_target(target: ResetTarget, protected: tuple[Path, ...]) -> None:
    path = _absolute(target.path)
    if not path.parts or path == Path(path.anchor):
        raise RuntimeError(f"refusing unsafe mgesture reset path: {path}")
    current = path
    while current != current.parent:
        if current.is_symlink():
            raise RuntimeError(f"refusing unsafe symlinked mgesture reset path: {path}")
        current = current.parent
    resolved = _resolved(path)
    for protected_path in protected:
        if any(resolved == root for root in _installation_roots()):
            break
        if resolved == protected_path or _is_descendant(protected_path, resolved):
            raise RuntimeError(f"refusing unsafe mgesture reset path: {path}")
    for root in _installation_roots():
        inside_install = _is_descendant(resolved, root)
        if inside_install and not target.legacy_install_entry:
            raise RuntimeError(f"refusing to reset installed application path: {path}")
        if not inside_install and _is_descendant(root, resolved):
            raise RuntimeError(f"refusing broad reset path containing installation: {path}")
    if target.legacy_install_entry:
        if path.name not in {"state.json", "recordings"}:
            raise RuntimeError(f"refusing unsafe legacy reset path: {path}")
        if _legacy_install_root(path.parent) is None:
            raise RuntimeError(f"refusing unsafe legacy reset path: {path}")


def reset_targets() -> tuple[ResetTarget, ...]:
    """Return the exact mutable paths eligible for reset after safety validation."""
    data = _absolute(data_dir())
    legacy_root = _legacy_install_root(data)
    if legacy_root is None:
        data_targets: tuple[ResetTarget, ...] = (
            ResetTarget("user data, calibration, tutorial state, and recordings", data),
        )
    else:
        data_targets = (
            ResetTarget("tutorial state", data / "state.json", True),
            ResetTarget("landmark recordings", data / "recordings", True),
        )
    targets = (
        ResetTarget("configuration", _absolute(config_path())),
        *data_targets,
        ResetTarget("cached application data", _absolute(cache_dir())),
        ResetTarget("application logs", _absolute(log_dir())),
    )
    protected = _protected_paths()
    for target in targets:
        _validate_reset_target(target, protected)
    return targets


def _remove_without_following_links(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        path.unlink()
        return
    with os.scandir(path) as entries:
        for entry in entries:
            child = Path(entry.path)
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                child.unlink()
            else:
                _remove_without_following_links(child)
    path.rmdir()


def reset_user_data(dry_run: bool = False) -> tuple[str, ...]:
    """Remove only validated mutable state; never remove an installation root."""
    targets = reset_targets()
    if dry_run:
        return tuple(target.label for target in targets)
    removed: list[str] = []
    for target in targets:
        if target.path.exists() or target.path.is_symlink():
            _remove_without_following_links(target.path)
            removed.append(target.label)
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
    vision_values = dict(raw.get("vision") or {})
    if "hand_selection" not in vision_values:
        # Existing files predate hand selection and must retain right-hand behavior.
        vision_values["hand_selection"] = HandSelection.RIGHT
    return validate(
        AppConfig(
            camera=_section(CameraConfig, raw.get("camera")),
            vision=_section(VisionConfig, vision_values),
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
    try:
        HandSelection.coerce(config.vision.hand_selection)
    except ValueError:
        errors.append("vision.hand_selection must be right, left, either, or auto")
    if config.camera.preview_mirror not in ("auto", "on", "off"):
        errors.append("camera.preview_mirror must be auto, on, or off")
    if config.vision.handedness_mirror not in ("auto", "on", "off"):
        errors.append("vision.handedness_mirror must be auto, on, or off")
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
    if config.gesture.scroll_entry_ms < 0:
        errors.append("gesture.scroll_entry_ms must be >= 0")
    if config.gesture.scroll_exit_grace_ms < 0:
        errors.append("gesture.scroll_exit_grace_ms must be >= 0")
    if config.gesture.scroll_sensitivity <= 0.0:
        errors.append("gesture.scroll_sensitivity must be > 0")
    if config.gesture.scroll_dead_zone < 0.0:
        errors.append("gesture.scroll_dead_zone must be >= 0")
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
        elif name in {field.name for field in fields(VisionConfig)}:
            result = replace(result, vision=replace(result.vision, **{name: value}))
        elif name in {field.name for field in fields(PerformanceConfig)}:
            result = replace(result, performance=replace(result.performance, **{name: value}))
        elif name in {field.name for field in fields(DisplayConfig)}:
            result = replace(result, display=replace(result.display, **{name: value}))
        elif name in {field.name for field in fields(GestureConfig)}:
            result = replace(result, gesture=replace(result.gesture, **{name: value}))
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
