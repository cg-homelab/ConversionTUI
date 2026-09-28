"""Full error detail for one job — errors must never be truncated into uselessness."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from convtui.core.models import Job


class DetailScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,enter", "dismiss", "close")]

    def __init__(self, job: Job) -> None:
        super().__init__()
        self.job = job

    def compose(self) -> ComposeResult:
        job = self.job
        lines = [
            f"[b]{job.src.name}[/b]",
            "",
            f"[dim]source[/dim]      {job.src}",
            f"[dim]destination[/dim] {job.dst}",
            f"[dim]backend[/dim]     {job.converter}",
            f"[dim]state[/dim]       {job.state.value}",
        ]
        if job.duration:
            lines.append(f"[dim]duration[/dim]    {job.duration:.2f}s")
        if job.skip_reason:
            lines.append(f"[dim]skipped[/dim]     {job.skip_reason.value}")
        if job.error:
            lines += ["", "[red]error[/red]", job.error.replace("[", r"\[")]
        with VerticalScroll(id="detail-box"):
            yield Static("\n".join(lines))
