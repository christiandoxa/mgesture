from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    runner: str
    architecture: str
    os: str
    asset: str
    format: str
    python: str
    mojo_engine: bool
    implementation: str
    python_fallback: bool
    mediapipe: bool
    native_smoke: bool
    minimum_glibc: str
    publishable: bool
    status: str
    notes: str


def load_targets(path: Path | None = None) -> dict[str, Target]:
    target_path = path or Path(__file__).resolve().parents[2] / "release" / "targets.toml"
    raw = tomllib.loads(target_path.read_text(encoding="utf-8"))
    return {row["name"]: Target(**row) for row in raw.get("target", [])}


def target(name: str, path: Path | None = None) -> Target:
    try:
        return load_targets(path)[name]
    except KeyError as exc:
        raise ValueError(f"unknown release target: {name}") from exc
