from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import publishable_targets  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.mojo_engine import MOJO_ABI_VERSION, native_library_name  # noqa: E402
from mgesture.release import mojo_source_metadata  # noqa: E402
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


def archive_metadata(path: Path, archive_format: str) -> dict[str, object]:
    member_suffix = "share/mgesture/release-metadata.json"
    try:
        if archive_format == "zip":
            with zipfile.ZipFile(path) as archive:
                member = next(name for name in archive.namelist() if name.endswith(member_suffix))
                value = json.loads(archive.read(member))
        else:
            with tarfile.open(path, "r:gz") as archive:
                member = next(
                    item for item in archive.getmembers() if item.name.endswith(member_suffix)
                )
                handle = archive.extractfile(member)
                if handle is None:
                    return {}
                value = json.load(handle)
    except (
        KeyError,
        OSError,
        StopIteration,
        tarfile.TarError,
        zipfile.BadZipFile,
        json.JSONDecodeError,
    ):
        return {}
    return value if isinstance(value, dict) else {}


def archive_file_digest(path: Path, archive_format: str, member_suffix: str) -> str:
    digest_value = hashlib.sha256()
    if archive_format == "zip":
        with zipfile.ZipFile(path) as archive:
            member = next(name for name in archive.namelist() if name.endswith(member_suffix))
            handle = archive.open(member)
            with handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest_value.update(chunk)
    else:
        with tarfile.open(path, "r:gz") as archive:
            member = next(
                item for item in archive.getmembers() if item.name.endswith(member_suffix)
            )
            handle = archive.extractfile(member)
            if handle is None:
                raise RuntimeError(f"archive member cannot be read: {member_suffix}")
            with handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest_value.update(chunk)
    return digest_value.hexdigest()


def render(version: str, commit: str, assets: Path, output: Path) -> None:
    if version != runtime_version():
        raise ValueError(f"manifest version {version} does not match runtime {runtime_version()}")
    targets = publishable_targets()
    source_metadata = mojo_source_metadata(ROOT / "mojo")
    if not source_metadata["available"]:
        raise RuntimeError("canonical Mojo production source is missing")
    rows: dict[str, dict[str, object]] = {}
    for name, target in targets.items():
        asset_path = assets / target.asset
        if not asset_path.exists():
            raise RuntimeError(f"missing required target asset: {target.asset}")
        metadata = archive_metadata(asset_path, target.format)
        mojo_source_sha256 = str(metadata.get("mojo_source_sha256", source_metadata["sha256"]))
        mojo_source_files = metadata.get("mojo_source_files", source_metadata["files"])
        vision_backend = str(metadata.get("vision_backend", "mediapipe"))
        runtime_default = str(metadata.get("runtime_default", target.runtime_default))
        native_mojo_engine = bool(
            metadata.get("native_mojo_engine_available", target.native_mojo_engine)
        )
        native_mojo_engine_loaded = bool(
            metadata.get("native_mojo_engine_loaded", native_mojo_engine)
        )
        mojo_abi_version = metadata.get(
            "mojo_abi_version", MOJO_ABI_VERSION if native_mojo_engine else None
        )
        mojo_library = metadata.get(
            "mojo_library", native_library_name(target.os) if native_mojo_engine else None
        )
        mojo_library_arch = metadata.get(
            "mojo_library_arch", target.architecture if native_mojo_engine else None
        )
        if native_mojo_engine:
            mojo_library_sha256 = archive_file_digest(
                asset_path,
                target.format,
                f"runtime/mojo/{mojo_library}",
            )
            declared_library_sha256 = metadata.get("mojo_library_sha256")
            if declared_library_sha256 not in (None, mojo_library_sha256):
                raise RuntimeError(f"native Mojo library checksum mismatch: {target.asset}")
        else:
            mojo_library_sha256 = None
        mojo_build_target = str(metadata.get("target", name))
        mojo_compiler_version = str(metadata.get("mojo_compiler_version", "not-recorded"))
        rows[name] = {
            "target": name,
            "asset": target.asset,
            "sha256": digest(asset_path),
            "os": target.os,
            "arch": target.architecture,
            "native": bool(metadata.get("native", True)),
            "standalone": target.standalone,
            "vision_available": target.vision,
            "vision_backend": vision_backend,
            "mojo_source": target.mojo_source,
            "mojo_source_sha256": mojo_source_sha256,
            "mojo_source_files": mojo_source_files,
            "native_mojo_engine": native_mojo_engine,
            "native_mojo_engine_loaded": native_mojo_engine_loaded,
            "mojo_abi_version": mojo_abi_version,
            "mojo_library": mojo_library,
            "mojo_library_arch": mojo_library_arch,
            "mojo_library_sha256": mojo_library_sha256,
            "mojo_compiler_version": mojo_compiler_version,
            "python_engine_available": bool(
                metadata.get("python_engine_available", target.python_engine)
            ),
            "runtime_default": runtime_default,
            "mojo": {
                "source_available": target.mojo_source,
                "source_sha256": mojo_source_sha256,
                "source_files": mojo_source_files,
                "native_engine_available": native_mojo_engine,
                "native_engine_loaded": native_mojo_engine_loaded,
                "abi_version": mojo_abi_version,
                "library": mojo_library,
                "library_arch": mojo_library_arch,
                "library_sha256": mojo_library_sha256,
                "build_target": mojo_build_target,
                "compiler_version": mojo_compiler_version,
            },
            "vision": {"available": target.vision, "implementation": vision_backend},
            "python_engine": {"available": target.python_engine},
            "python_runtime": str(metadata.get("python_runtime", target.python)),
            "mediapipe_version": str(metadata.get("mediapipe_version", "not-recorded")),
            "gesture_engine": runtime_default,
            "minimum_os": target.minimum_os,
            "package_format": target.format,
            "smoke_test": "native-package-smoke",
            "provenance": "github-actions-artifact-attestation",
            "implementation": runtime_default,
            "python_fallback": target.python_engine,
            "mojo_engine": native_mojo_engine,
            "architecture": target.architecture,
            "runner": target.runner,
            "mediapipe": target.vision,
            "format": target.format,
            "python": target.python,
            "minimum_glibc": target.minimum_glibc,
        }
    if set(rows) != set(targets):
        raise RuntimeError("release assets do not contain exactly the required target matrix")
    try:
        mediapipe_version = importlib.metadata.version("mediapipe")
    except importlib.metadata.PackageNotFoundError:
        mediapipe_version = "bundled-runtime-metadata"
    try:
        opencv_version = importlib.metadata.version("opencv-contrib-python")
    except importlib.metadata.PackageNotFoundError:
        opencv_version = "bundled-runtime-metadata"
    mojo_version = "unavailable"
    command = shutil.which("mojo") if sys.platform != "win32" else None
    if command:
        result = subprocess.run([command, "--version"], capture_output=True, text=True, check=False)
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
