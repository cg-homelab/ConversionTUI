"""The `?` overlay."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

KEYS: list[tuple[str, str]] = [
    ("j / k, ↑ / ↓", "move within a pane"),
    ("tab, 1 / 2 / 3", "focus tree / files / queue"),
    ("space", "toggle selection"),
    ("a / A", "select all / clear selection"),
    ("/", "filter files (substring or glob)"),
    ("t", "set target format"),
    ("o", "set output directory"),
    ("p", "cycle collision policy"),
    ("enter", "confirm and convert (in the file pane)"),
    ("enter", "show error detail (in the queue pane)"),
    ("c", "cancel the running queue"),
    ("r", "requeue failed jobs"),
    ("s", "save current settings as defaults"),
    ("?", "this help"),
    ("q", "quit"),
]


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,q,question_mark", "dismiss", "close"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box"):
            yield Static("[b]convtui[/b] — keys", id="help-title")
            table = DataTable(show_header=False, cursor_type="none", id="help-keys")
            yield table
            yield Static(
                "[dim]Conversions run on worker threads; cancelling stops the "
                "queue but lets in-flight files finish.[/dim]",
                id="help-note",
            )

    def on_mount(self) -> None:
        table = self.query_one("#help-keys", DataTable)
        table.add_column("key", width=16)
        table.add_column("action")
        for key, description in KEYS:
            table.add_row(f"[b]{key}[/b]", description)
