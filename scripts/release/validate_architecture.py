from __future__ import annotations

import argparse
import ctypes
import os
import platform
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402

_ARCH_ALIASES = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "x64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}
_ELF_MACHINES = {62: "x86_64", 183: "aarch64"}
_PE_MACHINES = {0x8664: "x86_64", 0xAA64: "aarch64"}
_MACH_CPU_TYPES = {0x01000007: "x86_64", 0x0100000C: "aarch64"}
_MACHO_THIN = {
    b"\xfe\xed\xfa\xce": ">",
    b"\xce\xfa\xed\xfe": "<",
    b"\xfe\xed\xfa\xcf": ">",
    b"\xcf\xfa\xed\xfe": "<",
}
_MACHO_FAT = {
    b"\xca\xfe\xba\xbe": (">", 20),
    b"\xbe\xba\xfe\xca": ("<", 20),
    b"\xca\xfe\xba\xbf": (">", 32),
    b"\xbf\xba\xfe\xca": ("<", 32),
}


def normalize_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    try:
        return _ARCH_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported architecture: {value}") from exc


def native_windows_architecture() -> str:
    # GetNativeSystemInfo reports the OS architecture even when PowerShell/Python is x64-emulated.
    buffer = ctypes.create_string_buffer(64)
    ctypes.windll.kernel32.GetNativeSystemInfo(buffer)  # type: ignore[attr-defined]
    values = {9: "x86_64", 12: "aarch64"}
    try:
        return values[int.from_bytes(buffer.raw[:2], "little")]
    except KeyError as exc:
        raise ValueError("unsupported native Windows architecture") from exc


def runner_architecture() -> tuple[str, str]:
    if os.name == "nt":
        return "windows", native_windows_architecture()
    system = platform.system()
    systems = {"Linux": "linux", "Darwin": "macos"}
    try:
        normalized_system = systems[system]
    except KeyError as exc:
        raise ValueError(f"unsupported operating system: {system}") from exc
    return normalized_system, normalize_architecture(os.uname().machine)


def validate_runner(target_name: str) -> None:
    release_target = target(target_name)
    actual_os, actual_architecture = runner_architecture()
    if (actual_os, actual_architecture) != (
        release_target.os,
        release_target.architecture,
    ):
        raise ValueError(
            f"native runner mismatch for {target_name}: "
            f"expected {release_target.os}/{release_target.architecture}, "
            f"got {actual_os}/{actual_architecture}"
        )
    print(f"native runner: {actual_os}/{actual_architecture}")


def _read_header(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(1024 * 1024)


def _macho_architectures(data: bytes) -> set[str]:
    magic = data[:4]
    if magic in _MACHO_THIN:
        endian = _MACHO_THIN[magic]
        if len(data) < 8:
            raise ValueError("truncated Mach-O header")
        cpu_type = struct.unpack_from(f"{endian}I", data, 4)[0]
        try:
            return {_MACH_CPU_TYPES[cpu_type]}
        except KeyError as exc:
            raise ValueError(f"unsupported Mach-O CPU type 0x{cpu_type:x}") from exc
    if magic not in _MACHO_FAT:
        raise ValueError("unrecognized Mach-O header")
    endian, entry_size = _MACHO_FAT[magic]
    if len(data) < 8:
        raise ValueError("truncated fat Mach-O header")
    count = struct.unpack_from(f"{endian}I", data, 4)[0]
    architectures: set[str] = set()
    for index in range(count):
        offset = 8 + index * entry_size
        if len(data) < offset + 4:
            raise ValueError("truncated fat Mach-O architecture table")
        cpu_type = struct.unpack_from(f"{endian}I", data, offset)[0]
        if cpu_type in _MACH_CPU_TYPES:
            architectures.add(_MACH_CPU_TYPES[cpu_type])
    if not architectures:
        raise ValueError("fat Mach-O contains no supported 64-bit architecture")
    return architectures


def binary_architectures(path: Path) -> set[str] | None:
    data = _read_header(path)
    if len(data) >= 2:
        machine = struct.unpack_from("<H", data, 0)[0]
        if machine in _PE_MACHINES:
            return {_PE_MACHINES[machine]}
    if data.startswith(b"\x7fELF"):
        if len(data) < 20 or data[4] != 2:
            raise ValueError("ELF binary is not 64-bit")
        endian = "<" if data[5] == 1 else ">" if data[5] == 2 else ""
        if not endian:
            raise ValueError("ELF binary has invalid byte order")
        machine = struct.unpack_from(f"{endian}H", data, 18)[0]
        try:
            return {_ELF_MACHINES[machine]}
        except KeyError as exc:
            raise ValueError(f"unsupported ELF machine {machine}") from exc
    if data.startswith(b"MZ"):
        if len(data) < 64:
            raise ValueError("truncated PE DOS header")
        pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
        if len(data) < pe_offset + 6 or data[pe_offset : pe_offset + 4] != b"PE\0\0":
            raise ValueError("invalid PE header")
        machine = struct.unpack_from("<H", data, pe_offset + 4)[0]
        try:
            return {_PE_MACHINES[machine]}
        except KeyError as exc:
            raise ValueError(f"unsupported PE machine 0x{machine:x}") from exc
    if data[:4] in _MACHO_THIN or data[:4] in _MACHO_FAT:
        return _macho_architectures(data)
    return None


def _native_candidate(path: Path, target_os: str) -> bool:
    name = path.name.lower()
    if target_os == "windows":
        return name.endswith((".exe", ".dll", ".pyd"))
    if target_os == "macos":
        return name.endswith((".dylib", ".so", ".bundle"))
    return ".so" in name


def validate_bundle(target_name: str, root: Path) -> None:
    release_target = target(target_name)
    binary = root / "bin" / ("mgesture.exe" if release_target.os == "windows" else "mgesture")
    if not binary.is_file():
        raise ValueError(f"bundle is missing {binary.relative_to(root)}")
    candidates = [binary]
    candidates.extend(
        path
        for path in root.rglob("*")
        if path.is_file() and path != binary and _native_candidate(path, release_target.os)
    )
    checked = 0
    for path in candidates:
        architectures = binary_architectures(path)
        if architectures is None:
            if path == binary or _native_candidate(path, release_target.os):
                raise ValueError(f"native candidate has an unknown binary format: {path}")
            continue
        checked += 1
        if release_target.architecture not in architectures:
            actual = ",".join(sorted(architectures))
            raise ValueError(
                f"architecture mismatch in {path.relative_to(root)}: "
                f"expected {release_target.architecture}, got {actual}"
            )
    print(f"validated {checked} native binaries for {target_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    runner = subparsers.add_parser("runner")
    runner.add_argument("--target", required=True)
    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--target", required=True)
    bundle.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "runner":
        validate_runner(args.target)
    else:
        validate_bundle(args.target, args.root)


if __name__ == "__main__":
    main()
