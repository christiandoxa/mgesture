from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from build_mojo_library import build_object  # noqa: E402
from release_targets import publishable_targets  # noqa: E402

from mgesture.release import mojo_source_metadata  # noqa: E402


def build_objects(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    objects = []
    for name, release_target in publishable_targets().items():
        if release_target.mojo_build_mode == "cross-object":
            objects.append(build_object(name, output_dir / f"{name}.o"))
    if not objects:
        raise ValueError("canonical target matrix has no cross-object Mojo targets")
    compiler = shutil.which("mojo")
    if compiler is None:
        raise RuntimeError("Mojo compiler is required to record cross-object provenance")
    result = subprocess.run([compiler, "--version"], capture_output=True, text=True, check=True)
    (output_dir / "mojo-build-metadata.json").write_text(
        json.dumps(
            {
                "compiler_version": (result.stdout or result.stderr).strip(),
                "source_sha256": mojo_source_metadata(ROOT / "mojo")["sha256"],
                "targets": [path.stem for path in objects],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return objects


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for path in build_objects(args.output_dir):
        print(path)


if __name__ == "__main__":
    main()
