from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from convtui.core.registry import Availability, Registry, exts


class FakeConverter:
    """An in-memory converter so core tests never touch markitdown."""

    def __init__(
        self,
        name: str = "fake",
        inputs: tuple[str, ...] = (".pdf", ".docx"),
        outputs: tuple[str, ...] = (".md",),
        priority: int = 0,
        ok: bool = True,
        fail_on: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.inputs = exts(inputs)
        self.outputs = exts(outputs)
        self.priority = priority
        self._ok = ok
        self._fail_on = fail_on
        self.calls: list[Path] = []

    def available(self) -> Availability:
        return Availability.available() if self._ok else Availability.missing("nope", "install it")

    def convert(self, src: Path, dst: Path, opts: Mapping[str, Any]) -> None:
        self.calls.append(src)
        if src.name in self._fail_on:
            raise RuntimeError(f"boom: {src.name}")
        dst.write_text(f"# {src.stem}\n\nconverted by {self.name}\n", encoding="utf-8")


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter()


@pytest.fixture
def registry(converter: FakeConverter) -> Registry:
    r = Registry()
    r.register(converter)
    return r


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A small source tree: two files at the root, one nested, one unsupported."""
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "b.docx").write_bytes(b"PK fake")
    (root / "sub" / "c.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "notes.txt").write_text("not convertible")
    return root
