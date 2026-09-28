"""Pane 3: the job queue and what each job is doing."""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable

from convtui.core.models import Job, JobState

STATE_MARK: dict[JobState, str] = {
    JobState.QUEUED: "[dim]·[/dim]",
    JobState.RUNNING: "[yellow]▶[/yellow]",
    JobState.DONE: "[green]✓[/green]",
    JobState.FAILED: "[red]✗[/red]",
    JobState.SKIPPED: "[dim]–[/dim]",
}


class QueuePane(DataTable):
    """Live view of the current run.

    Rows are addressed by job index so a worker's update lands on the right row
    regardless of completion order.
    """

    BORDER_TITLE = "3 Queue"

    BINDINGS = [Binding("enter", "show_detail", "detail", show=False)]

    class DetailRequested(Message):
        def __init__(self, job: Job) -> None:
            self.job = job
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", **kwargs)
        self.jobs: list[Job] = []

    def on_mount(self) -> None:
        self.add_column("", width=2, key="state")
        self.add_column("file", key="file")
        self.add_column("note", key="note")

    def set_jobs(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.clear()
        for index, job in enumerate(jobs):
            self.add_row(*self._row(job), key=str(index))

    def update_job(self, job: Job) -> None:
        """Re-render one row in place; called from the UI thread only."""
        try:
            index = self.jobs.index(job)
        except ValueError:
            return
        key = str(index)
        state, name, note = self._row(job)
        try:
            self.update_cell(key, "state", state)
            self.update_cell(key, "note", note)
        except Exception:
            # The table was rebuilt underneath us (a new run started).
            return

    def _row(self, job: Job) -> tuple[str, str, str]:
        note = ""
        if job.state is JobState.FAILED and job.error:
            note = f"[red]{_escape(job.error)}[/red]"
        elif job.state is JobState.SKIPPED and job.skip_reason:
            note = f"[dim]{job.skip_reason.value}[/dim]"
        elif job.state is JobState.DONE and job.duration:
            note = f"[dim]{job.duration:.1f}s[/dim]"
        return STATE_MARK[job.state], _name(job.src), note

    def action_show_detail(self) -> None:
        if not self.jobs or self.cursor_row >= len(self.jobs):
            return
        self.post_message(self.DetailRequested(self.jobs[self.cursor_row]))

    @property
    def failed_jobs(self) -> list[Job]:
        return [j for j in self.jobs if j.state is JobState.FAILED]


def _name(path: Path) -> str:
    return path.name


def _escape(text: str) -> str:
    """Error text is arbitrary; square brackets in it are not markup."""
    return text.replace("[", r"\[")
