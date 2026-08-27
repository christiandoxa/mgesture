from .dispatcher import InputDispatcher
from .factory import create_backend
from .fake_backend import FakeMouseBackend
from .hotkey import GlobalShortcutListener, normalize_shortcut
from .protocol import Monitor, MouseBackend, ScreenLayout

__all__ = [
    "FakeMouseBackend",
    "GlobalShortcutListener",
    "InputDispatcher",
    "Monitor",
    "MouseBackend",
    "ScreenLayout",
    "create_backend",
    "normalize_shortcut",
]
