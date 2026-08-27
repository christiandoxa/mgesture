from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout

_LIST_MONITORS_RE = re.compile(
    r"^\s*\d+:\s+(?P<flags>[+*]*)(?P<name>\S+)\s+"
    r"(?P<width>\d+)(?:/\d+)?x(?P<height>\d+)(?:/\d+)?"
    r"(?P<x>[+-]?\d+)(?P<y>[+-]\d+)",
    re.MULTILINE,
)
_CONNECTED_RE = re.compile(
    r"^\s*(?P<name>\S+)\s+connected(?:\s+(?P<primary>primary))?\s+"
    r"(?P<width>\d+)x(?P<height>\d+)"
    r"(?P<x>[+-]?\d+)(?P<y>[+-]\d+)",
    re.MULTILINE,
)


def parse_xrandr_monitors(output: str) -> ScreenLayout:
    monitors: list[Monitor] = []
    for match in _LIST_MONITORS_RE.finditer(output):
        monitors.append(
            Monitor(
                match.group("name"),
                int(match.group("x")),
                int(match.group("y")),
                int(match.group("width")),
                int(match.group("height")),
                "*" in match.group("flags"),
            )
        )
    if not monitors:
        for match in _CONNECTED_RE.finditer(output):
            monitors.append(
                Monitor(
                    match.group("name"),
                    int(match.group("x")),
                    int(match.group("y")),
                    int(match.group("width")),
                    int(match.group("height")),
                    match.group("primary") == "primary",
                )
            )
    if not monitors:
        raise ValueError("xrandr did not report any active monitors")
    primary = next((index for index, monitor in enumerate(monitors) if monitor.primary), 0)
    return ScreenLayout(
        tuple(
            Monitor(
                monitor.name, monitor.x, monitor.y, monitor.width, monitor.height, index == primary
            )
            for index, monitor in enumerate(monitors)
        )
    )


def x11_screen_layout() -> ScreenLayout:
    if sys.platform != "linux":
        raise RuntimeError("X11 backend requires Linux")
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("X11 backend requires DISPLAY")
    last_error = ""
    for arguments in (("--listactivemonitors",), ("--query",)):
        try:
            result = subprocess.run(
                ["xrandr", *arguments],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("X11 monitor layout requires the xrandr command") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = str(exc)
            continue
        if getattr(result, "returncode", 0) != 0:
            last_error = (result.stderr or "").strip() or f"exit code {result.returncode}"
            continue
        try:
            return parse_xrandr_monitors(result.stdout)
        except ValueError as exc:
            last_error = str(exc)
    raise RuntimeError(f"cannot query X11 monitor layout with xrandr: {last_error}")


class PynputMouseBackend:
    name = "pynput-x11"
    absolute_coordinates: bool = True
    dpi_aware: bool | None = None

    def __init__(self) -> None:
        if sys.platform != "linux":
            raise RuntimeError("X11 backend requires Linux")
        if not os.environ.get("DISPLAY"):
            raise RuntimeError("X11 backend requires DISPLAY")
        self._mouse: Any = None
        self._controller: Any = None
        try:
            from pynput import mouse  # type: ignore[import-untyped]

            self._mouse = mouse
            self._controller = mouse.Controller()
        except Exception as exc:
            raise RuntimeError(f"pynput X11 backend unavailable: {exc}") from exc
        self._held: set[Button] = set()

    def get_screen_layout(self) -> ScreenLayout:
        return x11_screen_layout()

    def get_pointer_position(self) -> tuple[float, float] | None:
        if self._controller is None:
            return None
        position = self._controller.position
        return float(position[0]), float(position[1])

    def move_absolute(self, x: float, y: float) -> None:
        if self._controller is None:
            raise RuntimeError("X11 input backend is closed")
        self._controller.position = (int(round(x)), int(round(y)))

    def move_relative(self, dx: float, dy: float) -> None:
        if self._controller is None:
            raise RuntimeError("X11 input backend is closed")
        self._controller.move(int(round(dx)), int(round(dy)))

    def button_down(self, button: Button) -> None:
        if self._controller is None:
            raise RuntimeError("X11 input backend is closed")
        if button in self._held:
            return
        value = self._mouse.Button.left if button is Button.LEFT else self._mouse.Button.right
        self._controller.press(value)
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        if self._controller is None:
            raise RuntimeError("X11 input backend is closed")
        value = self._mouse.Button.left if button is Button.LEFT else self._mouse.Button.right
        self._controller.release(value)
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        if self._controller is None:
            raise RuntimeError("X11 input backend is closed")
        self._controller.scroll(int(round(dx)), int(round(dy)))

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
            raise RuntimeError(f"{len(errors)} X11 button release operation(s) failed") from errors[
                0
            ]

    def close(self) -> None:
        if self._controller is None:
            self._held.clear()
            return
        errors: list[Exception] = []
        try:
            self.release_all()
        except Exception as exc:
            errors.append(exc)
        self._controller = None
        self._mouse = None
        if errors:
            raise RuntimeError(f"{len(errors)} X11 close operation(s) failed") from errors[0]
