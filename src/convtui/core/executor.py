"""Job execution.

Conversions run on worker threads so the TUI stays responsive: MarkItDown is
synchronous, and calling it on Textual's event loop freezes the interface.
Threads win here because the heavy work (PDF parsing, lxml, image decode)
happens in C extensions that release the GIL.

`Executor` is a protocol so a process-backed implementation can be dropped in
later without touching the callers. Worker functions therefore take plain
paths and build their own converter, which is already pickle-safe.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from convtui.core.models import Job, JobState, Result
from convtui.core.registry import Registry

ProgressCallback = Callable[[Job], None]


def default_workers() -> int:
    return min(4, os.cpu_count() or 1)


class Executor(Protocol):
    """Runs jobs and reports results; implementations may use threads or processes."""

    def submit(self, job: Job) -> Future[Result]: ...

    def cancel_all(self) -> None: ...

    def shutdown(self, wait: bool = True) -> None: ...


class ThreadExecutor:
    """Thread-pool executor with cooperative, two-tier cancellation.

    `cancel_all()` drops everything still queued at once and asks in-flight
    workers to stop. A file already inside a converter runs to completion —
    a thread cannot be killed — so callers should report those as in-flight
    rather than claiming the run stopped instantly.
    """

    def __init__(
        self,
        registry: Registry,
        *,
        workers: int | None = None,
        opts: Mapping[str, Any] | None = None,
        on_update: ProgressCallback | None = None,
    ) -> None:
        self.registry = registry
        self.workers = workers or default_workers()
        self.opts: Mapping[str, Any] = opts or {}
        self.on_update = on_update
        self._cancelled = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="convtui")
        self._futures: list[Future[Result]] = []
        self._inflight = 0
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def inflight(self) -> int:
        """Jobs currently inside a converter, which cancellation cannot stop."""
        with self._lock:
            return self._inflight

    def submit(self, job: Job) -> Future[Result]:
        future = self._pool.submit(self._run, job)
        self._futures.append(future)
        return future

    def submit_all(self, jobs: list[Job]) -> list[Future[Result]]:
        return [self.submit(j) for j in jobs]

    def cancel_all(self) -> None:
        self._cancelled.set()
        for f in self._futures:
            f.cancel()

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    def _notify(self, job: Job) -> None:
        if self.on_update is not None:
            self.on_update(job)

    def _run(self, job: Job) -> Result:
        if self._cancelled.is_set():
            # Checked here as well as at submit time: a worker picking up a job
            # after cancellation must not start converting.
            return Result(job=job, ok=False, error="cancelled")

        converter = self.registry.by_name(job.converter)
        if converter is None:
            job.mark_failed(f"unknown converter: {job.converter}")
            self._notify(job)
            return Result(job=job, ok=False, error=job.error)

        job.mark_running()
        self._notify(job)
        with self._lock:
            self._inflight += 1
        try:
            job.dst.parent.mkdir(parents=True, exist_ok=True)
            converter.convert(job.src, job.dst, self.opts)
        except Exception as exc:  # a bad file must not take the run down
            job.mark_failed(_describe(exc))
            return Result(job=job, ok=False, error=job.error)
        else:
            job.mark_done()
            return Result(job=job, ok=True)
        finally:
            with self._lock:
                self._inflight -= 1
            self._notify(job)


def run_plan(
    jobs: list[Job],
    registry: Registry,
    *,
    workers: int | None = None,
    opts: Mapping[str, Any] | None = None,
    on_update: ProgressCallback | None = None,
) -> list[Job]:
    """Run jobs to completion. Used by the CLI; the TUI drives ThreadExecutor itself."""
    runnable = [j for j in jobs if j.state is JobState.QUEUED]
    executor = ThreadExecutor(registry, workers=workers, opts=opts, on_update=on_update)
    try:
        futures = executor.submit_all(runnable)
        for f in futures:
            f.result()
    finally:
        executor.shutdown()
    return jobs


def _describe(exc: Exception) -> str:
    """A one-line error the UI can show without a traceback."""
    text = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, OSError) and exc.filename:
        text = f"{text}: {Path(exc.filename).name}"
    return text.splitlines()[0][:300]
