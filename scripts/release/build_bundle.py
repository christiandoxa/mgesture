from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402
from validate_architecture import (  # noqa: E402
    _native_candidate,
    binary_architectures,
)
from validate_architecture import validate_bundle as validate_bundle_architecture  # noqa: E402
from validate_mojo_abi import validate as validate_mojo_abi  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.mojo_engine import native_library_name  # noqa: E402
from mgesture.release import mojo_source_metadata, mojo_source_paths  # noqa: E402
from mgesture.vision.model_manager import available_model  # noqa: E402


def _version() -> str:
    namespace: dict[str, object] = {}
    exec((ROOT / "src/mgesture/version.py").read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def _commit(value: str | None) -> str:
    if value:
        return value
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "source-tree"


def _mojo_compiler_version(required: bool) -> str:
    metadata_path = ROOT / "mojo-objects" / "mojo-build-metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        version = metadata.get("compiler_version") if isinstance(metadata, dict) else None
        if isinstance(version, str) and version:
            return version
    command = shutil.which("mojo")
    if command:
        result = subprocess.run([command, "--version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version = (result.stdout or result.stderr).strip()
            if version:
                return version
    if required:
        raise RuntimeError("native Mojo compiler provenance metadata is unavailable")
    return "not-used"


def _prune_foreign_native_binaries(app_bin: Path, target_os: str, target_architecture: str) -> None:
    for path in app_bin.rglob("*"):
        if not path.is_file() or not _native_candidate(path, target_os):
            continue
        architectures = binary_architectures(path)
        if architectures is None:
            raise RuntimeError(f"native candidate has an unknown binary format: {path}")
        if target_architecture not in architectures:
            path.unlink()


def build(
    target_name: str,
    output: Path,
    model: Path | None,
    version: str,
    commit: str,
    mojo_library: Path | None = None,
) -> Path:
    if version != _version():
        raise ValueError(f"bundle version {version} does not match runtime version {_version()}")
    release_target = target(target_name)
    if not release_target.publishable:
        raise RuntimeError(f"target {target_name} is not publishable: {release_target.status}")
    if release_target.native_mojo_engine and mojo_library is None:
        raise RuntimeError("a verified native Mojo library is required for this target")
    model = model or available_model()
    if model is None:
        raise RuntimeError(
            "verified model is unavailable; run `mgesture model install` or pass --model"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mgesture-build-") as temporary:
        work = Path(temporary)
        dist = work / "dist"
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "mgesture",
            "--paths",
            str(ROOT / "src"),
            "--collect-all",
            "mediapipe",
            "--collect-all",
            "cv2",
            "--copy-metadata",
            "mediapipe",
            "--distpath",
            str(dist),
            "--workpath",
            str(work / "pyinstaller-work"),
            "--specpath",
            str(work / "spec"),
            str(work / "entry.py"),
        ]
        if release_target.os == "macos":
            command.extend(
                [
                    "--target-architecture",
                    "arm64" if release_target.architecture == "aarch64" else "x86_64",
                ]
            )
        (work / "entry.py").write_text("from mgesture.cli import main\nmain()\n", encoding="utf-8")
        subprocess.run(command, cwd=ROOT, check=True)
        bundle = work / "mgesture"
        app_bin = bundle / "bin"
        app_bin.parent.mkdir(parents=True)
        shutil.copytree(dist / "mgesture", app_bin)
        _prune_foreign_native_binaries(app_bin, release_target.os, release_target.architecture)
        share = bundle / "share" / "mgesture"
        (share / "models").mkdir(parents=True)
        shutil.copy2(model, share / "models" / "hand_landmarker.task")
        license_file = model.with_suffix(model.suffix + ".license")
        if license_file.exists():
            shutil.copy2(license_file, share / "models" / license_file.name)
        (bundle / "licenses").mkdir()
        shutil.copy2(ROOT / "LICENSE", bundle / "licenses" / "LICENSE")
        (bundle / "licenses" / "MEDIAPIPE_MODEL.txt").write_text(
            "MediaPipe Hand Landmarker model; see upstream MediaPipe model card and Apache-2.0 terms.\n",
            encoding="utf-8",
        )
        (bundle / "licenses" / "THIRD_PARTY_NOTICES.txt").write_text(
            "Bundled runtime notices:\n"
            "- MediaPipe: Apache-2.0; https://github.com/google-ai-edge/mediapipe\n"
            "- OpenCV: Apache-2.0; https://opencv.org/license/\n"
            "- NumPy: BSD-3-Clause; https://numpy.org/license.html\n"
            "- pynput: LGPL-3.0-or-later; https://github.com/moses-palmer/pynput\n"
            "- PyInstaller: GPL-2.0-or-later with bootloader exception; https://pyinstaller.org/\n"
            "Consult each bundled distribution's metadata for complete notices.\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "release/targets.toml", share / "targets.toml")
        native_mojo = mojo_library is not None
        if native_mojo:
            if not mojo_library.is_file():
                raise FileNotFoundError(mojo_library)
            validate_mojo_abi(target_name, mojo_library)
            mojo_runtime = bundle / "runtime" / "mojo"
            mojo_runtime.mkdir(parents=True)
            bundled_mojo_library = mojo_runtime / native_library_name(release_target.os)
            shutil.copy2(mojo_library, bundled_mojo_library)
            if not bundled_mojo_library.is_file():
                raise RuntimeError(f"native Mojo library was not staged: {bundled_mojo_library}")
        source_dir = share / "mojo"
        source_dir.mkdir(parents=True)
        for source_path in mojo_source_paths(ROOT / "mojo"):
            shutil.copy2(source_path, source_dir / source_path.name)
        source_metadata = mojo_source_metadata(ROOT / "mojo")
        mojo_library_sha256 = _sha256(mojo_library) if native_mojo else None
        mojo_compiler_version = _mojo_compiler_version(native_mojo)
        fixture = share / "fixtures" / "basic.json"
        fixture.parent.mkdir(parents=True)
        shutil.copy2(ROOT / "tests/fixtures/basic.json", fixture)
        try:
            mediapipe_version = importlib.metadata.version("mediapipe")
        except importlib.metadata.PackageNotFoundError:
            mediapipe_version = "not-installed"
        try:
            opencv_version = importlib.metadata.version("opencv-contrib-python")
        except importlib.metadata.PackageNotFoundError:
            opencv_version = "not-installed"
        metadata = {
            "schema_version": 1,
            "version": version,
            "commit": commit,
            "target": target_name,
            "os": release_target.os,
            "architecture": release_target.architecture,
            "native": True,
            "standalone": release_target.standalone,
            "vision_available": release_target.vision,
            "mojo_source_available": release_target.mojo_source,
            "mojo_source_sha256": str(source_metadata["sha256"]),
            "mojo_source_files": source_metadata["files"],
            "native_mojo_engine_available": native_mojo,
            "native_mojo_engine_loaded": False,
            "python_engine_available": release_target.python_engine,
            "runtime_default": "mojo" if native_mojo else release_target.runtime_default,
            "implementation": "mojo" if native_mojo else release_target.runtime_default,
            "compiler_required": False,
            "python_runtime_bundled": True,
            "model_sha256": _sha256(model),
            "packaging": "PyInstaller onedir",
            "python": release_target.python,
            "python_runtime": platform.python_version(),
            "python_architecture": platform.machine(),
            "pointer_bits": struct.calcsize("P") * 8,
            "mediapipe_version": mediapipe_version,
            "opencv_version": opencv_version,
            "vision_backend": "mediapipe",
            "minimum_os": release_target.minimum_os,
            "package_format": release_target.format,
            "mojo_version": "mojo-abi-1" if native_mojo else "not bundled",
            "mojo_compiler_version": mojo_compiler_version,
            "mojo_abi_version": 1 if native_mojo else None,
            "mojo_library": native_library_name(release_target.os) if native_mojo else None,
            "mojo_library_arch": release_target.architecture if native_mojo else None,
            "mojo_library_sha256": mojo_library_sha256,
            "mojo": {
                "source_available": release_target.mojo_source,
                "source_sha256": str(source_metadata["sha256"]),
                "source_files": source_metadata["files"],
                "native_engine_available": native_mojo,
                "native_engine_loaded": False,
                "abi_version": 1 if native_mojo else None,
                "library": native_library_name(release_target.os) if native_mojo else None,
                "library_arch": release_target.architecture if native_mojo else None,
                "library_sha256": mojo_library_sha256,
                "build_target": target_name if native_mojo else None,
                "compiler_version": mojo_compiler_version,
            },
            "vision": {"available": release_target.vision, "implementation": "mediapipe"},
            "python_engine": {"available": release_target.python_engine},
            "gesture_engine": {
                "implementation": "mojo" if native_mojo else release_target.runtime_default,
                "compiler_required": False,
                "self_test": "pending-runtime-smoke",
            },
        }
        (share / "release-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        binary = app_bin / ("mgesture.exe" if sys.platform == "win32" else "mgesture")
        subprocess.run(
            [
                str(binary),
                "self-test",
                "--headless",
                "--fake-input",
                "--engine",
                "mojo" if native_mojo else "auto",
            ],
            cwd=bundle,
            env={
                **os.environ,
                "MGESTURE_BUNDLE_ROOT": str(bundle),
                **({"MGESTURE_MOJO_LIBRARY": str(bundled_mojo_library)} if native_mojo else {}),
            },
            check=True,
        )
        metadata["gesture_engine"]["self_test"] = "passed"
        metadata["native_mojo_engine_loaded"] = native_mojo
        metadata["mojo"]["native_engine_loaded"] = native_mojo
        (share / "release-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        validate_bundle_architecture(target_name, bundle)
        shutil.copy2(ROOT / "install.sh", bundle / "install.sh")
        shutil.copy2(ROOT / "install.ps1", bundle / "install.ps1")
        archive_output = output.with_name(f".{output.name}.{os.getpid()}.tmp")
        try:
            if output.suffix == ".zip":
                with zipfile.ZipFile(archive_output, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in bundle.rglob("*"):
                        if path.is_file():
                            archive.write(path, Path("mgesture") / path.relative_to(bundle))
            else:
                with tarfile.open(archive_output, "w:gz") as archive:
                    archive.add(bundle, arcname="mgesture")
            os.replace(archive_output, output)
            if native_mojo:
                member = f"mgesture/runtime/mojo/{native_library_name(release_target.os)}"
                if output.suffix == ".zip":
                    with zipfile.ZipFile(output) as archive:
                        present = member in archive.namelist()
                else:
                    with tarfile.open(output, "r:gz") as archive:
                        present = member in archive.getnames()
                if not present:
                    raise RuntimeError(f"archive is missing bundled native Mojo library: {member}")
        finally:
            archive_output.unlink(missing_ok=True)
    return output


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--version", default=_version())
    parser.add_argument("--commit")
    parser.add_argument("--mojo-library", type=Path)
    args = parser.parse_args()
    build(
        args.target,
        args.output,
        args.model,
        args.version,
        _commit(args.commit),
        args.mojo_library,
    )
    print(args.output)


if __name__ == "__main__":
    main()
