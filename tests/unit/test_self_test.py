from __future__ import annotations

import mgesture.self_test as self_test
from mgesture.input import Monitor, ScreenLayout


def test_platform_input_checks_probe_modules_without_moving_cursor(monkeypatch):
    imported: list[str] = []

    class Listener:
        def __init__(self, _shortcut):
            self.stopped = False

        def start(self):
            pass

        def stop(self):
            self.stopped = True

    class Backend:
        name = "fake-platform"
        moved = False

        def get_screen_layout(self):
            return ScreenLayout((Monitor("primary", 0, 0, 1920, 1080, True),))

        def close(self):
            pass

        def move_absolute(self, *_args):
            self.moved = True

    backend = Backend()
    monkeypatch.setattr(
        self_test.importlib,
        "import_module",
        lambda name: imported.append(name) or object(),
    )
    monkeypatch.setattr(self_test, "GlobalShortcutListener", Listener)
    monkeypatch.setattr(self_test, "create_backend", lambda: backend)

    assert self_test.platform_input_checks() == {
        "input_modules": "passed",
        "keyboard_listener": "passed",
        "mouse_backend": "passed",
    }
    assert imported == list(self_test._PLATFORM_INPUT_MODULES)
    assert backend.moved is False
