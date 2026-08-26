from __future__ import annotations

import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from mgesture.release import current_target

ROOT = Path(__file__).resolve().parents[2]


def _release_fixture(path: Path) -> Path:
    bundle = path / "bundle" / "mgesture" / "bin"
    bundle.mkdir(parents=True)
    binary = bundle / "mgesture"
    binary.write_text(
        "#!/bin/sh\ncase \"$1\" in --version) echo 'mgesture 0.1.0';; *) exit 0;; esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    asset = path / f"mgesture-{current_target()}.tar.gz"
    with tarfile.open(asset, "w:gz") as archive:
        archive.add(path / "bundle" / "mgesture", arcname="mgesture")
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
    return asset


@pytest.mark.skipif(
    sys.platform == "win32", reason="the Unix installer is not available on Windows"
)
def test_unix_installer_stages_and_activates_without_python_runtime(tmp_path: Path):
    fixture = tmp_path / "release"
    fixture.mkdir()
    asset = _release_fixture(fixture)
    home = tmp_path / "home"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "SHELL": "/bin/sh",
        "MGESTURE_RELEASE_BASE_URL": str(fixture),
        "MGESTURE_INSTALL_DIR": str(home / "app"),
        "MGESTURE_BIN_DIR": str(home / "bin"),
        "MGESTURE_NO_PATH_UPDATE": "true",
    }
    result = subprocess.run(
        ["sh", str(ROOT / "install.sh")], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    command = home / "bin" / "mgesture"
    assert (
        subprocess.run(
            [str(command), "--version"], env=env, capture_output=True, text=True, check=True
        ).stdout.strip()
        == "mgesture 0.1.0"
    )
    assert (home / "app" / "current").is_symlink()
    asset.write_bytes(b"corrupted")
    failed_home = tmp_path / "failed-home"
    failed_env = {
        **env,
        "HOME": str(failed_home),
        "MGESTURE_INSTALL_DIR": str(failed_home / "app"),
        "MGESTURE_BIN_DIR": str(failed_home / "bin"),
    }
    failed = subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        cwd=ROOT,
        env=failed_env,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert not (failed_home / "app" / "current").exists()
