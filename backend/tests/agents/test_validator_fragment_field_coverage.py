"""tests/agents/test_validator_fragment_field_coverage.py — the ``fragment_field_coverage`` validator (A1).

Fixture-based (the required bad/good pair):
``tests/fixtures/fragment_field_coverage/journeys.md`` is the REAL "Screen 6:
Vellum" section from run 5130337e (3 discount checkboxes). ``screens_good/6.html``
is that run's real, correct fragment (all 3 present). ``screens_bad/6.html`` is
constructed by stripping exactly those 3 field blocks from the same real fragment
— run 5130337e itself self-healed by the time it reached disk (STABILIZATION.md
traces the root cause to journey-designer, not the builder), so the ON-DISK
fragment for that run no longer reproduces the defect; this fixture reproduces the
documented symptom ("screen 6 shipped without Bundle with Home Policy / Paperless
Billing / Good Student Discount") directly and mechanically.

The sidecar rule uses the REAL ``screens/2_fixed.html`` from run a786cc27 pass 3
(a worker wrote to the wrong target file).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "fragment_field_coverage"


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
    def __init__(self, runner: Any, step: str = "screen-builder") -> None:
        self.runner = runner
        self.name = "prototype.html"
        self.path = None
        self.step = step
        self.task_meta: dict = {}


def _build_sandbox(tmp_path: Path, *, screens_variant: str) -> Path:
    import shutil

    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "journeys.md").write_text(
        (_FIXTURES / "journeys.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    shutil.copytree(_FIXTURES / screens_variant, root / "screens")
    return root


def test_resolves_after_discover() -> None:
    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    assert v.name == "fragment_field_coverage"


@pytest.mark.asyncio
async def test_bad_fixture_flags_missing_field_labels(tmp_path):
    """5130337e: screen 6 shipped without its 3 discount checkbox labels."""
    root = _build_sandbox(tmp_path, screens_variant="screens_bad")
    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))

    assert issues, "expected the stripped fragment to be flagged"
    messages = " | ".join(i.message for i in issues)
    assert "screens/6.html" in messages
    for label in ("Bundle with Home Policy", "Paperless Billing", "Good Student Discount"):
        assert label in messages, messages
    assert all(i.severity == "P0" for i in issues)
    assert all(i.validator == "fragment_field_coverage" for i in issues)


@pytest.mark.asyncio
async def test_good_fixture_passes_clean(tmp_path):
    """The real, correct 5130337e fragment (all 3 checkboxes present) raises nothing."""
    root = _build_sandbox(tmp_path, screens_variant="screens_good")
    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_sidecar_file_is_flagged(tmp_path):
    """a786cc27 pass 3: a worker wrote screens/2_fixed.html instead of screens/2.html."""
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "journeys.md").write_text("## SCREEN 2: BEACON\n\nno fields here\n", encoding="utf-8")
    import shutil

    shutil.copytree(_FIXTURES / "screens_sidecar", root / "screens")

    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues, "expected the sidecar file to be flagged"
    messages = " | ".join(i.message for i in issues)
    assert "screens/2_fixed.html" in messages
    assert "screens/2.html" in messages
    assert all(i.severity == "P0" for i in issues)


@pytest.mark.asyncio
async def test_no_screens_dir_degrades_to_no_issues(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "journeys.md").write_text("## SCREEN 1: ANCHOR\n", encoding="utf-8")
    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


class _NoSandboxRunner:
    sandbox = None


@pytest.mark.asyncio
async def test_no_sandbox_degrades_to_no_issues():
    v = CapabilityRegistry().resolve("validator", "fragment_field_coverage")
    issues = await v.validate(_Target(_NoSandboxRunner()))
    assert issues == []
