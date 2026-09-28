"""MarkItDown backend: documents and data files to markdown.

The extension set is curated rather than scraped from markitdown's converter
list — that list lives in private modules whose shape changes between
releases. What we do probe at runtime is whether the optional dependency for a
given format actually imported, so the UI can say "install convtui[audio]"
instead of failing halfway through a batch.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from convtui.core.registry import Availability, ConverterError, exts, registry

#: Extension -> the convtui extra that provides it (None = in the base install).
#:
#: Image formats are deliberately absent: markitdown only describes an image
#: via an LLM client or exiftool metadata, so without either it produces an
#: empty document. Revisit when there is somewhere to configure an LLM.
SUPPORTED: dict[str, str | None] = {
    ".pdf": None,
    ".docx": None,
    ".pptx": None,
    ".xlsx": None,
    ".xls": None,
    ".csv": None,
    ".html": None,
    ".htm": None,
    ".epub": None,
    ".ipynb": None,
    ".json": None,
    ".jsonl": None,
    ".txt": None,
    ".zip": None,
    ".msg": "outlook",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
}

#: Extension -> the third-party modules its converter needs.
#:
#: Probing the real imports is stable across markitdown releases, unlike its
#: private per-converter dependency flags — and it catches the case where
#: markitdown registers a converter whose optional deps were never installed.
_REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    ".pdf": ("pdfminer",),
    ".docx": ("mammoth",),
    ".pptx": ("pptx",),
    ".xlsx": ("openpyxl", "pandas"),
    ".xls": ("xlrd", "pandas"),
    ".msg": ("olefile",),
    ".wav": ("pydub", "speech_recognition"),
    ".mp3": ("pydub", "speech_recognition"),
    ".m4a": ("pydub", "speech_recognition"),
}


class MarkItDownConverter:
    """Converts documents to markdown via Microsoft's MarkItDown."""

    name = "markitdown"
    priority = 0
    inputs = exts(SUPPORTED)
    outputs = exts([".md"])

    def __init__(self) -> None:
        self._md: Any | None = None

    # ---- availability --------------------------------------------------

    def available(self) -> Availability:
        try:
            import markitdown  # noqa: F401
        except ImportError as exc:
            return Availability.missing(
                f"markitdown is not importable: {exc}",
                hint="pip install 'convtui'",
            )
        return Availability.available()

    def available_for(self, ext: str) -> Availability:
        """Per-format availability, so the UI can grey out one row not all of them."""
        base = self.available()
        if not base.ok:
            return base

        ext = ext.lower()
        if ext not in self.inputs:
            return Availability.missing(f"{ext} is not supported by markitdown")

        if not _dependencies_ok(ext):
            extra = SUPPORTED.get(ext)
            hint = f"pip install 'convtui[{extra}]'" if extra else "pip install --upgrade convtui"
            return Availability.missing(
                f"optional dependencies for {ext} are not installed",
                hint=hint,
            )
        return Availability.available()

    # ---- conversion ----------------------------------------------------

    def convert(self, src: Path, dst: Path, opts: Mapping[str, Any]) -> None:
        md = self._instance()
        try:
            result = md.convert(str(src))
        except Exception as exc:  # markitdown raises a wide variety of types
            raise ConverterError(_clean(exc)) from exc

        if result is None:
            raise ConverterError("markitdown returned no result")

        text = getattr(result, "markdown", None) or getattr(result, "text_content", None) or ""
        if not text.strip():
            # An empty conversion is almost always a silent failure (scanned
            # PDF, unsupported embedded content), so surface it rather than
            # writing a blank file the user has to notice for themselves.
            #
            # Note the inverse case we cannot catch here: markitdown falls back
            # to its plain-text converter for a file whose bytes do not match
            # its extension, so a mislabelled .docx yields its raw bytes as
            # "markdown" instead of an error.
            raise ConverterError("conversion produced no text (scanned or unsupported content?)")

        dst.write_text(_ensure_trailing_newline(text), encoding="utf-8")

    def _instance(self) -> Any:
        """Build the MarkItDown object once per converter, lazily.

        Construction is not free (it wires up every sub-converter), and the
        import alone pulls a large dependency tree, so it stays out of module
        import time.
        """
        if self._md is None:
            try:
                from markitdown import MarkItDown
            except ImportError as exc:  # pragma: no cover - guarded by available()
                raise ConverterError(f"markitdown is not installed: {exc}") from exc
            self._md = MarkItDown(enable_plugins=False)
        return self._md


def _dependencies_ok(ext: str) -> bool:
    """Whether every module this format's converter needs can be imported."""
    for module in _REQUIRED_MODULES.get(ext, ()):
        try:
            __import__(module)
        except ImportError:
            return False
    return True


def _clean(exc: Exception) -> str:
    """Flatten a markitdown exception into one useful line.

    Its FileConversionException puts a bare summary on line one and the actual
    cause ("PdfConverter threw PDFSyntaxError with message: ...") underneath,
    so taking only the first line would throw away the diagnosis.
    """
    text = str(exc).strip() or exc.__class__.__name__
    lines = [ln.strip(" -\t") for ln in text.splitlines() if ln.strip(" -\t")]
    if not lines:
        return exc.__class__.__name__
    if len(lines) > 1 and lines[0].startswith("File conversion failed"):
        return lines[1]
    return " ".join(lines[:2])


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else text + "\n"


registry.register(MarkItDownConverter())
