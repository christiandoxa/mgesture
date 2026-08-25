from __future__ import annotations

from dataclasses import dataclass

from mgesture.engine.models import Button

from .protocol import Monitor, ScreenLayout


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    kind: str
    x: float | None = None
    y: float | None = None
    dx: float | None = None
    dy: float | None = None
    button: str | None = None


class FakeMouseBackend:
    name = "fake"

    def __init__(self, layout: ScreenLayout | None = None) -> None:
        self.layout = layout or ScreenLayout((Monitor("primary", 0, 0, 1920, 1080, True),))
        self.events: list[RecordedEvent] = []
        self.held: set[Button] = set()
        self.position = (
            self.layout.primary_monitor.x + self.layout.primary_monitor.width / 2,
            self.layout.primary_monitor.y + self.layout.primary_monitor.height / 2,
        )
        self.closed = False

    def get_screen_layout(self) -> ScreenLayout:
        return self.layout

    def get_pointer_position(self) -> tuple[float, float]:
        return self.position

    def move_absolute(self, x: float, y: float) -> None:
        self.position = (x, y)
        self.events.append(RecordedEvent("move_absolute", x=x, y=y))

    def move_relative(self, dx: float, dy: float) -> None:
        self.position = (self.position[0] + dx, self.position[1] + dy)
        self.events.append(RecordedEvent("move_relative", dx=dx, dy=dy))

    def button_down(self, button: Button) -> None:
        if button not in self.held:
            self.held.add(button)
            self.events.append(RecordedEvent("button_down", button=button.value))

    def button_up(self, button: Button) -> None:
        self.held.discard(button)
        self.events.append(RecordedEvent("button_up", button=button.value))

    def scroll(self, dx: float, dy: float) -> None:
        self.events.append(RecordedEvent("scroll", dx=dx, dy=dy))

    def release_all(self) -> None:
        for button in (Button.LEFT, Button.RIGHT):
            if button in self.held:
                self.button_up(button)

    def close(self) -> None:
        self.release_all()
        self.closed = True
