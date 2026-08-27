from __future__ import annotations

import importlib
import os
import sys
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


def uinput_status(path: str = "/dev/uinput") -> tuple[bool, str]:
    exists = os.path.exists(path)
    writable = exists and os.access(path, os.W_OK)
    return exists and writable, f"exists={exists}, writable={writable}"


class LinuxWaylandBackend:
    """Native relative pointer injection through /dev/uinput when permitted."""

    name = "linux-wayland-uinput"
    absolute_coordinates: bool = False
    dpi_aware: bool | None = None

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        if sys.platform != "linux":
            raise RuntimeError("Wayland backend requires Linux")
        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland" and not os.environ.get(
            "WAYLAND_DISPLAY"
        ):
            raise RuntimeError(
                "Wayland backend requires a Wayland session "
                "(XDG_SESSION_TYPE=wayland or WAYLAND_DISPLAY)"
            )
        available, detail = uinput_status()
        if not available:
            raise RuntimeError(
                f"Wayland uinput unavailable: {detail}; check /dev/uinput permissions"
            )
        if width <= 0 or height <= 0:
            raise ValueError("Wayland configured display dimensions must be positive")
        try:
            evdev = importlib.import_module("evdev")
        except ImportError as exc:
            raise RuntimeError(
                "Wayland backend needs python-evdev; install Pixi Linux dependencies"
            ) from exc
        try:
            ecodes = evdev.ecodes
            self._ecodes: Any = ecodes
            self._ui: Any = evdev.UInput(
                {
                    ecodes.EV_REL: [
                        ecodes.REL_X,
                        ecodes.REL_Y,
                        ecodes.REL_WHEEL,
                        ecodes.REL_HWHEEL,
                    ],
                    ecodes.EV_KEY: [ecodes.BTN_LEFT, ecodes.BTN_RIGHT],
                },
                name="mgesture virtual mouse",
            )
        except OSError as exc:
            raise RuntimeError(f"cannot open /dev/uinput for Wayland injection: {exc}") from exc
        self._held: set[Button] = set()
        # ponytail: uinput has no portable cursor query; compositor-specific absolute input is the upgrade path.
        self._position: tuple[float, float] | None = None
        self._layout: ScreenLayout = ScreenLayout(
            (Monitor("configured", 0, 0, width, height, True),)
        )
        self._closed: bool = False

    def get_screen_layout(self) -> ScreenLayout:
        return self._layout

    def get_pointer_position(self) -> tuple[float, float] | None:
        return None

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Wayland input backend is closed")

    def move_absolute(self, x: float, y: float) -> None:
        self._ensure_open()
        if self._position is None:
            self._position = (x, y)
            return
        previous = self._position
        self.move_relative(x - previous[0], y - previous[1])
        self._position = (x, y)

    def move_relative(self, dx: float, dy: float) -> None:
        self._ensure_open()
        dx_i, dy_i = int(round(dx)), int(round(dy))
        if dx_i:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_X, dx_i)
        if dy_i:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_Y, dy_i)
        if dx_i or dy_i:
            self._ui.syn()
        if self._position is not None:
            self._position = (self._position[0] + dx, self._position[1] + dy)

    def button_down(self, button: Button) -> None:
        self._ensure_open()
        if button in self._held:
            return
        code = self._ecodes.BTN_LEFT if button is Button.LEFT else self._ecodes.BTN_RIGHT
        self._ui.write(self._ecodes.EV_KEY, code, 1)
        self._ui.syn()
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        self._ensure_open()
        code = self._ecodes.BTN_LEFT if button is Button.LEFT else self._ecodes.BTN_RIGHT
        self._ui.write(self._ecodes.EV_KEY, code, 0)
        self._ui.syn()
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        self._ensure_open()
        if dx:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_HWHEEL, int(round(dx)))
        if dy:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_WHEEL, int(round(dy)))
        if dx or dy:
            self._ui.syn()

    def release_all(self) -> None:
        errors: list[Exception] = []
        for button in tuple(self._held):
            try:
                self.button_up(button)
            except Exception as exc:
                errors.append(exc)
            finally:
                self._held.discard(button)
        if errors:
            raise RuntimeError(
                f"{len(errors)} Wayland button release operation(s) failed"
            ) from errors[0]

    def close(self) -> None:
        if self._closed:
            return
        errors: list[Exception] = []
        try:
            self.release_all()
        except Exception as exc:
            errors.append(exc)
        try:
            self._ui.close()
        except Exception as exc:
            errors.append(exc)
        self._closed = True
        if errors:
            raise RuntimeError(f"{len(errors)} Wayland close operation(s) failed") from errors[0]
