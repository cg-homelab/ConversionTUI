from __future__ import annotations

import pytest

from convtui.core.models import CollisionPolicy, JobState, SkipReason
from convtui.core.planner import PlanError, build_plan


def plan_for(tree, out, registry, **kw):
    return build_plan([tree], out, "md", registry, **kw)


def test_mirrors_source_tree_into_output_dir(tree, tmp_path, registry):
    out = tmp_path / "out"
    plan = plan_for(tree, out, registry)
    dsts = sorted(j.dst.relative_to(out).as_posix() for j in plan.runnable)
    assert dsts == ["a.md", "b.md", "sub/c.md"]


def test_unsupported_files_are_not_listed_at_all(tree, tmp_path, registry):
    plan = plan_for(tree, tmp_path / "out", registry)
    assert not any(j.src.name == "notes.txt" for j in plan.jobs)


def test_non_recursive_skips_subdirectories(tree, tmp_path, registry):
    plan = plan_for(tree, tmp_path / "out", registry, recursive=False)
    assert sorted(j.src.name for j in plan.runnable) == ["a.pdf", "b.docx"]


def test_include_and_exclude_globs(tree, tmp_path, registry):
    only_pdf = plan_for(tree, tmp_path / "out", registry, include=["*.pdf"])
    assert sorted(j.src.name for j in only_pdf.runnable) == ["a.pdf", "c.pdf"]

    no_sub = plan_for(tree, tmp_path / "out", registry, exclude=["sub/**"])
    assert sorted(j.src.name for j in no_sub.runnable) == ["a.pdf", "b.docx"]


def test_hidden_files_excluded_unless_requested(tree, tmp_path, registry):
    (tree / ".secret.pdf").write_bytes(b"%PDF")
    hidden = plan_for(tree, tmp_path / "out", registry)
    assert not any(j.src.name == ".secret.pdf" for j in hidden.jobs)
    shown = plan_for(tree, tmp_path / "out", registry, show_hidden=True)
    assert any(j.src.name == ".secret.pdf" for j in shown.runnable)


# ---- collision policies ------------------------------------------------


def test_skip_policy_marks_existing_destinations(tree, tmp_path, registry):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.md").write_text("already here")
    plan = plan_for(tree, out, registry, collision=CollisionPolicy.SKIP)
    a = next(j for j in plan.jobs if j.src.name == "a.pdf")
    assert a.state is JobState.SKIPPED
    assert a.skip_reason is SkipReason.EXISTS
    assert len(plan.runnable) == 2


def test_overwrite_policy_keeps_the_job_runnable(tree, tmp_path, registry):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.md").write_text("already here")
    plan = plan_for(tree, out, registry, collision=CollisionPolicy.OVERWRITE)
    assert len(plan.runnable) == 3


def test_rename_policy_picks_a_free_name(tree, tmp_path, registry):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.md").write_text("already here")
    plan = plan_for(tree, out, registry, collision=CollisionPolicy.RENAME)
    a = next(j for j in plan.jobs if j.src.name == "a.pdf")
    assert a.dst.name == "a-1.md"
    assert a.state is JobState.QUEUED


def test_in_place_writes_beside_the_source(tree, registry):
    plan = build_plan([tree], None, "md", registry, collision=CollisionPolicy.IN_PLACE)
    a = next(j for j in plan.jobs if j.src.name == "a.pdf")
    assert a.dst == tree / "a.md"


def test_rename_avoids_collisions_within_one_plan(tmp_path, registry):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "same.pdf").write_bytes(b"%PDF")
    (root / "same.docx").write_bytes(b"PK")
    out = tmp_path / "out"
    plan = build_plan([root], out, "md", registry, collision=CollisionPolicy.RENAME)
    assert len({j.dst for j in plan.runnable}) == 2


# ---- guards ------------------------------------------------------------


def test_missing_source_is_an_error(tmp_path, registry):
    with pytest.raises(PlanError, match="no such file"):
        build_plan([tmp_path / "nope"], tmp_path / "out", "md", registry)


def test_output_inside_source_tree_is_refused(tree, registry):
    with pytest.raises(PlanError, match="inside the source tree"):
        build_plan([tree], tree / "out", "md", registry)


def test_output_dir_required_unless_in_place(tree, registry):
    with pytest.raises(PlanError, match="output directory is required"):
        build_plan([tree], None, "md", registry)


def test_empty_target_format_is_an_error(tree, tmp_path, registry):
    with pytest.raises(PlanError, match="no target format"):
        build_plan([tree], tmp_path / "out", "", registry)


def test_single_file_source(tree, tmp_path, registry):
    plan = build_plan([tree / "a.pdf"], tmp_path / "out", "md", registry)
    assert len(plan.runnable) == 1
    assert plan.runnable[0].dst == tmp_path / "out" / "a.md"


def test_symlinks_are_not_followed(tree, tmp_path, registry):
    (tree / "link.pdf").symlink_to(tree / "a.pdf")
    plan = plan_for(tree, tmp_path / "out", registry)
    assert not any(j.src.name == "link.pdf" for j in plan.jobs)


def test_unavailable_converter_is_reported_as_skipped(tmp_path):
    from convtui.core.registry import Registry
    from tests.conftest import FakeConverter

    r = Registry()
    r.register(FakeConverter(ok=False))
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.pdf").write_bytes(b"%PDF")
    plan = build_plan([root], tmp_path / "out", "md", r)
    assert plan.jobs[0].state is JobState.SKIPPED
    assert plan.jobs[0].skip_reason is SkipReason.UNAVAILABLE


def test_summary_counts(tree, tmp_path, registry):
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.md").write_text("x")
    plan = plan_for(tree, out, registry)
    assert plan.summary() == "2 to convert, 1 skipped"
