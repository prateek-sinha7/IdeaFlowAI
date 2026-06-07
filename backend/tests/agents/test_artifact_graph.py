"""tests/agents/test_artifact_graph.py — Wave 0 unit coverage for the typed
artifact substrate ``agents/artifacts/graph.py`` (ART-01/02/03/04).

This is the RED suite written before ``graph.py`` exists (interface-first, plan
05-01 Task 1). It pins the ``ArtifactRef`` field set (plan §6:454-466 + the D-01
inline ``content`` field) and the ``ArtifactGraph`` typed produces/consumes
routing + in-memory lineage walk (plan §17:688-695).

Kernel-purity: this test imports ONLY ``agents.artifacts.graph`` + stdlib. It must
NOT import ``app.models.*`` / ``app.api.*`` — the package under test is
kernel-importable typed data (the dataclass↔ORM mapping lives in the store helper,
05-03, not here).
"""

from __future__ import annotations

import hashlib

from agents.artifacts.graph import ArtifactGraph, ArtifactRef


def _write_spec(graph: ArtifactGraph, *, content: str = "spec-content") -> ArtifactRef:
    return graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="spec",
        producer_step="specify",
        producer_agent="prototype-specify",
        task_id=None,
        content=content,
        location="spec.md",
    )


# ── ART-01 — typed lineage walk ────────────────────────────────────────────────
def test_art01_lineage_resolves_derived_ref_to_parent() -> None:
    """Write ref A (spec) then ref B (plan) derived from A; B's lineage walks B→A."""
    graph = ArtifactGraph()
    ref_a = _write_spec(graph, content="the spec")
    ref_b = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="plan",
        producer_step="plan",
        producer_agent="prototype-plan",
        task_id=None,
        content="the plan",
        location="plan.md",
        parents=[ref_a.id],
        derived_from=ref_a.id,
    )

    # Read B back through the graph and confirm its declared lineage links to A.
    fetched_b = graph.get(ref_b.id)
    assert fetched_b is not None
    assert ref_a.id in fetched_b.parents
    assert fetched_b.derived_from == ref_a.id

    # The in-memory lineage walk resolves B's ancestry to include A.
    lineage_ids = {r.id for r in graph.lineage(ref_b.id)}
    assert ref_a.id in lineage_ids
    assert ref_b.id in lineage_ids


# ── ART-02 — provenance + sha256 content_hash + version ────────────────────────
def test_art02_records_provenance_hash_and_version() -> None:
    graph = ArtifactGraph()
    content = "deterministic-content"
    ref = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="spec",
        producer_step="specify",
        producer_agent="prototype-specify",
        task_id="task-7",
        content=content,
        location="spec.md",
    )

    # Provenance is non-null.
    assert ref.producer_step == "specify"
    assert ref.producer_agent == "prototype-specify"
    assert ref.task_id == "task-7"

    # content_hash is an exact sha256 over the UTF-8 content (D-01, deterministic).
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert ref.content_hash == expected

    # version is an int and starts at 1 for the first ref of a (run, kind).
    assert isinstance(ref.version, int)
    assert ref.version == 1


def test_art02_version_increments_per_run_and_kind() -> None:
    graph = ArtifactGraph()
    first = _write_spec(graph, content="v1")
    second = _write_spec(graph, content="v2")
    assert first.version == 1
    assert second.version == 2

    # A different kind in the same run starts its own version sequence at 1.
    plan_ref = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="plan",
        producer_step="plan",
        producer_agent="prototype-plan",
        task_id=None,
        content="plan-v1",
        location="plan.md",
    )
    assert plan_ref.version == 1


# ── ART-03 — typed consumes routing (NOT substring match) ──────────────────────
def test_art03_consumed_for_returns_exactly_matching_kinds() -> None:
    graph = ArtifactGraph()
    spec_ref = _write_spec(graph)
    plan_ref = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="plan",
        producer_step="plan",
        producer_agent="prototype-plan",
        task_id=None,
        content="the plan",
        location="plan.md",
    )

    # An agent that consumes=["spec"] gets exactly the spec ref, never the plan ref.
    consumed = graph.consumed_for(["spec"])
    consumed_ids = {r.id for r in consumed}
    assert spec_ref.id in consumed_ids
    assert plan_ref.id not in consumed_ids
    # Typed equality on .kind — never a substring match on ids.
    assert all(r.kind == "spec" for r in consumed)


# ── ART-03 — revision lineage via derived_from across a parent run source ──────
def test_art03_derived_from_exposes_parent_run_source_link() -> None:
    graph = ArtifactGraph()
    parent_source_id = "parent-run-spec-ref-id"
    ref = graph.write_ref(
        run_id="run-2",
        owner_id="alice",
        workspace_id="ws-1",
        kind="spec",
        producer_step="specify",
        producer_agent="prototype-specify",
        task_id=None,
        content="revised spec",
        location="spec.md",
        derived_from=parent_source_id,
        parents=[parent_source_id],
    )
    assert ref.derived_from == parent_source_id
    assert parent_source_id in ref.parents


# ── ART-04 — retention default + overrides ─────────────────────────────────────
def test_art04_retention_default_is_run_ttl() -> None:
    graph = ArtifactGraph()
    ref = _write_spec(graph)
    assert ref.retention == "run_ttl"


def test_art04_retention_overrides_persist_verbatim() -> None:
    graph = ArtifactGraph()
    keep = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="spec",
        producer_step="specify",
        producer_agent="prototype-specify",
        task_id=None,
        content="keep me",
        location="spec.md",
        retention="keep",
    )
    days = graph.write_ref(
        run_id="run-1",
        owner_id="alice",
        workspace_id="ws-1",
        kind="plan",
        producer_step="plan",
        producer_agent="prototype-plan",
        task_id=None,
        content="thirty days",
        location="plan.md",
        retention="days:30",
    )
    assert keep.retention == "keep"
    assert days.retention == "days:30"
