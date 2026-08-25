from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mgesture.engine import EngineConfig, LandmarkFrame, create_engine
from mgesture.input import FakeMouseBackend, InputDispatcher


def load_fixture(path: Path) -> list[LandmarkFrame]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        LandmarkFrame(
            int(item["timestamp_ms"]),
            tuple(float(value) for value in item["landmarks"]),
            str(item.get("handedness", "Right")),
            float(item.get("handedness_confidence", 1.0)),
            int(item.get("width", 640)),
            int(item.get("height", 480)),
        )
        for item in raw
    ]


def action_json(action: Any) -> dict[str, object]:
    return {
        "type": action.type.value,
        "x": action.x,
        "y": action.y,
        "dx": action.dx,
        "dy": action.dy,
        "button": action.button.value if action.button else None,
        "state": action.state.value if action.state else None,
    }


def run_replay(path: Path, engine_name: str = "python") -> dict[str, object]:
    backend = FakeMouseBackend()
    dispatcher = InputDispatcher(backend)
    config = EngineConfig(screen_width=1920, screen_height=1080, mirror=True, reacquisition_ms=0)
    engine = create_engine(engine_name, config, armed=True)
    actions: list[dict[str, object]] = []
    for frame in load_fixture(path):
        batch = engine.process(frame)
        for action in batch.actions:
            actions.append(action_json(action))
        dispatcher.dispatch(batch)
    release = engine.reset("replay end")
    for action in release.actions:
        actions.append(action_json(action))
    dispatcher.dispatch(release)
    dispatcher.release_all()
    return {
        "engine": getattr(engine, "name", engine_name),
        "frames": len(load_fixture(path)),
        "actions": actions,
        "held_buttons": [button.value for button in backend.held],
    }
