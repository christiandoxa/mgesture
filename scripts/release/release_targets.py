from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

STABLE_TARGETS = frozenset(
    {
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
        "x86_64-apple-darwin",
        "aarch64-apple-darwin",
        "x86_64-pc-windows-msvc",
        "aarch64-pc-windows-msvc",
    }
)


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    runner: str
    architecture: str
    os: str
    asset: str
    format: str
    standalone: bool
    python: str
    vision: bool
    mojo_source: bool
    mojo_ci_mode: str
    python_engine: bool
    native_mojo_engine: bool
    runtime_default: str
    native_smoke: bool
    minimum_glibc: str
    minimum_os: str
    publishable: bool
    status: str
    notes: str


def load_targets(path: Path | None = None) -> dict[str, Target]:
    target_path = path or Path(__file__).resolve().parents[2] / "release" / "targets.toml"
    raw = tomllib.loads(target_path.read_text(encoding="utf-8"))
    rows = raw.get("target", [])
    names = [row["name"] for row in rows]
    assets = [row["asset"] for row in rows]
    if len(set(names)) != len(names):
        raise ValueError("release target IDs must be unique")
    if len(set(assets)) != len(assets):
        raise ValueError("release target assets must be unique")
    return {row["name"]: Target(**row) for row in rows}


def target(name: str, path: Path | None = None) -> Target:
    try:
        return load_targets(path)[name]
    except KeyError as exc:
        raise ValueError(f"unknown release target: {name}") from exc


def publishable_targets(path: Path | None = None) -> dict[str, Target]:
    targets = {name: value for name, value in load_targets(path).items() if value.publishable}
    if set(targets) != STABLE_TARGETS:
        raise ValueError(
            "stable releases require exactly the six canonical publishable targets: "
            + ", ".join(sorted(STABLE_TARGETS))
        )
    return targets


def ci_matrix(path: Path | None = None) -> list[dict[str, str]]:
    return [
        {
            "target": value.name,
            "runner": value.runner,
            "mojo_ci_mode": value.mojo_ci_mode,
        }
        for value in publishable_targets(path).values()
    ]
