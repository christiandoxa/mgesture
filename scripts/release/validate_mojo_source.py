from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import publishable_targets  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.release import mojo_source_metadata  # noqa: E402


def validate_source() -> None:
    source = mojo_source_metadata()
    if not source["available"] or "mgesture_core.mojo" not in source["files"]:
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
    ):
        raise ValueError("bundle Mojo source metadata does not match its source files")
    mojo = metadata.get("mojo")
    if (
        not isinstance(mojo, dict)
        or mojo.get("source_available") is not True
        or mojo.get("source_sha256") != source["sha256"]
        or mojo.get("source_files") != source["files"]
        or mojo.get("native_engine_available") != metadata.get("native_mojo_engine_available")
    ):
        raise ValueError("bundle nested Mojo source metadata does not match")
    print(f"validated bundled Mojo source: {source['sha256']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    validate_bundle(args.root) if args.root else validate_source()


if __name__ == "__main__":
    main()
