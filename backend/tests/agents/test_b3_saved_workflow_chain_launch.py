"""tests/agents/test_b3_saved_workflow_chain_launch.py — B3 regression guard.

GIT_VERSIONING_BUGS.md B3: "chaining a saved workflow from history has no route."

The gap was entirely frontend: the backend already accepts both ``user_workflow_id``
and ``source_workflow_run_id`` in the same ``LaunchCommand`` payload since the
``USER_WORKFLOW_FLAT`` / ``USER_WORKFLOW_MANIFEST`` launch branches were introduced.

This file provides two backend-side proofs:

1. **Schema-level**: ``LaunchCommand`` accepts both fields simultaneously and
   neither value is zeroed by the other's presence.

2. **admit_chain_launch with a user-workflow launch**: the chain admission gate
   reads ``chains_from`` from the target workflow's compiled manifest regardless
   of launch shape — both the FILE_PIPELINE and USER_WORKFLOW_* branches go
   through the same gate.  The gate returns ``declaration_gate`` (inactive) when
   the manifest does not declare ``chains_from``, and falls through to the
   ownership + finalization checks when it does.  This confirms the backend
   handles ``user_workflow_id + source_workflow_run_id`` without any changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


# ---------------------------------------------------------------------------
# 1. LaunchCommand accepts both user_workflow_id and source_workflow_run_id
# ---------------------------------------------------------------------------


class TestLaunchCommandAcceptsBothChainFields:
    """LaunchCommand schema accepts user_workflow_id and source_workflow_run_id
    simultaneously — the prerequisite for the B3 frontend fix to work."""

    def test_both_fields_accepted_together(self) -> None:
        """Pydantic validation must not reject a body with both fields set."""
        from app.api.run_commands import LaunchCommand

        cmd = LaunchCommand(
            message="a brief for the new workflow",
            pipeline_type="custom",
            user_workflow_id="saved-workflow-uuid-1234",
            source_workflow_run_id="source-run-uuid-5678",
        )
        assert cmd.user_workflow_id == "saved-workflow-uuid-1234"
        assert cmd.source_workflow_run_id == "source-run-uuid-5678"

    def test_user_workflow_id_alone_still_works(self) -> None:
        """A saved-workflow launch without chaining is still valid (regression)."""
        from app.api.run_commands import LaunchCommand

        cmd = LaunchCommand(
            message="run the saved workflow",
            pipeline_type="custom",
            user_workflow_id="saved-workflow-uuid-alone",
        )
        assert cmd.user_workflow_id == "saved-workflow-uuid-alone"
        assert cmd.source_workflow_run_id is None

    def test_source_workflow_run_id_alone_still_works(self) -> None:
        """A chain launch without a saved workflow is still valid (regression)."""
        from app.api.run_commands import LaunchCommand

        cmd = LaunchCommand(
            message="chain from a previous run",
            pipeline_type="user_stories",
            source_workflow_run_id="source-run-uuid-only",
        )
        assert cmd.source_workflow_run_id == "source-run-uuid-only"
        assert cmd.user_workflow_id is None

    def test_neither_field_is_required(self) -> None:
        """Both fields are optional — a plain launch body must still validate."""
        from app.api.run_commands import LaunchCommand

        cmd = LaunchCommand(
            message="plain launch",
            pipeline_type="user_stories",
        )
        assert cmd.user_workflow_id is None
        assert cmd.source_workflow_run_id is None


# ---------------------------------------------------------------------------
# 2. admit_chain_launch gate works regardless of launch shape
# ---------------------------------------------------------------------------


class TestAdmitChainLaunchWithSavedWorkflow:
    """The admission gate reads chains_from from the compiled manifest.
    For a USER_WORKFLOW_* launch the compiled plan is set before the gate fires,
    just as it is for FILE_PIPELINE.  The gate's behaviour is launch-shape-agnostic.

    These tests drive admit_chain_launch directly with a pre-compiled plan
    (bypassing the HTTP layer) to prove the chain contract holds.
    """

    def test_declaration_gate_fires_when_chains_from_false(self) -> None:
        """A workflow that does not declare chains_from=True is refused immediately
        with zero cross-run reads, regardless of whether it is a saved workflow.
        This is the fast path for every non-chained launch.
        """
        from unittest.mock import MagicMock
        from app.api.run_commands import admit_chain_launch, ChainAdmission

        # Build a minimal compiled plan stub with chains_from=False.
        deliverable = MagicMock()
        deliverable.chains_from = False
        deliverable.chain_policy = "refuse"
        deliverable.name = None
        compiled = MagicMock()
        compiled.deliverable = deliverable

        # Any source_run_id — declaration_gate fires before the DB is touched.
        result = admit_chain_launch(
            db=MagicMock(),
            compiled=compiled,
            source_run_id="any-source-run-id",
            current_user=MagicMock(id="user-1"),
            pipeline_type="custom",
        )
        assert result.active is False
        assert result.refusal_reason == "declaration_gate"

    def test_declaration_gate_fires_when_source_run_id_none(self) -> None:
        """No cross-run reads when source_workflow_run_id is absent, even when
        the manifest declares chains_from=True — the gate short-circuits on
        source_run_id=None so a plain launch never touches foreign sandboxes.
        """
        from unittest.mock import MagicMock
        from app.api.run_commands import admit_chain_launch

        deliverable = MagicMock()
        deliverable.chains_from = True
        deliverable.chain_policy = "refuse"
        deliverable.name = "output.md"
        compiled = MagicMock()
        compiled.deliverable = deliverable

        result = admit_chain_launch(
            db=MagicMock(),
            compiled=compiled,
            source_run_id=None,  # ← no source supplied
            current_user=MagicMock(id="user-1"),
            pipeline_type="user_stories",
        )
        assert result.active is False
        assert result.refusal_reason == "declaration_gate"

    def test_chains_from_true_with_source_proceeds_to_idor_gate(self) -> None:
        """When chains_from=True and source_run_id is non-None, the gate passes
        the declaration check and tries to fetch the source row.  A missing /
        cross-owner source raises HTTPException(404) — the gate does NOT return
        declaration_gate, proving it reached the ownership check.
        """
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from app.api.run_commands import admit_chain_launch

        deliverable = MagicMock()
        deliverable.chains_from = True
        deliverable.chain_policy = "refuse"
        deliverable.name = "output.md"
        compiled = MagicMock()
        compiled.deliverable = deliverable

        # DB session returns None for the source row → cross-owner / missing.
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            admit_chain_launch(
                db=db,
                compiled=compiled,
                source_run_id="non-existent-run-id",
                current_user=MagicMock(id="user-1"),
                pipeline_type="user_stories",
            )
        assert exc_info.value.status_code == 404, (
            "Missing / cross-owner source must return 404 (IDOR gate, "
            "Requirement 6 AC 1)"
        )

    def test_same_gate_called_for_user_workflow_manifest_shape(self) -> None:
        """USER_WORKFLOW_MANIFEST shape: the compiled plan is built from the
        manifest JSON before the gate.  The gate's logic is identical regardless
        of which branch produced `compiled`.  Proved by driving the gate with a
        compiled plan built from a real manifest string (user_stories, which
        declares chains_from=True) — the declaration check passes and the gate
        proceeds to the IDOR check.
        """
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from agents.execution_engine.engine import compile_for_run

        # Compile the real user_stories manifest (which has chains_from=True).
        # If the manifest cannot be found on this machine, skip.
        try:
            compiled = compile_for_run("user_stories")
        except FileNotFoundError:
            pytest.skip("user_stories workflow.yaml not found on this machine")

        assert (
            compiled.deliverable.chains_from is True
        ), "user_stories must declare chains_from=True for this test to be meaningful"

        from app.api.run_commands import admit_chain_launch

        # DB returns None → IDOR 404, proving the gate reached step 2.
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            admit_chain_launch(
                db=db,
                compiled=compiled,  # ← same object USER_WORKFLOW_MANIFEST sets
                source_run_id="any-source",
                current_user=MagicMock(id="user-x"),
                pipeline_type="user_stories",
            )
        assert exc_info.value.status_code == 404, (
            "USER_WORKFLOW_MANIFEST-shaped compiled plan must reach the IDOR gate "
            "— the declaration check passed because chains_from=True"
        )
