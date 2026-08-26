from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path

from .models import EngineConfig
from .mojo_engine import MojoGestureEngine, NativeMojoGestureEngine, native_library_name
from .protocol import GestureEngine
from .python_engine import PythonGestureEngine

LOGGER = logging.getLogger(__name__)


class EngineUnavailableError(RuntimeError):
    pass


def _load_mojo(config: EngineConfig, armed: bool) -> GestureEngine:
    standalone = _standalone_root()
    library = _native_library_path(standalone)
    if library is not None:
        try:
            return NativeMojoGestureEngine(library, config, armed, _target_name(standalone))
        except Exception as exc:
            raise EngineUnavailableError(
                f"native Mojo engine unavailable: {library.name} failed ABI/load validation: {exc}"
            ) from exc
    if standalone is not None:
        raise EngineUnavailableError(f"standalone bundle is missing {native_library_name()}")
    if sys.platform == "win32":
        raise EngineUnavailableError(
            "native Mojo engine is unavailable on Windows; use --engine python"
        )
    source_dir = Path(__file__).resolve().parents[3] / "mojo"
    try:
        importlib.import_module("mojo.importer")
        if str(source_dir) not in sys.path:
            sys.path.insert(0, str(source_dir))
        module = importlib.import_module("mgesture_python")
        return MojoGestureEngine(module, config, armed)
    except Exception as exc:
        raise EngineUnavailableError(
            "Mojo engine unavailable: import/build failed. Run `pixi run mojo-build` and inspect the compiler error. "
            f"Root error: {exc}"
        ) from exc


def _standalone_root() -> Path | None:
    configured = os.environ.get("MGESTURE_BUNDLE_ROOT")
    if configured:
        return Path(configured)
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).parent
    executable_root = Path(sys.executable).resolve().parent.parent
    if (executable_root / "share" / "mgesture" / "release-metadata.json").exists():
        return executable_root
    return None


def _target_name(root: Path | None) -> str:
    if root is not None:
        metadata = root / "share" / "mgesture" / "release-metadata.json"
        if metadata.exists():
            import json

            value = json.loads(metadata.read_text(encoding="utf-8"))
            target = value.get("target") if isinstance(value, dict) else None
            if isinstance(target, str):
                return target
    return ""


def _native_library_path(root: Path | None) -> Path | None:
    configured = os.environ.get("MGESTURE_MOJO_LIBRARY")
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        raise EngineUnavailableError(f"MGESTURE_MOJO_LIBRARY does not exist: {path}")
    candidates: list[Path] = []
    if root is not None:
        candidates.append(root / "runtime" / "mojo" / native_library_name())
    repository_root = Path(__file__).resolve().parents[3]
    candidates.append(repository_root / "build" / native_library_name())
    return next((path for path in candidates if path.is_file()), None)


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
