from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mgesture.release import mojo_source_metadata  # noqa: E402


def runtime_version(root: Path) -> str:
    namespace: dict[str, object] = {}
    exec((root / "src/mgesture/version.py").read_text(encoding="utf-8"), namespace)
    return str(namespace["__version__"])


def generate(output: Path, version: str) -> None:
    names = ("mgesture", "mediapipe", "numpy", "opencv-contrib-python", "platformdirs", "pynput")
    packages = []
    for name in names:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = "not-installed-in-build-environment"
        identifier = "SPDXRef-Package-" + hashlib.sha256(name.encode()).hexdigest()[:16]
        packages.append(
            {
                "SPDXID": identifier,
                "name": name,
                "versionInfo": installed,
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
            }
        )
    source = mojo_source_metadata(ROOT / "mojo")
    packages.append(
        {
            "SPDXID": "SPDXRef-Package-mgesture-mojo-source",
            "name": "mgesture-mojo-source",
            "versionInfo": str(source["sha256"]),
            "downloadLocation": "https://github.com/christiandoxa/mgesture/tree/main/mojo",
            "licenseConcluded": "Apache-2.0",
            "licenseDeclared": "Apache-2.0",
            "filesAnalyzed": False,
            "comment": "Canonical Mojo source files: " + ", ".join(source["files"]),
        }
    )
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"mgesture-{version}",
        "documentNamespace": f"https://github.com/christiandoxa/mgesture/sbom/{version}/{platform.system().lower()}",
        "creationInfo": {
            "created": datetime.fromtimestamp(int(os.environ.get("SOURCE_DATE_EPOCH", "0")), UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "creators": ["Tool: mgesture release sbom"],
        },
        "packages": packages,
    }
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    runtime = runtime_version(args.root)
    version = args.version or runtime
    if version != runtime:
        raise SystemExit(f"SBOM version {version} does not match runtime {runtime}")
    generate(args.output, version)


if __name__ == "__main__":
    main()
