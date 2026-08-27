import json
from pathlib import Path

import pytest

from mgesture import config
from mgesture.config import (
    AppConfig,
    GestureConfig,
    config_text,
    effective_handedness_mirror,
    effective_preview_mirror,
    load_config,
    validate,
    with_overrides,
    write_config,
)
from mgesture.engine import HandSelection


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    write_config(load_config(path), path)
    loaded = load_config(path)
    assert loaded.camera.mirror is True
    assert loaded.compute.mode == "auto"
    assert loaded.vision.hand_selection is HandSelection.AUTO
    assert loaded.gesture.scroll_exit_grace_ms == 120
    assert "[performance]" in config_text(loaded)
    assert "scroll_exit_grace_ms = 120" in config_text(loaded)


def test_hand_selection_config_round_trip_and_override(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[vision]\nhand_selection = "left"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.vision.hand_selection is HandSelection.LEFT
    assert (
        with_overrides(loaded, hand_selection="either").vision.hand_selection
        is HandSelection.EITHER
    )


def test_legacy_config_keeps_right_hand_and_mirror_behavior(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[camera]\nmirror = true\n[vision]\nhandedness_mirrored_input = true\n",
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.vision.hand_selection is HandSelection.RIGHT
    assert effective_handedness_mirror(loaded.vision) is True
    assert effective_preview_mirror(loaded.camera) is True


def test_transform_policies_round_trip_independently(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[camera]\npreview_mirror = "off"\n'
        '[vision]\nhandedness_mirror = "on"\nhand_selection = "either"\n'
        "[gesture]\npointer_mirror = false\n",
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.camera.preview_mirror == "off"
    assert loaded.vision.handedness_mirror == "on"
    assert loaded.vision.hand_selection is HandSelection.EITHER
    assert loaded.gesture.pointer_mirror is False
    assert effective_preview_mirror(loaded.camera) is False
    assert effective_handedness_mirror(loaded.vision) is True


def test_onboarding_state_round_trip(tmp_path: Path, monkeypatch):
    state = tmp_path / "mgesture" / "state.json"
    monkeypatch.setattr(config, "state_path", lambda: state)

    assert config.onboarding_completed() is False
    config.set_onboarding_completed()
    assert config.onboarding_completed() is True
    assert json.loads(state.read_text())["schema_version"] == 1


def test_scroll_exit_grace_must_be_nonnegative():
    with pytest.raises(ValueError, match="scroll_exit_grace_ms"):
        validate(AppConfig(gesture=GestureConfig(scroll_exit_grace_ms=-1)))


def test_reset_removes_only_owned_user_directories(tmp_path: Path, monkeypatch):
    roots = {name: tmp_path / name / "mgesture" for name in ("config", "data", "cache", "logs")}
    for root in roots.values():
        root.mkdir(parents=True)
        (root / "owned").write_text("x")
    (roots["config"] / "config.toml").write_text("config")
    keep = tmp_path / "keep.txt"
    keep.write_text("keep")
    monkeypatch.setattr(config, "config_path", lambda: roots["config"] / "config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: roots["data"])
    monkeypatch.setattr(config, "cache_dir", lambda: roots["cache"])
    monkeypatch.setattr(config, "log_dir", lambda: roots["logs"])

    removed = config.reset_user_data()

    assert len(removed) == 4
    assert keep.read_text() == "keep"
    assert roots["config"].exists()
    assert not (roots["config"] / "config.toml").exists()
    assert all(not roots[name].exists() for name in ("data", "cache", "logs"))
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


def test_reset_dry_run_does_not_delete_user_state(tmp_path: Path, monkeypatch):
    roots = {name: tmp_path / name / "mgesture" for name in ("config", "data", "cache", "logs")}
    for root in roots.values():
        root.mkdir(parents=True)
        (root / "owned").write_text("x")
    (roots["config"] / "config.toml").write_text("config")
    monkeypatch.setattr(config, "config_path", lambda: roots["config"] / "config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: roots["data"])
    monkeypatch.setattr(config, "cache_dir", lambda: roots["cache"])
    monkeypatch.setattr(config, "log_dir", lambda: roots["logs"])

    labels = config.reset_user_data(dry_run=True)

    assert labels == (
        "configuration",
        "user data, calibration, tutorial state, and recordings",
        "cached application data",
        "application logs",
    )
    assert all(root.exists() for root in roots.values())


def test_reset_unlinks_symlink_children_without_following_them(tmp_path: Path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "keep.txt"
    secret.write_text("keep")
    cache = tmp_path / "cache" / "mgesture"
    cache.mkdir(parents=True)
    (cache / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config/mgesture/config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data/mgesture")
    monkeypatch.setattr(config, "cache_dir", lambda: cache)
    monkeypatch.setattr(config, "log_dir", lambda: tmp_path / "logs/mgesture")

    config.reset_user_data()

    assert secret.read_text() == "keep"


def test_reset_preserves_direct_standalone_bundle(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "mgesture"
    binary = bundle / "bin/mgesture"
    native = bundle / "runtime/mojo/libmgesture_mojo.so"
    model = bundle / "share/mgesture/models/hand_landmarker.task"
    binary.parent.mkdir(parents=True)
    native.parent.mkdir(parents=True)
    model.parent.mkdir(parents=True)
    binary.write_text("binary")
    native.write_text("native")
    model.write_text("model")
    (bundle / "state.json").write_text("state")
    (bundle / "recordings").mkdir()
    monkeypatch.setenv("MGESTURE_BUNDLE_ROOT", str(bundle))
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config/mgesture/config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: bundle)
    monkeypatch.setattr(config, "cache_dir", lambda: tmp_path / "cache/mgesture")
    monkeypatch.setattr(config, "log_dir", lambda: tmp_path / "logs/mgesture")

    config.reset_user_data()

    assert binary.exists()
    assert native.exists()
    assert model.exists()
    assert not (bundle / "state.json").exists()
    assert not (bundle / "recordings").exists()


def test_reset_rejects_non_data_target_inside_installation(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "mgesture"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "current").mkdir()
    (bundle / "releases").mkdir()
    monkeypatch.setenv("MGESTURE_BUNDLE_ROOT", str(bundle))
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config/mgesture/config.toml")
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data/mgesture")
    monkeypatch.setattr(config, "cache_dir", lambda: bundle)
    monkeypatch.setattr(config, "log_dir", lambda: tmp_path / "logs/mgesture")

    try:
        config.reset_targets()
    except RuntimeError as exc:
        assert "installed application" in str(exc)
    else:
        raise AssertionError("reset accepted an installation root as mutable cache")
