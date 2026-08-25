from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "release"))

from release_targets import target  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))
from mgesture.vision.model_manager import available_model  # noqa: E402


def _version() -> str:
    namespace: dict[str, object] = {}
    exec((ROOT / "src/mgesture/version.py").read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def _commit(value: str | None) -> str:
    if value:
        return value
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "source-tree"


def build(target_name: str, output: Path, model: Path | None, version: str, commit: str) -> Path:
    if version != _version():
        raise ValueError(f"bundle version {version} does not match runtime version {_version()}")
    release_target = target(target_name)
    if not release_target.publishable:
        raise RuntimeError(f"target {target_name} is not publishable: {release_target.status}")
    model = model or available_model()
    if model is None:
        raise RuntimeError(
            "verified model is unavailable; run `mgesture model install` or pass --model"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mgesture-build-") as temporary:
        work = Path(temporary)
        dist = work / "dist"
        command = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--name",
            "mgesture",
            "--paths",
            str(ROOT / "src"),
            "--collect-all",
            "mediapipe",
            "--collect-all",
            "cv2",
            "--copy-metadata",
            "mediapipe",
            "--distpath",
            str(dist),
            "--workpath",
            str(work / "pyinstaller-work"),
            "--specpath",
            str(work / "spec"),
            str(work / "entry.py"),
        ]
        (work / "entry.py").write_text("from mgesture.cli import main\nmain()\n", encoding="utf-8")
        subprocess.run(command, cwd=ROOT, check=True)
        bundle = work / "mgesture"
        app_bin = bundle / "bin"
        app_bin.parent.mkdir(parents=True)
        shutil.copytree(dist / "mgesture", app_bin)
        share = bundle / "share" / "mgesture"
        (share / "models").mkdir(parents=True)
        shutil.copy2(model, share / "models" / "hand_landmarker.task")
        license_file = model.with_suffix(model.suffix + ".license")
        if license_file.exists():
            shutil.copy2(license_file, share / "models" / license_file.name)
        (bundle / "licenses").mkdir()
        shutil.copy2(ROOT / "LICENSE", bundle / "licenses" / "LICENSE")
        (bundle / "licenses" / "MEDIAPIPE_MODEL.txt").write_text(
            "MediaPipe Hand Landmarker model; see upstream MediaPipe model card and Apache-2.0 terms.\n",
            encoding="utf-8",
        )
        (bundle / "licenses" / "THIRD_PARTY_NOTICES.txt").write_text(
            "Bundled runtime notices:\n"
            "- MediaPipe: Apache-2.0; https://github.com/google-ai-edge/mediapipe\n"
            "- OpenCV: Apache-2.0; https://opencv.org/license/\n"
            "- NumPy: BSD-3-Clause; https://numpy.org/license.html\n"
            "- pynput: LGPL-3.0-or-later; https://github.com/moses-palmer/pynput\n"
            "- PyInstaller: GPL-2.0-or-later with bootloader exception; https://pyinstaller.org/\n"
            "Consult each bundled distribution's metadata for complete notices.\n",
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "release/targets.toml", share / "targets.toml")
        metadata = {
            "schema_version": 1,
            "version": version,
            "commit": commit,
            "target": target_name,
            "standalone": True,
            "implementation": release_target.implementation,
            "compiler_required": False,
            "python_runtime_bundled": True,
            "model_sha256": _sha256(model),
            "packaging": "PyInstaller onedir",
            "python": release_target.python,
            "mojo_version": "not bundled",
            "gesture_engine": {
                "implementation": release_target.implementation,
                "compiler_required": False,
                "self_test": "pending-runtime-smoke",
            },
        }
        (share / "release-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        subprocess.run(
            [str(app_bin / "mgesture"), "self-test", "--headless", "--fake-input"],
            cwd=bundle,
            env={**os.environ, "MGESTURE_BUNDLE_ROOT": str(bundle)},
            check=True,
        )
        metadata["gesture_engine"]["self_test"] = "passed"
        (share / "release-metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        shutil.copy2(ROOT / "install.sh", bundle / "install.sh")
        shutil.copy2(ROOT / "install.ps1", bundle / "install.ps1")
        if output.suffix == ".zip":
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in bundle.rglob("*"):
                    if path.is_file():
                        archive.write(path, Path("mgesture") / path.relative_to(bundle))
        else:
            with tarfile.open(output, "w:gz") as archive:
                archive.add(bundle, arcname="mgesture")
    return output


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--version", default=_version())
    parser.add_argument("--commit")
    args = parser.parse_args()
    build(args.target, args.output, args.model, args.version, _commit(args.commit))
    print(args.output)


if __name__ == "__main__":
    main()
