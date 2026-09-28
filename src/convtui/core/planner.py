"""Discovery: turn a set of source paths into a concrete, previewable Plan.

This is a pure step — it stats files but never writes. Both the CLI's
`--dry-run` and the TUI's confirm screen render the same Plan that the
executor will then run, so the preview cannot drift from the real work.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from pathlib import Path

from convtui.core.models import CollisionPolicy, Job, Plan, SkipReason
from convtui.core.registry import Registry, normalize_ext

DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/**",
    ".hg/**",
    ".svn/**",
    "node_modules/**",
    "__pycache__/**",
    ".venv/**",
    "venv/**",
    ".DS_Store",
)


class PlanError(ValueError):
    """Raised for a request that cannot produce a sane plan."""


def build_plan(
    sources: Sequence[Path],
    out_dir: Path | None,
    to: str,
    registry: Registry,
    *,
    recursive: bool = True,
    collision: CollisionPolicy = CollisionPolicy.SKIP,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    show_hidden: bool = False,
    prefer: str | None = None,
) -> Plan:
    """Build the job list for a conversion request.

    `out_dir` mirrors the source tree: with root `docs/`, the file
    `docs/a/b.pdf` becomes `<out_dir>/a/b.md`. In-place conversions write
    beside the source instead and ignore `out_dir`.
    """
    dst_ext = normalize_ext(to)
    if not dst_ext:
        raise PlanError("no target format given")

    in_place = collision is CollisionPolicy.IN_PLACE
    if out_dir is None and not in_place:
        raise PlanError("an output directory is required unless converting in place")

    sources = [Path(s).expanduser() for s in sources]
    for s in sources:
        if not s.exists():
            raise PlanError(f"no such file or directory: {s}")

    root = _common_root(sources)
    out_dir = None if in_place else Path(out_dir).expanduser()  # type: ignore[arg-type]
    if out_dir is not None:
        _guard_output_inside_source(root, out_dir, sources)

    excludes = (*DEFAULT_EXCLUDES, *exclude)
    includes = tuple(include)

    plan = Plan(root=root, out_dir=out_dir, collision=collision)
    seen: set[Path] = set()
    taken: set[Path] = set()

    for src in _discover(sources, recursive=recursive, show_hidden=show_hidden):
        src = src.resolve()
        if src in seen:
            continue
        seen.add(src)

        rel = _relative_to_root(src, root)
        if _is_excluded(rel, excludes) or not _is_included(rel, includes):
            continue

        converter = registry.resolve(src.suffix, dst_ext, prefer=prefer)
        if converter is None:
            # Only surface a miss for files something could plausibly handle;
            # otherwise every stray .txt in a folder becomes noise.
            if normalize_ext(src.suffix) not in registry.input_extensions():
                continue
            reason = (
                SkipReason.UNAVAILABLE
                if registry.candidates(src.suffix, dst_ext)
                else SkipReason.NO_CONVERTER
            )
            job = Job(src=src, dst=src.with_suffix(dst_ext), converter="-")
            job.mark_skipped(reason)
            plan.jobs.append(job)
            continue

        dst = _destination(src, rel, out_dir, dst_ext, in_place=in_place)
        job = Job(src=src, dst=dst, converter=converter.name)

        if dst == src:
            job.mark_skipped(SkipReason.EXISTS)
        elif dst in taken or dst.exists():
            if collision is CollisionPolicy.SKIP:
                # Two sources mapping to one destination is a different problem
                # from an existing file, and needs a different fix (--rename),
                # so say which one actually happened.
                job.mark_skipped(SkipReason.COLLIDES if dst in taken else SkipReason.EXISTS)
            elif collision is CollisionPolicy.RENAME:
                job.dst = _unique(dst, taken)
            # OVERWRITE and IN_PLACE keep the path as-is.

        taken.add(job.dst)
        plan.jobs.append(job)

    plan.jobs.sort(key=lambda j: str(j.src))
    return plan


def _discover(sources: Iterable[Path], *, recursive: bool, show_hidden: bool) -> Iterable[Path]:
    for src in sources:
        if src.is_file():
            yield src
        elif src.is_dir():
            yield from _walk(src, recursive=recursive, show_hidden=show_hidden)


def _walk(root: Path, *, recursive: bool, show_hidden: bool) -> Iterable[Path]:
    """Walk a directory without following symlinks (no cycle handling in 0.1)."""
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_symlink():
            continue
        if not show_hidden and entry.name.startswith("."):
            continue
        if entry.is_file():
            yield entry
        elif entry.is_dir() and recursive:
            yield from _walk(entry, recursive=recursive, show_hidden=show_hidden)


def _common_root(sources: Sequence[Path]) -> Path:
    """The directory that relative destination paths are computed against."""
    dirs = [s if s.is_dir() else s.parent for s in sources]
    resolved = [d.resolve() for d in dirs]
    if len(resolved) == 1:
        return resolved[0]
    common = resolved[0]
    for d in resolved[1:]:
        while not _is_relative_to(d, common):
            if common.parent == common:
                return common
            common = common.parent
    return common


def _relative_to_root(src: Path, root: Path) -> Path:
    try:
        return src.relative_to(root)
    except ValueError:
        return Path(src.name)


def _destination(
    src: Path, rel: Path, out_dir: Path | None, dst_ext: str, *, in_place: bool
) -> Path:
    if in_place or out_dir is None:
        return src.with_suffix(dst_ext)
    return (out_dir / rel).with_suffix(dst_ext)


def _unique(dst: Path, taken: set[Path]) -> Path:
    """Find `name-1.md`, `name-2.md`, ... for a destination already in use."""
    stem, suffix, parent = dst.stem, dst.suffix, dst.parent
    n = 1
    while True:
        candidate = parent / f"{stem}-{n}{suffix}"
        if not candidate.exists() and candidate not in taken:
            return candidate
        n += 1


def _is_excluded(rel: Path, patterns: Iterable[str]) -> bool:
    return any(_matches(rel, p) for p in patterns)


def _is_included(rel: Path, patterns: Sequence[str]) -> bool:
    return not patterns or any(_matches(rel, p) for p in patterns)


def _matches(rel: Path, pattern: str) -> bool:
    """Match a glob against the relative path or any single path segment."""
    text = rel.as_posix()
    if fnmatch.fnmatch(text, pattern) or fnmatch.fnmatch(rel.name, pattern):
        return True
    # `node_modules/**` should match a nested hit too, not just a top-level one.
    return any(fnmatch.fnmatch(f"{part}/", pattern.split("**")[0]) for part in rel.parts[:-1])


def _guard_output_inside_source(root: Path, out_dir: Path, sources: Sequence[Path]) -> None:
    """Refuse an output dir nested in a scanned source tree.

    Otherwise a recursive run re-discovers its own output on the next pass and
    the folder grows `a.md`, `a-1.md`, ... every time.
    """
    out = out_dir.resolve()
    for s in sources:
        s = s.resolve()
        if s.is_dir() and _is_relative_to(out, s) and out != s:
            raise PlanError(
                f"output directory {out} is inside the source tree {s}; "
                "choose a location outside it"
            )


def _is_relative_to(path: Path, other: Path) -> bool:
    # Path.is_relative_to is 3.9+, but keep one helper for readability.
    try:
        path.relative_to(other)
    except ValueError:
        return False
    return True
