"""The preview shown before anything is written.

Renders exactly the Plan the executor will run, so what the user approves and
what happens cannot diverge.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Static

from convtui.core.models import JobState, Plan


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        # priority: the preview table would otherwise swallow enter for its own
        # row-selected event, and enter here means "yes, convert".
        Binding("enter", "confirm", "convert", priority=True),
        Binding("y", "confirm", "convert", show=False),
        Binding("n", "cancel", "cancel", show=False),
    ]

    def __init__(self, plan: Plan) -> None:
        super().__init__()
        self.plan = plan

    def compose(self) -> ComposeResult:
        plan = self.plan
        destination = str(plan.out_dir) if plan.out_dir else "beside each source file"
        with Vertical(id="confirm-box"):
            yield Static(f"[b]Convert {plan.summary()}[/b]", id="confirm-title")
            yield Static(
                f"[dim]into[/dim] {destination}   [dim]on collision[/dim] {plan.collision.value}",
                id="confirm-meta",
            )
            yield DataTable(id="confirm-table", cursor_type="row")
            with Horizontal(id="confirm-buttons"):
                yield Button("Convert", variant="primary", id="go")
                yield Button("Cancel", id="stop")

    def on_mount(self) -> None:
        table = self.query_one("#confirm-table", DataTable)
        table.add_column("source", key="src")
        table.add_column("→", width=3, key="arrow")
        table.add_column("destination", key="dst")
        root = self.plan.root
        out = self.plan.out_dir
        for job in self.plan.jobs:
            src = _rel(job.src, root)
            dst = _rel(job.dst, out)
            if job.state is JobState.SKIPPED:
                reason = job.skip_reason.value if job.skip_reason else "skipped"
                table.add_row(f"[dim]{src}[/dim]", "", f"[dim]{reason}[/dim]")
            else:
                table.add_row(src, "→", dst)
        if not self.plan.runnable:
            self.query_one("#go", Button).disabled = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "go")

    def action_confirm(self) -> None:
        self.dismiss(bool(self.plan.runnable))

    def action_cancel(self) -> None:
        self.dismiss(False)


def _rel(path, root) -> str:
    if root is None:
        return str(path)
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
