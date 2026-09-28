"""User configuration: XDG TOML, created lazily on first change.

Precedence is CLI flags > CONVTUI_* env vars > config file > defaults. A
malformed config degrades to defaults with a warning; it must never stop the
tool from starting.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_path

from convtui.core.executor import default_workers
from convtui.core.models import CollisionPolicy
from convtui.core.planner import DEFAULT_EXCLUDES

try:  # tomllib is stdlib from 3.11; 3.10 needs the backport shim
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on 3.10
    import tomli as tomllib  # type: ignore[no-redef]

APP_NAME = "convtui"
ENV_PREFIX = "CONVTUI_"


def config_path() -> Path:
    return user_config_path(APP_NAME) / "config.toml"


@dataclass
class Config:
    output_dir: str = "./out"
    target_format: str = "md"
    collision: CollisionPolicy = CollisionPolicy.SKIP
    workers: int = field(default_factory=default_workers)
    recursive: bool = True
    theme: str = "gruvbox"
    show_hidden: bool = False
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))

    # ---- loading -------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> tuple[Config, str | None]:
        """Read config file then env. Returns (config, warning)."""
        path = path or config_path()
        cfg = cls()
        warning: str | None = None
        if path.is_file():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                warning = f"ignoring unreadable config {path}: {exc}"
            else:
                cfg, warning = cls._from_dict(data)
        return cfg._with_env(), warning

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> tuple[Config, str | None]:
        defaults = data.get("defaults", {})
        ui = data.get("ui", {})
        excl = data.get("exclude", {})
        cfg = cls()
        warning = None
        try:
            if "collision" in defaults:
                cfg = replace(cfg, collision=CollisionPolicy(defaults["collision"]))
        except ValueError:
            warning = f"unknown collision policy {defaults['collision']!r}; using 'skip'"
        for key in ("output_dir", "target_format", "workers", "recursive"):
            if key in defaults:
                cfg = replace(cfg, **{key: defaults[key]})
        for key in ("theme", "show_hidden"):
            if key in ui:
                cfg = replace(cfg, **{key: ui[key]})
        if "globs" in excl:
            cfg = replace(cfg, exclude=list(excl["globs"]))
        return cfg, warning

    def _with_env(self) -> Config:
        """Apply CONVTUI_* overrides over whatever the file provided."""
        cfg = self
        env = os.environ
        if v := env.get(f"{ENV_PREFIX}OUTPUT_DIR"):
            cfg = replace(cfg, output_dir=v)
        if v := env.get(f"{ENV_PREFIX}FORMAT"):
            cfg = replace(cfg, target_format=v)
        if v := env.get(f"{ENV_PREFIX}COLLISION"):
            with contextlib.suppress(ValueError):
                cfg = replace(cfg, collision=CollisionPolicy(v))
        if v := env.get(f"{ENV_PREFIX}WORKERS"):
            with_int = _int_or_none(v)
            if with_int:
                cfg = replace(cfg, workers=with_int)
        if v := env.get(f"{ENV_PREFIX}THEME"):
            cfg = replace(cfg, theme=v)
        return cfg

    # ---- saving --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {
            "defaults": {
                "output_dir": d["output_dir"],
                "target_format": d["target_format"],
                "collision": self.collision.value,
                "workers": d["workers"],
                "recursive": d["recursive"],
            },
            "ui": {"theme": d["theme"], "show_hidden": d["show_hidden"]},
            "exclude": {"globs": d["exclude"]},
        }

    def save(self, path: Path | None = None) -> Path:
        """Write the config, creating the directory on first use."""
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(self.to_dict()), encoding="utf-8")
        return path


def _int_or_none(value: str) -> int | None:
    try:
        n = int(value)
    except ValueError:
        return None
    return n if n > 0 else None
