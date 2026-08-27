from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from mgesture import __version__
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
    assert all(target.native_mojo_engine for target in targets.values())
    assert {target.runtime_default for target in targets.values()} == {"mojo"}


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


def _update_manifest(target: str, version: str, asset: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "version": version,
        "commit": "0" * 40,
        "targets": {
            target: {
                "target": target,
                "asset": asset,
                "sha256": "0" * 64,
                "standalone": True,
                "native_mojo_engine": True,
                "python_engine_available": True,
                "architecture": target.split("-", 1)[0],
            }
        },
    }


def test_update_checks_stable_manifest_and_pins_download_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mgesture.release as release

    target = "x86_64-unknown-linux-gnu"
    asset = f"mgesture-{target}.tar.gz"
    (tmp_path / "release-manifest.json").write_text(
        json.dumps(_update_manifest(target, "0.3.0", asset)), encoding="utf-8"
    )
    installer = tmp_path / "install.sh"
    installer.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, str], bool]] = []
    monkeypatch.setenv("MGESTURE_RELEASE_BASE_URL", str(tmp_path))
    monkeypatch.setattr(release, "__version__", "0.2.0")
    monkeypatch.setattr(release, "current_target", lambda: target)
    monkeypatch.setattr(release, "_installer_path", lambda: installer)
    monkeypatch.setattr(
        release.subprocess,
        "run",
        lambda command, *, env, check: (
            calls.append((command, env, check)) or SimpleNamespace(returncode=0)
        ),
    )

    status = release.check_for_update()
    assert status["update_available"] is True
    assert status["newer_installed"] is False
    assert release.run_update() == 0
    assert calls[0][1]["MGESTURE_RELEASE"] == "0.3.0"


@pytest.mark.parametrize(
    ("current", "latest", "available", "newer_installed"),
    (("0.3.0", "0.3.0", False, False), ("0.4.0", "0.3.0", False, True)),
)
def test_update_never_reinstalls_or_downgrades(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    current: str,
    latest: str,
    available: bool,
    newer_installed: bool,
) -> None:
    import mgesture.release as release

    target = "x86_64-unknown-linux-gnu"
    asset = f"mgesture-{target}.tar.gz"
    (tmp_path / "release-manifest.json").write_text(
        json.dumps(_update_manifest(target, latest, asset)), encoding="utf-8"
    )
    monkeypatch.setenv("MGESTURE_RELEASE_BASE_URL", str(tmp_path))
    monkeypatch.setattr(release, "__version__", current)
    monkeypatch.setattr(release, "current_target", lambda: target)

    status = release.check_for_update()

    assert status["update_available"] is available
    assert status["newer_installed"] is newer_installed


def test_update_rejects_wrong_target_asset_or_manifest_capabilities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mgesture.release as release

    target = "x86_64-unknown-linux-gnu"
    manifest = _update_manifest(target, "0.3.0", "wrong.tar.gz")
    (tmp_path / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("MGESTURE_RELEASE_BASE_URL", str(tmp_path))
    monkeypatch.setattr(release, "current_target", lambda: target)

    with pytest.raises(RuntimeError, match="invalid asset"):
        release.resolve_release()


def test_explicit_release_url_uses_v_prefixed_tag() -> None:
    import mgesture.release as release

    assert release.release_base_url("0.3.0").endswith("/releases/download/v0.3.0")


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


def test_bundle_smoke_rejects_archive_path_escape(tmp_path: Path) -> None:
    from smoke_bundle import _safe_destination

    root = tmp_path / "extract"
    root.mkdir()
    with pytest.raises(ValueError, match="unsafe archive member"):
        _safe_destination(root, "mgesture/../../outside")


def test_windows_tool_lookup_matches_target_architecture(monkeypatch: pytest.MonkeyPatch) -> None:
    import build_mojo_library

    candidates = "\n".join(
        (
            r"C:\VS\bin\HostX64\arm\cl.exe",
            r"C:\VS\bin\HostX64\arm64\cl.exe",
            r"C:\VS\bin\HostX64\x64\cl.exe",
        )
    )
    monkeypatch.setattr(
        build_mojo_library.shutil,
        "which",
        lambda name: "C:/VS/Installer/vswhere.exe" if name == "vswhere.exe" else None,
    )
    monkeypatch.setattr(
        build_mojo_library.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=candidates),
    )

    assert build_mojo_library.find_windows_tool("cl.exe", "aarch64").endswith(r"\arm64\cl.exe")
    assert build_mojo_library.find_windows_tool("cl.exe", "x86_64").endswith(r"\x64\cl.exe")


def test_bundle_uses_cross_compile_provenance_when_mojo_command_collides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import build_bundle

    metadata = tmp_path / "mojo-objects"
    metadata.mkdir()
    (metadata / "mojo-build-metadata.json").write_text(
        '{"compiler_version": "Mojo 1.0.0 (cross-object)"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(build_bundle, "ROOT", tmp_path)
    monkeypatch.setattr(build_bundle.shutil, "which", lambda name: r"C:\Strawberry\mojo.BAT")
    monkeypatch.setattr(
        build_bundle.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout="", stderr=""),
    )

    assert build_bundle._mojo_compiler_version(required=True) == "Mojo 1.0.0 (cross-object)"


def test_bundle_prunes_foreign_native_binaries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import build_bundle

    app_bin = tmp_path / "bin"
    app_bin.mkdir()
    native = app_bin / "native.dll"
    foreign = app_bin / "foreign.dll"
    native.write_bytes(b"native")
    foreign.write_bytes(b"foreign")
    monkeypatch.setattr(
        build_bundle,
        "binary_architectures",
        lambda path: {"x86_64"} if path == native else {"aarch64"},
    )

    build_bundle._prune_foreign_native_binaries(app_bin, "windows", "x86_64")

    assert native.is_file()
    assert not foreign.exists()


def test_windows_arm_link_does_not_add_x86_shim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import build_mojo_library

    object_path = tmp_path / "aarch64-pc-windows-msvc.o"
    object_path.write_bytes(b"COFF")
    (tmp_path / "mojo-build-metadata.json").write_text(
        '{"source_sha256": "source", "targets": ["aarch64-pc-windows-msvc"]}\n',
        encoding="utf-8",
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(build_mojo_library, "binary_architectures", lambda path: {"aarch64"})
    monkeypatch.setattr(
        build_mojo_library,
        "mojo_source_metadata",
        lambda path: {"sha256": "source"},
    )
    monkeypatch.setattr(
        build_mojo_library,
        "find_windows_tool",
        lambda name, architecture=None: "link.exe" if name == "link.exe" else None,
    )
    monkeypatch.setattr(
        build_mojo_library.subprocess,
        "run",
        lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0),
    )

    output = build_mojo_library.link_library(
        "aarch64-pc-windows-msvc", object_path, tmp_path / "mgesture_mojo.dll"
    )

    assert output.name == "mgesture_mojo.dll"
    assert len(commands) == 1
    assert "/MACHINE:ARM64" in commands[0]
    assert not any("fltused" in argument.lower() for argument in commands[0])


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


def _release_fixture(
    path: Path, version: str = __version__, manifest_version: str | None = None
) -> None:
    rendered_version = manifest_version or version
    bundle = path / "bundle" / "mgesture" / "bin"
    bundle.mkdir(parents=True)
    binary = bundle / "mgesture"
    binary.write_text(
        f"#!/bin/sh\ncase \"$1\" in --version) echo 'mgesture {version}';; *) exit 0;; esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    runtime = path / "bundle" / "mgesture" / "runtime" / "mojo"
    runtime.mkdir(parents=True)
    for name in ("libmgesture_mojo.so", "libmgesture_mojo.dylib", "mgesture_mojo.dll"):
        (runtime / name).write_bytes(b"native Mojo fixture")
    metadata = path / "bundle" / "mgesture" / "share" / "mgesture"
    metadata.mkdir(parents=True)
    (metadata / "release-metadata.json").write_text(
        '{"mojo_compiler_version": "Mojo 1.0.0 (fixture)"}\n', encoding="utf-8"
    )
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
            rendered_version,
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
            rendered_version,
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
            rendered_version,
        ],
        cwd=ROOT,
        check=True,
    )
    if version != rendered_version:
        manifest = path / "release-manifest.json"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                f'"version": "{rendered_version}"', f'"version": "{version}"', 1
            ),
            encoding="utf-8",
        )
        tsv = path / "release-manifest.tsv"
        tsv.write_text(
            tsv.read_text(encoding="utf-8").replace(
                f"# version\t{rendered_version}", f"# version\t{version}", 1
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [sys.executable, "scripts/release/generate_checksums.py", str(path)],
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
            == f"mgesture {__version__}"
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


@pytest.mark.skipif(
    sys.platform == "win32", reason="the Unix installer is not available on Windows"
)
def test_unix_install_transition_preserves_user_state(tmp_path: Path):
    old_release = tmp_path / "old-release"
    new_release = tmp_path / "new-release"
    old_release.mkdir()
    new_release.mkdir()
    _release_fixture(old_release, "0.2.0", manifest_version=__version__)
    _release_fixture(new_release, "0.3.0", manifest_version=__version__)
    home = tmp_path / "home"
    app = home / "app"
    bin_dir = home / "bin"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "SHELL": "/bin/sh",
        "MGESTURE_RELEASE_BASE_URL": str(old_release),
        "MGESTURE_INSTALL_DIR": str(app),
        "MGESTURE_BIN_DIR": str(bin_dir),
        "MGESTURE_NO_PATH_UPDATE": "true",
    }
    installed = subprocess.run(
        ["sh", str(ROOT / "install.sh")], cwd=ROOT, env=env, capture_output=True, text=True
    )
    assert installed.returncode == 0, installed.stderr
    config_file = home / ".config/mgesture/config.toml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("saved", encoding="utf-8")
    state_file = app / "state.json"
    state_file.write_text("saved-state", encoding="utf-8")

    updated = subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        cwd=ROOT,
        env={**env, "MGESTURE_RELEASE_BASE_URL": str(new_release), "MGESTURE_RELEASE": "0.3.0"},
        capture_output=True,
        text=True,
    )

    assert updated.returncode == 0, updated.stderr
    assert (
        subprocess.run(
            [str(bin_dir / "mgesture"), "--version"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == "mgesture 0.3.0"
    )
    assert config_file.read_text(encoding="utf-8") == "saved"
    assert state_file.read_text(encoding="utf-8") == "saved-state"
    assert (app / "releases").is_dir()


@pytest.mark.skipif(
    sys.platform == "win32", reason="the Unix installer is not available on Windows"
)
def test_run_update_transitions_fixture_and_preserves_state(tmp_path: Path, monkeypatch) -> None:
    import mgesture.release as release

    old_release = tmp_path / "old-release"
    new_release = tmp_path / "new-release"
    old_release.mkdir()
    new_release.mkdir()
    _release_fixture(old_release, "0.2.0", manifest_version=__version__)
    _release_fixture(new_release, "0.3.0", manifest_version=__version__)
    home = tmp_path / "home"
    app = home / "app"
    bin_dir = home / "bin"
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "SHELL": "/bin/sh",
        "MGESTURE_RELEASE_BASE_URL": str(old_release),
        "MGESTURE_INSTALL_DIR": str(app),
        "MGESTURE_BIN_DIR": str(bin_dir),
        "MGESTURE_NO_PATH_UPDATE": "true",
    }
    installed = subprocess.run(
        ["sh", str(ROOT / "install.sh")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr
    config_file = home / ".config/mgesture/config.toml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text("saved-config", encoding="utf-8")
    monkeypatch.setenv("MGESTURE_RELEASE_BASE_URL", str(new_release))
    monkeypatch.setenv("MGESTURE_INSTALL_DIR", str(app))
    monkeypatch.setenv("MGESTURE_BIN_DIR", str(bin_dir))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(release, "current_target", lambda: "x86_64-unknown-linux-gnu")
    monkeypatch.setattr(release, "_installer_path", lambda: ROOT / "install.sh")
    monkeypatch.setattr(release, "__version__", "0.2.0")

    assert release.run_update() == 0
    assert (
        subprocess.run(
            [str(bin_dir / "mgesture"), "--version"],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == "mgesture 0.3.0"
    )
    assert config_file.read_text(encoding="utf-8") == "saved-config"
