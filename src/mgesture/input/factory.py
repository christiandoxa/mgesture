from __future__ import annotations

import os
import sys

from .fake_backend import FakeMouseBackend
from .protocol import Monitor, MouseBackend, ScreenLayout


def _fake_layout(width: int, height: int) -> ScreenLayout:
    return ScreenLayout((Monitor("primary", 0, 0, width, height, True),))


def create_backend(name: str = "auto", width: int = 1920, height: int = 1080) -> MouseBackend:
    selected = name
    if selected == "auto":
        if sys.platform == "win32":
            selected = "windows"
        elif sys.platform == "darwin":
            selected = "macos"
        elif os.environ.get("XDG_SESSION_TYPE", "x11").lower() == "wayland":
            selected = "wayland"
        else:
            selected = "x11"
    if selected == "fake":
        return FakeMouseBackend(_fake_layout(width, height))
    if selected == "x11":
        from .linux_x11_backend import LinuxX11Backend

        return LinuxX11Backend()
    if selected == "wayland":
        from .linux_wayland_backend import LinuxWaylandBackend

        return LinuxWaylandBackend()
    if selected == "windows":
        from .windows_backend import WindowsMouseBackend

        return WindowsMouseBackend()
    if selected == "macos":
        from .macos_backend import MacOSMouseBackend

        return MacOSMouseBackend()
    raise ValueError(f"Unknown input backend: {name}")
