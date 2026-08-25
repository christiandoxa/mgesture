from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mgesture.engine.models import Button


@dataclass(frozen=True, slots=True)
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False


@dataclass(frozen=True, slots=True)
class ScreenLayout:
    monitors: tuple[Monitor, ...]

    @property
    def x(self) -> int:
        return min((monitor.x for monitor in self.monitors), default=0)

    @property
    def y(self) -> int:
        return min((monitor.y for monitor in self.monitors), default=0)

    @property
    def right(self) -> int:
        return max((monitor.x + monitor.width for monitor in self.monitors), default=1920)

    @property
    def bottom(self) -> int:
        return max((monitor.y + monitor.height for monitor in self.monitors), default=1080)

    @property
    def width(self) -> int:
        return self.right - self.x

    @property
    def height(self) -> int:
        return self.bottom - self.y

    @property
    def primary_monitor(self) -> Monitor:
        return next((monitor for monitor in self.monitors if monitor.primary), self.monitors[0])


class MouseBackend(Protocol):
    name: str

    def get_screen_layout(self) -> ScreenLayout: ...

    def get_pointer_position(self) -> tuple[float, float] | None: ...

    def move_absolute(self, x: float, y: float) -> None: ...

    def move_relative(self, dx: float, dy: float) -> None: ...

    def button_down(self, button: Button) -> None: ...

    def button_up(self, button: Button) -> None: ...

    def scroll(self, dx: float, dy: float) -> None: ...

    def release_all(self) -> None: ...

    def close(self) -> None: ...
