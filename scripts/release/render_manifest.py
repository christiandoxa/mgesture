from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import load_targets  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.vision.model_manager import MODEL_SHA256  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def runtime_version() -> str:
    namespace: dict[str, object] = {}
    exec((ROOT / "src/mgesture/version.py").read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def render(version: str, commit: str, assets: Path, output: Path) -> None:
    if version != runtime_version():
        raise ValueError(f"manifest version {version} does not match runtime {runtime_version()}")
    targets = load_targets()
    rows: dict[str, dict[str, object]] = {}
    for name, target in targets.items():
        asset_path = assets / target.asset
        if not asset_path.exists():
            continue
        rows[name] = {
            "asset": target.asset,
            "sha256": digest(asset_path),
            "implementation": target.implementation,
            "python_fallback": target.python_fallback,
            "mojo_engine": target.mojo_engine,
            "os": target.os,
            "architecture": target.architecture,
            "runner": target.runner,
            "mediapipe": target.mediapipe,
            "format": target.format,
            "python": target.python,
            "minimum_glibc": target.minimum_glibc,
        }
    if not rows:
        raise RuntimeError("no target assets found")
    try:
        mediapipe_version = importlib.metadata.version("mediapipe")
    except importlib.metadata.PackageNotFoundError:
        mediapipe_version = "bundled-runtime-metadata"
    try:
        opencv_version = importlib.metadata.version("opencv-contrib-python")
    except importlib.metadata.PackageNotFoundError:
        opencv_version = "bundled-runtime-metadata"
    mojo_version = "unavailable"
    if shutil.which("mojo"):
        result = subprocess.run(["mojo", "--version"], capture_output=True, text=True, check=False)
        mojo_version = (result.stdout or result.stderr).strip()
    manifest = {
        "schema_version": 1,
        "version": version,
        "commit": commit,
        "build": {
            "python_runtime": platform.python_version(),
            "packaging": "PyInstaller onedir",
            "mediapipe_version": mediapipe_version,
            "opencv_version": opencv_version,
            "mojo_version": mojo_version,
        },
        "model": {"version": "hand_landmarker/float16/1", "sha256": MODEL_SHA256},
        "targets": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# schema_version\t1",
        f"# version\t{version}",
        f"# commit\t{commit}",
        "# target\tasset\timplementation\tpython_fallback\tsha256",
    ]
    lines.extend(
        f"{name}\t{row['asset']}\t{row['implementation']}\t{str(row['python_fallback']).lower()}\t{row['sha256']}"
        for name, row in rows.items()
    )
    (output / "release-manifest.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.version, args.commit, args.assets, args.output)


if __name__ == "__main__":
    main()
