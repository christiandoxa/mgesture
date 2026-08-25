from __future__ import annotations

import argparse
import re
import tomllib
from pathlib import Path


def runtime_version(root: Path) -> str:
    namespace: dict[str, object] = {}
    exec((root / "src/mgesture/version.py").read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def validate(root: Path, expected: str | None = None) -> str:
    version = runtime_version(root)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[+-][0-9A-Za-z.-]+)?", version):
        raise ValueError(f"invalid runtime version: {version}")
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if "version" not in pyproject.get("project", {}).get("dynamic", []):
        raise ValueError("pyproject must use dynamic version metadata")
    if expected and expected != version:
        raise ValueError(f"requested release {expected} does not match runtime {version}")
    return version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--version")
    args = parser.parse_args()
    print(validate(args.root, args.version))


if __name__ == "__main__":
    main()
