from __future__ import annotations

import threading

from convtui.core.executor import ThreadExecutor, default_workers, run_plan
from convtui.core.models import Job, JobState, Summary
from convtui.core.planner import build_plan
from convtui.core.registry import Registry
from tests.conftest import FakeConverter


def test_default_workers_is_sane():
    assert 1 <= default_workers() <= 4


def test_runs_every_job_and_writes_output(tree, tmp_path, registry, converter):
    plan = build_plan([tree], tmp_path / "out", "md", registry)
    run_plan(plan.jobs, registry)
    assert all(j.state is JobState.DONE for j in plan.jobs)
    assert (tmp_path / "out" / "sub" / "c.md").read_text().startswith("# c")
    assert len(converter.calls) == 3


def test_creates_nested_output_directories(tree, tmp_path, registry):
    plan = build_plan([tree], tmp_path / "deep" / "nested" / "out", "md", registry)
    run_plan(plan.jobs, registry)
    assert (tmp_path / "deep" / "nested" / "out" / "sub" / "c.md").is_file()


def test_a_failing_file_does_not_stop_the_run(tree, tmp_path):
    r = Registry()
    r.register(FakeConverter(fail_on=("a.pdf",)))
    plan = build_plan([tree], tmp_path / "out", "md", r)
    run_plan(plan.jobs, r)
    states = {j.src.name: j.state for j in plan.jobs}
    assert states["a.pdf"] is JobState.FAILED
    assert states["b.docx"] is JobState.DONE
    failed = next(j for j in plan.jobs if j.state is JobState.FAILED)
    assert "boom: a.pdf" in failed.error


def test_error_is_one_line_and_bounded(tmp_path):
    class Exploding(FakeConverter):
        def convert(self, src, dst, opts):
            raise RuntimeError("line one\nline two\n" + "x" * 1000)

    r = Registry()
    r.register(Exploding())
    job = Job(src=tmp_path / "a.pdf", dst=tmp_path / "a.md", converter="fake")
    run_plan([job], r)
    assert "\n" not in job.error
    assert len(job.error) <= 300


def test_unknown_converter_fails_the_job_cleanly(tmp_path, registry):
    job = Job(src=tmp_path / "a.pdf", dst=tmp_path / "a.md", converter="ghost")
    run_plan([job], registry)
    assert job.state is JobState.FAILED
    assert "unknown converter" in job.error


def test_progress_callback_sees_running_then_terminal(tree, tmp_path, registry):
    seen: list[tuple[str, JobState]] = []
    lock = threading.Lock()

    def on_update(job: Job) -> None:
        with lock:
            seen.append((job.src.name, job.state))

    plan = build_plan([tree / "a.pdf"], tmp_path / "out", "md", registry)
    run_plan(plan.jobs, registry, on_update=on_update)
    assert ("a.pdf", JobState.RUNNING) in seen
    assert ("a.pdf", JobState.DONE) in seen


def test_cancel_all_prevents_queued_work(tree, tmp_path):
    started = threading.Event()
    release = threading.Event()

    class Blocking(FakeConverter):
        def convert(self, src, dst, opts):
            started.set()
            release.wait(timeout=5)
            super().convert(src, dst, opts)

    r = Registry()
    r.register(Blocking())
    plan = build_plan([tree], tmp_path / "out", "md", r)

    ex = ThreadExecutor(r, workers=1)
    futures = ex.submit_all(plan.runnable)
    started.wait(timeout=5)
    ex.cancel_all()
    release.set()
    for f in futures:
        f.result() if not f.cancelled() else None
    ex.shutdown()

    assert ex.cancelled
    # The in-flight file finished; nothing else was converted.
    done = [j for j in plan.jobs if j.state is JobState.DONE]
    assert len(done) <= 1


def test_inflight_count_returns_to_zero(tree, tmp_path, registry):
    plan = build_plan([tree], tmp_path / "out", "md", registry)
    ex = ThreadExecutor(registry, workers=2)
    for f in ex.submit_all(plan.runnable):
        f.result()
    ex.shutdown()
    assert ex.inflight == 0


def test_summary_from_jobs(tree, tmp_path):
    r = Registry()
    r.register(FakeConverter(fail_on=("a.pdf",)))
    out = tmp_path / "out"
    out.mkdir()
    (out / "b.md").write_text("exists")
    plan = build_plan([tree], out, "md", r)
    run_plan(plan.jobs, r)
    s = Summary.from_jobs(plan.jobs)
    assert (s.done, s.failed, s.skipped) == (1, 1, 1)
    assert s.exit_code == 1
    assert str(s) == "1 converted, 1 failed, 1 skipped"
