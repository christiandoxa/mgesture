from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any, cast

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", _MouseInput)]


class WindowsMouseBackend:
    name = "windows-sendinput"
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
        if __import__("sys").platform != "win32":
            raise RuntimeError("Windows backend requires native Windows, not WSL")
        self._user32 = cast(Any, ctypes).windll.user32
        self._held: set[Button] = set()

    def get_screen_layout(self) -> ScreenLayout:
        x = self._user32.GetSystemMetrics(self._SM_XVIRTUALSCREEN)
        y = self._user32.GetSystemMetrics(self._SM_YVIRTUALSCREEN)
        width = self._user32.GetSystemMetrics(self._SM_CXVIRTUALSCREEN)
        height = self._user32.GetSystemMetrics(self._SM_CYVIRTUALSCREEN)
        return ScreenLayout((Monitor("virtual-desktop", x, y, width, height, True),))

    def get_pointer_position(self) -> tuple[float, float] | None:
        point = wintypes.POINT()
        return (
            (float(point.x), float(point.y))
            if self._user32.GetCursorPos(ctypes.byref(point))
            else None
        )

    def _send(self, dx: int, dy: int, data: int, flags: int) -> None:
        item = _Input(self._INPUT_MOUSE, _MouseInput(dx, dy, data, flags, 0, None))
        if self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item)) != 1:
            raise cast(Any, ctypes).WinError()

    def move_absolute(self, x: float, y: float) -> None:
        layout = self.get_screen_layout()
        nx = round((x - layout.x) * 65535 / max(1, layout.width - 1))
        ny = round((y - layout.y) * 65535 / max(1, layout.height - 1))
        self._send(nx, ny, 0, self._MOVE | self._ABSOLUTE | self._VIRTUALDESK)

    def move_relative(self, dx: float, dy: float) -> None:
        self._send(round(dx), round(dy), 0, self._MOVE)

    def button_down(self, button: Button) -> None:
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
        for button in tuple(self._held):
            self.button_up(button)

    def close(self) -> None:
        self.release_all()
