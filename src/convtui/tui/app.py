"""The convtui application shell.

Three panes, lazygit style, over the same core the CLI uses. The only subtlety
worth remembering: conversions run on worker threads, so every widget update
coming out of a worker goes through `call_from_thread`.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header

from convtui.core.config import Config
from convtui.core.executor import ThreadExecutor
from convtui.core.models import CollisionPolicy, Job, JobState, Plan, Summary
from convtui.core.planner import PlanError, build_plan
from convtui.core.registry import Registry, load_backends
from convtui.tui.screens import ConfirmScreen, DetailScreen, HelpScreen, PromptScreen
from convtui.tui.widgets import FileList, QueuePane, SourceTree, StatusBar

POLICY_CYCLE: tuple[CollisionPolicy, ...] = (
    CollisionPolicy.SKIP,
    CollisionPolicy.OVERWRITE,
    CollisionPolicy.RENAME,
    CollisionPolicy.IN_PLACE,
)


class ConvtuiApp(App[None]):
    """Pick files on the left, watch them convert on the right."""

    CSS_PATH = "app.tcss"
    TITLE = "convtui"

    BINDINGS = [
        Binding("question_mark", "help", "help"),
        Binding("tab", "focus_next_pane", "pane", show=False),
        Binding("1", "focus_pane('tree')", "tree", show=False),
        Binding("2", "focus_pane('files')", "files", show=False),
        Binding("3", "focus_pane('queue')", "queue", show=False),
        Binding("slash", "filter", "filter"),
        Binding("t", "set_target", "format"),
        Binding("o", "set_output", "output"),
        Binding("p", "cycle_policy", "policy"),
        Binding("c", "cancel", "cancel"),
        Binding("r", "retry", "retry"),
        Binding("s", "save_settings", "save"),
        Binding("q", "request_quit", "quit"),
    ]

    def __init__(self, root: Path | None = None, registry: Registry | None = None) -> None:
        super().__init__()
        self.root = (root or Path.cwd()).resolve()
        self.registry = registry or load_backends()
        self.config, self._config_warning = Config.load()
        self.current_dir = self.root if self.root.is_dir() else self.root.parent
        self.target = self.config.target_format
        self.out_dir = Path(self.config.output_dir).expanduser().resolve()
        self.collision = self.config.collision
        self.executor: ThreadExecutor | None = None
        self.plan: Plan | None = None

    # ---- layout --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="panes"):
            yield SourceTree(str(self.current_dir), id="tree")
            yield FileList(self.registry, id="files")
            yield QueuePane(id="queue")
        yield StatusBar(id="status")
        yield Footer()

    def on_mount(self) -> None:
        for pane_id in ("tree", "files", "queue"):
            self.query_one(f"#{pane_id}").border_title = {
                "tree": "1 Tree",
                "files": "2 Files",
                "queue": "3 Queue",
            }[pane_id]
        self._reload_files()
        self._sync_status()
        self.query_one("#files", FileList).focus()
        if self._config_warning:
            self.notify(self._config_warning, severity="warning", timeout=8)

    # ---- pane plumbing -------------------------------------------------

    def on_source_tree_directory_selected(self, message: SourceTree.DirectorySelected) -> None:
        self.current_dir = message.path
        self._reload_files()

    def on_file_list_selection_changed(self, message: FileList.SelectionChanged) -> None:
        self.query_one("#status", StatusBar).selected = message.count

    def on_file_list_convert_requested(self, message: FileList.ConvertRequested) -> None:
        self.action_convert()

    def on_queue_pane_detail_requested(self, message: QueuePane.DetailRequested) -> None:
        self.push_screen(DetailScreen(message.job))

    def _reload_files(self) -> None:
        files = self.query_one("#files", FileList)
        files.load(self.current_dir, target=self.target, show_hidden=self.config.show_hidden)

    def _sync_status(self) -> None:
        status = self.query_one("#status", StatusBar)
        status.selected = len(self.query_one("#files", FileList).selected)
        status.target = self.target
        status.out_dir = str(self.out_dir)
        status.collision = self.collision
        status.worker_count = self.config.workers

    # ---- navigation actions --------------------------------------------

    def action_focus_pane(self, pane: str) -> None:
        self.query_one(f"#{pane}").focus()

    def action_focus_next_pane(self) -> None:
        order = ["tree", "files", "queue"]
        current = next((p for p in order if self.query_one(f"#{p}").has_focus), order[-1])
        self.query_one(f"#{order[(order.index(current) + 1) % len(order)]}").focus()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    # ---- settings actions ----------------------------------------------

    @work
    async def action_filter(self) -> None:
        pattern = await self.push_screen_wait(
            PromptScreen("Filter files", placeholder="*.pdf or part of a name")
        )
        if pattern is not None:
            self.query_one("#files", FileList).set_filter(pattern)

    @work
    async def action_set_target(self) -> None:
        available = ", ".join(sorted(self.registry.output_extensions()))
        value = await self.push_screen_wait(
            PromptScreen(f"Target format  [dim]({available})[/dim]", value=self.target)
        )
        if value:
            self.target = value.strip().lstrip(".")
            self._reload_files()
            self._sync_status()

    @work
    async def action_set_output(self) -> None:
        value = await self.push_screen_wait(
            PromptScreen("Output directory", value=str(self.out_dir))
        )
        if value:
            self.out_dir = Path(value.strip()).expanduser().resolve()
            self._sync_status()

    def action_cycle_policy(self) -> None:
        index = POLICY_CYCLE.index(self.collision)
        self.collision = POLICY_CYCLE[(index + 1) % len(POLICY_CYCLE)]
        self._sync_status()

    def action_save_settings(self) -> None:
        self.config.target_format = self.target
        self.config.output_dir = str(self.out_dir)
        self.config.collision = self.collision
        path = self.config.save()
        self.notify(f"saved defaults to {path}")

    # ---- the run --------------------------------------------------------

    @work
    async def action_convert(self) -> None:
        files = self.query_one("#files", FileList)
        sources = sorted(files.selected) or files.visible_paths
        if not sources:
            self.notify("nothing to convert", severity="warning")
            return

        try:
            plan = build_plan(
                sources,
                None if self.collision is CollisionPolicy.IN_PLACE else self.out_dir,
                self.target,
                self.registry,
                recursive=self.config.recursive,
                collision=self.collision,
                exclude=self.config.exclude,
                show_hidden=self.config.show_hidden,
            )
        except PlanError as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return

        if await self.push_screen_wait(ConfirmScreen(plan)):
            self.plan = plan
            self.query_one("#queue", QueuePane).set_jobs(plan.jobs)
            self.query_one("#queue", QueuePane).focus()
            self._run_plan(plan)

    @work(thread=True, exclusive=True, group="convert")
    def _run_plan(self, plan: Plan) -> None:
        """Convert on worker threads, reporting each change back to the UI thread."""
        queue = self.query_one("#queue", QueuePane)
        status = self.query_one("#status", StatusBar)

        def on_update(job: Job) -> None:
            self.call_from_thread(queue.update_job, job)

        executor = ThreadExecutor(self.registry, workers=self.config.workers, on_update=on_update)
        self.executor = executor
        self.call_from_thread(setattr, status, "activity", "converting…")
        try:
            for future in executor.submit_all(plan.runnable):
                if future.cancelled():
                    continue
                future.result()
        finally:
            executor.shutdown()
            self.executor = None
            summary = Summary.from_jobs(plan.jobs)
            self.call_from_thread(self._run_finished, summary)

    def _run_finished(self, summary: Summary) -> None:
        self.query_one("#status", StatusBar).activity = ""
        severity = "error" if summary.failed else "information"
        self.notify(str(summary), severity=severity)

    def action_cancel(self) -> None:
        executor = self.executor
        if executor is None:
            return
        executor.cancel_all()
        inflight = executor.inflight
        status = self.query_one("#status", StatusBar)
        # Be honest: queued work stops now, but a file already inside a
        # converter cannot be interrupted.
        status.activity = f"cancelling… {inflight} in flight" if inflight else "cancelled"

    def action_retry(self) -> None:
        queue = self.query_one("#queue", QueuePane)
        failed = queue.failed_jobs
        if not failed:
            self.notify("no failed jobs to retry")
            return
        for job in failed:
            job.state = JobState.QUEUED
            job.error = None
            queue.update_job(job)
        plan = Plan(jobs=failed, root=self.plan.root if self.plan else None, out_dir=self.out_dir)
        self._run_plan(plan)

    # ---- quit -----------------------------------------------------------

    def action_request_quit(self) -> None:
        if self.executor is not None:
            self.notify(
                "conversions are still running — press c to cancel first", severity="warning"
            )
            return
        self.exit()
