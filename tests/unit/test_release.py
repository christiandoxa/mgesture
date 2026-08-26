from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from mgesture.release import normalize_architecture

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import publishable_targets  # noqa: E402


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


def _release_fixture(path: Path) -> None:
    bundle = path / "bundle" / "mgesture" / "bin"
    bundle.mkdir(parents=True)
    binary = bundle / "mgesture"
    binary.write_text(
        "#!/bin/sh\ncase \"$1\" in --version) echo 'mgesture 0.1.0';; *) exit 0;; esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    for release_target in publishable_targets().values():
        archive_path = path / release_target.asset
        if release_target.format == "tar.gz":
            with tarfile.open(archive_path, "w:gz") as archive:
                archive.add(path / "bundle" / "mgesture", arcname="mgesture")
        else:
            archive_path.write_bytes(b"fixture placeholder")
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
