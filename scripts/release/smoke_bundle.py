from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402
from validate_architecture import validate_bundle as validate_bundle_architecture  # noqa: E402
from validate_mojo_source import validate_bundle as validate_mojo_bundle  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.mojo_engine import native_library_name  # noqa: E402


def _safe_destination(root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ":" in parts[0] or ".." in parts:
        raise ValueError(f"unsafe archive member: {member_name}")
    destination = (root.joinpath(*parts)).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise ValueError(f"archive member escapes extraction root: {member_name}")
    return destination


def _extract_archive(archive_path: Path, destination: Path, archive_format: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive_format == "zip":
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                path = _safe_destination(destination, member.filename)
                mode = (member.external_attr >> 16) & 0o170000
                if stat.S_ISLNK(mode):
                    raise ValueError(f"symlink archive member is not allowed: {member.filename}")
                if member.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output, 1024 * 1024)
                permissions = (member.external_attr >> 16) & 0o777
                if permissions:
                    path.chmod(permissions)
        return

    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            path = _safe_destination(destination, member.name)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"non-regular archive member is not allowed: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"archive member cannot be read: {member.name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            path.chmod(member.mode & 0o777)


def _run(binary: Path, arguments: list[str], root: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        [str(binary), *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{binary.name} {' '.join(arguments)} failed: {detail}")
    return result.stdout


def _isolated_environment(bundle: Path, target_os: str, temporary: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "MGESTURE_BIN_DIR",
        "MGESTURE_INSTALL_DIR",
        "MGESTURE_RELEASE",
        "MGESTURE_RELEASE_BASE_URL",
    ):
        environment.pop(name, None)
    environment["MGESTURE_BUNDLE_ROOT"] = str(bundle)
    home = temporary / "home"
    environment["HOME"] = str(home)
    if target_os == "windows":
        environment["LOCALAPPDATA"] = str(temporary / "local-app-data")
        environment["APPDATA"] = str(temporary / "roaming-app-data")
    else:
        environment["XDG_CONFIG_HOME"] = str(temporary / "config")
        environment["XDG_CACHE_HOME"] = str(temporary / "cache")
        environment["XDG_STATE_HOME"] = str(temporary / "state")
        environment["XDG_DATA_HOME"] = str(
            bundle.parent if target_os == "linux" else temporary / "data"
        )
    return environment


def smoke(archive_path: Path, target_name: str) -> None:
    release_target = target(target_name)
    with tempfile.TemporaryDirectory(
        prefix="mgesture-bundle-smoke-", ignore_cleanup_errors=True
    ) as temporary_name:
        temporary = Path(temporary_name)
        extracted = temporary / "extracted"
        _extract_archive(archive_path, extracted, release_target.format)
        bundle = extracted / "mgesture"
        metadata_path = bundle / "share" / "mgesture" / "release-metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("target") != target_name:
            raise ValueError(f"bundle target mismatch: expected {target_name}")
        validate_mojo_bundle(bundle)
        validate_bundle_architecture(target_name, bundle)

        binary_name = "mgesture.exe" if release_target.os == "windows" else "mgesture"
        binary = bundle / "bin" / binary_name
        native = bundle / "runtime" / "mojo" / native_library_name(release_target.os)
        model = bundle / "share" / "mgesture" / "models" / "hand_landmarker.task"
        for path in (binary, native, model):
            if not path.is_file():
                raise ValueError(f"bundle is missing required file: {path}")

        environment = _isolated_environment(bundle, release_target.os, temporary)
        version_output = _run(binary, ["--version"], bundle, environment)
        if str(metadata.get("version", "")) not in version_output:
            raise RuntimeError("packaged version output does not match metadata")
        _run(binary, ["--help"], bundle, environment)
        _run(
            binary,
            ["self-test", "--headless", "--fake-input", "--engine", "mojo"],
            bundle,
            environment,
        )
        doctor_output = _run(binary, ["doctor", "--runtime", "--json"], bundle, environment)
        doctor = json.loads(doctor_output)
        if doctor.get("gesture_engine", {}).get("active_engine") != "mojo":
            raise RuntimeError("packaged doctor did not report the native Mojo engine")
        fixture = bundle / "share" / "mgesture" / "fixtures" / "basic.json"
        _run(binary, ["replay", "--fixture", str(fixture), "--engine", "mojo"], bundle, environment)

        _run(binary, ["--reset", "--yes"], bundle, environment)
        for path in (binary, native, model):
            if not path.is_file():
                raise RuntimeError(f"reset removed packaged application file: {path}")
        _run(binary, ["--version"], bundle, environment)
        _run(
            binary,
            ["self-test", "--headless", "--fake-input", "--engine", "mojo"],
            bundle,
            environment,
        )
    print(f"standalone bundle smoke passed: {target_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    smoke(args.archive, args.target)


if __name__ == "__main__":
    main()
