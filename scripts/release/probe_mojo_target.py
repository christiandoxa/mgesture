from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from build_mojo_library import (  # noqa: E402
    _TARGET_CPUS,
    MOJO_EXPORTS,
    build_object,
    find_windows_tool,
    link_library,
)
from release_targets import publishable_targets, target  # noqa: E402
from validate_architecture import binary_architectures  # noqa: E402
from validate_mojo_abi import _symbols  # noqa: E402
from validate_mojo_abi import validate as validate_mojo_abi  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.engine.models import EngineConfig, LandmarkFrame  # noqa: E402
from mgesture.engine.mojo_engine import NativeMojoGestureEngine  # noqa: E402
from mgesture.engine.synthetic import synthetic_landmarks  # noqa: E402
from mgesture.release import current_target, mojo_source_metadata  # noqa: E402


def _run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout or result.stderr).strip()


def _compiler_probe(mojo: str | None, target_name: str) -> dict[str, object]:
    if mojo is None:
        return {"available": False, "target_triple_recognized": False}
    cpu = _TARGET_CPUS[target_name]
    supported_code, supported = _run(
        [
            mojo,
            "build",
            f"--target-triple={target_name}",
            "--print-supported-cpus",
        ]
    )
    effective_code, effective = _run(
        [
            mojo,
            "build",
            f"--target-triple={target_name}",
            f"--target-cpu={cpu}",
            "--print-effective-target",
        ]
    )
    return {
        "available": True,
        "target_triple_recognized": supported_code == 0 and effective_code == 0,
        "cpu": cpu,
        "supported_cpus": supported,
        "effective_target": effective,
    }


def _linker(target_name: str) -> str | None:
    release_target = target(target_name)
    try:
        if current_target() != target_name:
            return None
    except RuntimeError:
        return None
    if release_target.os == "windows":
        return find_windows_tool("link.exe", release_target.architecture) or find_windows_tool(
            "lld-link.exe", release_target.architecture
        )
    if release_target.os == "macos":
        return shutil.which("cc") or shutil.which("clang")
    return shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")


def _dependencies(target_name: str, library: Path) -> dict[str, object]:
    release_target = target(target_name)
    if release_target.os == "linux":
        command = shutil.which("readelf")
        arguments = [command, "-d", str(library)] if command else None
    elif release_target.os == "macos":
        command = shutil.which("otool")
        arguments = [command, "-L", str(library)] if command else None
    else:
        command = find_windows_tool("dumpbin.exe", release_target.architecture)
        arguments = [command, "/DEPENDENTS", str(library)] if command else None
    if arguments is None:
        return {"available": False, "dependencies": []}
    code, output = _run(arguments)
    if release_target.os == "linux":
        dependencies = [
            line.split("[", 1)[1].split("]", 1)[0]
            for line in output.splitlines()
            if "(NEEDED)" in line and "[" in line and "]" in line
        ]
    else:
        dependencies = [line.strip() for line in output.splitlines() if line.strip()]
    return {"available": code == 0, "dependencies": dependencies, "output": output}


def _native_execution(target_name: str, library: Path) -> dict[str, object]:
    try:
        if current_target() != target_name:
            return {"runner_matches_target": False, "executed": False}
    except RuntimeError as exc:
        return {"runner_matches_target": False, "executed": False, "error": str(exc)}
    engine = None
    try:
        validate_mojo_abi(target_name, library)
        engine = NativeMojoGestureEngine(
            library,
            EngineConfig(reacquisition_ms=0, activation_gesture=False),
            armed=True,
            target=target_name,
        )
        batch = engine.process(LandmarkFrame(0, synthetic_landmarks(), "Right", 0.99))
        if batch.diagnostics.get("native") is not True:
            raise RuntimeError("native diagnostic marker is missing")
        engine.reset("target probe")
        return {"runner_matches_target": True, "executed": True, "fixture_processed": True}
    except Exception as exc:
        return {"runner_matches_target": True, "executed": False, "error": str(exc)}
    finally:
        if engine is not None:
            engine.close()


def probe(
    target_name: str, object_path: Path | None, library_path: Path | None, work: Path
) -> dict[str, object]:
    release_target = target(target_name)
    mojo = shutil.which("mojo")
    linker = _linker(target_name)
    row: dict[str, object] = {
        "target": target_name,
        "host": f"{platform.system()}-{platform.machine()}",
        "compiler": _compiler_probe(mojo, target_name),
        "object": {"available": False},
        "linker": {"available": linker is not None, "path": Path(linker).name if linker else None},
        "library": {"available": False},
        "native": {"runner_matches_target": False, "executed": False},
    }
    if object_path is None:
        object_path = work / f"{target_name}.o"
        try:
            build_object(target_name, object_path)
        except Exception as exc:
            row["object"] = {"available": False, "generated": False, "error": str(exc)}
            return row
        generated = True
    else:
        generated = False
    object_architecture = binary_architectures(object_path)
    row["object"] = {
        "available": True,
        "generated": generated,
        "architecture": sorted(object_architecture or ()),
        "file": object_path.name,
    }

    if library_path is None and row["linker"]["available"] is True:
        link_dir = work / f"link-{target_name}"
        link_dir.mkdir()
        link_object = link_dir / object_path.name
        shutil.copy2(object_path, link_object)
        if release_target.mojo_build_mode == "cross-object":
            metadata = {
                "compiler_version": "probe",
                "source_sha256": mojo_source_metadata(ROOT / "mojo")["sha256"],
                "targets": [target_name],
            }
            (link_dir / "mojo-build-metadata.json").write_text(
                json.dumps(metadata) + "\n", encoding="utf-8"
            )
        library_path = (
            work
            / f"{target_name}.{Path('dll' if release_target.os == 'windows' else 'dylib' if release_target.os == 'macos' else 'so')}"
        )
        try:
            link_library(target_name, link_object, library_path)
        except Exception as exc:
            row["library"] = {"available": False, "linked": False, "error": str(exc)}
            return row
        linked = True
    else:
        linked = False

    if library_path is None or not library_path.is_file():
        row["library"] = {
            "available": False,
            "linked": linked,
            "reason": "target linker unavailable on this runner",
        }
        return row
    architectures = binary_architectures(library_path)
    library_row: dict[str, object] = {
        "available": True,
        "linked": linked,
        "architecture": sorted(architectures or ()),
        "file": library_path.name,
        "dependencies": _dependencies(target_name, library_path),
    }
    try:
        symbols = _symbols(library_path, release_target.os)
        missing = [symbol for symbol in MOJO_EXPORTS if symbol not in symbols]
        library_row["exports"] = [symbol for symbol in MOJO_EXPORTS if symbol not in missing]
        library_row["missing_exports"] = missing
    except Exception as exc:
        library_row["exports_error"] = str(exc)
    row["library"] = library_row
    row["native"] = _native_execution(target_name, library_path)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Mojo target compilation and native ABI readiness"
    )
    parser.add_argument("--target", action="append", dest="targets")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--object", type=Path)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.object or args.library:
        if not args.targets or len(args.targets) != 1 or args.all:
            parser.error("--object/--library require exactly one --target")
    targets = args.targets or (list(publishable_targets()) if args.all else [])
    if not targets:
        parser.error("provide --target or --all")
    source = mojo_source_metadata(ROOT / "mojo")
    with tempfile.TemporaryDirectory(prefix="mgesture-mojo-probe-") as temporary:
        work = Path(temporary)
        report: dict[str, Any] = {
            "schema_version": 1,
            "compiler_version": "not-available",
            "source_sha256": source["sha256"],
            "targets": {},
        }
        mojo = shutil.which("mojo")
        if mojo is not None:
            code, version = _run([mojo, "--version"])
            if code == 0:
                report["compiler_version"] = version
        for target_name in targets:
            report["targets"][target_name] = probe(
                target_name,
                args.object,
                args.library,
                work,
            )
        payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
