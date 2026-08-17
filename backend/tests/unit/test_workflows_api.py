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
pattern as ``test_agents_api_real_registry.py``). The router issues NO DB query,
so no ``get_db`` override is needed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.execution_engine.engine import compile_for_run
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents
from app.api.workflows import _KNOWN_WORKFLOW_IDS, router
from app.core.dependencies import get_current_user


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id="user-1")
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/workflows — list every authored workflow with metadata
# ---------------------------------------------------------------------------


class TestList:
    def test_list_returns_all_authored_workflows(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ids = {w["id"] for w in body}
        # FIX-051: "authored workflow" = has a workflow.yaml manifest, not just
        # a PIPELINE_AGENTS key (PIPELINE_AGENTS can now list a pipeline_type
        # with agents but no manifest yet, e.g. spec_kit — see ISS-035).
        assert ids == _KNOWN_WORKFLOW_IDS, (
            f"list did not cover every authored workflow: {ids ^ _KNOWN_WORKFLOW_IDS}"
        )
        assert len(body) == len(_KNOWN_WORKFLOW_IDS)

    def test_list_entries_carry_metadata(self, client):
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        proto = by_id["prototype"]
        assert proto["name"] == "Prototype"
        assert proto["description"], "empty description"
        assert proto["step_count"] == len(get_pipeline_agents("prototype"))
        assert [s["agent_id"] for s in proto["steps"]] == [
            s.id for s in get_pipeline_agents("prototype")
        ]

    @pytest.mark.parametrize("workflow_id", sorted(_KNOWN_WORKFLOW_IDS))
    def test_list_step_count_matches_compiled_plan(self, client, workflow_id):
        # WR-01 regression guard: the list step_count must derive from the
        # COMPILED plan and match get_pipeline_agents — 'ppt' (whose agents now
        # declare pipeline_type: ppt directly) reports its real 3 steps.
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        compiled = compile_for_run(workflow_id)
        entry = by_id[workflow_id]
        assert entry["step_count"] == len(compiled.steps), (
            f"{workflow_id}: list step_count {entry['step_count']} != "
            f"compiled plan {len(compiled.steps)}"
        )
        assert len(entry["steps"]) == len(compiled.steps)

    def test_list_ppt_reports_nonempty_steps(self, client):
        # The specific bug WR-01 fixed: 'ppt' previously reported step_count=0
        # and empty steps. It has 3 well-defined steps.
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}
        ppt = by_id["ppt"]
        assert ppt["step_count"] == len(compile_for_run("ppt").steps) > 0
        assert len(ppt["steps"]) > 0
        # Names resolve via the membership fallback, not bare agent ids.
        assert all(s["name"] for s in ppt["steps"])

    def test_list_carries_launchable_flags(self, client):
        # Plan 20-01 (+ Plan 20-02 is_beta sibling): launchability is a DECLARED
        # manifest flag surfaced per row, never a hardcoded name list. Every
        # non-revision, non-internal pipeline is user_launchable=true (including
        # reverse_engineer/the sample_* proofs — nothing is hidden from the
        # catalog; incomplete pipelines are marked is_beta=true instead, which
        # the FE renders greyed-out and non-interactive rather than absent).
        # Every *_revision id stays user_launchable=false (revisions are dispatched
        # from an existing run, never launched standalone from the catalog); `chat`
        # also stays user_launchable=false — its launch surface is the dedicated
        # ChatRunner, not run_pipeline/ExecutionEngine, so a catalog card would
        # submit a launch this backend path cannot service (see chat/workflow.yaml).
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}

        # sample_brownfield/sample_fanout/sample_wave carry catalog metadata too
        # (display_name/user_launchable/is_beta) for consistency, but never reach
        # this endpoint at all — SUPPORTED_PIPELINE_TYPES excludes them (ISS-015:
        # they are execution-engine test fixtures with no product launch surface),
        # so they are asserted absent below, not launchable.
        launchable_plain = {
            "app_builder",
            "user_stories",
            "custom",
            "mulesoft_to_springboot",
            "dotnet_to_azure",
            "reverse_engineer",
        }
        for wid in launchable_plain:
            assert by_id[wid]["user_launchable"] is True, f"{wid} should be launchable"
            assert by_id[wid]["launch_surface"] is None, f"{wid} has no wizard surface"

        # ADR-0005: these three used to be ABSENT here, but only because the
        # hand-typed SUPPORTED_PIPELINE_TYPES frozenset happened to omit them —
        # an accident this test's own first paragraph forbids ("never a hardcoded
        # name list ... nothing is hidden from the catalog"). Now that the set is
        # derived from disk they appear, and they say what they are: their
        # manifests declare `user_launchable: false` because their agents have no
        # AGENT.md and a launch would raise. Assert the DECLARED FLAG, which is
        # the rule, instead of absence, which was the accident.
        for sample_id in ("sample_brownfield", "sample_fanout", "sample_wave"):
            assert sample_id in by_id, (
                f"{sample_id} has a manifest, so it belongs in the catalog "
                "response — hiding it by name is the SC-001 violation this "
                "test's own preamble rules out"
            )
            assert by_id[sample_id]["user_launchable"] is False, (
                f"{sample_id} references agents with no AGENT.md and cannot run; "
                "its manifest must declare user_launchable: false"
            )
            assert by_id[sample_id]["is_beta"] is True, (
                f"{sample_id} is incomplete and must render greyed-out"
            )

        for wid in ("prototype", "ppt"):
            assert by_id[wid]["user_launchable"] is True, f"{wid} should be launchable"
            assert by_id[wid]["launch_surface"] == "wizard", f"{wid} is a wizard tile"

        # Non-launchables: the *_revision ids + chat (dedicated ChatRunner surface).
        non_launchable = {wid for wid in by_id if wid.endswith("_revision")} | {"chat"}
        assert non_launchable, "expected at least one non-launchable id to assert on"
        for wid in non_launchable:
            assert by_id[wid]["user_launchable"] is False, (
                f"{wid} must NOT be user_launchable"
            )
            assert by_id[wid]["launch_surface"] is None

        # display_name carries ONLY the manifest's EXPLICIT label (WR-01 /
        # UXFIX-01-D-18): the BE never coalesces to the title-cased raw id, so a
        # row's display_name is exactly what its manifest authors (or None where
        # intentionally unauthored — the FE then falls back to the friendly
        # WORKFLOW_LABELS map). `name` keeps the _display_name value for
        # back-compat consumers (asserted via test_list_entries_carry_metadata).
        #
        # 22-07 authored friendly names on the launchable manifests; `custom`
        # (the user-composed entry) stays unauthored on purpose. Assert BOTH
        # halves of the coalesce contract: authored rows carry their verbatim
        # label, and the deliberately-unauthored row stays None.
        authored = {
            "user_stories": "Generate product requirements",
            "prototype": "Build an interactive prototype",
            "ppt": "Pitch an idea",
            "app_builder": "Build an end-to-end application",
            "mulesoft_to_springboot": "MuleSoft to Spring Boot",
            "dotnet_to_azure": ".NET to Azure",
        }
        for wid, label in authored.items():
            if wid in by_id:
                assert by_id[wid]["display_name"] == label, (
                    f"{wid} must carry its authored display_name verbatim "
                    f"(got {by_id[wid]['display_name']!r})"
                )
        # `custom` now carries an authored display_name too (every catalog
        # entry has a proper, user-facing name — none stay unauthored).
        if "custom" in by_id:
            assert by_id["custom"]["display_name"] == "Compose a custom workflow", (
                f"custom must carry its authored display_name verbatim "
                f"(got {by_id['custom']['display_name']!r})"
            )

    def test_list_does_not_query_workflow_run(self, client):
        # The router imports no DB session; a clean list call must succeed with
        # no get_db override present (proves no WorkflowRun dependency).
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text

    def test_list_carries_chained_from_and_short_name(self, client):
        # Plan 34-01: chaining is backend-owned via each target's OWN authored
        # `chained_from` consent list — REPLACES the formerly frontend-hardcoded
        # CHAIN_OPTIONS/CHAINABLE_FROM_TYPES (workflowChaining.ts). A source
        # workflow may only offer "chain into X" if X's manifest lists it.
        resp = client.get("/api/workflows")
        assert resp.status_code == 200, resp.text
        by_id = {w["id"]: w for w in resp.json()}

        # short_name: concise noun-phrase label authored on every real manifest
        # (chiefly for the chain-suggestion chips, where display_name's full
        # action-phrase sentence is too long).
        short_names = {
            "prototype": "Prototype",
            "user_stories": "User Stories",
            "ppt": "PPT",
            "app_builder": "App Builder",
        }
        for wid, short in short_names.items():
            assert by_id[wid]["short_name"] == short, (
                f"{wid} must carry its authored short_name verbatim "
                f"(got {by_id[wid]['short_name']!r})"
            )

        # chained_from: prototype/user_stories/ppt chain into each other freely
        # (no beta edges among the three). Order is NOT asserted — only set
        # membership + each entry's beta flag.
        def _as_set(entries):
            return {(e["id"], e["beta"]) for e in entries}

        assert _as_set(by_id["prototype"]["chained_from"]) == {
            ("user_stories", False),
            ("ppt", False),
        }
        assert _as_set(by_id["user_stories"]["chained_from"]) == {
            ("prototype", False),
            ("ppt", False),
        }
        assert _as_set(by_id["ppt"]["chained_from"]) == {
            ("prototype", False),
            ("user_stories", False),
        }

        # app_builder: prototype, ppt, and user_stories may all chain into it
        # (app_builder/workflow.yaml's chained_from consent list), and every
        # edge is beta ("Coming Soon") even though app_builder itself is NOT
        # is_beta and is fully launchable on its own catalog card.
        assert by_id["app_builder"]["is_beta"] is False
        assert _as_set(by_id["app_builder"]["chained_from"]) == {
            ("prototype", True),
            ("ppt", True),
            ("user_stories", True),
        }

        # A manifest that never declares chained_from degrades to an empty
        # list (INV-3 parity) — never raises, never omits the key.
        for wid in ("chat", "custom", "reverse_engineer"):
            if wid in by_id:
                assert by_id[wid]["chained_from"] == [], (
                    f"{wid} should have no authored chaining relationships"
                )


# ---------------------------------------------------------------------------
# GET /api/workflows/{id} — full compiled config + 404
# ---------------------------------------------------------------------------


class TestGetAnd404:
    def test_get_prototype_matches_manifest(self, client):
        resp = client.get("/api/workflows/prototype")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        compiled = compile_for_run("prototype")
        specs = get_pipeline_agents("prototype")

        # Agents in compiled order match the registry-ordered specs.
        assert [s["agent_id"] for s in body["steps"]] == [
            st.agent_id for st in compiled.steps
        ]
        assert [s["agent_id"] for s in body["steps"]] == [sp.id for sp in specs]

        # Per-step gates match the compiled manifest gates verbatim.
        compiled_gates = {st.agent_id: list(st.gates) for st in compiled.steps}
        body_gates = {s["agent_id"]: s["gates"] for s in body["steps"]}
        assert body_gates == compiled_gates

        # Deliverable matches the manifest.
        assert body["deliverable"]["strategy"] == compiled.deliverable.strategy
        assert body["deliverable"]["name"] == compiled.deliverable.name

        # Declared capabilities / clarify surfaced.
        assert body["planner"] == compiled.planner
        assert body["clarify_defaults"] == list(compiled.clarify.defaults)

    def test_get_each_known_id_compiles(self, client):
        # Every authored id returns 200 with a step list of the right length.
        for wid in _KNOWN_WORKFLOW_IDS:
            resp = client.get(f"/api/workflows/{wid}")
            assert resp.status_code == 200, f"{wid}: {resp.text}"
            compiled = compile_for_run(wid)
            assert len(resp.json()["steps"]) == len(compiled.steps)

    def test_get_unknown_id_is_404(self, client):
        resp = client.get("/api/workflows/not_a_real_workflow")
        assert resp.status_code == 404, resp.text

    def test_get_path_traversal_id_is_404(self, client):
        # A traversal-looking id must be rejected by the known-id allow-list,
        # never reaching the filesystem (T-04-13).
        resp = client.get("/api/workflows/..%2f..%2fetc%2fpasswd")
        assert resp.status_code == 404, resp.text


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
        assert load_manifest("sample_subagents_parallel", _WORKFLOWS_DIR).user_launchable is True

    def test_spec_kit_has_agents_but_no_manifest_yet(self):
        # ISS-035 proof case: spec_kit agents are real and discoverable via
        # get_pipeline_agents/PIPELINE_AGENTS, but there is no authored
        # workflow.yaml for spec_kit yet, so it must NOT be exposed as a
        # launchable workflow. If a manifest is later added, this assertion
        # forces a conscious test update rather than an unnoticed catalog
        # change.
        assert get_pipeline_agents("spec_kit"), (
            "expected spec_kit to have real, loadable agents on disk"
        )
        assert "spec_kit" not in _KNOWN_WORKFLOW_IDS

    def test_every_known_workflow_id_compiles(self):
        # Would have caught the naive "PIPELINE_AGENTS.keys() == workflows"
        # assumption directly: every id claimed as a known workflow must
        # actually compile.
        for wid in _KNOWN_WORKFLOW_IDS:
            compile_for_run(wid)  # raises on failure
