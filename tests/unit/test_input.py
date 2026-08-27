from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest

from mgesture.application import Application
from mgesture.engine import Action, ActionBatch, Button, EngineConfig, PythonGestureEngine
from mgesture.input import FakeMouseBackend, InputDispatcher, Monitor, ScreenLayout
from mgesture.input.linux_wayland_backend import LinuxWaylandBackend
from mgesture.input.macos_backend import MacOSMouseBackend, active_display_ids
from mgesture.input.pynput_backend import parse_xrandr_monitors, x11_screen_layout
from mgesture.input.windows_backend import (
    enable_process_dpi_awareness,
    normalize_absolute,
    virtual_screen_layout,
)


def test_screen_layout_and_fake_backend_preserve_negative_multi_monitor_bounds():
    layout = ScreenLayout(
        (
            Monitor("left", -1920, -100, 1920, 1200),
            Monitor("primary", 0, 0, 2560, 1440, True),
        )
    )
    backend = FakeMouseBackend(layout)

    assert (layout.x, layout.y, layout.right, layout.bottom) == (-1920, -100, 2560, 1440)
    assert (layout.width, layout.height) == (4480, 1540)
    assert backend.get_pointer_position() == (1280.0, 720.0)


def test_dispatch_failure_releases_buttons_and_preserves_failure():
    class FailingBackend(FakeMouseBackend):
        def move_absolute(self, x: float, y: float) -> None:
            raise OSError("synthetic input failure")

    backend = FailingBackend()
    dispatcher = InputDispatcher(backend)

    with pytest.raises(OSError, match="synthetic input failure"):
        dispatcher.dispatch(
            ActionBatch((Action.button_down(Button.LEFT), Action.move_absolute(1.0, 2.0)))
        )

    assert dispatcher.held == set()
    assert backend.held == set()
    assert [event.kind for event in backend.events] == ["button_down", "button_up"]


def test_dispatcher_release_all_is_idempotent():
    backend = FakeMouseBackend()
    dispatcher = InputDispatcher(backend)
    dispatcher.dispatch(ActionBatch((Action.button_down(Button.RIGHT),)))

    dispatcher.release_all()
    dispatcher.release_all()

    assert not dispatcher.held
    assert not backend.held
    assert [event.kind for event in backend.events] == ["button_down", "button_up"]


def test_dispatcher_close_closes_backend_after_release_failure():
    class BrokenReleaseBackend(FakeMouseBackend):
        def button_up(self, button: Button) -> None:
            raise OSError("synthetic release failure")

        def release_all(self) -> None:
            raise OSError("synthetic release-all failure")

        def close(self) -> None:
            self.closed = True

    backend = BrokenReleaseBackend()
    dispatcher = InputDispatcher(backend)
    dispatcher.held.add(Button.LEFT)

    with pytest.raises(RuntimeError, match="cleanup"):
        dispatcher.close()

    assert backend.closed
    assert dispatcher.held == set()


def test_application_processes_two_queued_toggles_without_a_frame():
    class QueuedListener:
        def process(self, callback):
            callback()
            callback()
            return 2

    backend = FakeMouseBackend()
    dispatcher = InputDispatcher(backend)
    engine = PythonGestureEngine(
        EngineConfig(reacquisition_ms=0, activation_gesture=False),
        armed=True,
    )
    engine._held = Button.LEFT
    dispatcher.held.add(Button.LEFT)
    backend.held.add(Button.LEFT)
    app = object.__new__(Application)
    app._hotkey_listener = QueuedListener()
    app.engine = engine
    app.dispatcher = dispatcher

    app._process_toggle_requests()

    assert engine.armed is True
    assert engine.state.value == "ARMED"
    assert engine._reacquire_since is None
    assert backend.held == set()
    assert [event.kind for event in backend.events] == ["button_up"]


def test_application_cleanup_releases_input_when_engine_reset_fails():
    class BrokenEngine:
        def reset(self, reason: str) -> ActionBatch:
            raise RuntimeError(reason)

    backend = FakeMouseBackend()
    backend.held.add(Button.LEFT)
    dispatcher = InputDispatcher(backend)
    dispatcher.held.add(Button.LEFT)
    app = object.__new__(Application)
    app._cleaned = False
    app._hotkey_listener = None
    app.engine = BrokenEngine()
    app.dispatcher = dispatcher
    app.preview = False
    app._signal_handlers = {}
    app._signals_installed = False

    app._cleanup(None, None)
    app._cleanup(None, None)

    assert backend.closed
    assert not backend.held
    assert not dispatcher.held


def test_xrandr_parser_handles_primary_and_negative_monitor_origin():
    layout = parse_xrandr_monitors(
        """Monitors: 2
 0: +*DP-1 2560/600x1440/340+0+0 DP-1
 1: +HDMI-1 1920/520x1080/290-1920-100 HDMI-1
"""
    )

    assert [
        (monitor.name, monitor.x, monitor.y, monitor.primary) for monitor in layout.monitors
    ] == [
        ("DP-1", 0, 0, True),
        ("HDMI-1", -1920, -100, False),
    ]


def test_x11_layout_queries_xrandr_without_falling_back_to_fake_bounds(
    monkeypatch: pytest.MonkeyPatch,
):
    import mgesture.input.pynput_backend as x11

    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(x11.sys, "platform", "linux")
    monkeypatch.setattr(
        x11.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=" 0: +*DP-1 1280/300x720/170-1280+0 DP-1\n",
            stderr="",
        ),
    )

    layout = x11_screen_layout()
    assert (layout.x, layout.y, layout.width, layout.height) == (-1280, 0, 1280, 720)


def test_windows_virtual_desktop_normalization_handles_negative_coordinates():
    class Metrics:
        values = {76: -1920, 77: -100, 78: 3840, 79: 1200}

        def GetSystemMetrics(self, index: int) -> int:
            return self.values[index]

    layout = virtual_screen_layout(Metrics())
    assert normalize_absolute(-1920, -100, layout) == (0, 0)
    assert normalize_absolute(1919, 1099, layout) == (65535, 65535)
    assert normalize_absolute(-5000, 5000, layout) == (0, 65535)


def test_windows_backend_requests_per_monitor_dpi_awareness():
    contexts: list[object] = []
    user32 = SimpleNamespace(
        SetProcessDpiAwarenessContext=lambda context: contexts.append(context) or 1
    )

    assert enable_process_dpi_awareness(user32)
    assert contexts[0].value == ctypes.c_void_p(-4).value  # type: ignore[attr-defined]


def test_quartz_layout_uses_active_logical_displays_without_pointer_access():
    class Quartz:
        def CGMainDisplayID(self) -> int:
            return 100

        def CGGetActiveDisplayList(self, *_args: object) -> tuple[int, tuple[int, ...], int]:
            return 0, (100, 200), 2

        def CGDisplayBounds(self, display: int) -> SimpleNamespace:
            return SimpleNamespace(
                origin=SimpleNamespace(x=0 if display == 100 else -1440, y=0),
                size=SimpleNamespace(width=1440, height=900),
            )

    quartz = Quartz()
    assert active_display_ids(quartz) == (100, 200)
    backend = object.__new__(MacOSMouseBackend)
    backend._quartz = quartz
    layout = backend.get_screen_layout()

    assert [(monitor.x, monitor.width, monitor.primary) for monitor in layout.monitors] == [
        (0, 1440, True),
        (-1440, 1440, False),
    ]


def test_wayland_absolute_emulation_suppresses_unknown_initial_cursor_position():
    class Device:
        def __init__(self) -> None:
            self.events: list[tuple[object, object, int]] = []

        def write(self, event_type: object, code: object, value: int) -> None:
            self.events.append((event_type, code, value))

        def syn(self) -> None:
            pass

    backend = object.__new__(LinuxWaylandBackend)
    backend._ui = Device()
    backend._ecodes = SimpleNamespace(EV_REL=1, REL_X=2, REL_Y=3)
    backend._held = set()
    backend._position = None
    backend._closed = False

    backend.move_absolute(100.0, 200.0)
    assert backend._ui.events == []
    backend.move_absolute(110.0, 215.0)
    assert backend._ui.events == [(1, 2, 10), (1, 3, 15)]
