from __future__ import annotations

import sys
import types

from mgesture.input.hotkey import GlobalShortcutListener, normalize_shortcut


def test_normalize_shortcut_uses_global_hotkeys_names() -> None:
    assert normalize_shortcut(" Ctrl + ALT + M ") == "<ctrl>+<alt>+m"
    assert normalize_shortcut("<CTRL>+<ALT>+M") == "<ctrl>+<alt>+m"


def test_global_shortcut_lifecycle_preserves_edges_and_queue(monkeypatch) -> None:
    class FakeGlobalHotKeys:
        instances: list[FakeGlobalHotKeys] = []

        def __init__(self, hotkeys):
            self.hotkeys = hotkeys
            self.pressed = False
            self.started = False
            self.stopped = 0
            self.instances.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped += 1

        def press(self):
            if not self.pressed:
                next(iter(self.hotkeys.values()))()
            self.pressed = True

        def release(self):
            self.pressed = False

    keyboard = types.ModuleType("pynput.keyboard")
    keyboard.GlobalHotKeys = FakeGlobalHotKeys  # type: ignore[attr-defined]
    pynput = types.ModuleType("pynput")
    pynput.keyboard = keyboard  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)

    listener = GlobalShortcutListener("ctrl+alt+m")
    listener.start()
    listener.start()
    fake = FakeGlobalHotKeys.instances[0]

    assert tuple(fake.hotkeys) == ("<ctrl>+<alt>+m",)
    fake.press()
    fake.press()
    assert listener.drain() == 1
    fake.release()
    fake.press()
    assert listener.process(lambda: None) == 1
    assert len(FakeGlobalHotKeys.instances) == 1

    fake.release()
    fake.press()
    listener.stop()
    listener.stop()
    assert fake.started
    assert fake.stopped == 1
    assert listener.drain() == 0
