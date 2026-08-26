from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from validate_architecture import binary_architectures, normalize_architecture  # noqa: E402


@pytest.mark.parametrize(
    ("alias", "expected"),
    [("x86_64", "x86_64"), ("AMD64", "x86_64"), ("x64", "x86_64"), ("arm64", "aarch64")],
)
def test_normalize_architecture(alias: str, expected: str) -> None:
    assert normalize_architecture(alias) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\x7fELF" + bytes([2, 1]) + bytes(12) + struct.pack("<H", 62), {"x86_64"}),
        (b"\x7fELF" + bytes([2, 1]) + bytes(12) + struct.pack("<H", 183), {"aarch64"}),
        (
            b"MZ" + bytes(58) + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x8664),
            {"x86_64"},
        ),
        (
            b"MZ" + bytes(58) + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0xAA64),
            {"aarch64"},
        ),
        (
            b"MZ" + bytes(58) + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x014C),
            {"i386"},
        ),
        (b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x01000007), {"x86_64"}),
        (b"\xcf\xfa\xed\xfe" + struct.pack("<I", 0x0100000C), {"aarch64"}),
    ],
)
def test_binary_architectures(tmp_path: Path, header: bytes, expected: set[str]) -> None:
    path = tmp_path / "binary"
    path.write_bytes(header)
    assert binary_architectures(path) == expected
