from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

from .models import EngineConfig
from .mojo_engine import MojoGestureEngine
from .protocol import GestureEngine
from .python_engine import PythonGestureEngine

LOGGER = logging.getLogger(__name__)


class EngineUnavailableError(RuntimeError):
    pass


def _load_mojo(config: EngineConfig, armed: bool) -> GestureEngine:
    if sys.platform == "win32":
        raise EngineUnavailableError(
            "native Mojo engine is unavailable on Windows; use --engine python"
        )
    source_dir = Path(__file__).resolve().parents[3] / "mojo"
    try:
        importlib.import_module("mojo.importer")
        if str(source_dir) not in sys.path:
            sys.path.insert(0, str(source_dir))
        module = importlib.import_module("mgesture_core")
        return MojoGestureEngine(module, config, armed)
    except Exception as exc:
        raise EngineUnavailableError(
            "Mojo engine unavailable: import/build failed. Run `pixi run mojo-build` and inspect the compiler error. "
            f"Root error: {exc}"
        ) from exc


def create_engine(requested: str, config: EngineConfig, armed: bool = False) -> GestureEngine:
    selected = os.environ.get("MGESTURE_ENGINE", requested).lower()
    if selected not in ("auto", "mojo", "python"):
        raise EngineUnavailableError("MGESTURE_ENGINE/--engine must be auto, mojo, or python")
    if selected == "python":
        return PythonGestureEngine(config, armed=armed)
    try:
        engine = _load_mojo(config, armed)
        LOGGER.info("gesture engine: mojo")
        return engine
    except EngineUnavailableError:
        if selected == "mojo":
            raise
        LOGGER.info("Mojo unavailable; using Python reference engine")
        return PythonGestureEngine(config, armed=armed)
