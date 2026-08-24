"""tests/unit/test_deliverable_mimetype.py — ISS-021 type-driven deliverable contract.

Pins the BACKEND half of ISS-021 (18-01): a DECLARED, type-driven deliverable shape
hint so the FE renderer (18-03) can dispatch on a mimetype instead of a hardcoded
workflow-name branch (SC-001).

Coverage:
  * Task 1 — ``DeliverableSpec.mimetype`` is an optional field; the compiler passes
    it through verbatim (a thin pass-through, NO defaulting in the compiler — INV-5);
    each resolver exposes a deterministic per-resolver default; an extra/unknown
    manifest key is tolerated (additive-only).
  * Task 2 — ``pipeline_complete`` carries ``deliverable_mimetype`` +
    ``deliverable_filename`` (sourced from the resolved ``ectx.deliverable`` with the
    per-resolver default), unconditionally (clean AND degraded), and BOTH new keys
    are members of ``_VOLATILE_STRIP_KEYS`` so the 5 characterization goldens stay
    byte-identical (the INV-3 parity seam).
"""

from __future__ import annotations

import pytest

from agents.capabilities.deliverables._mimetype import default_mimetype
from agents.capabilities.deliverables.ppt import PptResolver
from agents.capabilities.deliverables.serialized_sandbox import SerializedSandboxResolver
from agents.capabilities.deliverables.single_file import SingleFileResolver
from agents.capabilities.deliverables.streamed_text import StreamedTextResolver
from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.plan import DeliverableSpec
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.compiler import WorkflowCompiler


def _manifest(deliverable: dict, _id: str = "t-mimetype") -> WorkflowManifest:
    """Minimal valid manifest carrying only the deliverable under test."""
    return WorkflowManifest(
        id=_id,
        steps=[],
        deliverable=deliverable,
        planner="skip",
        clarify={"mode": "auto", "defaults": []},
    )


# ── Task 1: DeliverableSpec.mimetype + compiler pass-through ──────────────────


def test_deliverable_spec_mimetype_defaults_none() -> None:
    """An unset mimetype defaults to None — existing compiled specs are byte-unchanged."""
    spec = DeliverableSpec(strategy="single_file", name="prototype.html")
    assert spec.mimetype is None


def test_deliverable_spec_mimetype_roundtrips_through_compiler() -> None:
    """A declared mimetype rides verbatim from the manifest onto the compiled spec."""
    manifest = _manifest(
        {"strategy": "single_file", "name": "x.html", "mimetype": "text/html"},
        "t-mimetype-set",
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.deliverable.mimetype == "text/html"


def test_compiler_does_not_default_unset_mimetype() -> None:
    """An UNSET mimetype compiles to None — the compiler is a thin pass-through (INV-5).

    The per-resolver default is applied at EMISSION time (Task 2), NOT in the compiler;
    no DSL / defaulting logic lives in the compiler.
    """
    manifest = _manifest(
        {"strategy": "single_file", "name": "prototype.html"}, "t-mimetype-unset"
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.deliverable.mimetype is None


def test_compiler_tolerates_unknown_manifest_key() -> None:
    """An extra/unknown deliverable key does not raise (additive-only contract)."""
    manifest = _manifest(
        {
            "strategy": "streamed_text",
            "name": "out.md",
            "mimetype": "text/markdown",
            "some_future_key": "ignored",
        },
        "t-mimetype-extra",
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.deliverable.mimetype == "text/markdown"


# ── Task 1: per-resolver default mimetype (deterministic, declared-shape-driven) ──


@pytest.mark.parametrize(
    "name,expected",
    [
        ("prototype.html", "text/html"),
        ("index.htm", "text/html"),
        ("report.md", "text/markdown"),
        ("noext", "application/octet-stream"),
        ("archive.unknownext", "application/octet-stream"),
        (None, "application/octet-stream"),
    ],
)
def test_single_file_default_mimetype_infers_from_name(name, expected) -> None:
    assert default_mimetype("single_file", name) == expected
    assert SingleFileResolver.default_mimetype(name) == expected


def test_serialized_sandbox_default_mimetype_is_zip() -> None:
    assert default_mimetype("serialized_sandbox", "bundle") == "application/zip"
    assert SerializedSandboxResolver.default_mimetype("bundle") == "application/zip"


def test_streamed_text_default_mimetype_is_markdown() -> None:
    assert default_mimetype("streamed_text", "out.txt") == "text/markdown"
    assert StreamedTextResolver.default_mimetype("out.txt") == "text/markdown"


def test_ppt_default_mimetype_is_html() -> None:
    assert default_mimetype("ppt", "deck") == "text/html"
    assert PptResolver.default_mimetype("deck") == "text/html"


def test_default_mimetype_unknown_strategy_falls_back_to_octet_stream() -> None:
    """An unknown/None strategy is octet-stream — derive from the DECLARED shape only,
    never content-sniff."""
    assert default_mimetype("totally_unknown", "x.bin") == "application/octet-stream"
    assert default_mimetype(None, None) == "application/octet-stream"


# ── Task 2: pipeline_complete emission + INV-3 _VOLATILE_STRIP_KEYS guard ─────


def test_new_keys_are_in_volatile_strip_keys() -> None:
    """INV-3 parity seam: both additive keys are stripped before the golden compare."""
    from tests.agents.characterization._normalize import _VOLATILE_STRIP_KEYS

    assert "deliverable_mimetype" in _VOLATILE_STRIP_KEYS
    assert "deliverable_filename" in _VOLATILE_STRIP_KEYS


@pytest.mark.asyncio
async def test_pipeline_complete_carries_deliverable_mimetype_and_filename() -> None:
    """A scripted custom run's ``pipeline_complete`` carries final_output AND the two
    new declared-shape keys, sourced from the resolved deliverable + resolver default."""
    from tests.agents._scripted_model import _drive

    events = await _drive("prototype")
    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert completes, "no pipeline_complete event emitted"
    data = completes[-1].get("data") or {}

    assert "final_output" in data
    # prototype declares single_file + prototype.html → text/html via the resolver default
    assert data.get("deliverable_mimetype") == "text/html"
    assert data.get("deliverable_filename") == "prototype.html"


@pytest.mark.asyncio
async def test_pipeline_complete_mimetype_never_null_when_deliverable_present() -> None:
    """When DeliverableSpec.mimetype is unset, the emitted mimetype is the resolved
    per-resolver default — NEVER null when a deliverable exists."""
    from tests.agents._scripted_model import _drive

    events = await _drive("ppt")
    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert completes, "no pipeline_complete event emitted"
    data = completes[-1].get("data") or {}
    assert data.get("deliverable_mimetype") is not None


# ── 22-03 (UXFIX-02 / D-19): persist the emitted shape on the WorkflowRun row ──


def test_workflow_run_has_deliverable_shape_columns() -> None:
    """The two additive nullable columns exist on the WorkflowRun model (D-19).

    History-reopen drives the deliverable mimetype from the PERSISTED value (so a
    binary deliverable, e.g. application/zip, re-renders faithfully) — legacy NULL
    rows fall back to the FE deriveDeliverableMimetype heuristic (parity).
    """
    from app.models.workflow import WorkflowRun

    cols = {c.name: c for c in WorkflowRun.__table__.columns}
    assert "deliverable_mimetype" in cols
    assert "deliverable_filename" in cols
    # Additive nullable — existing rows stay NULL (no narrowing, no backfill).
    assert cols["deliverable_mimetype"].nullable is True
    assert cols["deliverable_filename"].nullable is True


def test_migration_0022_is_additive_only() -> None:
    """Migration 0022 is single-head additive (down_revision 0021), upgrade adds
    ONLY the two columns, and contains no drop/alter-narrow of existing columns
    (T-22-03-01). Source-level assertion — no DB round-trip required."""
    import pathlib

    mig = (
        pathlib.Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0022_workflow_run_deliverable_mimetype.py"
    )
    src = mig.read_text(encoding="utf-8")
    assert 'revision = "0022"' in src
    assert 'down_revision = "0021"' in src
    # upgrade() body: additive add_column only; no destructive ops on existing cols.
    upgrade_body = src.split("def upgrade")[1].split("def downgrade")[0]
    assert "add_column" in upgrade_body
    assert "deliverable_mimetype" in upgrade_body
    assert "deliverable_filename" in upgrade_body
    assert "drop_column" not in upgrade_body
    assert "alter_column" not in upgrade_body
    assert "drop_table" not in upgrade_body
