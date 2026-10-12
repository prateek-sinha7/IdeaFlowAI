"""A binary deliverable with a declared text form (the backlog's Backlog.pdf / backlog.md).

The run declares the binary when it is on disk and falls back to the text form when
it is not; final_output always carries the text form, never binary bytes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.deliverables.single_file import SingleFileResolver
from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.engine import (
    ExecutionEngine,
    _write_chain_payload,
    build_flat_payload,
    effective_deliverable,
)
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.plan import DeliverableSpec

_BACKLOG_YAML = Path(__file__).parents[3] / "agents/workflows/backlog/workflow.yaml"
_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\nbinary\n"
_MD = "# Backlog\n\n## EPIC-01 Quote\n"


def _backlog_spec() -> DeliverableSpec:
    raw = yaml.safe_load(_BACKLOG_YAML.read_text())["deliverable"]
    manifest = WorkflowManifest(id="t-binary", steps=[], deliverable=raw, planner="skip",
                                clarify={"mode": "auto", "defaults": []})
    return WorkflowCompiler().compile(manifest, CapabilityRegistry()).deliverable


def _sandbox(tmp_path, *, pdf: bool):
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox("user-1", "run-1", runs_root=str(tmp_path))
    sb.ensure()
    sb.write("backlog.md", _MD)
    if pdf:
        sb.path_for("Backlog.pdf").write_bytes(_PDF)
    return sb


def _declared(spec, sb):
    """What pipeline_complete declares: (deliverable_filename, deliverable_mimetype, final_output)."""
    deliverable = effective_deliverable(spec, sb)
    ctx = SimpleNamespace(runner=SimpleNamespace(sandbox=sb), deliverable=deliverable,
                          last_streamed="", revision_original_html="")
    output = SingleFileResolver().resolve(ctx)
    mimetype = deliverable.mimetype or default_mimetype(deliverable.strategy, deliverable.name)
    return deliverable.name, mimetype, output


def test_backlog_declares_the_pdf_with_the_markdown_as_final_output(tmp_path):
    spec = _backlog_spec()
    assert (spec.name, spec.text_name) == ("Backlog.pdf", "backlog.md")
    assert _declared(spec, _sandbox(tmp_path, pdf=True)) == ("Backlog.pdf", "application/pdf", _MD)


def test_a_missing_pdf_falls_back_to_backlog_md(tmp_path):
    assert _declared(_backlog_spec(), _sandbox(tmp_path, pdf=False)) == (
        "backlog.md", "text/markdown", _MD)


def test_steps_are_told_to_write_the_text_form():
    ectx = SimpleNamespace(current_step=SimpleNamespace(is_leaf=True), deliverable=_backlog_spec())
    assert ExecutionEngine._deliverable_filename_override(ectx, 0, []) == "backlog.md"


def test_the_chain_payload_carries_the_text_form_with_the_pdf(tmp_path):
    sb = _sandbox(tmp_path, pdf=True)
    ectx = MagicMock(runner=SimpleNamespace(sandbox=sb), final_status="completed",
                     revision_ordinal=1, completed_tasks=[], git_tag=None,
                     deliverable=_backlog_spec())
    _write_chain_payload("run-1", ectx)
    chain = sb.root / ".chain" / "run-1"
    assert (chain / "backlog.md").read_text() == _MD
    assert (chain / "Backlog.pdf").read_bytes() == _PDF


def _flat_payload(sb, spec):
    ectx = MagicMock(runner=SimpleNamespace(sandbox=sb), final_status="completed",
                     revision_ordinal=1, completed_tasks=[], git_tag=None, deliverable=spec)
    return build_flat_payload("run-1", ectx)


@pytest.mark.allow_io("git index: the text form must really be force-staged beside the PDF")
def test_the_flat_chain_payload_carries_the_text_form_with_the_pdf(tmp_path):
    # The live writer: what a run chained from a backlog reads (run fa7bcb5f's .chain/ had
    # only Backlog.pdf, logs.jsonl and summary.md).
    sb = _sandbox(tmp_path, pdf=True)
    sb._ws().git_init_sandbox()  # type: ignore[attr-defined]
    payload = _flat_payload(sb, _backlog_spec())
    assert (sb.root / ".chain" / "backlog.md").read_text() == _MD
    assert (sb.root / ".chain" / "Backlog.pdf").read_bytes() == _PDF
    assert payload.allowlist == frozenset({".chain/logs.jsonl", ".chain/summary.md",
                                           ".chain/Backlog.pdf", ".chain/backlog.md"})
    assert payload.materialized
    assert {".chain/Backlog.pdf", ".chain/backlog.md"} <= set(sb.staged_entries())


def test_a_text_form_that_is_not_a_plain_file_on_disk_is_not_staged(tmp_path):
    sb = _sandbox(tmp_path, pdf=True)
    sb.has_git = False  # the files and the allowlist are the point here, not the index
    for text_name in ("../escape.md", "docs/backlog.md", "missing.md"):
        spec = DeliverableSpec(strategy="single_file", name="Backlog.pdf", text_name=text_name)
        payload = _flat_payload(sb, spec)
        assert payload.allowlist == frozenset({".chain/logs.jsonl", ".chain/summary.md", ".chain/Backlog.pdf"})
        assert sorted(p.name for p in (sb.root / ".chain").iterdir()) == ["Backlog.pdf", "logs.jsonl", "summary.md"]


def test_a_text_deliverable_is_unchanged(tmp_path):
    spec = DeliverableSpec(strategy="single_file", name="prototype.html")
    assert effective_deliverable(spec, _sandbox(tmp_path, pdf=False)) is spec
    ectx = SimpleNamespace(current_step=SimpleNamespace(is_leaf=True), deliverable=spec)
    assert ExecutionEngine._deliverable_filename_override(ectx, 0, []) == "prototype.html"


def test_share_of_a_pdf_deliverable_serves_the_file_bytes(tmp_path):
    from app import main

    _sb = _sandbox(tmp_path, pdf=True)
    run = SimpleNamespace(id="run-1", user_id="user-1", output=_MD,
                          deliverable_mimetype="application/pdf",
                          deliverable_filename="Backlog.pdf")
    with patch("app.api.runs.get_shared_run_by_token", return_value=run), \
         patch("app.models.database.get_db", return_value=iter([MagicMock()])), \
         patch("app.api.run_files._resolve_chain_root_or_404", return_value="run-1"), \
         patch.object(main.settings, "RUNS_ROOT", str(tmp_path)):
        resp = asyncio.run(main.view_shared_run("tok"))
    assert resp.media_type == "application/pdf"
    assert resp.body == _PDF
