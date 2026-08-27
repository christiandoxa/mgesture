from __future__ import annotations

import importlib
import sys
from typing import Any

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


def active_display_ids(quartz: Any) -> tuple[int, ...]:
    getter = getattr(quartz, "CGGetActiveDisplayList", None)
    if not callable(getter):
        return (int(quartz.CGMainDisplayID()),)
    try:
        result = getter(32, None, None)
    except TypeError:
        result = getter(32, None)
    if not isinstance(result, tuple) or len(result) < 2:
        raise RuntimeError("Quartz returned an invalid active display list")
    error = int(result[0])
    if error:
        raise RuntimeError(f"Quartz display enumeration failed ({error})")
    displays = result[1] or ()
    count = int(result[2]) if len(result) > 2 and result[2] is not None else len(displays)
    display_ids = tuple(int(display) for display in displays[:count])
    if display_ids:
        return display_ids
    main = int(quartz.CGMainDisplayID())
    if main:
        return (main,)
    raise RuntimeError("Quartz reported no active displays")


class MacOSMouseBackend:
    name = "macos-quartz"
    absolute_coordinates: bool = True
    dpi_aware: bool | None = None
    _closed: bool

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("macOS backend requires macOS")
        try:
            quartz = importlib.import_module("Quartz")
        except ImportError as exc:
            raise RuntimeError("macOS backend needs pyobjc-framework-Quartz") from exc
        self._quartz: Any = quartz
        self._held: set[Button] = set()
        self._closed = False

    def get_screen_layout(self) -> ScreenLayout:
        main = int(self._quartz.CGMainDisplayID())
        displays = list(active_display_ids(self._quartz))
        if main not in displays:
            displays.insert(0, main)
        monitors: list[Monitor] = []
        for display in displays:
            # CGDisplayBounds is the global Quartz coordinate space; keep Retina points, not pixels.
            bounds = self._quartz.CGDisplayBounds(display)
            width = int(round(float(bounds.size.width)))
            height = int(round(float(bounds.size.height)))
            if width <= 0 or height <= 0:
                raise RuntimeError(f"Quartz returned invalid bounds for display {display}")
            monitors.append(
                Monitor(
                    f"display-{display}",
                    int(round(float(bounds.origin.x))),
                    int(round(float(bounds.origin.y))),
                    width,
                    height,
                    display == main,
                )
            )
        return ScreenLayout(tuple(monitors))

    def get_pointer_position(self) -> tuple[float, float] | None:
        if self._closed:
            return None
        event = self._quartz.CGEventCreate(None)
        point = self._quartz.CGEventGetLocation(event)
        return float(point.x), float(point.y)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("macOS input backend is closed")

    def _post(self, event_type: int, x: float, y: float, button: Button | None = None) -> None:
        value = (
            self._quartz.kCGMouseButtonLeft
            if button is not Button.RIGHT
            else self._quartz.kCGMouseButtonRight
        )
        event = self._quartz.CGEventCreateMouseEvent(None, event_type, (x, y), value)
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

    def move_absolute(self, x: float, y: float) -> None:
        self._ensure_open()
        self._post(self._quartz.kCGEventMouseMoved, x, y)

    def move_relative(self, dx: float, dy: float) -> None:
        position = self.get_pointer_position() or (0.0, 0.0)
        self.move_absolute(position[0] + dx, position[1] + dy)

    def button_down(self, button: Button) -> None:
        self._ensure_open()
        if button in self._held:
            return
        event = (
            self._quartz.kCGEventLeftMouseDown
            if button is Button.LEFT
            else self._quartz.kCGEventRightMouseDown
        )
        self._post(event, *(self.get_pointer_position() or (0.0, 0.0)), button)
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        self._ensure_open()
        event = (
            self._quartz.kCGEventLeftMouseUp
            if button is Button.LEFT
            else self._quartz.kCGEventRightMouseUp
        )
        self._post(event, *(self.get_pointer_position() or (0.0, 0.0)), button)
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        self._ensure_open()
        event = self._quartz.CGEventCreateScrollWheelEvent(
            None, self._quartz.kCGScrollEventUnitLine, 2, int(round(dy)), int(round(dx))
        )
        self._quartz.CGEventPost(self._quartz.kCGHIDEventTap, event)

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
                f"{len(errors)} macOS button release operation(s) failed"
            ) from errors[0]

    def close(self) -> None:
        if self._closed:
            return
        errors: list[Exception] = []
        try:
            self.release_all()
        except Exception as exc:
            errors.append(exc)
        self._closed = True
        if errors:
            raise RuntimeError(f"{len(errors)} macOS close operation(s) failed") from errors[0]
