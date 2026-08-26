from __future__ import annotations

import importlib
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


class LinuxWaylandBackend:
    """Native relative pointer injection through /dev/uinput when permitted."""

    name = "linux-wayland-uinput"

    def __init__(self) -> None:
        try:
            evdev = importlib.import_module("evdev")
        except ImportError as exc:
            raise RuntimeError(
                "Wayland backend needs python-evdev; install Pixi Linux dependencies"
            ) from exc
        try:
            ecodes = evdev.ecodes
            self._ecodes = ecodes
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
        self._position = (960.0, 540.0)

    def get_screen_layout(self) -> ScreenLayout:
        return ScreenLayout((Monitor("primary", 0, 0, 1920, 1080, True),))

    def get_pointer_position(self) -> tuple[float, float]:
        return self._position

    def move_absolute(self, x: float, y: float) -> None:
        self.move_relative(x - self._position[0], y - self._position[1])

    def move_relative(self, dx: float, dy: float) -> None:
        dx_i, dy_i = int(round(dx)), int(round(dy))
        if dx_i:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_X, dx_i)
        if dy_i:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_Y, dy_i)
        if dx_i or dy_i:
            self._ui.syn()
        self._position = (self._position[0] + dx, self._position[1] + dy)

    def button_down(self, button: Button) -> None:
        code = self._ecodes.BTN_LEFT if button is Button.LEFT else self._ecodes.BTN_RIGHT
        self._ui.write(self._ecodes.EV_KEY, code, 1)
        self._ui.syn()
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        code = self._ecodes.BTN_LEFT if button is Button.LEFT else self._ecodes.BTN_RIGHT
        self._ui.write(self._ecodes.EV_KEY, code, 0)
        self._ui.syn()
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        if dx:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_HWHEEL, int(round(dx)))
        if dy:
            self._ui.write(self._ecodes.EV_REL, self._ecodes.REL_WHEEL, int(round(dy)))
        if dx or dy:
            self._ui.syn()

    def release_all(self) -> None:
        for button in tuple(self._held):
            self.button_up(button)

    def close(self) -> None:
        self.release_all()
        self._ui.close()
