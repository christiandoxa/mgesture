from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any, cast

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout

_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_PROCESS_PER_MONITOR_DPI_AWARE = 2
_ERROR_ACCESS_DENIED = 5
_E_ACCESSDENIED = 0x80070005


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", _MouseInput)]


class WindowsMouseBackend:
    name = "windows-sendinput"
    absolute_coordinates: bool = True
    dpi_aware: bool | None = True
    _user32: Any
    _closed: bool
    _INPUT_MOUSE = 0
    _MOVE = 0x0001
    _LEFT_DOWN = 0x0002
    _LEFT_UP = 0x0004
    _RIGHT_DOWN = 0x0008
    _RIGHT_UP = 0x0010
    _WHEEL = 0x0800
    _HWHEEL = 0x01000
    _ABSOLUTE = 0x8000
    _VIRTUALDESK = 0x4000
    _SM_XVIRTUALSCREEN = 76
    _SM_YVIRTUALSCREEN = 77
    _SM_CXVIRTUALSCREEN = 78
    _SM_CYVIRTUALSCREEN = 79

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows backend requires native Windows, not WSL")
        user32 = cast(Any, ctypes).windll.user32
        if not enable_process_dpi_awareness(user32):
            raise RuntimeError("Windows backend could not enable per-monitor DPI awareness")
        self._user32 = user32
        self._held: set[Button] = set()
        self.dpi_aware = True
        self._closed = False

    def get_screen_layout(self) -> ScreenLayout:
        return virtual_screen_layout(self._user32)

    def get_pointer_position(self) -> tuple[float, float] | None:
        if self._closed:
            return None
        point = wintypes.POINT()
        return (
            (float(point.x), float(point.y))
            if self._user32.GetCursorPos(ctypes.byref(point))
            else None
        )

    def _send(self, dx: int, dy: int, data: int, flags: int) -> None:
        if self._closed:
            raise RuntimeError("Windows input backend is closed")
        item = _Input(self._INPUT_MOUSE, _MouseInput(dx, dy, data, flags, 0, 0))
        if self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item)) != 1:
            raise cast(Any, ctypes).WinError()

    def move_absolute(self, x: float, y: float) -> None:
        layout = self.get_screen_layout()
        nx, ny = normalize_absolute(x, y, layout)
        self._send(nx, ny, 0, self._MOVE | self._ABSOLUTE | self._VIRTUALDESK)

    def move_relative(self, dx: float, dy: float) -> None:
        self._send(round(dx), round(dy), 0, self._MOVE)

    def button_down(self, button: Button) -> None:
        if button in self._held:
            return
        self._send(0, 0, 0, self._LEFT_DOWN if button is Button.LEFT else self._RIGHT_DOWN)
        self._held.add(button)

    def button_up(self, button: Button) -> None:
        self._send(0, 0, 0, self._LEFT_UP if button is Button.LEFT else self._RIGHT_UP)
        self._held.discard(button)

    def scroll(self, dx: float, dy: float) -> None:
        if dy:
            self._send(0, 0, round(dy * 120), self._WHEEL)
        if dx:
            self._send(0, 0, round(dx * 120), self._HWHEEL)

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
                f"{len(errors)} Windows button release operation(s) failed"
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
            raise RuntimeError(f"{len(errors)} Windows close operation(s) failed") from errors[0]


def _last_error() -> int:
    getter = getattr(ctypes, "get_last_error", None)
    return int(getter()) if callable(getter) else 0


def enable_process_dpi_awareness(user32: Any) -> bool:
    setter = getattr(user32, "SetProcessDpiAwarenessContext", None)
    if callable(setter):
        try:
            if setter(_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
                return True
            if _last_error() == _ERROR_ACCESS_DENIED:
                return True
        except OSError:
            pass
    try:
        setter = cast(Any, ctypes).windll.shcore.SetProcessDpiAwareness
        result = int(setter(_PROCESS_PER_MONITOR_DPI_AWARE))
        if result == 0:
            return True
        return (
            result in (_ERROR_ACCESS_DENIED, _E_ACCESSDENIED)
            or _last_error() == _ERROR_ACCESS_DENIED
        )
    except (AttributeError, OSError):
        return False


def virtual_screen_layout(user32: Any) -> ScreenLayout:
    x = int(user32.GetSystemMetrics(WindowsMouseBackend._SM_XVIRTUALSCREEN))
    y = int(user32.GetSystemMetrics(WindowsMouseBackend._SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(WindowsMouseBackend._SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(WindowsMouseBackend._SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        raise RuntimeError("Windows virtual desktop metrics are unavailable")
    return ScreenLayout((Monitor("virtual-desktop", x, y, width, height, True),))


def normalize_absolute(x: float, y: float, layout: ScreenLayout) -> tuple[int, int]:
    x = min(max(x, float(layout.x)), float(layout.right - 1))
    y = min(max(y, float(layout.y)), float(layout.bottom - 1))
    return (
        round((x - layout.x) * 65535 / max(1, layout.width - 1)),
        round((y - layout.y) * 65535 / max(1, layout.height - 1)),
    )
