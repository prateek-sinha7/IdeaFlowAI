"""tests/agents/test_screens_plan_coverage.py — the ``screens_plan_coverage`` validator.

Fake-target/fake-sandbox helpers follow ``test_validator_fragment_field_coverage.py``'s
convention rather than inventing new ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import agents.capabilities.registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry


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
    def __init__(self, runner: Any, step: str = "screen-plan") -> None:
        self.runner = runner
        self.name = "prototype.html"
        self.path = None
        self.step = step
        self.task_meta: dict = {}


class _NoSandboxRunner:
    sandbox = None


def _spec(*ids: str) -> str:
    """A minimal spec.md with one ``### <id> — <Name>`` section per id, plus one
    UC heading and one Flow heading that must NOT be treated as screens."""
    sections = "\n\n".join(f"### {sid} — {sid.title()}\n\nSome content." for sid in ids)
    return (
        "# Spec\n\n"
        "## Use Cases\n\n"
        "### UC-1 — Search for a policy\n\nNot a screen.\n\n"
        "## Flows\n\n"
        "### Flow 1: Happy path\n\nNot a screen either.\n\n"
        "## Screens\n\n" + sections + "\n"
    )


def _inventory(*ids: str) -> str:
    return json.dumps(
        {
            "title": "Test App",
            "entry": ids[0] if ids else "screen",
            "screens": [{"id": sid, "title": sid.title()} for sid in ids],
        }
    )


def _build_sandbox(tmp_path: Path, *, spec: str | None, screens_json: str | None) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    if spec is not None:
        (root / "spec.md").write_text(spec, encoding="utf-8")
    if screens_json is not None:
        build_dir = root / "build"
        build_dir.mkdir()
        (build_dir / "screens.json").write_text(screens_json, encoding="utf-8")
    return root


def test_resolves_after_discover() -> None:
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    assert v.name == "screens_plan_coverage"


@pytest.mark.asyncio
async def test_all_spec_screens_present_no_issues(tmp_path):
    root = _build_sandbox(
        tmp_path,
        spec=_spec("search", "directory"),
        screens_json=_inventory("search", "directory"),
    )
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_two_missing_screens_named_in_message(tmp_path):
    root = _build_sandbox(
        tmp_path,
        spec=_spec("search", "directory", "quote-detail"),
        screens_json=_inventory("search"),
    )
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert len(issues) == 1
    assert issues[0].severity == "P0"
    assert issues[0].validator == "screens_plan_coverage"
    assert "directory" in issues[0].message
    assert "quote-detail" in issues[0].message


@pytest.mark.asyncio
async def test_missing_screens_json_file_flags_the_path(tmp_path):
    root = _build_sandbox(tmp_path, spec=_spec("search"), screens_json=None)
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert len(issues) == 1
    assert issues[0].severity == "P0"
    assert "build/screens.json" in issues[0].message


@pytest.mark.asyncio
async def test_unparseable_screens_json_flags_one_issue_no_crash(tmp_path):
    root = _build_sandbox(tmp_path, spec=_spec("search"), screens_json="not json at all {")
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert len(issues) == 1
    assert issues[0].severity == "P0"


@pytest.mark.asyncio
async def test_missing_spec_degrades_to_no_issues(tmp_path):
    root = _build_sandbox(tmp_path, spec=None, screens_json=_inventory("search"))
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_uc_and_flow_headings_are_not_treated_as_screens(tmp_path):
    """`### UC-1 — ...` (uppercase) and `### Flow 1: ...` (no em dash) must not be
    read as screen ids — only ``search`` is a declared screen here, and it's covered."""
    root = _build_sandbox(
        tmp_path,
        spec=_spec("search"),
        screens_json=_inventory("search"),
    )
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_extra_inventory_id_not_flagged(tmp_path):
    root = _build_sandbox(
        tmp_path,
        spec=_spec("search"),
        screens_json=_inventory("search", "extra-screen"),
    )
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_FakeRunner(root)))
    assert issues == []


@pytest.mark.asyncio
async def test_no_sandbox_degrades_to_no_issues():
    v = CapabilityRegistry().resolve("validator", "screens_plan_coverage")
    issues = await v.validate(_Target(_NoSandboxRunner()))
    assert issues == []
