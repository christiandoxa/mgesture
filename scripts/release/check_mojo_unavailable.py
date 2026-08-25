from __future__ import annotations

from mgesture.engine import EngineConfig, EngineUnavailableError, create_engine

try:
    create_engine("mojo", EngineConfig(), armed=False)
except EngineUnavailableError as exc:
    print(f"explicit Mojo unavailability: {exc}")
else:
    raise SystemExit("native Windows unexpectedly loaded Mojo")
