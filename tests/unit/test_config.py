from pathlib import Path

from mgesture.config import config_text, load_config, write_config


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.toml"
    write_config(load_config(path), path)
    loaded = load_config(path)
    assert loaded.camera.mirror is True
    assert loaded.compute.mode == "auto"
    assert "[performance]" in config_text(loaded)
