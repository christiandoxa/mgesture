from __future__ import annotations

import random
from pathlib import Path

import pytest

from mgesture.engine import EngineConfig, create_engine
from mgesture.engine.models import LandmarkFrame
from mgesture.engine.mojo_engine import MOJO_ABI_VERSION, native_library_name
from mgesture.engine.synthetic import synthetic_frames, synthetic_landmarks
from mgesture.self_test import run_self_test

ROOT = Path(__file__).resolve().parents[2]


def _native_library() -> Path:
    return ROOT / "build" / native_library_name()


def _require_native_library() -> None:
    if not _native_library().is_file():
        pytest.skip("native Mojo ABI library has not been built")


def _signature(batch: object) -> list[tuple[str, str | None, str | None]]:
    return [
        (
            action.type.value,
            action.button.value if action.button else None,
            action.state.value if action.state else None,
        )
        for action in batch.actions  # type: ignore[attr-defined]
    ]


def test_forced_mojo_self_test_rejects_non_native_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMojoEngine:
        name = "mojo"

    monkeypatch.setattr(
        "mgesture.self_test.create_engine",
        lambda *args, **kwargs: FakeMojoEngine(),
    )
    result = run_self_test(require_mojo=True, engine_request="mojo")
    assert result["passed"] is False
    assert result["active_engine"] == "unavailable"
    assert "native Mojo engine was not selected" in str(result["failures"]["gesture_engine"])


def test_standalone_root_finds_metadata_above_pyinstaller_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import mgesture.engine.loader as loader

    root = tmp_path / "mgesture"
    (root / "share" / "mgesture").mkdir(parents=True)
    (root / "share" / "mgesture" / "release-metadata.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("MGESTURE_BUNDLE_ROOT", raising=False)
    monkeypatch.setattr(loader.sys, "executable", str(root / "bin" / "mgesture"))
    monkeypatch.setattr(loader.sys, "_MEIPASS", str(root / "bin" / "bin"), raising=False)

    assert loader._standalone_root() == root


def test_native_mojo_abi_loads_and_processes_landmarks() -> None:
    _require_native_library()
    engine = create_engine(
        "mojo", EngineConfig(reacquisition_ms=0, activation_gesture=False), armed=True
    )
    batch = engine.process(LandmarkFrame(0, synthetic_landmarks(), "Right", 0.99))
    assert batch.engine == "mojo"
    assert batch.diagnostics["abi_version"] == MOJO_ABI_VERSION
    assert batch.diagnostics["native"] is True
    engine.reset("ABI test")


def test_native_mojo_matches_python_action_contract() -> None:
    _require_native_library()
    config = EngineConfig(reacquisition_ms=0, activation_gesture=False)
    python_engine = create_engine("python", config, armed=True)
    mojo_engine = create_engine("mojo", config, armed=True)
    for frame in synthetic_frames(100):
        python_batch = python_engine.process(frame)
        mojo_batch = mojo_engine.process(frame)
        assert _signature(mojo_batch) == _signature(python_batch)
        python_moves = [
            action for action in python_batch.actions if action.type.value == "move_absolute"
        ]
        mojo_moves = [
            action for action in mojo_batch.actions if action.type.value == "move_absolute"
        ]
        assert len(mojo_moves) == len(python_moves)
        for mojo_move, python_move in zip(mojo_moves, python_moves, strict=True):
            assert abs((mojo_move.x or 0.0) - (python_move.x or 0.0)) < 1.0
            assert abs((mojo_move.y or 0.0) - (python_move.y or 0.0)) < 1.0


def test_native_mojo_matches_deterministic_randomized_contract() -> None:
    _require_native_library()
    config = EngineConfig(reacquisition_ms=0, activation_gesture=False, dead_zone=0.0)
    python_engine = create_engine("python", config, armed=True)
    mojo_engine = create_engine("mojo", config, armed=True)
    rng = random.Random(17)
    for index in range(300):
        handedness = "Right" if rng.random() > 0.1 else "Left"
        confidence = 0.99 if handedness == "Right" else 0.2
        frame = LandmarkFrame(
            index * 37,
            synthetic_landmarks(rng.random(), rng.random(), rng.choice((None, "left", "right"))),
            handedness,
            confidence,
        )
        assert _signature(mojo_engine.process(frame)) == _signature(python_engine.process(frame))
    mojo_engine.reset("randomized cleanup")
    python_engine.reset("randomized cleanup")
