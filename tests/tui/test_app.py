from __future__ import annotations

from convtui.core.models import CollisionPolicy, JobState
from convtui.tui.screens import ConfirmScreen, HelpScreen
from convtui.tui.widgets import FileList, QueuePane, StatusBar


async def test_starts_with_three_panes_and_lists_files(app, workspace):
    async with app.run_test() as pilot:
        await pilot.pause()
        files = app.query_one("#files", FileList)
        assert sorted(p.name for p in files.paths) == ["manual.pdf", "report.docx"]
        assert app.query_one("#queue", QueuePane) is not None
        assert app.query_one("#status", StatusBar) is not None


async def test_help_opens_and_closes(app):
    async with app.run_test() as pilot:
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_space_toggles_selection(app):
    async with app.run_test() as pilot:
        app.query_one("#files", FileList).focus()
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
        assert len(app.query_one("#files", FileList).selected) == 1
        await pilot.press("space")
        await pilot.pause()
        assert len(app.query_one("#files", FileList).selected) == 0


async def test_select_all_and_clear(app):
    async with app.run_test() as pilot:
        files = app.query_one("#files", FileList)
        files.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert len(files.selected) == 2
        assert app.query_one("#status", StatusBar).selected == 2
        await pilot.press("A")
        await pilot.pause()
        assert len(files.selected) == 0


async def test_policy_cycles_through_all_four(app):
    async with app.run_test() as pilot:
        seen = [app.collision]
        for _ in range(3):
            await pilot.press("p")
            await pilot.pause()
            seen.append(app.collision)
        assert set(seen) == set(CollisionPolicy)


async def test_filter_narrows_the_list(app):
    async with app.run_test() as pilot:
        files = app.query_one("#files", FileList)
        files.set_filter("*.pdf")
        await pilot.pause()
        assert [p.name for p in files.visible_paths] == ["manual.pdf"]


async def test_convert_runs_and_writes_output(app, workspace, tmp_path):
    async with app.run_test() as pilot:
        files = app.query_one("#files", FileList)
        files.focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("enter")  # approve
        for _ in range(40):
            await pilot.pause(0.05)
            if app.plan and all(j.state is not JobState.QUEUED for j in app.plan.jobs):
                break
        assert app.plan is not None
        assert all(j.state is JobState.DONE for j in app.plan.jobs)
        assert (tmp_path / "out" / "report.md").is_file()
        assert (tmp_path / "out" / "manual.md").is_file()


async def test_confirm_can_be_cancelled_without_writing(app, tmp_path):
    async with app.run_test() as pilot:
        app.query_one("#files", FileList).focus()
        await pilot.pause()
        await pilot.press("a")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.plan is None
        assert not (tmp_path / "out").exists()


async def test_quit_is_blocked_while_a_run_is_active(app, monkeypatch):
    async with app.run_test() as pilot:
        app.executor = object()  # pretend a run is in flight
        await pilot.press("q")
        await pilot.pause()
        assert app.is_running
        app.executor = None


async def test_retry_with_nothing_failed_is_harmless(app):
    async with app.run_test() as pilot:
        await pilot.press("r")
        await pilot.pause()
        assert app.is_running


async def test_save_settings_writes_config(app, tmp_path):
    async with app.run_test() as pilot:
        await pilot.press("p")  # change something first
        await pilot.press("s")
        await pilot.pause()
        assert (tmp_path / "config.toml").is_file()
        assert app.config.collision is not CollisionPolicy.SKIP
