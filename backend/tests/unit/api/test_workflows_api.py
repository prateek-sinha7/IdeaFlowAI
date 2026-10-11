"""Plan 04-05 Task 2 — /api/workflows serves manifest-derived definitions (API-01).

After the run-history CRUD moved to ``/api/runs`` (Task 1 / D-02), this router
was reclaimed for the composer: it lists every authored workflow from the
compiled manifests and returns the full compiled step config for a known id,
404 on an unknown id. These tests pin:

* ``test_list_returns_all_authored_workflows`` — one entry per
  ``PIPELINE_AGENTS`` id, with id/name/description/step-summary metadata.
* ``test_get_prototype_matches_manifest`` — the ``prototype`` payload matches
  its compiled manifest (agents in order, gates, deliverable).
* ``test_get_unknown_id_is_404`` — an unknown id is rejected without ever
  touching the filesystem (T-04-13 path-traversal mitigation).

Drives a FastAPI ``TestClient`` with ``get_current_user`` overridden (the same
pattern as ``test_agents_api_real_registry.py``), plus a ``get_db`` override on
an in-memory SQLite session.

The DB override exists ONLY for spec 016's workflow-override read: the router
looks up whether THIS caller has saved an override of a built-in. It still
issues no run-history query — see ``test_list_does_not_query_workflow_run``,
which is what that test has always actually been about. Every test here runs
with an EMPTY overrides table, so every assertion below is the un-overridden
payload: that is the point, it pins the no-override path as unchanged.
"""

from __future__ import annotations


from agents.execution_engine.engine import compile_for_run
from agents.registry import get_pipeline_agents
from app.api.workflows import _KNOWN_WORKFLOW_IDS


# ---------------------------------------------------------------------------
# GET /api/workflows — list every authored workflow with metadata
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /api/workflows/{id} — full compiled config + 404
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FIX-051 / ISS-035 — _KNOWN_WORKFLOW_IDS is manifest-derived, not a
# PIPELINE_AGENTS proxy (drift pins)
# ---------------------------------------------------------------------------


class TestKnownWorkflowIdsDiscovery:
    def test_matches_workflows_directory_independently(self):
        # Re-derive the manifest-id set directly from the filesystem (not via
        # the router's own helper) and assert it matches exactly — catches
        # "a manifest was added/removed but discovery didn't pick it up". Must
        # also gate on SUPPORTED_PIPELINE_TYPES: agents/workflows/ contains
        # non-pipeline test-fixture manifests (sample_brownfield/fanout/wave)
        # that must never surface as real workflows (ISS-015).
        from agents.execution_engine.engine import _WORKFLOWS_DIR
        from agents.loader import SUPPORTED_PIPELINE_TYPES

        on_disk = {
            p.name
            for p in _WORKFLOWS_DIR.iterdir()
            if p.is_dir()
            and p.name in SUPPORTED_PIPELINE_TYPES
            and (p / "workflow.yaml").exists()
        }
        assert _KNOWN_WORKFLOW_IDS == on_disk

    def test_sample_fixtures_declare_themselves_unlaunchable(self):
        # Was `test_sample_fixtures_are_not_exposed`, asserting these ids never
        # reached _KNOWN_WORKFLOW_IDS. That held only because the hand-typed
        # SUPPORTED_PIPELINE_TYPES frozenset omitted them — nobody DECIDED to
        # hide them, and FANOUT-USER-FACING-SCOPE.md:30 records the actual
        # intent as "carry NO user_launchable key -> default False".
        #
        # ADR-0005 derives the type set from disk, so a name-based exclusion is
        # no longer available and would violate SC-001 if reintroduced. The
        # honest mechanism is the declared flag: these three reference agents
        # with no AGENT.md, cannot run, and now say so in their manifests.
        from agents.execution_engine.engine import _WORKFLOWS_DIR
        from agents.workflows.manifest import load_manifest

        for fixture_id in ("sample_brownfield", "sample_fanout", "sample_wave"):
            assert fixture_id in _KNOWN_WORKFLOW_IDS, (
                f"{fixture_id} has an authored workflow.yaml, so discovery must "
                "find it — visibility and launchability are separate concerns"
            )
            manifest = load_manifest(fixture_id, _WORKFLOWS_DIR)
            assert manifest.user_launchable is False, (
                f"{fixture_id} references agents with no AGENT.md; its manifest "
                "must declare user_launchable: false rather than rely on a "
                "hardcoded exclusion list (SC-001)"
            )

        # sample_subagents_parallel is the control: same directory, same is_beta,
        # but its agent (custom-agent) DOES exist, so it is legitimately launchable.
        assert "sample_subagents_parallel" in _KNOWN_WORKFLOW_IDS
        assert (
            load_manifest("sample_subagents_parallel", _WORKFLOWS_DIR).user_launchable
            is True
        )

    def test_spec_kit_has_agents_but_no_manifest_yet(self):
        # ISS-035 proof case: spec_kit agents are real and discoverable via
        # get_pipeline_agents/PIPELINE_AGENTS, but there is no authored
        # workflow.yaml for spec_kit yet, so it must NOT be exposed as a
        # launchable workflow. If a manifest is later added, this assertion
        # forces a conscious test update rather than an unnoticed catalog
        # change.
        assert get_pipeline_agents(
            "spec_kit"
        ), "expected spec_kit to have real, loadable agents on disk"
        assert "spec_kit" not in _KNOWN_WORKFLOW_IDS

    def test_every_known_workflow_id_compiles(self):
        # Would have caught the naive "PIPELINE_AGENTS.keys() == workflows"
        # assumption directly: every id claimed as a known workflow must
        # actually compile.
        for wid in _KNOWN_WORKFLOW_IDS:
            compile_for_run(wid)  # raises on failure
