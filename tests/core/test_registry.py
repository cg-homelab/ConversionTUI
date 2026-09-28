from __future__ import annotations

from convtui.core.registry import Registry, normalize_ext
from tests.conftest import FakeConverter


def test_normalize_ext_adds_dot_and_lowercases():
    assert normalize_ext("PDF") == ".pdf"
    assert normalize_ext(".MD") == ".md"
    assert normalize_ext("") == ""


def test_resolve_finds_converter_for_pair(registry):
    assert registry.resolve(".pdf", ".md") is not None
    assert registry.resolve(".xyz", ".md") is None
    assert registry.resolve(".pdf", ".html") is None


def test_resolve_is_case_insensitive(registry):
    assert registry.resolve("PDF", "MD") is not None


def test_higher_priority_wins_then_registration_order():
    r = Registry()
    low = FakeConverter(name="low", priority=0)
    high = FakeConverter(name="high", priority=10)
    r.register(low)
    r.register(high)
    assert r.resolve(".pdf", ".md").name == "high"
    assert [c.name for c in r.candidates(".pdf", ".md")] == ["high", "low"]


def test_prefer_forces_a_named_converter():
    r = Registry()
    r.register(FakeConverter(name="one", priority=10))
    r.register(FakeConverter(name="two"))
    assert r.resolve(".pdf", ".md", prefer="two").name == "two"
    assert r.resolve(".pdf", ".md", prefer="missing") is None


def test_unavailable_converter_is_not_resolved_but_is_still_a_candidate():
    r = Registry()
    r.register(FakeConverter(name="broken", ok=False))
    assert r.resolve(".pdf", ".md") is None
    assert len(r.candidates(".pdf", ".md")) == 1


def test_available_converter_wins_over_unavailable_one():
    r = Registry()
    r.register(FakeConverter(name="broken", priority=10, ok=False))
    r.register(FakeConverter(name="working"))
    assert r.resolve(".pdf", ".md").name == "working"


def test_extension_sets(registry):
    assert registry.input_extensions() == {".pdf", ".docx"}
    assert registry.output_extensions() == {".md"}
