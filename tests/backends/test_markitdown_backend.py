"""Backend tests. These do touch markitdown, unlike everything under tests/core."""

from __future__ import annotations

from pathlib import Path

import pytest

from convtui.backends.markitdown_backend import SUPPORTED, MarkItDownConverter
from convtui.core.registry import ConverterError, load_backends

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
MARKER = "Conversion fixture heading"


@pytest.fixture
def backend() -> MarkItDownConverter:
    return MarkItDownConverter()


def test_backend_registers_itself():
    assert load_backends().by_name("markitdown") is not None


def test_declares_markdown_output(backend):
    assert backend.outputs == frozenset({".md"})
    assert ".pdf" in backend.inputs


def test_markitdown_is_available(backend):
    assert backend.available().ok


@pytest.mark.parametrize(
    "fixture",
    ["sample.pdf", "sample.docx", "sample.pptx", "sample.xlsx", "sample.csv", "sample.html"],
)
def test_converts_fixture_to_markdown(backend, tmp_path, fixture):
    dst = tmp_path / "out.md"
    backend.convert(FIXTURES / fixture, dst, {})
    text = dst.read_text(encoding="utf-8")
    assert MARKER in text
    assert text.endswith("\n")


def test_empty_file_fails_with_a_readable_message(backend, tmp_path):
    src = tmp_path / "empty.pdf"
    src.write_bytes(b"")
    with pytest.raises(ConverterError) as exc:
        backend.convert(src, tmp_path / "out.md", {})
    message = str(exc.value)
    assert "\n" not in message
    # The useful diagnosis lives on markitdown's second line, not its first.
    assert "File conversion failed after" not in message
    assert "PDF" in message.upper()


def test_no_output_file_is_written_on_failure(backend, tmp_path):
    src = tmp_path / "empty.pdf"
    src.write_bytes(b"")
    dst = tmp_path / "out.md"
    with pytest.raises(ConverterError):
        backend.convert(src, dst, {})
    assert not dst.exists()


# ---- availability ------------------------------------------------------


def test_base_formats_are_available(backend):
    for ext in (".pdf", ".docx", ".pptx", ".xlsx", ".xls"):
        assert backend.available_for(ext).ok, ext


def test_extra_gated_format_reports_an_actionable_hint(backend):
    result = backend.available_for(".mp3")
    if not result.ok:  # the audio extra is not installed in the default dev env
        assert "convtui[audio]" in result.hint


def test_unsupported_extension_is_reported(backend):
    result = backend.available_for(".xyz")
    assert not result.ok
    assert ".xyz" in result.reason


def test_every_supported_extension_has_a_known_extra():
    assert set(SUPPORTED.values()) <= {None, "audio", "outlook", "azure", "web"}


def test_image_formats_are_excluded(backend):
    # markitdown needs an LLM or exiftool for images; without one it emits nothing.
    assert ".png" not in backend.inputs
