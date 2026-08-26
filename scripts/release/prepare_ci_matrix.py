from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import STABLE_TARGETS, ci_matrix, publishable_targets  # noqa: E402


def main() -> None:
    rows = ci_matrix()
    names = [row["target"] for row in rows]
    if len(rows) != 6 or len(set(names)) != 6 or set(names) != STABLE_TARGETS:
        raise ValueError("CI requires exactly the six canonical release targets")
    if len({row["runner"] for row in rows}) != 6:
        raise ValueError("CI target runners must be unique")
    if {row["mojo_ci_mode"] for row in rows} != {"native"}:
        raise ValueError("all six Mojo CI jobs must validate a native engine")
    if {row["mojo_build_mode"] for row in rows} != {"native", "cross-object"}:
        raise ValueError("CI matrix must contain native and cross-object Mojo build modes")
    targets = publishable_targets()
    if sum(target.native_mojo_engine for target in targets.values()) != 6:
        raise ValueError("stable releases require native Mojo engines for all six targets")
    if {target.runtime_default for target in targets.values()} != {"mojo"}:
        raise ValueError("stable releases must default to the native Mojo engine")
    print(json.dumps({"include": rows}, separators=(",", ":")))


if __name__ == "__main__":
    main()
