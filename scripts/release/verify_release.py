from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import publishable_targets  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.release import mojo_source_metadata  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(directory: Path, version: str | None = None) -> None:
    manifest_path = directory / "release-manifest.json"
    checksums_path = directory / "SHA256SUMS"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported release manifest schema")
    if version and manifest.get("version") != version:
        raise ValueError("release manifest version mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("commit", ""))):
        raise ValueError("release manifest commit must be a full SHA")
    expected_targets = publishable_targets()
    expected_source = mojo_source_metadata()
    manifest_targets = manifest.get("targets")
    if not isinstance(manifest_targets, dict) or set(manifest_targets) != set(expected_targets):
        raise ValueError("release manifest must contain exactly the six publishable target entries")
    checksum_rows = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
        if match:
            checksum_rows[match[2]] = match[1].lower()
    required_fields = {
        "target",
        "os",
        "arch",
        "asset",
        "sha256",
        "native",
        "standalone",
        "vision_available",
        "vision_backend",
        "mojo_source",
        "mojo_source_sha256",
        "mojo_source_files",
        "native_mojo_engine",
        "python_runtime",
        "mediapipe_version",
        "gesture_engine",
        "python_engine_available",
        "runtime_default",
        "minimum_os",
        "package_format",
        "smoke_test",
        "provenance",
        "mojo",
        "vision",
        "python_engine",
    }
    for name, target in manifest_targets.items():
        if not isinstance(target, dict) or not required_fields <= set(target):
            raise ValueError(f"manifest entry is incomplete: {name}")
        expected = expected_targets[name]
        if (
            target["target"] != name
            or target["asset"] != expected.asset
            or target["os"] != expected.os
            or target["arch"] != expected.architecture
            or target["package_format"] != expected.format
        ):
            raise ValueError(f"manifest target metadata mismatch: {name}")
        if (
            target["native"] is not True
            or target["standalone"] is not expected.standalone
            or target["vision_available"] is not expected.vision
            or target["mojo_source"] is not expected.mojo_source
            or target["native_mojo_engine"] is not expected.native_mojo_engine
            or target["python_engine_available"] is not expected.python_engine
            or target["mojo_source_sha256"] != expected_source["sha256"]
            or target["mojo_source_files"] != expected_source["files"]
        ):
            raise ValueError(f"manifest capability metadata mismatch: {name}")
        mojo = target["mojo"]
        if (
            not isinstance(mojo, dict)
            or mojo.get("source_available") is not True
            or mojo.get("source_sha256") != expected_source["sha256"]
            or mojo.get("source_files") != expected_source["files"]
            or mojo.get("native_engine_available") is not target["native_mojo_engine"]
        ):
            raise ValueError(f"manifest Mojo source metadata mismatch: {name}")
        vision = target["vision"]
        if (
            not isinstance(vision, dict)
            or vision.get("available") is not expected.vision
            or vision.get("implementation") != target["vision_backend"]
        ):
            raise ValueError(f"manifest vision metadata mismatch: {name}")
        python_engine = target["python_engine"]
        if (
            not isinstance(python_engine, dict)
            or python_engine.get("available") is not expected.python_engine
        ):
            raise ValueError(f"manifest Python engine metadata mismatch: {name}")
        asset = str(target["asset"])
        path = directory / asset
        if not path.exists() or digest(path) != str(target["sha256"]):
            raise ValueError(f"asset digest mismatch: {asset}")
        if checksum_rows.get(asset) != digest(path):
            raise ValueError(f"SHA256SUMS mismatch: {asset}")
    for filename, expected in checksum_rows.items():
        if filename == "SHA256SUMS":
            continue
        path = directory / filename
        if not path.exists():
            raise ValueError(f"SHA256SUMS names missing file: {filename}")
        if digest(path) != expected:
            raise ValueError(f"SHA256SUMS digest mismatch: {filename}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args()
    verify(args.directory, args.version)
    print("release verification passed")


if __name__ == "__main__":
    main()
