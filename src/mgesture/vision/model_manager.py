from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from platformdirs import user_cache_dir

from ..version import __version__

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
# SHA-256 of the versioned official model at MODEL_URL.
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL_LICENSE = "Apache-2.0; MediaPipe model card and terms apply"


def model_cache_path() -> Path:
    return Path(user_cache_dir("mgesture")) / "models" / "hand_landmarker.task"


def bundled_model_path() -> Path | None:
    candidates: list[Path] = []
    bundle_root = os.environ.get("MGESTURE_BUNDLE_ROOT")
    if bundle_root:
        candidates.append(
            Path(bundle_root) / "share" / "mgesture" / "models" / "hand_landmarker.task"
        )
    if hasattr(sys, "_MEIPASS"):
        candidates.append(
            Path(sys._MEIPASS) / "share" / "mgesture" / "models" / "hand_landmarker.task"
        )
    candidates.append(
        Path(sys.executable).resolve().parent.parent
        / "share"
        / "mgesture"
        / "models"
        / "hand_landmarker.task"
    )
    return next(
        (path for path in candidates if path.exists() and checksum(path) == MODEL_SHA256), None
    )


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_model(path: Path | None = None) -> Path | None:
    target = path or model_cache_path()
    if not target.exists():
        return None
    return target if checksum(target) == MODEL_SHA256 else None


def available_model(path: Path | None = None) -> Path | None:
    if path is not None:
        return path if path.is_file() and path.stat().st_size > 0 else None
    return installed_model() or bundled_model_path()


def install_model(destination: Path | None = None, url: str = MODEL_URL) -> Path:
    target = destination or model_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="hand_landmarker.", suffix=".part", dir=target.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": f"mgesture/{__version__}"})
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            temporary.open("wb") as output,
        ):
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        actual = checksum(temporary)
        if actual != MODEL_SHA256:
            raise RuntimeError(f"model checksum mismatch: expected {MODEL_SHA256}, got {actual}")
        temporary.replace(target)
        target.with_suffix(target.suffix + ".license").write_text(
            f"source = {url}\nsha256 = {MODEL_SHA256}\nlicense = {MODEL_LICENSE}\n",
            encoding="utf-8",
        )
        return target
    finally:
        temporary.unlink(missing_ok=True)
