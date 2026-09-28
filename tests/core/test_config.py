from __future__ import annotations

from convtui.core.config import Config
from convtui.core.models import CollisionPolicy


def test_defaults_when_no_file(tmp_path):
    cfg, warning = Config.load(tmp_path / "absent.toml")
    assert warning is None
    assert cfg.collision is CollisionPolicy.SKIP
    assert cfg.target_format == "md"
    assert cfg.recursive is True


def test_round_trip_save_and_load(tmp_path):
    path = tmp_path / "config.toml"
    original = Config(output_dir="~/converted", collision=CollisionPolicy.RENAME, workers=8)
    original.save(path)
    loaded, warning = Config.load(path)
    assert warning is None
    assert loaded.output_dir == "~/converted"
    assert loaded.collision is CollisionPolicy.RENAME
    assert loaded.workers == 8


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "deep" / "nested" / "config.toml"
    Config().save(path)
    assert path.is_file()


def test_broken_config_warns_and_falls_back(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not [ valid toml")
    cfg, warning = Config.load(path)
    assert warning is not None and "ignoring unreadable config" in warning
    assert cfg.collision is CollisionPolicy.SKIP


def test_unknown_collision_value_warns_but_keeps_working(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[defaults]\ncollision = "explode"\n')
    cfg, warning = Config.load(path)
    assert warning is not None and "unknown collision policy" in warning
    assert cfg.collision is CollisionPolicy.SKIP


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    Config(workers=2, target_format="md").save(path)
    monkeypatch.setenv("CONVTUI_WORKERS", "7")
    monkeypatch.setenv("CONVTUI_FORMAT", "html")
    monkeypatch.setenv("CONVTUI_COLLISION", "overwrite")
    cfg, _ = Config.load(path)
    assert cfg.workers == 7
    assert cfg.target_format == "html"
    assert cfg.collision is CollisionPolicy.OVERWRITE


def test_bad_env_values_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("CONVTUI_WORKERS", "not-a-number")
    monkeypatch.setenv("CONVTUI_COLLISION", "nonsense")
    cfg, _ = Config.load(tmp_path / "absent.toml")
    assert cfg.workers >= 1
    assert cfg.collision is CollisionPolicy.SKIP
