from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from convtui.cli import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
runner = CliRunner()


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A source folder with distinct stems, so nothing collides by accident."""
    root = tmp_path / "docs"
    (root / "nested").mkdir(parents=True)
    shutil.copy(FIXTURES / "sample.docx", root / "report.docx")
    shutil.copy(FIXTURES / "sample.pdf", root / "manual.pdf")
    shutil.copy(FIXTURES / "sample.csv", root / "nested" / "data.csv")
    return root


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "convtui" in result.stdout


def test_formats_lists_backends():
    result = runner.invoke(app, ["formats"])
    assert result.exit_code == 0
    assert "markitdown" in result.stdout


def test_convert_mirrors_tree(docs, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["convert", str(docs), "-o", str(out), "--to", "md"])
    assert result.exit_code == 0
    assert (out / "report.md").is_file()
    assert (out / "manual.md").is_file()
    assert (out / "nested" / "data.md").is_file()


def test_dry_run_writes_nothing(docs, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["convert", str(docs), "-o", str(out), "-n"])
    assert result.exit_code == 0
    assert not out.exists()


def test_json_output_is_one_object_per_line(docs, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["convert", str(docs), "-o", str(out), "--json"])
    assert result.exit_code == 0
    lines = [json.loads(ln) for ln in result.stdout.strip().splitlines()]
    assert lines[-1]["summary"]["done"] == 3
    assert all("src" in ln for ln in lines[:-1])


def test_failure_exits_one(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "broken.pdf").write_bytes(b"")
    result = runner.invoke(app, ["convert", str(src), "-o", str(tmp_path / "out")])
    assert result.exit_code == 1


def test_missing_source_exits_two(tmp_path):
    result = runner.invoke(app, ["convert", str(tmp_path / "ghost"), "-o", str(tmp_path / "out")])
    assert result.exit_code == 2


def test_exclusive_collision_flags_exit_two(docs, tmp_path):
    result = runner.invoke(
        app, ["convert", str(docs), "-o", str(tmp_path / "out"), "--overwrite", "--rename"]
    )
    assert result.exit_code == 2


def test_unknown_converter_exits_two(docs, tmp_path):
    result = runner.invoke(
        app, ["convert", str(docs), "-o", str(tmp_path / "out"), "--converter", "ghost"]
    )
    assert result.exit_code == 2


def test_second_run_skips_everything(docs, tmp_path):
    out = tmp_path / "out"
    runner.invoke(app, ["convert", str(docs), "-o", str(out)])
    result = runner.invoke(app, ["convert", str(docs), "-o", str(out), "--json"])
    assert result.exit_code == 0
    summary = json.loads(result.stdout.strip().splitlines()[-1])["summary"]
    assert summary == {"done": 0, "failed": 0, "skipped": 3}


def test_overwrite_reconverts(docs, tmp_path):
    out = tmp_path / "out"
    runner.invoke(app, ["convert", str(docs), "-o", str(out)])
    (out / "report.md").write_text("stale")
    runner.invoke(app, ["convert", str(docs), "-o", str(out), "--overwrite"])
    assert "stale" not in (out / "report.md").read_text()


def test_include_glob(docs, tmp_path):
    out = tmp_path / "out"
    runner.invoke(app, ["convert", str(docs), "-o", str(out), "--include", "*.pdf"])
    assert (out / "manual.md").is_file()
    assert not (out / "report.md").exists()


def test_bare_path_argument_opens_the_tui(docs, monkeypatch):
    """`convtui ./docs` must reach the TUI, not be read as a subcommand name."""
    opened: list[Path] = []
    monkeypatch.setattr("convtui.cli._launch_tui", lambda root: opened.append(root))
    from convtui.cli import main

    with pytest.raises(SystemExit) as exc:
        main([str(docs)])
    assert exc.value.code == 0
    assert opened == [docs]


def test_subcommand_is_not_swallowed_by_the_path_argument(monkeypatch):
    monkeypatch.setattr(
        "convtui.cli._launch_tui", lambda root: pytest.fail("should not open the TUI")
    )
    from convtui.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["formats"])
    assert exc.value.code == 0
