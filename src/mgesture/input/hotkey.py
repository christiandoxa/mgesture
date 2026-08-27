from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

_MODIFIERS = {"ctrl", "alt", "shift", "cmd"}


def normalize_shortcut(shortcut: str) -> str:
    """Convert config shortcut names to pynput's GlobalHotKeys syntax."""
    return "+".join(
        f"<{part}>" if part in _MODIFIERS else part
        for part in (piece.strip().casefold() for piece in shortcut.split("+"))
    )


class GlobalShortcutListener:
    """Queue edge-triggered global shortcut activations from pynput."""

    def __init__(self, shortcut: str) -> None:
        self.shortcut = normalize_shortcut(shortcut)
        self._pending = 0
        self._lock = threading.Lock()
        self._listener: Any = None

    def _queue_toggle(self) -> None:
        with self._lock:
            self._pending += 1

    def start(self) -> None:
        if self._listener is not None:
            return
        from pynput import keyboard  # type: ignore[import-untyped]

        listener = keyboard.GlobalHotKeys({self.shortcut: self._queue_toggle})
        try:
            listener.start()
        except Exception:
            try:
                listener.stop()
            except Exception:
                pass
            raise
        self._listener = listener

    def drain(self) -> int:
        with self._lock:
            pending, self._pending = self._pending, 0
        return pending

    def process(self, on_toggle: Callable[[], None]) -> int:
        pending = self.drain()
        for _ in range(pending):
            on_toggle()
        return pending

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        try:
            if listener is not None:
                listener.stop()
        finally:
            with self._lock:
                self._pending = 0
