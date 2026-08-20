"""Entitlements must agree with the frontend copy and with what exists on disk.

Three hand-maintained lists describe "which pipelines are real and who may run
them", and nothing used to check they agreed:

  1. ``backend/app/core/entitlements.py::TIER_PIPELINES``  (authoritative — returns 403)
  2. ``frontend/src/lib/entitlements.ts::TIER_PIPELINES``  (decides what the UI offers)
  3. ``backend/agents/workflows/*/workflow.yaml``          (what can actually run)

Every drift between them is a user-visible bug, and all three kinds had shipped:

  * (1) vs (2): ``hello_html`` was entitled on every tier in the frontend and on
    none in the backend, so the UI offered a workflow that 403'd on launch. In the
    other direction ``custom_revision`` was entitled on the backend and missing
    from the frontend, so the UI hid Revise for runs that could be revised.
  * (1) vs (3): ``od_prototype_revision`` was entitled but had no manifest and no
    agents, and ``dotnet_to_azure`` / ``mulesoft_to_springboot`` are launchable but
    their revision pipelines are entitled to nobody — the reported
    ``pipeline_not_entitled`` 403 that could not be fixed by upgrading.

These tests turn each of those into a test failure instead of a support ticket.
They parse the frontend file as text on purpose: importing it would need a JS
runtime, and the point is to catch a hand-edit to either file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.entitlements import TIER_PIPELINES, UPGRADE_PATH

_REPO = Path(__file__).resolve().parents[3]
_FE_ENTITLEMENTS = _REPO / "frontend" / "src" / "lib" / "entitlements.ts"
_WORKFLOWS = Path(__file__).resolve().parents[2] / "agents" / "workflows"


def _frontend_tier_pipelines() -> dict[str, set[str]]:
    """Parse ``TIER_PIPELINES`` out of the frontend module."""
    src = _FE_ENTITLEMENTS.read_text(encoding="utf-8")
    block = re.search(r"TIER_PIPELINES[^=]*=\s*\{(.*?)\n\};", src, re.S)
    assert block, f"could not find TIER_PIPELINES in {_FE_ENTITLEMENTS}"
    body = block.group(1)
    # Strip // comments so a pipeline name mentioned in prose is not read as data.
    body = re.sub(r"//[^\n]*", "", body)
    return {
        tier: set(re.findall(r'"([\w]+)"', entries))
        for tier, entries in re.findall(r"(\w+):\s*new Set\(\[(.*?)\]\)", body, re.S)
    }


def _manifest_ids() -> set[str]:
    return {d.name for d in _WORKFLOWS.iterdir() if (d / "workflow.yaml").is_file()}


def _manifest(pipeline_id: str) -> dict:
    return yaml.safe_load((_WORKFLOWS / pipeline_id / "workflow.yaml").read_text(encoding="utf-8")) or {}


# Pipelines entitled without a manifest, by deliberate exception.
_ENTITLED_WITHOUT_MANIFEST = {
    # UI meta-grouping: the "Platform workflows" card makes the user choose a
    # concrete sub-pipeline before Run, so this is never dispatched. The frontend
    # gates the card on the entitlement, so the entry has to exist.
    "migration",
}


class TestFrontendBackendParity:
    def test_same_tiers(self) -> None:
        assert set(_frontend_tier_pipelines()) == set(TIER_PIPELINES)

    @pytest.mark.parametrize("tier", sorted(TIER_PIPELINES))
    def test_same_pipelines_per_tier(self, tier: str) -> None:
        fe = _frontend_tier_pipelines()[tier]
        be = TIER_PIPELINES[tier]
        assert fe == be, (
            f"tier {tier!r} has drifted.\n"
            f"  UI offers, backend refuses (launch 403s): {sorted(fe - be)}\n"
            f"  backend allows, UI hides:                 {sorted(be - fe)}"
        )


class TestEntitlementsMatchDisk:
    @pytest.mark.parametrize(
        "pipeline",
        sorted(set().union(*TIER_PIPELINES.values()) - _ENTITLED_WITHOUT_MANIFEST),
    )
    def test_entitled_pipeline_has_a_manifest(self, pipeline: str) -> None:
        """An entitled pipeline with no manifest passes the 403 gate and then dies
        at ``compile_for_run`` with FileNotFoundError — a 500 where the user was
        promised access."""
        assert pipeline in _manifest_ids(), (
            f"{pipeline!r} is entitled but has no agents/workflows/{pipeline}/workflow.yaml"
        )

    @pytest.mark.parametrize(
        "pipeline",
        sorted(p for p in _manifest_ids() if (_WORKFLOWS / p / "workflow.yaml").is_file()),
    )
    def test_user_launchable_manifest_is_entitled_somewhere(self, pipeline: str) -> None:
        """A launchable, non-beta manifest that no tier grants is offered in the UI
        and 403s for every user, including the top tier — where the message is the
        terminal "not available on your current plan" with no upgrade to offer.

        ``is_beta`` is part of the predicate, not an oversight: the catalog gates on
        ``!isBeta && canRunPipeline(...)`` (frontend HomeLaunchGrid), so a beta
        manifest is never offered no matter what the entitlements say. Two of them —
        ``reverse_engineer`` (which compiles to zero steps) and
        ``sample_subagents_parallel`` (a fan-out fixture) — are launchable and
        entitled to nobody, and are unreachable only because of that flag. Clearing
        ``is_beta`` on either without adding a tier entry should fail this test,
        which is exactly what it does.
        """
        manifest = _manifest(pipeline)
        if not manifest.get("user_launchable"):
            pytest.skip(f"{pipeline} is not user_launchable")
        if manifest.get("is_beta"):
            pytest.skip(f"{pipeline} is beta — the catalog hides it regardless")
        granted_by = [t for t, ps in TIER_PIPELINES.items() if pipeline in ps]
        assert granted_by, f"{pipeline!r} is user_launchable but entitled to no tier"


class TestRevisionCoverage:
    """A launchable pipeline whose revision is unreachable strands the user at the
    Revise button — which is exactly the reported bug."""

    @pytest.mark.parametrize(
        "pipeline",
        sorted(p for p in _manifest_ids() if not p.endswith("_revision")),
    )
    def test_revision_is_entitled_wherever_the_base_is(self, pipeline: str) -> None:
        revision = f"{pipeline}_revision"
        if revision not in _manifest_ids():
            pytest.skip(f"{pipeline} has no revision pipeline")
        for tier, granted in TIER_PIPELINES.items():
            if pipeline in granted:
                assert revision in granted, (
                    f"tier {tier!r} can run {pipeline!r} but not {revision!r} — "
                    f"Revise will 403 with a plan error the user cannot act on"
                )


class TestUpgradePathIsTotal:
    """``can_run_pipeline`` falls through to the terminal 'not available on your
    current plan' message whenever ``UPGRADE_PATH`` has no entry — which reads as
    "your plan is wrong" for what is really "this does not exist"."""

    @pytest.mark.parametrize("tier", sorted(TIER_PIPELINES))
    def test_every_tier_has_an_upgrade_entry(self, tier: str) -> None:
        assert tier in UPGRADE_PATH
