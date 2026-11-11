"""Unit tests for the pre-mint uploads-present gate in ``app/api/run_commands.py``.

``_guard_uploads_present`` refuses a fresh launch whose brief carries inlined
``=== Attached: … ===`` blocks but no ``staged_upload_ids``, for a plan with a
step granted the ``file_extract`` tool set. Plans are plain namespaces, so the
predicate is exercised on its declared-tool-set key alone (SC-001). No I/O.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.api.run_commands as run_commands
from app.api.run_commands import _guard_uploads_present

_BRIEF = (
    "create prototype from given docs\n\n"
    "=== Attached: Business_Process_Requirements 1.pdf ===\n"
    "page text one\n"
    "=== End: Business_Process_Requirements 1.pdf ===\n\n"
    "=== Attached: Epics_and_user_Stories 1.pdf ===\n"
    "page text two\n"
    "=== End: Epics_and_user_Stories 1.pdf ==="
)


def _plan(*tool_sets: list[str] | None) -> SimpleNamespace:
    return SimpleNamespace(
        steps=[SimpleNamespace(tools=SimpleNamespace(tool_sets=ts)) for ts in tool_sets]
    )


_EXTRACT_PLAN = _plan(None, ["file_extract"])


_TEXT_ONLY_BRIEF = (
    "build from the notes\n\n"
    "=== Attached: requirements.md ===\n"
    "# Requirements\n"
    "=== End: requirements.md ==="
)


def _guard(**overrides) -> None:
    kwargs = {
        "content": _BRIEF,
        "staged_upload_ids": None,
        "admitted_source_run_id": None,
        "manifest_json": None,
        "plan": _EXTRACT_PLAN,
    }
    kwargs.update(overrides)
    _guard_uploads_present(**kwargs)


@pytest.mark.parametrize("staged", [None, []])
def test_guard_uploads_present_raises_uploads_missing_when_fresh_launch_has_unstaged_attachments(
    staged, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_commands")

    with pytest.raises(HTTPException) as excinfo:
        _guard(staged_upload_ids=staged)

    assert excinfo.value.status_code == 422
    detail = excinfo.value.detail
    assert detail["code"] == "uploads_missing"
    assert detail["recoverable"] is True
    assert detail["attachment_count"] == 2
    rendered = repr(detail)
    assert "Business_Process_Requirements" not in rendered
    assert "Epics_and_user_Stories" not in rendered
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "2 inline attachment(s)" in logged
    assert "Business_Process_Requirements" not in logged


def test_guard_uploads_present_returns_when_staged_ids_present():
    _guard(staged_upload_ids=["0" * 32])


def test_guard_uploads_present_returns_when_text_only_attachment_was_staged():
    # Every launch surface now stages text documents too (UPLD-05), so a
    # text-only brief for a file_extract plan arrives with its stage id.
    _guard(content=_TEXT_ONLY_BRIEF, staged_upload_ids=["0" * 32])


def test_guard_uploads_present_raises_when_text_only_attachment_has_no_stage_id():
    with pytest.raises(HTTPException) as excinfo:
        _guard(content=_TEXT_ONLY_BRIEF)

    assert excinfo.value.detail["code"] == "uploads_missing"
    assert excinfo.value.detail["attachment_count"] == 1


def test_guard_uploads_present_returns_when_no_attachment_blocks():
    _guard(content="a brief with no attached documents")


@pytest.mark.parametrize(
    "plan",
    [None, _plan(), _plan(None), _plan(["documents"]), SimpleNamespace(steps=None)],
)
def test_guard_uploads_present_returns_when_no_step_declares_file_extract(plan):
    _guard(plan=plan)


def test_guard_uploads_present_warns_and_returns_when_chain_source_admitted(caplog):
    caplog.set_level(logging.WARNING, logger="app.api.run_commands")

    _guard(admitted_source_run_id="source-run-id")

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "2 inline attachment(s)" in warnings[0]
    assert "not rejected" in warnings[0]


@pytest.mark.parametrize(
    "from_run",
    [
        [".uploads/manifest.json"],
        ["synthesis.md", "/.uploads/a.pdf"],
        ["./.uploads/a.pdf"],
    ],
)
def test_guard_uploads_present_warns_and_returns_when_manifest_seeds_uploads(
    from_run, caplog
):
    caplog.set_level(logging.WARNING, logger="app.api.run_commands")

    _guard(manifest_json={"seed_files": {"from_run": from_run, "run_id": "prior"}})

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "not rejected" in warnings[0]


def test_guard_uploads_present_raises_when_seed_files_copy_no_uploads():
    with pytest.raises(HTTPException) as excinfo:
        _guard(
            manifest_json={"seed_files": {"from_run": ["synthesis.md"], "run_id": "p"}}
        )

    assert excinfo.value.detail["code"] == "uploads_missing"


def test_resolve_saved_trigger_target_preserves_flat_launch_settings_when_owned(
    monkeypatch,
):
    row = SimpleNamespace(
        id="saved-flat",
        base_pipeline_type="custom",
        agents='["custom-agent"]',
        manifest_json=None,
        attached_hooks=[{"name": "audit", "event": "after_agent"}],
        attached_skills=[{"name": "brand", "content": "Use the brand voice."}],
        model_overrides={"custom-agent": "model-1"},
        overrides_pipeline_type=None,
    )

    class _Db:
        def close(self):
            return None

    spec = SimpleNamespace(id="custom-agent")
    monkeypatch.setattr("app.api.run_engine._get_db", lambda: _Db())
    monkeypatch.setattr("app.api.run_engine._parent_run_trust", lambda *_: "db")
    monkeypatch.setattr("app.api.user_workflows._owned", lambda *_: row)
    monkeypatch.setattr("agents.loader.load_agent_spec", lambda agent_id: spec)
    monkeypatch.setattr(
        "app.api.composition_order.presort_specs", lambda agents: agents
    )

    resolved = run_commands._resolve_saved_trigger_target(
        "saved-flat", "owner-1", "parent-run-1"
    )

    assert resolved.pipeline_type == "custom"
    assert resolved.agents == [spec]
    assert resolved.compiled is None
    assert resolved.manifest_json is None
    assert resolved.attached_hooks == row.attached_hooks
    assert resolved.attached_skills == row.attached_skills
    assert resolved.model_overrides == row.model_overrides


def test_resolve_saved_trigger_target_stamps_manifest_for_durable_resume_when_owned(
    monkeypatch,
):
    row = SimpleNamespace(
        id="saved-manifest",
        base_pipeline_type="custom",
        agents="[]",
        manifest_json={"steps": [{"agent": "custom-agent"}]},
        attached_hooks=[{"name": "audit", "event": "after_agent"}],
        attached_skills=[{"name": "brand", "content": "Use the brand voice."}],
        model_overrides={"custom-agent": "model-1"},
        overrides_pipeline_type=None,
    )

    class _Db:
        def close(self):
            return None

    parsed = object()
    compiled = object()
    captured: dict[str, object] = {}

    def _build_manifest(raw_manifest, source):
        captured["raw_manifest"] = raw_manifest
        captured["source"] = source
        return parsed

    def _compile_with_baseline(manifest, registry, *, trust, overrides):
        captured["compile"] = (manifest, registry, trust, overrides)
        return compiled

    import agents.execution_engine.engine as engine_module

    registry = object()
    monkeypatch.setattr("app.api.run_engine._get_db", lambda: _Db())
    monkeypatch.setattr("app.api.run_engine._parent_run_trust", lambda *_: "db")
    monkeypatch.setattr("app.api.user_workflows._owned", lambda *_: row)
    monkeypatch.setattr(
        "agents.workflows.manifest.build_manifest_from_dict", _build_manifest
    )
    monkeypatch.setattr(
        "agents.execution_engine.overrides.compile_with_baseline",
        _compile_with_baseline,
    )
    monkeypatch.setattr(engine_module, "_CAPABILITY_REGISTRY", registry)

    resolved = run_commands._resolve_saved_trigger_target(
        "saved-manifest", "owner-1", "parent-run-1"
    )

    assert captured["source"] == "workflow:saved-manifest"
    assert captured["compile"] == (parsed, registry, "db", None)
    assert resolved.compiled is compiled
    assert resolved.manifest_json == {
        "steps": [{"agent": "custom-agent"}],
        "id": "user-workflow-saved-manifest",
        "deliverable": {"strategy": "streamed_text", "name": "output.md"},
        "planner": "skip",
        "clarify": {"mode": "skip", "defaults": []},
        "capabilities": {},
        "_trust": "db",
    }
    assert resolved.attached_hooks == row.attached_hooks
    assert resolved.attached_skills == row.attached_skills
    assert resolved.model_overrides == row.model_overrides


# ---------------------------------------------------------------------------
# connector_grants_not_allowed at launch (design 5.5 layer 4)
# ---------------------------------------------------------------------------
# A FILE_PIPELINE or flat-row launch never admits connected-app grants: the 422
# comes before any run row is minted, so the route never reaches the database.


class _LaunchUser:
    id = "owner"
    tier = "enterprise"


def _launch(monkeypatch, selections):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.dependencies import get_current_principal
    from tests.fakes.principal import principal_for

    class _StubSession:
        """The override lookup is the only read before the grant check; it finds none."""

        def close(self) -> None:
            return None

        def add(self, *_args, **_kwargs):
            raise AssertionError("a refused connector launch must not write a row")

    monkeypatch.setattr(run_commands, "_get_db", lambda: _StubSession(), raising=False)
    monkeypatch.setattr(
        "app.api._workflow_override.resolve_override", lambda *_a, **_k: None
    )
    user = _LaunchUser()
    app = FastAPI()
    app.include_router(run_commands.router)
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )
    return TestClient(app).post(
        "/api/runs",
        json={
            "message": "go",
            "pipeline_type": "custom",
            "agent_ids": ["market-research-agent", "swot-analyst"],
            "selections": selections,
        },
    )


class TestLaunchConnectorGrantsNotAllowed:
    def test_launch_run_returns_422_envelope_when_file_pipeline_selections_name_connectors(
        self, monkeypatch
    ):
        response = _launch(
            monkeypatch,
            {"market-research-agent": {"tools": {"connectors": ["jira__get_issue"]}}},
        )

        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "connector_grants_not_allowed"
        assert detail["recoverable"] is False
        assert "Predefined workflows cannot use connected apps" in detail["error"]


class _RecordingEngine:
    """Stub for ExecutionEngine.execute: records the kwargs and ends the run at once."""

    def __init__(self) -> None:
        self.kwargs: dict = {}

    async def execute(self, **kwargs):
        self.kwargs = kwargs
        yield {"type": "pipeline_complete", "data": {"status": "completed"}}


async def _drive_launch(user) -> None:
    """Run the launch driver with no workflow row, so it writes nothing to the database."""
    await run_commands._drive_launch_to_queue(
        workflow_run_id=None,
        pipeline_run_id="run-1",
        agents=[],
        content="go",
        pipeline_type="custom",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=asyncio.Queue(),
    )


class TestDriveLaunchRunToolBinder:
    @pytest.mark.asyncio
    async def test_drive_launch_to_queue_passes_services_binder_when_services_available(
        self, monkeypatch
    ):
        engine = _RecordingEngine()
        binder = object()
        monkeypatch.setattr(
            "agents.execution_engine.engine.get_execution_engine", lambda: engine
        )
        monkeypatch.setattr(
            "app.connectors.services.get_connector_services",
            lambda: SimpleNamespace(binder=binder),
        )

        await _drive_launch(_LaunchUser())

        assert engine.kwargs["run_tool_binder"] is binder
        assert engine.kwargs["user_id"] == "owner"

    @pytest.mark.asyncio
    async def test_drive_launch_to_queue_passes_none_binder_when_services_lookup_raises(
        self, monkeypatch, caplog
    ):
        caplog.set_level(logging.ERROR, logger="app.api.run_commands")
        engine = _RecordingEngine()
        monkeypatch.setattr(
            "agents.execution_engine.engine.get_execution_engine", lambda: engine
        )

        def _services_down():
            raise RuntimeError("services down")

        monkeypatch.setattr(
            "app.connectors.services.get_connector_services", _services_down
        )

        await _drive_launch(_LaunchUser())

        assert engine.kwargs["pipeline_run_id"] == "run-1"
        assert engine.kwargs["run_tool_binder"] is None
        assert any("connected tools off" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_drive_launch_to_queue_passes_owner_user_id_when_trigger_stand_in_used(
        self, monkeypatch
    ):
        engine = _RecordingEngine()
        binder = object()
        monkeypatch.setattr(
            "agents.execution_engine.engine.get_execution_engine", lambda: engine
        )
        monkeypatch.setattr(
            "app.connectors.services.get_connector_services",
            lambda: SimpleNamespace(binder=binder),
        )

        await _drive_launch(SimpleNamespace(id="owner-7"))

        assert engine.kwargs["user_id"] == "owner-7"
        assert engine.kwargs["run_tool_binder"] is binder


# ---------------------------------------------------------------------------
# NUL-byte sanitisation of WorkflowRun.title / .input  (PostgreSQL fix)
# ---------------------------------------------------------------------------
# psycopg2 raises ValueError if any bound parameter contains \x00 bytes.
# PDFs extracted by /api/files/extract-text can produce \x00 in the extracted
# text, which the frontend inlines into the brief as "=== Attached: ===" blocks.
# _launch_run_core derives WorkflowRun.title from _clean_run_title(content, ...)
# and WorkflowRun.input from content directly.  Both have .replace("\x00", "")
# applied before the DB INSERT so that db.commit() never sees NUL characters.
# The tests below pin that stripping pattern using _clean_run_title directly.
# ---------------------------------------------------------------------------

_BRIEF_WITH_NUL = (
    "build a prototype from documents\n\n"
    "=== Attached: Ricoh-Oracle-Doc.pdf ===\n"
    "extracted text with\x00binary PDF streams\x00and more\n"
    "=== End: Ricoh-Oracle-Doc.pdf ==="
)


class TestNulByteStrippingForWorkflowRunFields:
    def test_title_has_no_nul_bytes_after_strip_when_content_has_nul_in_attachment_block(
        self,
    ):
        """WorkflowRun.title = _clean_run_title(content, ...).replace('\\x00', '').
        NUL bytes from a PDF attachment block must be removed before the DB INSERT."""
        from app.api.run_commands import _clean_run_title

        title = _clean_run_title(_BRIEF_WITH_NUL, "prototype_v2").replace("\x00", "")

        assert "\x00" not in title
        # The user's brief survives intact
        assert "build a prototype from documents" in title

    def test_input_has_no_nul_bytes_after_strip_when_content_has_nul_in_attachment_block(
        self,
    ):
        """WorkflowRun.input = content.replace('\\x00', '').
        NUL bytes from a PDF attachment block must be removed before the DB INSERT."""
        input_val = _BRIEF_WITH_NUL.replace("\x00", "")

        assert "\x00" not in input_val
        # Text is preserved with NUL bytes removed (contiguous, no placeholder)
        assert "extracted text withbinary PDF streams" in input_val

    def test_title_is_unchanged_when_content_has_no_nul_bytes(self):
        """When the content has no NUL bytes, .replace('\\x00', '') is a no-op."""
        from app.api.run_commands import _clean_run_title

        clean_brief = "build a prototype from the attached documents"
        title = _clean_run_title(clean_brief, "prototype_v2").replace("\x00", "")

        assert title == clean_brief
