from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402
from validate_architecture import binary_architectures  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.mojo_engine import native_library_name  # noqa: E402
from mgesture.release import current_target, mojo_source_metadata  # noqa: E402

_TARGET_CPUS = {
    "x86_64-unknown-linux-gnu": "x86-64",
    "aarch64-unknown-linux-gnu": "generic",
    "x86_64-apple-darwin": "x86-64",
    "aarch64-apple-darwin": "generic",
    "x86_64-pc-windows-msvc": "x86-64",
    "aarch64-pc-windows-msvc": "generic",
}
MOJO_EXPORTS = (
    "mgesture_mojo_abi_version",
    "mgesture_mojo_config_size",
    "mgesture_mojo_config_alignment",
    "mgesture_mojo_action_size",
    "mgesture_mojo_action_alignment",
    "mgesture_mojo_engine_size",
    "mgesture_mojo_engine_alignment",
    "mgesture_mojo_engine_init",
    "mgesture_mojo_engine_reset",
    "mgesture_mojo_engine_set_armed",
    "mgesture_mojo_engine_process",
    "mgesture_mojo_engine_destroy",
)


def find_windows_tool(name: str) -> str | None:
    command = shutil.which(name)
    if command is not None:
        return command
    vswhere = shutil.which("vswhere.exe")
    if vswhere is None:
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            candidate = (
                Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
            if candidate.is_file():
                vswhere = str(candidate)
    if vswhere is None:
        return None
    result = subprocess.run(
        [vswhere, "-latest", "-products", "*", "-find", f"**\\{name}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)


def build_object(target_name: str, output: Path) -> Path:
    if target_name not in _TARGET_CPUS:
        raise ValueError(f"no Mojo target CPU is defined for {target_name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    mojo = shutil.which("mojo")
    if mojo is None:
        raise RuntimeError("Mojo compiler is required to emit the native engine object")
    subprocess.run(
        [
            mojo,
            "build",
            f"--target-triple={target_name}",
            f"--target-cpu={_TARGET_CPUS[target_name]}",
            "--emit",
            "object",
            "-o",
            str(output),
            str(ROOT / "mojo" / "mgesture_core.mojo"),
        ],
        cwd=ROOT,
        check=True,
    )
    architectures = binary_architectures(output)
    expected = target(target_name).architecture
    if architectures != {expected}:
        raise RuntimeError(
            f"Mojo object architecture mismatch for {target_name}: "
            f"expected {expected}, got {architectures}"
        )
    return output


def link_library(target_name: str, object_path: Path, output: Path) -> Path:
    release_target = target(target_name)
    if not object_path.is_file():
        raise FileNotFoundError(object_path)
    architectures = binary_architectures(object_path)
    if architectures != {release_target.architecture}:
        raise RuntimeError(
            f"Mojo object architecture mismatch for {target_name}: "
            f"expected {release_target.architecture}, got {architectures}"
        )
    if release_target.mojo_build_mode == "cross-object":
        provenance = object_path.parent / "mojo-build-metadata.json"
        if not provenance.is_file():
            raise RuntimeError(f"cross-target Mojo object provenance is missing: {provenance}")
        metadata = json.loads(provenance.read_text(encoding="utf-8"))
        if (
            not isinstance(metadata, dict)
            or metadata.get("source_sha256") != mojo_source_metadata()["sha256"]
            or target_name not in metadata.get("targets", [])
        ):
            raise RuntimeError(f"cross-target Mojo object provenance is invalid: {provenance}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shim_directory: tempfile.TemporaryDirectory[str] | None = None
    if release_target.os == "linux":
        linker = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if linker is None:
            raise RuntimeError("a C compiler is required to link the Linux Mojo library")
        command = [
            linker,
            "-shared",
            "-Wl,--no-undefined",
            "-o",
            str(output),
            str(object_path),
            "-lm",
        ]
    elif release_target.os == "macos":
        linker = shutil.which("cc") or shutil.which("clang")
        if linker is None:
            raise RuntimeError("Apple Clang is required to link the macOS Mojo library")
        command = [
            linker,
            "-dynamiclib",
            "-Wl,-undefined,error",
            "-o",
            str(output),
            str(object_path),
        ]
    else:
        linker = find_windows_tool("link.exe") or find_windows_tool("lld-link.exe")
        if linker is None:
            raise RuntimeError(
                "MSVC link.exe or lld-link.exe is required to link the Windows Mojo library"
            )
        machine = "ARM64" if release_target.architecture == "aarch64" else "X64"
        compiler = find_windows_tool("cl.exe") or find_windows_tool("clang-cl.exe")
        shim_directory = tempfile.TemporaryDirectory(prefix="mgesture-mojo-win-")
        shim_object: Path | None = None
        if compiler:
            shim_source = Path(shim_directory.name) / "fltused.c"
            shim_object = Path(shim_directory.name) / "fltused.obj"
            shim_source.write_text("int _fltused = 0;\n", encoding="ascii")
            subprocess.run(
                [compiler, "/nologo", "/c", "/GS-", "/Zl", f"/Fo{shim_object}", str(shim_source)],
                cwd=ROOT,
                check=True,
            )
        command = [
            linker,
            "/DLL",
            "/NOENTRY",
            "/NODEFAULTLIB",
            f"/MACHINE:{machine}",
            f"/OUT:{output}",
            *[f"/EXPORT:{symbol}" for symbol in MOJO_EXPORTS],
            str(object_path),
            *([str(shim_object)] if shim_object else []),
        ]
    environment = os.environ.copy()
    if release_target.os == "macos":
        environment.setdefault("MACOSX_DEPLOYMENT_TARGET", "13.0")
    try:
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
    finally:
        if shim_directory is not None:
            shim_directory.cleanup()
    return output


def build(target_name: str, output: Path, object_path: Path | None = None) -> Path:
    release_target = target(target_name)
    if object_path is None:
        object_path = output.with_suffix(".o")
        build_object(target_name, object_path)
    library = link_library(target_name, object_path, output)
    if library.name != native_library_name(release_target.os):
        raise RuntimeError(
            f"native Mojo library must be named {native_library_name(release_target.os)}"
        )
    return library


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--object", type=Path)
    parser.add_argument("--emit-object", type=Path)
    args = parser.parse_args()
    if args.emit_object and (args.output or args.object):
        parser.error("--emit-object cannot be combined with --output or --object")
    if args.emit_object:
        print(build_object(args.target or current_target(), args.emit_object))
        return
    target_name = args.target or current_target()
    output = args.output or Path("build") / native_library_name(target(target_name).os)
    print(build(target_name, output, args.object))


if __name__ == "__main__":
    main()
