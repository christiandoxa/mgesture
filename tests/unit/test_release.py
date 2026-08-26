from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from mgesture.release import mojo_source_metadata, normalize_architecture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import STABLE_TARGETS, ci_matrix, publishable_targets  # noqa: E402


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "x86_64-unknown-linux-gnu"),
        ("Linux", "aarch64", "aarch64-unknown-linux-gnu"),
        ("Darwin", "x86_64", "x86_64-apple-darwin"),
        ("Darwin", "arm64", "aarch64-apple-darwin"),
    ],
)
def test_current_target_aliases(
    monkeypatch: pytest.MonkeyPatch, system: str, machine: str, expected: str
) -> None:
    import mgesture.release as release

    monkeypatch.setattr(release.platform, "system", lambda: system)
    monkeypatch.setattr(release.platform, "machine", lambda: machine)
    assert release.current_target() == expected


@pytest.mark.parametrize("alias", ("x86_64", "amd64", "x64", "AMD64"))
def test_x86_architecture_aliases(alias: str) -> None:
    assert normalize_architecture(alias) == "x86_64"


@pytest.mark.parametrize("alias", ("aarch64", "arm64", "ARM64"))
def test_arm_architecture_aliases(alias: str) -> None:
    assert normalize_architecture(alias) == "aarch64"


def test_stable_targets_expose_all_source_capabilities() -> None:
    targets = publishable_targets()
    assert len(targets) == 6
    assert all(
        target.standalone and target.vision and target.mojo_source and target.python_engine
        for target in targets.values()
    )
    source = mojo_source_metadata()
    assert source["available"] is True
    assert "mgesture_core.mojo" in source["files"]
    assert len(str(source["sha256"])) == 64
    assert all(isinstance(target.native_mojo_engine, bool) for target in targets.values())


def test_mojo_source_hash_is_line_ending_independent(tmp_path: Path) -> None:
    from mgesture.release import mojo_source_metadata

    source_dir = tmp_path / "mojo"
    source_dir.mkdir()
    (source_dir / "mgesture_core.mojo").write_bytes(b"one\ntwo\n")
    (source_dir / "mgesture_python.mojo").write_bytes(b"three\nfour\n")
    unix_hash = mojo_source_metadata(source_dir)["sha256"]
    (source_dir / "mgesture_core.mojo").write_bytes(b"one\r\ntwo\r\n")
    (source_dir / "mgesture_python.mojo").write_bytes(b"three\r\nfour\r\n")
    assert mojo_source_metadata(source_dir)["sha256"] == unix_hash


def test_ci_matrix_uses_all_stable_targets_and_native_runners() -> None:
    rows = ci_matrix()
    assert len(rows) == 6
    assert {row["target"] for row in rows} == STABLE_TARGETS
    assert {row["mojo_ci_mode"] for row in rows} == {"native"}
    assert {row["mojo_build_mode"] for row in rows} == {"native", "cross-object"}
    targets = publishable_targets()
    assert {row["target"] for row in rows} == set(targets)
    assert all(row["runner"] == targets[row["target"]].runner for row in rows)
    assert all(row["asset"] == targets[row["target"]].asset for row in rows)


def test_readme_capability_table_matches_target_matrix() -> None:
    labels = {
        ("linux", "x86_64"): ("Linux", "x86_64"),
        ("linux", "aarch64"): ("Linux", "ARM64"),
        ("macos", "x86_64"): ("macOS", "Intel x86_64"),
        ("macos", "aarch64"): ("macOS", "Apple Silicon ARM64"),
        ("windows", "x86_64"): ("Windows", "x86_64"),
        ("windows", "aarch64"): ("Windows", "ARM64"),
    }
    rows: dict[tuple[str, str], list[str]] = {}
    in_table = False
    for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines():
        if line.startswith(
            "| Platform | Architecture | Standalone | Vision | Mojo source | Python engine |"
        ):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("|"):
            fields = [field.strip() for field in line.strip("|").split("|")]
            key = next(
                (key for key, value in labels.items() if value == (fields[0], fields[1])),
                None,
            )
            assert key is not None
            rows[key] = fields
            continue
        if in_table:
            break
    targets = publishable_targets()
    assert len(rows) == len(targets) == 6
    for name, target in targets.items():
        key = (target.os, target.architecture)
        fields = rows[key]
        assert fields[2] == ("Yes" if target.standalone else "No"), name
        assert fields[3].startswith("Yes (" if target.vision else "No"), name
        assert fields[4] == ("Yes" if target.mojo_source else "No"), name
        assert fields[5] == ("Yes" if target.python_engine else "No"), name


def _release_fixture(path: Path) -> None:
    bundle = path / "bundle" / "mgesture" / "bin"
    bundle.mkdir(parents=True)
    binary = bundle / "mgesture"
    binary.write_text(
        "#!/bin/sh\ncase \"$1\" in --version) echo 'mgesture 0.1.0';; *) exit 0;; esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    runtime = path / "bundle" / "mgesture" / "runtime" / "mojo"
    runtime.mkdir(parents=True)
    for name in ("libmgesture_mojo.so", "libmgesture_mojo.dylib", "mgesture_mojo.dll"):
        (runtime / name).write_bytes(b"native Mojo fixture")
    for release_target in publishable_targets().values():
        archive_path = path / release_target.asset
        if release_target.format == "tar.gz":
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(path / "bundle" / "mgesture", arcname="mgesture")
        else:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in (path / "bundle" / "mgesture").rglob("*"):
                    if file.is_file():
                        archive.write(
                            file, Path("mgesture") / file.relative_to(path / "bundle" / "mgesture")
                        )
    (path / "install.sh").write_bytes((ROOT / "install.sh").read_bytes())
    (path / "install.ps1").write_bytes((ROOT / "install.ps1").read_bytes())
    subprocess.run(
        [
            sys.executable,
            "scripts/release/render_manifest.py",
            "--version",
            "0.1.0",
            "--commit",
            "0" * 40,
            "--assets",
            str(path),
            "--output",
            str(path),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/release/sbom.py",
            "--version",
            "0.1.0",
            "--assets",
            str(path),
            "--output",
            str(path / "mgesture-sbom.spdx.json"),
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [sys.executable, "scripts/release/generate_checksums.py", str(path)], cwd=ROOT, check=True
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/release/verify_release.py",
            str(path),
            "--version",
            "0.1.0",
        ],
        cwd=ROOT,
        check=True,
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="the Unix installer is not available on Windows"
)
def test_unix_installer_stages_and_activates_without_python_runtime(tmp_path: Path):
    fixture = tmp_path / "release"
    fixture.mkdir()
    _release_fixture(fixture)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uname = fake_bin / "uname"
    uname.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        "  -s) printf '%s\\n' \"$MGESTURE_TEST_OS\";;\n"
        "  -m) printf '%s\\n' \"$MGESTURE_TEST_ARCH\";;\n"
        "esac\n",
        encoding="utf-8",
    )
    uname.chmod(0o755)
    for index, (os_name, architecture, target) in enumerate(
        (
            ("Linux", "x86_64", "x86_64-unknown-linux-gnu"),
            ("Linux", "aarch64", "aarch64-unknown-linux-gnu"),
            ("Darwin", "x86_64", "x86_64-apple-darwin"),
            ("Darwin", "arm64", "aarch64-apple-darwin"),
        )
    ):
        home = tmp_path / f"home-{index}"
        env = {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "HOME": str(home),
            "SHELL": "/bin/sh",
            "MGESTURE_TEST_OS": os_name,
            "MGESTURE_TEST_ARCH": architecture,
            "MGESTURE_RELEASE_BASE_URL": str(fixture),
            "MGESTURE_INSTALL_DIR": str(home / "app"),
            "MGESTURE_BIN_DIR": str(home / "bin"),
            "MGESTURE_NO_PATH_UPDATE": "true",
        }
        result = subprocess.run(
            ["sh", str(ROOT / "install.sh")], cwd=ROOT, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, f"{target}: {result.stderr}"
        command = home / "bin" / "mgesture"
        assert (
            subprocess.run(
                [str(command), "--version"], env=env, capture_output=True, text=True, check=True
            ).stdout.strip()
            == "mgesture 0.1.0"
        )
        assert (home / "app" / "current").is_symlink()
    home = tmp_path / "failed-home"
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "HOME": str(home),
        "SHELL": "/bin/sh",
        "MGESTURE_TEST_OS": "Linux",
        "MGESTURE_TEST_ARCH": "x86_64",
        "MGESTURE_RELEASE_BASE_URL": str(fixture),
        "MGESTURE_INSTALL_DIR": str(home / "app"),
        "MGESTURE_BIN_DIR": str(home / "bin"),
        "MGESTURE_NO_PATH_UPDATE": "true",
    }
    (fixture / "mgesture-x86_64-unknown-linux-gnu.tar.gz").write_bytes(b"corrupted")
    failed = subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert not (home / "app" / "current").exists()
