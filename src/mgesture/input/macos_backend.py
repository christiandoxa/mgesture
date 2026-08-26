from __future__ import annotations

import importlib
import sys
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


class MacOSMouseBackend:
    name = "macos-quartz"

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("macOS backend requires macOS")
        try:
            quartz = importlib.import_module("Quartz")
        except ImportError as exc:
            raise RuntimeError("macOS backend needs pyobjc-framework-Quartz") from exc
        self._quartz: Any = quartz
        self._held: set[Button] = set()

    def get_screen_layout(self) -> ScreenLayout:
        display = self._quartz.CGMainDisplayID()
        bounds = self._quartz.CGDisplayBounds(display)
        return ScreenLayout(
            (
                Monitor(
                    "main",
                    int(bounds.origin.x),
                    int(bounds.origin.y),
                    int(bounds.size.width),
                    int(bounds.size.height),
                    True,
                ),
            )
        )

    def get_pointer_position(self) -> tuple[float, float] | None:
        event = self._quartz.CGEventCreate(None)
        point = self._quartz.CGEventGetLocation(event)
        return float(point.x), float(point.y)

    def _post(self, event_type: int, x: float, y: float, button: Button | None = None) -> None:
        value = (
            self._quartz.kCGMouseButtonLeft
            if button is Button.LEFT
            else self._quartz.kCGMouseButtonRight
        )
        event = self._quartz.CGEventCreateMouseEvent(None, event_type, (x, y), value)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def move_absolute(self, x: float, y: float) -> None:
        self._post(self._quartz.kCGEventMouseMoved, x, y)

    def move_relative(self, dx: float, dy: float) -> None:
        position = self.get_pointer_position() or (0.0, 0.0)
        self.move_absolute(position[0] + dx, position[1] + dy)

    def button_down(self, button: Button) -> None:
        event = (
            self._quartz.kCGEventLeftMouseDown
            if button is Button.LEFT
            else self._quartz.kCGEventRightMouseDown
        )
        self._post(event, *(self.get_pointer_position() or (0.0, 0.0)), button)
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        event = (
            self._quartz.kCGEventLeftMouseUp
            if button is Button.LEFT
            else self._quartz.kCGEventRightMouseUp
        )
        self._post(event, *(self.get_pointer_position() or (0.0, 0.0)), button)
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        event = self._quartz.CGEventCreateScrollWheelEvent(
            None, self._quartz.kCGScrollEventUnitLine, 2, int(round(dy)), int(round(dx))
        )
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def release_all(self) -> None:
        for button in tuple(self._held):
            self.button_up(button)

    def close(self) -> None:
        self.release_all()
