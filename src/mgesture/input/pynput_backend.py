from __future__ import annotations

import re
import subprocess
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


def x11_screen_layout() -> ScreenLayout:
    monitors: list[Monitor] = []
    try:
        output = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, timeout=2, check=False
        ).stdout
        for index, match in enumerate(re.finditer(r"\s(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", output)):
            width, height, x, y = (int(value) for value in match.groups())
            monitors.append(Monitor(f"monitor-{index}", x, y, width, height, index == 0))
    except (OSError, subprocess.SubprocessError):
        pass
    if not monitors:
        monitors.append(Monitor("primary", 0, 0, 1920, 1080, True))
    return ScreenLayout(tuple(monitors))


class PynputMouseBackend:
    name = "pynput-x11"

    def __init__(self) -> None:
        try:
            from pynput import mouse  # type: ignore[import-untyped]

            self._mouse = mouse
            self._controller: Any = mouse.Controller()
        except Exception as exc:
            raise RuntimeError(f"pynput X11 backend unavailable: {exc}") from exc
        self._held: set[Button] = set()

    def get_screen_layout(self) -> ScreenLayout:
        return x11_screen_layout()

    def get_pointer_position(self) -> tuple[float, float] | None:
        position = self._controller.position
        return float(position[0]), float(position[1])

    def move_absolute(self, x: float, y: float) -> None:
        self._controller.position = (int(round(x)), int(round(y)))

    def move_relative(self, dx: float, dy: float) -> None:
        self._controller.move(int(round(dx)), int(round(dy)))

    def button_down(self, button: Button) -> None:
        value = self._mouse.Button.left if button is Button.LEFT else self._mouse.Button.right
        self._controller.press(value)
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        value = self._mouse.Button.left if button is Button.LEFT else self._mouse.Button.right
        self._controller.release(value)
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        self._controller.scroll(int(round(dx)), int(round(dy)))

    def release_all(self) -> None:
        for button in tuple(self._held):
            try:
                self.button_up(button)
            except Exception:
                # Best effort after a display server disconnect; caller logs the outer failure.
                self._held.discard(button)

    def close(self) -> None:
        self.release_all()
        controller = self._controller
        self._controller = None
        del controller
