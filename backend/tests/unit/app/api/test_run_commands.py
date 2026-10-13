"""Unit tests for the pre-mint uploads-present gate in ``app/api/run_commands.py``.

``_guard_uploads_present`` refuses a fresh launch whose brief carries inlined
``=== Attached: … ===`` blocks but no ``staged_upload_ids``, for a plan with a
step granted the ``file_extract`` tool set. Plans are plain namespaces, so the
predicate is exercised on its declared-tool-set key alone (SC-001). No I/O.
"""

from __future__ import annotations

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
    )

    class _Db:
        def close(self):
            return None

    spec = SimpleNamespace(id="custom-agent")
    monkeypatch.setattr(run_commands, "_get_db", lambda: _Db())
    monkeypatch.setattr("app.api.user_workflows._owned", lambda *_: row)
    monkeypatch.setattr("agents.loader.load_agent_spec", lambda agent_id: spec)
    monkeypatch.setattr(
        "app.api.composition_order.presort_specs", lambda agents: agents
    )

    resolved = run_commands._resolve_saved_trigger_target("saved-flat", "owner-1")

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

    class _Compiler:
        def compile(self, manifest, registry, *, trust):
            captured["compile"] = (manifest, registry, trust)
            return compiled

    import agents.execution_engine.engine as engine_module

    registry = object()
    monkeypatch.setattr(run_commands, "_get_db", lambda: _Db())
    monkeypatch.setattr("app.api.user_workflows._owned", lambda *_: row)
    monkeypatch.setattr(
        "agents.workflows.manifest.build_manifest_from_dict", _build_manifest
    )
    monkeypatch.setattr(engine_module, "_WORKFLOW_COMPILER", _Compiler())
    monkeypatch.setattr(engine_module, "_CAPABILITY_REGISTRY", registry)

    resolved = run_commands._resolve_saved_trigger_target("saved-manifest", "owner-1")

    assert captured["source"] == "workflow:saved-manifest"
    assert captured["compile"] == (parsed, registry, "db")
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
