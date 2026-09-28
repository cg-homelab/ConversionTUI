"""Converter protocol and the registry that resolves format pairs to backends.

A backend declares which extensions it reads and writes, whether it is usable
right now, and how to convert one file. Everything else in convtui is written
against this protocol, so adding pandoc or ffmpeg later touches no other module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Availability:
    """Whether a converter can run, and if not, what the user should do.

    Returned rather than raised: the UI lists unavailable backends greyed out
    with an actionable hint, which it cannot do if probing explodes.
    """

    ok: bool
    reason: str | None = None
    hint: str | None = None

    @classmethod
    def available(cls) -> Availability:
        return cls(ok=True)

    @classmethod
    def missing(cls, reason: str, hint: str | None = None) -> Availability:
        return cls(ok=False, reason=reason, hint=hint)


@runtime_checkable
class Converter(Protocol):
    """A single conversion backend."""

    name: str
    priority: int
    inputs: frozenset[str]
    outputs: frozenset[str]

    def available(self) -> Availability:
        """Report whether this backend can run, without raising."""
        ...

    def convert(self, src: Path, dst: Path, opts: Mapping[str, Any]) -> None:
        """Convert `src` to `dst`. Raise on failure; the executor catches."""
        ...


class ConverterError(RuntimeError):
    """Raised by a backend when a single file cannot be converted."""


class Registry:
    """Holds the known converters and resolves (src_ext, dst_ext) to one."""

    def __init__(self) -> None:
        self._converters: list[Converter] = []

    def register(self, converter: Converter) -> Converter:
        self._converters.append(converter)
        return converter

    def __len__(self) -> int:
        return len(self._converters)

    def all(self) -> list[Converter]:
        return list(self._converters)

    def by_name(self, name: str) -> Converter | None:
        return next((c for c in self._converters if c.name == name), None)

    def candidates(self, src_ext: str, dst_ext: str) -> list[Converter]:
        """Every converter claiming this pair, best first.

        Ordered by descending priority, then registration order — so a more
        specialised backend can outrank a general one deterministically.
        """
        src_ext, dst_ext = _norm(src_ext), _norm(dst_ext)
        matches = [
            (i, c)
            for i, c in enumerate(self._converters)
            if src_ext in c.inputs and dst_ext in c.outputs
        ]
        matches.sort(key=lambda pair: (-pair[1].priority, pair[0]))
        return [c for _, c in matches]

    def resolve(self, src_ext: str, dst_ext: str, prefer: str | None = None) -> Converter | None:
        """Pick the converter for a pair, optionally forcing one by name.

        Only available backends are returned; an installed-but-unusable one
        never silently wins over a working alternative.
        """
        cands = self.candidates(src_ext, dst_ext)
        if prefer is not None:
            return next((c for c in cands if c.name == prefer), None)
        return next((c for c in cands if c.available().ok), None)

    def input_extensions(self) -> set[str]:
        """Every extension any registered converter can read."""
        return {ext for c in self._converters for ext in c.inputs}

    def output_extensions(self) -> set[str]:
        return {ext for c in self._converters for ext in c.outputs}

    def supports(self, path: Path, dst_ext: str) -> bool:
        return bool(self.candidates(path.suffix, dst_ext))


def _norm(ext: str) -> str:
    """Normalise an extension to lowercase, dot-prefixed form."""
    ext = ext.strip().lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return ext


def normalize_ext(ext: str) -> str:
    return _norm(ext)


def exts(values: Iterable[str]) -> frozenset[str]:
    """Build a normalised extension set for a backend declaration."""
    return frozenset(_norm(v) for v in values)


registry = Registry()
"""The process-wide registry. Backends register into it at import time."""


def load_backends() -> Registry:
    """Import the shipped backends so they self-register.

    Kept lazy and in one place: the core stays importable (and testable)
    without pulling markitdown's heavy dependency tree.
    """
    from convtui import backends  # noqa: F401  (import triggers registration)

    return registry
