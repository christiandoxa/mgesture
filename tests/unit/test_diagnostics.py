from __future__ import annotations

from types import SimpleNamespace

import pytest

import mgesture.diagnostics as diagnostics
from mgesture.config import AppConfig


def test_pynput_dynamic_module_failure_is_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    def import_module(name: str) -> object:
        assert name == "pynput"
        cause = ModuleNotFoundError("No module named 'pynput.keyboard._xorg'")
        raise ImportError("pynput backend unavailable") from cause

    monkeypatch.setattr(diagnostics.importlib, "import_module", import_module)

    check = diagnostics._pynput_capability_check("ctrl+alt+m", True)

    assert not check.ok
    assert "missing packaged pynput dynamic module" in check.detail
    assert "pynput.keyboard._xorg" in check.detail
    assert check.data == {
        "keyboard": False,
        "mouse": False,
        "hotkey": False,
        "configured_shortcut": "ctrl+alt+m",
        "listener_started": False,
    }


def test_x11_display_check_reports_missing_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)

    check = diagnostics._x11_display_check()

    assert not check.ok
    assert check.detail == "DISPLAY is not set"
    assert "X11 session" in check.remediation


def test_x11_xtest_check_reports_missing_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[str] = []

    class Display:
        def __init__(self, name: str) -> None:
            assert name == ":99"

        def query_extension(self, name: str) -> SimpleNamespace:
            assert name == "XTEST"
            return SimpleNamespace(present=False, major_opcode=0)

        def close(self) -> None:
            closed.append("closed")

    def import_module(name: str) -> object:
        if name == "Xlib.ext.xtest":
            return SimpleNamespace()
        if name == "Xlib.display":
            return SimpleNamespace(Display=Display)
        raise AssertionError(name)

    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setattr(diagnostics.importlib, "import_module", import_module)

    check = diagnostics._x11_xtest_check(diagnostics.Check("X11 display", True, "connected"))

    assert not check.ok
    assert check.detail == "XTest extension is unavailable"
    assert closed == ["closed"]


def test_xrandr_check_reports_missing_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)

    check = diagnostics._xrandr_check()

    assert not check.ok
    assert check.detail == "command not found"


def test_pynput_capability_probe_does_not_create_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HotKey:
        @staticmethod
        def parse(_value: str) -> tuple[str]:
            return ("m",)

    def global_hotkeys(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("diagnostics must not create a global listener")

    pynput = SimpleNamespace(
        keyboard=SimpleNamespace(
            Controller=lambda: None,
            GlobalHotKeys=global_hotkeys,
            HotKey=HotKey,
        ),
        mouse=SimpleNamespace(Controller=lambda: None),
    )
    monkeypatch.setattr(diagnostics.importlib, "import_module", lambda name: pynput)

    check = diagnostics._pynput_capability_check("ctrl+alt+m", True)

    assert check.ok
    assert check.data is not None
    assert check.data["keyboard"] is True
    assert check.data["mouse"] is True
    assert check.data["hotkey"] is True
    assert check.data["listener_started"] is False
    assert "listener=not started" in check.detail


def test_wayland_auto_backend_skips_linux_x11_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")

    assert diagnostics._linux_x11_selected(AppConfig()) is False
