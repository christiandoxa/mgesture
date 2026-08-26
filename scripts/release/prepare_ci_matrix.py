from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import STABLE_TARGETS, ci_matrix  # noqa: E402


def main() -> None:
    rows = ci_matrix()
    names = [row["target"] for row in rows]
    if len(rows) != 6 or len(set(names)) != 6 or set(names) != STABLE_TARGETS:
        raise ValueError("CI requires exactly the six canonical release targets")
    if len({row["runner"] for row in rows}) != 6:
        raise ValueError("CI target runners must be unique")
    if {row["mojo_ci_mode"] for row in rows} != {"native", "source-contract"}:
        raise ValueError("CI matrix must contain native and source-contract Mojo modes")
    print(json.dumps({"include": rows}, separators=(",", ":")))


if __name__ == "__main__":
    main()
