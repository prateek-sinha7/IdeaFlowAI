"""tests/agents/test_validator_html_element_floor.py — the ``html_element_floor`` validator (A1).

Fixture-based (the required bad/good pair): ``tests/fixtures/html_element_floor/truncated/``
holds the REAL ``draft.v2.html`` / ``draft.v3.html`` from run 7e8a8e71 — the exact
story-layer truncation STABILIZATION.md documents (89 KB / 11 sections / 30 inputs
-> 29 KB / 1 section / 0 inputs). The "good" case (an edit that adds content, never
drops it) uses a small synthetic pair — no real large clean draft pair was needed
to exercise the "nothing dropped" path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "html_element_floor"


@pytest.fixture(autouse=True)
def _reset_registry():
    registry_mod.discover()
    known = set(registry_mod._KNOWN)
    impls = dict(registry_mod._IMPLS)
    trust = dict(registry_mod._TRUST)
    discovered = registry_mod._DISCOVERED
    try:
        yield
    finally:
        registry_mod._KNOWN.clear()
        registry_mod._KNOWN.update(known)
        registry_mod._IMPLS.clear()
        registry_mod._IMPLS.update(impls)
        registry_mod._TRUST.clear()
        registry_mod._TRUST.update(trust)
        registry_mod._DISCOVERED = discovered


class _FakeSandbox:
    def __init__(self, root: Path) -> None:
        self.root = root


class _FakeRunner:
    def __init__(self, root: Path) -> None:
        self.sandbox = _FakeSandbox(root)


class _Target:
    def __init__(self, runner: Any, step: str = "story-layer") -> None:
        self.runner = runner
        self.name = "prototype.html"
        self.path = None
        self.step = step
        self.task_meta: dict = {}


def test_resolves_after_discover() -> None:
    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    assert v.name == "html_element_floor"


@pytest.mark.asyncio
async def test_bad_fixture_flags_the_7e8a8e71_truncation(tmp_path):
    """89 KB/11 sections/30 inputs (v2) -> 29 KB/1/0 (v3): every tracked count drops."""
    import shutil

    root = tmp_path / "sandbox"
    shutil.copytree(_FIXTURES / "truncated", root)
    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    issues = await v.validate(_Target(_FakeRunner(root)))

    assert issues, "expected the truncated pair to be flagged"
    messages = " | ".join(i.message for i in issues)
    for needle in ("<section data-page=", "<input", "<select", "<button", "<textarea"):
        assert needle in messages, f"{needle!r} drop not reported: {messages}"
    assert any("bytes" in i.message and "draft.v3.html" in i.message for i in issues)
    assert all(i.severity == "P0" for i in issues)
    assert all(i.validator == "html_element_floor" for i in issues)


@pytest.mark.asyncio
async def test_good_pair_adds_content_and_passes(tmp_path):
    """A normal edit pass (structure-check/story-layer) only ADDS markup — no issues."""
    root = tmp_path / "sandbox"
    root.mkdir()
    v2 = (
        "<html><body>"
        "<section data-page=\"1\"><input><button>Go</button></section>"
        "</body></html>"
    )
    v3 = (
        "<html><body>"
        "<section data-page=\"1\"><input><button>Go</button>"
        "<textarea></textarea><select><option>a</option></select>"
        "<p>An added affordance sentence that is long enough to keep the byte "
        "count comfortably above the 40% floor even after this edit.</p>"
        "</section></body></html>"
    )
    (root / "draft.v2.html").write_text(v2, encoding="utf-8")
    (root / "draft.v3.html").write_text(v3, encoding="utf-8")

    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_numeric_version_sort_not_lexicographic(tmp_path):
    """draft.v10.html must outrank draft.v9.html (numeric sort, not string sort)."""
    root = tmp_path / "sandbox"
    root.mkdir()
    # v9 has real content; v10 (the "highest") dropped everything -> must be the
    # pair actually compared, not v1 vs v9 (which a naive lexicographic max would pick).
    (root / "draft.v9.html").write_text(
        "<section data-page=\"1\"><input><button>Go</button></section>", encoding="utf-8"
    )
    (root / "draft.v10.html").write_text("<section data-page=\"1\"></section>", encoding="utf-8")
    (root / "draft.v1.html").write_text("<section data-page=\"1\"></section>", encoding="utf-8")

    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    issues = await v.validate(_Target(_FakeRunner(root)))
    messages = " | ".join(i.message for i in issues)
    assert "draft.v10.html" in messages
    assert "draft.v9.html" in messages
    assert "<input" in messages
    assert "<button" in messages


@pytest.mark.asyncio
async def test_fewer_than_two_drafts_degrades_to_no_issues(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "draft.v1.html").write_text("<section data-page=\"1\"></section>", encoding="utf-8")
    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


class _NoSandboxRunner:
    sandbox = None


@pytest.mark.asyncio
async def test_no_sandbox_degrades_to_no_issues():
    v = CapabilityRegistry().resolve("validator", "html_element_floor")
    issues = await v.validate(_Target(_NoSandboxRunner()))
    assert issues == []
