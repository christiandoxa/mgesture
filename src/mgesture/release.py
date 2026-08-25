from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import __version__

REPOSITORY = "christiandoxa/mgesture"
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[+-][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True, slots=True)
class ReleaseTarget:
    name: str
    asset: str
    implementation: str
    python_fallback: bool


def current_target() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arch = (
        "x86_64"
        if machine in ("x86_64", "amd64")
        else "aarch64"
        if machine in ("aarch64", "arm64")
        else machine
    )
    if system == "Linux":
        return f"{arch}-unknown-linux-gnu"
    if system == "Darwin":
        return f"{arch}-apple-darwin"
    if system == "Windows":
        return f"{arch}-pc-windows-msvc"
    raise RuntimeError(f"unsupported operating system: {system}")


def release_base_url(release: str = "latest") -> str:
    override = os.environ.get("MGESTURE_RELEASE_BASE_URL")
    if override:
        return override.rstrip("/")
    if release == "latest":
        return f"https://github.com/{REPOSITORY}/releases/latest/download"
    if not _VERSION_RE.fullmatch(release):
        raise ValueError("release must be latest or semantic version x.y.z")
    return f"https://github.com/{REPOSITORY}/releases/download/{release}"


def _read_url(base: str, filename: str) -> bytes:
    if Path(base).is_dir():
        return (Path(base) / filename).read_bytes()
    if base.startswith("file://"):
        return (Path(base[7:]) / filename).read_bytes()
    with urllib.request.urlopen(f"{base}/{filename}", timeout=15) as response:
        return bytes(response.read())


def resolve_release(release: str = "latest", target: str | None = None) -> dict[str, Any]:
    target = target or current_target()
    manifest_value = json.loads(_read_url(release_base_url(release), "release-manifest.json"))
    if not isinstance(manifest_value, dict):
        raise RuntimeError("release-manifest.json must contain an object")
    manifest = cast(dict[str, Any], manifest_value)
    row = manifest.get("targets", {}).get(target)
    if not isinstance(row, dict):
        raise RuntimeError(f"release has no standalone asset for target {target}")
    asset = str(row.get("asset", ""))
    if not asset or not asset.startswith("mgesture-"):
        raise RuntimeError(f"release manifest has invalid asset for target {target}")
    return {
        "manifest": manifest,
        "target": target,
        "asset": ReleaseTarget(
            target,
            asset,
            str(row.get("implementation", "")),
            bool(row.get("python_fallback", False)),
        ),
        "base_url": release_base_url(release),
    }


def runtime_metadata() -> dict[str, Any]:
    candidates = []
    bundle_root = os.environ.get("MGESTURE_BUNDLE_ROOT")
    if bundle_root:
        candidates.append(Path(bundle_root) / "share" / "mgesture" / "release-metadata.json")
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "share" / "mgesture" / "release-metadata.json")
    candidates.append(
        Path(sys.executable).resolve().parent.parent
        / "share"
        / "mgesture"
        / "release-metadata.json"
    )
    for path in candidates:
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return cast(dict[str, Any], value)
    return {
        "version": __version__,
        "commit": "source-tree",
        "target": current_target(),
        "standalone": False,
        "implementation": "mojo-source-or-python-fallback",
        "compiler_required": False,
        "gesture_engine": {
            "implementation": "mojo-source-or-python-fallback",
            "compiler_required": False,
            "self_test": "not-packaged",
        },
    }


def check_for_update() -> dict[str, Any]:
    resolved = resolve_release()
    latest = str(resolved["manifest"].get("version", ""))
    return {
        "current": __version__,
        "latest": latest,
        "update_available": _version_key(latest) > _version_key(__version__),
        "target": resolved["target"],
        "asset": resolved["asset"].asset,
    }


def _version_key(value: str) -> tuple[int, int, int, str]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", value)
    if not match:
        raise ValueError(f"invalid semantic version: {value}")
    return int(match[1]), int(match[2]), int(match[3]), match[4]


def run_update(check_only: bool = False) -> int:
    status = check_for_update()
    print(json.dumps(status, indent=2))
    if check_only or not status["update_available"]:
        return 0
    installer = _installer_path()
    if installer is None:
        raise RuntimeError(
            "installer script is not present in this build; reinstall from the latest GitHub release"
        )
    environment = os.environ.copy()
    environment["MGESTURE_RELEASE"] = "latest"
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
        ]
    else:
        command = ["sh", str(installer)]
    return subprocess.run(command, env=environment, check=False).returncode


def _installer_path() -> Path | None:
    candidates: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(
            Path(sys._MEIPASS) / ("install.ps1" if sys.platform == "win32" else "install.sh")
        )
    candidates.append(
        Path(sys.executable).resolve().parent.parent
        / ("install.ps1" if sys.platform == "win32" else "install.sh")
    )
    candidates.append(
        Path(__file__).resolve().parents[2]
        / ("install.ps1" if sys.platform == "win32" else "install.sh")
    )
    return next((path for path in candidates if path.exists()), None)
