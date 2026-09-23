"""tests/agents/test_validator_journeys_coverage.py — the ``journeys_coverage`` validator (A1).

Fixture-based (the required bad/good pair): ``tests/fixtures/journeys_coverage/``
holds the REAL ``notes/doc-3.md`` / ``notes/doc-4.md`` from run a786cc27 (screens
5-8) plus that run's actual PASS-2 (good) ``journeys.md``. ``journeys_bad.md`` is a
constructed pass-1-shaped fixture (the DB agent_output for the actual bad pass
wasn't reachable offline — see STABILIZATION.md A1): the same good journeys.md with
screens 5-8 replaced by ``## SCREEN <N>: MISSING`` stubs, mirroring the journey-
designer's own MISSING-heading convention and the evidence's exact defect
(a786cc27 screens 5,6,7,8 marked MISSING despite notes/doc-3.md and notes/doc-4.md
fully documenting them).

The remaining rules (screen referenced only as a nav target with no section at
all; "Unknown Module"; a documented-but-empty FIELDS table) are covered with small
inline (non-fixture) sandboxes — the fixture pair alone cannot isolate rule 2 from
rule 1 (a MISSING heading still counts as "having a section").
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "journeys_coverage"


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
    def __init__(self, runner: Any, step: str = "journey-designer") -> None:
        self.runner = runner
        self.name = "journeys.md"
        self.path = None
        self.step = step
        self.task_meta: dict = {}


def _build_sandbox(tmp_path: Path, *, journeys_name: str) -> Path:
    """Copy the shared notes/ fixture + one journeys.md variant into a fresh sandbox root."""
    import shutil

    root = tmp_path / "sandbox"
    shutil.copytree(_FIXTURES / "notes", root / "notes")
    (root / "journeys.md").write_text(
        (_FIXTURES / journeys_name).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


def test_resolves_after_discover() -> None:
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    assert v.name == "journeys_coverage"


@pytest.mark.asyncio
async def test_bad_fixture_flags_missing_screens_documented_in_notes(tmp_path):
    """a786cc27: screens 5,6,7,8 marked MISSING while notes/doc-3.md + doc-4.md document them."""
    root = _build_sandbox(tmp_path, journeys_name="journeys_bad.md")
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))

    assert issues, "expected the bad fixture to flag the MISSING screens"
    messages = " | ".join(i.message for i in issues)
    for screen_num in ("5", "6", "7", "8"):
        assert f"Screen {screen_num}" in messages, messages
    # Feedback must name the notes file that actually documents the screen.
    assert "doc-3.md" in messages
    assert "doc-4.md" in messages
    # MISSING-despite-documented is the worst content-loss class -> P0/CRITICAL.
    assert all(i.severity == "P0" for i in issues if "MISSING" in i.message)


@pytest.mark.asyncio
async def test_good_fixture_passes_clean(tmp_path):
    """The same run's actual pass-2 journeys.md (every screen documented) raises nothing."""
    root = _build_sandbox(tmp_path, journeys_name="journeys_good.md")
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_screen_referenced_only_as_nav_target_with_no_section_at_all(tmp_path):
    """Rule 2: a screen named only as a navigation target, with zero section in journeys.md."""
    root = tmp_path / "sandbox"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "doc-1.md").write_text(
        "## Screen 1: Anchor\nNext -> Screen 7: Furrow\n", encoding="utf-8"
    )
    (root / "journeys.md").write_text(
        "## SCREEN 1: ANCHOR\n\n**FIELDS**\n\n| Label | Type |\n|---|---|\n| Name | text |\n",
        encoding="utf-8",
    )
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert any("Screen 7" in i.message and "no section" in i.message for i in issues)


@pytest.mark.asyncio
async def test_unknown_module_stage_header_flagged(tmp_path):
    """Rule 3: a stage/journey header naming 'Unknown Module' is always a defect."""
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "journeys.md").write_text(
        "## STAGE 1: UNKNOWN MODULE\n\n## SCREEN 1: ANCHOR\n\ncontent\n",
        encoding="utf-8",
    )
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert any("Unknown Module" in i.message for i in issues)


@pytest.mark.asyncio
async def test_zero_field_rows_while_notes_lists_fields(tmp_path):
    """Rule 4: a documented screen whose journeys.md FIELDS table lost every row."""
    root = tmp_path / "sandbox"
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "doc-1.md").write_text(
        "## Screen 1: Anchor\n\n**Fields:**\n- Client Name (text) — Mandatory\n- Policy Type (dropdown) — Mandatory\n",
        encoding="utf-8",
    )
    (root / "journeys.md").write_text(
        "## SCREEN 1: ANCHOR\n\n**Purpose:** intro\n\nno fields table here at all\n",
        encoding="utf-8",
    )
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert any(
        "Screen 1" in i.message and "zero rows" in i.message and i.severity == "P1"
        for i in issues
    )


class _NoSandboxRunner:
    sandbox = None


@pytest.mark.asyncio
async def test_no_sandbox_degrades_to_no_issues():
    v = CapabilityRegistry().resolve("validator", "journeys_coverage")
    issues = await v.validate(_Target(_NoSandboxRunner()))
    assert issues == []
