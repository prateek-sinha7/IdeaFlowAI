"""ISS-100 — the handoff pipeline's model spend is invisible.

Three call sites in ``app/services/handoff_pipeline.py`` construct/call agents
that ACCEPT a ``usage_sink`` kwarg (``classify_task``, ``TestAgent``,
``ComplianceAgent`` — see ``classifier.py:33``, ``test_agent.py:109``,
``compliance_agent.py:121``) but the pipeline never gives them one, so their
model spend is never captured. Separately, ``HandoffSession`` (the
``handoff_sessions`` table) has no column to even hold a captured token count.

These tests pin the CORRECT behaviour — a sink is threaded through, and the
model has somewhere to put the number — so they fail today and pass once
ISS-100 is fixed.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from typing import Any
from unittest.mock import patch

import pytest

# Reuse the frozen contract test's fakes for the git seam (clone / metadata /
# cleanup) rather than re-inventing a workspace fixture.
from tests.integration.test_handoff_contract import (
    HANDOFF_ID,
    HANDOFF_PUBLIC_URL,
    HANDOFF_TOKEN,
    ISSUER_EMAIL,
    REPO_URL,
    TASK,
    _fake_clone,
    _fake_cleanup_workspace,
    _fake_create_pull_request,
    _fake_get_repo_metadata,
)


class _FakeGitResult:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


@pytest.mark.issue("ISS-100")
@pytest.mark.xfail(reason="ISS-100 unfixed", strict=True)
@pytest.mark.asyncio
async def test_pipeline_threads_usage_sink_to_classify_and_agents() -> None:
    """classify_task / TestAgent / ComplianceAgent must each receive a usage_sink.

    Drives the real ``run_handoff_pipeline`` with ``requested_mode="auto"`` (so
    ``classify_task`` runs) resolving to "test" (so the coding/commit/push path,
    irrelevant here, is skipped). Spies on the three call sites and asserts each
    was given a non-None ``usage_sink`` — today none of them are.
    """
    from app.services import handoff_github as gh
    from app.services import handoff_pipeline as hp

    calls: dict[str, Any] = {}

    async def spy_classify(task_description, transcript_excerpt=None, usage_sink=None):
        calls["classify_task"] = usage_sink
        return "test"

    class SpyTestAgent:
        def __init__(self, usage_sink=None) -> None:
            calls["TestAgent"] = usage_sink

        async def analyse(self, **kwargs) -> dict[str, Any]:
            return {"summary": "ok", "verdict": "concerns", "tests_present": [],
                     "missing_coverage": [], "quality_issues": [], "recommended_additions": []}

    class SpyComplianceAgent:
        def __init__(self, usage_sink=None) -> None:
            calls["ComplianceAgent"] = usage_sink

        async def review(self, **kwargs) -> dict[str, Any]:
            return {"summary": "ok", "verdict": "approve_with_changes", "findings": [],
                     "positives": []}

    stack = contextlib.ExitStack()
    stack.enter_context(patch.object(gh, "clone", _fake_clone))
    stack.enter_context(patch.object(gh, "get_repo_metadata", _fake_get_repo_metadata))
    stack.enter_context(patch.object(gh, "create_pull_request", _fake_create_pull_request))
    stack.enter_context(patch.object(gh, "checkout_new_branch", lambda ws, b: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "stage_all", lambda ws: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "commit", lambda ws, m: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "push", lambda t, p, ws, b: _FakeGitResult(0)))
    stack.enter_context(patch.object(gh, "wipe_credentialed_remote", lambda ws: None))
    stack.enter_context(patch.object(gh, "cleanup_workspace", _fake_cleanup_workspace))
    stack.enter_context(patch.object(hp, "classify_task", spy_classify))
    stack.enter_context(patch.object(hp, "TestAgent", SpyTestAgent))
    stack.enter_context(patch.object(hp, "ComplianceAgent", SpyComplianceAgent))

    try:
        generator = hp.run_handoff_pipeline(
            handoff_id=HANDOFF_ID,
            handoff_token=HANDOFF_TOKEN,
            task_description=TASK,
            transcript_excerpt=None,
            repo_url=REPO_URL,
            requested_mode="auto",
            source_branch=None,
            pat="github_pat_fake_value",
            issuer_email=ISSUER_EMAIL,
            handoff_public_url=HANDOFF_PUBLIC_URL,
        )
        async for _event in generator:
            pass
    finally:
        stack.close()

    assert calls.get("classify_task") is not None, "classify_task got no usage_sink"
    assert calls.get("TestAgent") is not None, "TestAgent got no usage_sink"
    assert calls.get("ComplianceAgent") is not None, "ComplianceAgent got no usage_sink"


@pytest.mark.issue("ISS-100")
@pytest.mark.xfail(reason="ISS-100 unfixed", strict=True)
def test_handoff_session_has_a_token_usage_column() -> None:
    """``handoff_sessions`` must have somewhere to persist captured model spend.

    Today the table has 21 columns and none of them are cost/token related, so
    even a correctly captured usage number has no home.
    """
    from app.models.handoff import HandoffSession

    column_names = {c.name for c in HandoffSession.__table__.columns}
    token_columns = {c for c in column_names if "token" in c.lower() and c != "token"}
    cost_columns = {c for c in column_names if any(w in c.lower() for w in ("usage", "cost", "spend"))}

    assert token_columns or cost_columns, (
        f"handoff_sessions has no token/cost column; columns={sorted(column_names)}"
    )
