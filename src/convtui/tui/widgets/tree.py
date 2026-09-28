"""Pane 1: the directory tree."""

from __future__ import annotations

from pathlib import Path

from textual.message import Message
from textual.widgets import DirectoryTree


class SourceTree(DirectoryTree):
    """Directory tree that announces the folder the user moved to.

    Files are filtered out: picking individual files is the file list's job,
    and showing them twice makes the panes fight over the same decision.
    """

    BORDER_TITLE = "1 Tree"

    class DirectorySelected(Message):
        def __init__(self, path: Path) -> None:
            self.path = path
            super().__init__()

    def filter_paths(self, paths):
        return [p for p in paths if p.is_dir() and not p.name.startswith(".")]

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        event.stop()
        self.post_message(self.DirectorySelected(Path(event.path)))
