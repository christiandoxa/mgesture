from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import publishable_targets  # noqa: E402
from validate_mojo_abi import validate as validate_mojo_abi  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.mojo_engine import native_library_name  # noqa: E402
from mgesture.release import mojo_source_metadata  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_source() -> None:
    source = mojo_source_metadata(ROOT / "mojo")
    required_source = {"mgesture_core.mojo", "mgesture_python.mojo"}
    if not source["available"] or not required_source <= set(source["files"]):
        raise ValueError("canonical Mojo production source is missing")
    targets = publishable_targets()
    for name, target in targets.items():
        if not (
            target.standalone and target.vision and target.mojo_source and target.python_engine
        ):
            raise ValueError(f"target capabilities are incomplete: {name}")
    print(f"Mojo source is available for {len(targets)} targets: {source['sha256']}")


def validate_bundle(root: Path) -> None:
    metadata_path = root / "share" / "mgesture" / "release-metadata.json"
    source_dir = root / "share" / "mgesture" / "mojo"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    target_name = metadata.get("target")
    if not isinstance(target_name, str):
        raise ValueError("bundle metadata has no target")
    source = mojo_source_metadata(source_dir)
    if not source["available"]:
        raise ValueError("bundle is missing canonical Mojo source")
    if (
        metadata.get("mojo_source_available") is not True
        or metadata.get("mojo_source_sha256") != source["sha256"]
        or metadata.get("mojo_source_files") != source["files"]
        or metadata.get("standalone") is not True
        or metadata.get("vision_available") is not True
        or metadata.get("python_engine_available") is not True
        or metadata.get("native_mojo_engine_available") is not True
        or metadata.get("native_mojo_engine_loaded") is not True
        or metadata.get("mojo_abi_version") != 1
        or metadata.get("mojo_library") != native_library_name(str(metadata.get("os", "")))
        or metadata.get("mojo_library_arch") != metadata.get("architecture")
    ):
        raise ValueError("bundle Mojo source metadata does not match its source files")
    mojo = metadata.get("mojo")
    if (
        not isinstance(mojo, dict)
        or mojo.get("source_available") is not True
        or mojo.get("source_sha256") != source["sha256"]
        or mojo.get("source_files") != source["files"]
        or mojo.get("native_engine_available") is not True
        or mojo.get("native_engine_loaded") is not True
        or mojo.get("abi_version") != metadata.get("mojo_abi_version")
        or mojo.get("library") != native_library_name(str(metadata.get("os", "")))
        or mojo.get("library_arch") != metadata.get("architecture")
        or mojo.get("library_sha256") != metadata.get("mojo_library_sha256")
    ):
        raise ValueError("bundle nested Mojo source metadata does not match")
    library = root / "runtime" / "mojo" / native_library_name(str(metadata.get("os", "")))
    if metadata.get("mojo_library_sha256") != digest(library):
        raise ValueError("bundle native Mojo library checksum does not match metadata")
    validate_mojo_abi(target_name, library)
    print(f"validated bundled Mojo source: {source['sha256']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    validate_bundle(args.root) if args.root else validate_source()


if __name__ == "__main__":
    main()
