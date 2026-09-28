"""Pane 2: the convertible files in the current folder, with multi-select."""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.message import Message
from textual.widgets import DataTable
from textual.widgets.data_table import RowKey

from convtui.core.registry import Registry, normalize_ext


class FileList(DataTable):
    """A checkbox list of files, backed by a DataTable for free scrolling.

    Only files some registered converter claims are listed — a folder of source
    code should not show a hundred rows nothing can act on.
    """

    BORDER_TITLE = "2 Files"

    BINDINGS = [
        # enter is bound here rather than on the app: DataTable consumes it for
        # its own row-selected event before an app-level binding would fire.
        Binding("enter", "request_convert", "convert", show=False),
        Binding("space", "toggle", "select", show=False),
        Binding("a", "select_all", "all", show=False),
        Binding("A", "clear_selection", "none", show=False),
    ]

    class SelectionChanged(Message):
        def __init__(self, count: int) -> None:
            self.count = count
            super().__init__()

    class ConvertRequested(Message):
        """The user pressed enter in the file pane."""

    def __init__(self, registry: Registry, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=False, **kwargs)
        self.registry = registry
        self.paths: list[Path] = []
        self.selected: set[Path] = set()
        self._filter: str = ""

    def on_mount(self) -> None:
        self.add_column("", width=3, key="mark")
        self.add_column("name", key="name")
        self.add_column("size", width=9, key="size")

    # ---- population ----------------------------------------------------

    def load(self, directory: Path, *, target: str, show_hidden: bool = False) -> None:
        """List the convertible files directly inside `directory`."""
        dst_ext = normalize_ext(target)
        inputs = self.registry.input_extensions()
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            entries = []

        self.paths = [
            p
            for p in entries
            if p.is_file()
            and not p.is_symlink()
            and (show_hidden or not p.name.startswith("."))
            and normalize_ext(p.suffix) in inputs
            and normalize_ext(p.suffix) != dst_ext
        ]
        self.selected &= set(self.paths)
        self.refresh_rows()

    def set_filter(self, pattern: str) -> None:
        self._filter = pattern.strip()
        self.refresh_rows()

    @property
    def visible_paths(self) -> list[Path]:
        if not self._filter:
            return self.paths
        needle = self._filter.lower()
        if any(ch in needle for ch in "*?["):
            from fnmatch import fnmatch

            return [p for p in self.paths if fnmatch(p.name.lower(), needle)]
        return [p for p in self.paths if needle in p.name.lower()]

    def refresh_rows(self) -> None:
        self.clear()
        for path in self.visible_paths:
            mark = "[green]x[/green]" if path in self.selected else " "
            self.add_row(mark, path.name, _human(path), key=str(path))
        self.post_message(self.SelectionChanged(len(self.selected)))

    # ---- actions -------------------------------------------------------

    def action_toggle(self) -> None:
        path = self._cursor_path()
        if path is None:
            return
        if path in self.selected:
            self.selected.discard(path)
        else:
            self.selected.add(path)
        row = self.cursor_row
        self.refresh_rows()
        # refresh_rows rebuilds every row, so put the cursor back where it was.
        if row < self.row_count:
            self.move_cursor(row=row)

    def action_select_all(self) -> None:
        self.selected.update(self.visible_paths)
        self.refresh_rows()

    def action_request_convert(self) -> None:
        self.post_message(self.ConvertRequested())

    def action_clear_selection(self) -> None:
        self.selected.clear()
        self.refresh_rows()

    def _cursor_path(self) -> Path | None:
        if not self.row_count:
            return None
        try:
            key: RowKey = self.coordinate_to_cell_key(self.cursor_coordinate).row_key
        except Exception:
            return None
        return Path(key.value) if key.value else None


def _human(path: Path) -> str:
    try:
        size = float(path.stat().st_size)
    except OSError:
        return "-"
    for unit in ("B", "K", "M", "G"):
        if size < 1024 or unit == "G":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}G"
