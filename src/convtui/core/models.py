"""Data types shared by every layer.

These are deliberately plain: the planner builds them, the executor consumes
them, and both UI surfaces render them. Nothing here imports a backend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class CollisionPolicy(str, Enum):
    """What to do when the destination file already exists."""

    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"
    IN_PLACE = "in-place"


class SkipReason(str, Enum):
    EXISTS = "destination exists"
    COLLIDES = "two sources map to this destination"
    NO_CONVERTER = "no converter for this format pair"
    UNAVAILABLE = "converter not available"


@dataclass
class Job:
    """One source file to convert into one destination file."""

    src: Path
    dst: Path
    converter: str
    state: JobState = JobState.QUEUED
    error: str | None = None
    skip_reason: SkipReason | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    @property
    def size(self) -> int:
        try:
            return self.src.stat().st_size
        except OSError:
            return 0

    def mark_running(self) -> None:
        self.state = JobState.RUNNING
        self.started_at = time.monotonic()

    def mark_done(self) -> None:
        self.state = JobState.DONE
        self.finished_at = time.monotonic()

    def mark_failed(self, error: str) -> None:
        self.state = JobState.FAILED
        self.error = error
        self.finished_at = time.monotonic()

    def mark_skipped(self, reason: SkipReason) -> None:
        self.state = JobState.SKIPPED
        self.skip_reason = reason


@dataclass
class Result:
    """Outcome of a single job, as reported back from a worker."""

    job: Job
    ok: bool
    error: str | None = None


@dataclass
class Plan:
    """The full set of jobs discovered for a request, before anything runs.

    Built by the planner and rendered as-is by `--dry-run` and the TUI confirm
    screen, so what the user previews is exactly what will execute.
    """

    jobs: list[Job] = field(default_factory=list)
    root: Path | None = None
    out_dir: Path | None = None
    collision: CollisionPolicy = CollisionPolicy.SKIP

    @property
    def runnable(self) -> list[Job]:
        return [j for j in self.jobs if j.state is JobState.QUEUED]

    @property
    def skipped(self) -> list[Job]:
        return [j for j in self.jobs if j.state is JobState.SKIPPED]

    def summary(self) -> str:
        parts = [f"{len(self.runnable)} to convert"]
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        return ", ".join(parts)


@dataclass
class Summary:
    """Aggregate outcome of a completed run."""

    done: int = 0
    failed: int = 0
    skipped: int = 0

    @classmethod
    def from_jobs(cls, jobs: list[Job]) -> Summary:
        s = cls()
        for j in jobs:
            if j.state is JobState.DONE:
                s.done += 1
            elif j.state is JobState.FAILED:
                s.failed += 1
            elif j.state is JobState.SKIPPED:
                s.skipped += 1
        return s

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0

    def __str__(self) -> str:
        return f"{self.done} converted, {self.failed} failed, {self.skipped} skipped"
