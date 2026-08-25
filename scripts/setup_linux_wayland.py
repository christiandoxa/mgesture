from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path

RULE = 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="input", MODE="0660"\n'


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install the narrowly scoped mgesture uinput permission rule"
    )
    parser.add_argument(
        "--install", action="store_true", help="write the system udev rule; requires sudo/root"
    )
    args = parser.parse_args()
    if platform.system() != "Linux":
        raise SystemExit("Wayland uinput setup is Linux-only")
    if not args.install:
        print(
            "Dry run: would install /etc/udev/rules.d/99-mgesture-uinput.rules for the input group."
        )
        print(
            "Run with --install under sudo, then reload udev and re-login. The application itself does not need root."
        )
        return
    if os.geteuid() != 0:
        raise SystemExit(
            "--install must be run with sudo; normal mgesture execution remains unprivileged"
        )
    target = Path("/etc/udev/rules.d/99-mgesture-uinput.rules")
    target.write_text(RULE, encoding="utf-8")
    print(f"wrote {target}; run `udevadm control --reload-rules && udevadm trigger`, then re-login")


if __name__ == "__main__":
    main()
