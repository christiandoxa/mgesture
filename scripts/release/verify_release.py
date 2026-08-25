from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


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
    checksum_rows = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line)
        if match:
            checksum_rows[match[2]] = match[1].lower()
    for target in manifest.get("targets", {}).values():
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
