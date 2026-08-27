from __future__ import annotations

from pathlib import Path

import pytest

import mgesture.cli as cli
from mgesture.cli import _parser, main


def test_landmark_recording_requires_explicit_developer_flag() -> None:
    args = _parser().parse_args(["record-landmarks", "--output", "recording.jsonl"])
    assert args.developer is False

    with pytest.raises(SystemExit, match="developer-only"):
        main(["record-landmarks", "--output", "recording.jsonl"])


def test_help_and_version_are_available() -> None:
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    assert help_exit.value.code == 0
    with pytest.raises(SystemExit) as version_exit:
        main(["--version"])
    assert version_exit.value.code == 0


def test_zero_argument_startup_reuses_run_path(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(cli, "_run_application", lambda args: calls.append(args) or 0)

    with pytest.raises(SystemExit) as first:
        main([])
    with pytest.raises(SystemExit) as explicit:
        main(["run"])

    assert first.value.code == explicit.value.code == 0
    assert calls[0].command == calls[1].command == "run"
    for name in ("camera", "engine", "compute", "backend", "profile", "preview", "armed"):
        assert getattr(calls[0], name) == getattr(calls[1], name)


def test_run_hand_selection_reaches_application(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []

    class Application:
        def __init__(self, config, *args):
            captured.append((config.vision.hand_selection, config.vision.handedness_mirror))

        def run(self):
            return 0

    monkeypatch.setattr(cli, "Application", Application)
    monkeypatch.setattr(cli, "onboarding_completed", lambda: True)

    assert (
        cli._run_application(_parser().parse_args(["run", "--hand", "left", "--mirror", "on"])) == 0
    )
    assert str(captured[0][0]) == "left"
    assert captured[0][1] == "on"


def test_invalid_hand_selection_is_rejected() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["run", "--hand", "banana"])


def test_reset_requires_confirmation_for_noninteractive_input(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as result:
        main(["--reset"])
    assert result.value.code == 2


def test_reset_yes_delegates_to_user_state_owner(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(cli, "reset_user_data", lambda: calls.append(True) or ("configuration",))

    with pytest.raises(SystemExit) as result:
        main(["--reset", "--yes"])

    assert result.value.code == 0
    assert calls == [True]


def test_reset_dry_run_never_calls_delete(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class Target:
        label = "configuration"
        path = Path("/tmp/mgesture-config")

    monkeypatch.setattr(cli, "reset_targets", lambda: (Target(),))
    monkeypatch.setattr(
        cli,
        "reset_user_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("delete called")),
    )

    with pytest.raises(SystemExit) as result:
        main(["--reset", "--dry-run"])

    assert result.value.code == 0
    assert "Nothing was deleted." in capsys.readouterr().out


def test_first_run_runs_tutorial_before_application(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class Application:
        def __init__(self, *args):
            calls.append("application")

        def run(self):
            calls.append("run")
            return 0

    monkeypatch.setattr(cli, "Application", Application)
    monkeypatch.setattr(cli, "onboarding_completed", lambda: False)
    monkeypatch.setattr(cli, "run_tutorial", lambda config, **kwargs: calls.append("tutorial") or 0)

    assert cli._run_application(_parser().parse_args(["run"])) == 0
    assert calls == ["tutorial", "application", "run"]


def test_self_test_platform_input_flag_is_forwarded(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "run_self_test",
        lambda **kwargs: calls.append(kwargs) or {"passed": True},
    )

    with pytest.raises(SystemExit) as result:
        cli.main(["self-test", "--platform-input"])

    assert result.value.code == 0
    assert calls == [
        {"require_mojo": False, "engine_request": "auto", "check_platform_input": True}
    ]
