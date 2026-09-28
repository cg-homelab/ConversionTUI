from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from convtui.core.config import Config
from convtui.tui.app import ConvtuiApp

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch) -> Path:
    """A source folder plus an isolated config, so tests never touch ~/.config."""
    root = tmp_path / "docs"
    (root / "nested").mkdir(parents=True)
    shutil.copy(FIXTURES / "sample.docx", root / "report.docx")
    shutil.copy(FIXTURES / "sample.pdf", root / "manual.pdf")
    shutil.copy(FIXTURES / "sample.csv", root / "nested" / "data.csv")
    monkeypatch.setattr("convtui.core.config.config_path", lambda: tmp_path / "config.toml")
    Config(output_dir=str(tmp_path / "out")).save(tmp_path / "config.toml")
    return root


@pytest.fixture
def app(workspace: Path) -> ConvtuiApp:
    return ConvtuiApp(root=workspace)
