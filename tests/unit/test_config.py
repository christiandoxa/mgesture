import json
from pathlib import Path

from mgesture import config
from mgesture.config import config_text, load_config, write_config


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    write_config(load_config(path), path)
    loaded = load_config(path)
    assert loaded.camera.mirror is True
    assert loaded.compute.mode == "auto"
    assert "[performance]" in config_text(loaded)


def test_onboarding_state_round_trip(tmp_path: Path, monkeypatch):
    state = tmp_path / "mgesture" / "state.json"
    monkeypatch.setattr(config, "state_path", lambda: state)

    assert config.onboarding_completed() is False
    config.set_onboarding_completed()
    assert config.onboarding_completed() is True
    assert json.loads(state.read_text())["schema_version"] == 1


def test_reset_removes_only_owned_user_directories(tmp_path: Path, monkeypatch):
    roots = {name: tmp_path / name / "mgesture" for name in ("config", "data", "cache", "logs")}
    for root in roots.values():
        root.mkdir(parents=True)
        (root / "owned").write_text("x")
    keep = tmp_path / "keep.txt"
    keep.write_text("keep")
    monkeypatch.setattr(config, "config_path", lambda: roots["config"] / "config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: roots["data"])
    monkeypatch.setattr(config, "cache_dir", lambda: roots["cache"])
    monkeypatch.setattr(config, "log_dir", lambda: roots["logs"])

    removed = config.reset_user_data()

    assert len(removed) == 4
    assert keep.read_text() == "keep"
    assert all(not root.exists() for root in roots.values())
    assert config.reset_user_data() == ()


def test_reset_rejects_symlinked_owned_directory(tmp_path: Path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "mgesture"
    link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(config, "data_dir", lambda: link)
    monkeypatch.setattr(
        config, "config_path", lambda: tmp_path / "config" / "mgesture" / "config.toml"
    )
    monkeypatch.setattr(config, "cache_dir", lambda: tmp_path / "cache" / "mgesture")
    monkeypatch.setattr(config, "log_dir", lambda: tmp_path / "logs" / "mgesture")

    try:
        config.reset_user_data()
    except RuntimeError as exc:
        assert "unsafe" in str(exc)
    else:
        raise AssertionError("symlinked reset target was accepted")
    assert outside.exists()
