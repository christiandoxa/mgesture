from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine import EngineConfig, EngineUnavailableError, create_engine  # noqa: E402
from mgesture.release import current_target, mojo_source_metadata, runtime_metadata  # noqa: E402


def check(target_name: str) -> None:
    release_target = target(target_name)
    if release_target.mojo_ci_mode != "source-contract":
        raise SystemExit(f"target is not a source-contract Mojo target: {target_name}")
    if current_target() != target_name:
        raise SystemExit(f"native runner target mismatch: expected {target_name}")
    source = mojo_source_metadata()
    if not release_target.mojo_source or not source["available"]:
        raise SystemExit("canonical Mojo source is unavailable")
    if release_target.native_mojo_engine:
        raise SystemExit("source-contract target must not claim a native Mojo bundle")
    metadata = runtime_metadata()
    if (
        metadata.get("mojo_source_available") is not True
        or metadata.get("mojo_source_sha256") != source["sha256"]
        or metadata.get("mojo_source_files") != source["files"]
        or metadata.get("native_mojo_engine_available") is True
    ):
        raise SystemExit("source-contract target unexpectedly reports a native Mojo runtime")
    nested = metadata.get("mojo")
    if (
        not isinstance(nested, dict)
        or nested.get("source_available") is not True
        or nested.get("source_sha256") != source["sha256"]
        or nested.get("native_engine_available") is True
    ):
        raise SystemExit("source-contract target has inconsistent Mojo metadata")

    previous_engine = os.environ.pop("MGESTURE_ENGINE", None)
    try:
        auto_engine = create_engine("auto", EngineConfig(), armed=False)
        python_engine = create_engine("python", EngineConfig(), armed=False)
        if auto_engine.name != "python":
            raise SystemExit(f"--engine auto selected {auto_engine.name}, expected python")
        if python_engine.name != "python":
            raise SystemExit("--engine python did not select the Python reference engine")
        try:
            create_engine("mojo", EngineConfig(), armed=False)
        except EngineUnavailableError as exc:
            print(f"Mojo source-contract passed for {target_name}: {exc}")
        else:
            raise SystemExit("--engine mojo unexpectedly loaded a native engine")
    finally:
        if previous_engine is not None:
            os.environ["MGESTURE_ENGINE"] = previous_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target")
    args = parser.parse_args()
    check(args.target or current_target())


if __name__ == "__main__":
    main()
