"""The bottom bar: current settings, and what the run is doing right now."""

from __future__ import annotations

from pathlib import Path

from textual.reactive import reactive
from textual.widgets import Static

from convtui.core.models import CollisionPolicy


class StatusBar(Static):
    """One line of state, always visible."""

    selected: reactive[int] = reactive(0)
    target: reactive[str] = reactive("md")
    out_dir: reactive[str] = reactive("./out")
    collision: reactive[CollisionPolicy] = reactive(CollisionPolicy.SKIP)
    # Not `workers`: Widget.workers is Textual's worker manager.
    worker_count: reactive[int] = reactive(4)
    activity: reactive[str] = reactive("")

    def render(self) -> str:
        out = _shorten(self.out_dir)
        parts = [
            f"[b]{self.selected}[/b] selected",
            f"→ [b]{self.target}[/b]",
            f"out: [b]{out}[/b]",
            self.collision.value,
            f"{self.worker_count} workers",
        ]
        line = "  ·  ".join(parts)
        if self.activity:
            line += f"   [yellow]{self.activity}[/yellow]"
        return f"{line}   [dim]?:help[/dim]"


def _shorten(path: str) -> str:
    """Render a path against $HOME so the bar stays readable."""
    try:
        return f"~/{Path(path).resolve().relative_to(Path.home())}"
    except (ValueError, OSError):
        return path
