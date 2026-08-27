from __future__ import annotations

import argparse
import ctypes
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))
sys.path.insert(0, str(ROOT / "src"))

from build_mojo_library import MOJO_EXPORTS, find_windows_tool  # noqa: E402
from release_targets import target  # noqa: E402
from validate_architecture import binary_architectures  # noqa: E402

from mgesture.engine.mojo_engine import MOJO_ABI_VERSION  # noqa: E402


def _symbols(path: Path, system: str) -> str:
    if system == "windows":
        command = find_windows_tool("dumpbin.exe") or shutil.which("llvm-nm.exe")
        if command is None:
            raise RuntimeError("dumpbin.exe or llvm-nm.exe is required for Windows ABI validation")
        arguments = (
            [command, "/exports", str(path)]
            if Path(command).name.lower() == "dumpbin.exe"
            else [command, "--defined-only", str(path)]
        )
    elif system == "macos":
        command = shutil.which("nm")
        if command is None:
            raise RuntimeError("nm is required for macOS ABI validation")
        arguments = [command, "-gU", str(path)]
    else:
        command = shutil.which("nm")
        if command is None:
            raise RuntimeError("nm is required for Linux ABI validation")
        arguments = [command, "-D", "--defined-only", str(path)]
    result = subprocess.run(arguments, capture_output=True, text=True, check=True)
    return result.stdout + result.stderr


def validate(target_name: str, library: Path) -> None:
    release_target = target(target_name)
    architectures = binary_architectures(library)
    if architectures != {release_target.architecture}:
        raise ValueError(
            f"native Mojo library architecture mismatch: expected "
            f"{release_target.architecture}, got {architectures}"
        )
    system = release_target.os
    symbols = _symbols(library, system)
    missing = [symbol for symbol in MOJO_EXPORTS if symbol not in symbols]
    if missing:
        raise ValueError(f"native Mojo library is missing exports: {', '.join(missing)}")
    loaded = ctypes.CDLL(str(library))
    version = loaded.mgesture_mojo_abi_version
    version.restype = ctypes.c_int32
    if version() != MOJO_ABI_VERSION:
        raise ValueError("native Mojo ABI version mismatch")
    print(
        f"validated native Mojo ABI for {target_name}: "
        f"{platform.system()} {release_target.architecture}, {len(MOJO_EXPORTS)} exports"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--library", type=Path, required=True)
    args = parser.parse_args()
    validate(args.target, args.library)


if __name__ == "__main__":
    main()
