"""Unit tests for the per-run ``ExecutionContext`` value object (Phase 0B, CTX-01/CTX-02).

``ExecutionContext`` (``agents/execution_engine/context.py``) is the per-RUN state
container the kernel constructs once inside ``execute()`` and threads explicitly through
the call tree (D-03) — DISTINCT from the factory's per-AGENT ``AgentContext``. These tests
pin the D-01 minimal field set, mutable-default isolation (``field(default_factory=...)``),
and the import-direction constraint (data only — no legacy engine/factory imports), so the
Phase-1 import-linter kernel→ports scaffold stays green.

Offline / unmarked — no DB, no API key; runs in the CI ``backend:characterization`` job.
"""

from __future__ import annotations

import importlib

from agents.execution_engine.context import ExecutionContext


def test_constructs_with_only_required_fields_defaulting_the_rest() -> None:
    """``run_id`` + ``owner_id`` are the only required fields; everything else defaults."""
    ectx = ExecutionContext(run_id="r", owner_id="anon")

    assert ectx.run_id == "r"
    assert ectx.owner_id == "anon"
    # Optionals default to None / empty / 0.
    assert ectx.od_context is None
    assert ectx.gate_agent_ids is None
    assert ectx.parent_run_id is None
    assert ectx.checkpointer is None
    assert ectx.cancel_event is None
    assert ectx.depth == 0
    assert ectx.current_task_block == ""
    assert ectx.build_task_number == ""
    assert ectx.build_task_total == ""
    assert ectx.revision_original_html == ""
    assert ectx.revision_instruction is None
    # Mutable defaults are empty containers.
    assert ectx.completed_tasks == []
    assert ectx.disk_skills == {}
    assert ectx.revision_baseline_static == set()
    assert ectx.revision_baseline_console == set()


def test_mutable_list_default_is_not_shared_between_instances() -> None:
    """``completed_tasks`` must be ``field(default_factory=list)`` — not a shared default."""
    a = ExecutionContext(run_id="a", owner_id="anon")
    b = ExecutionContext(run_id="b", owner_id="anon")

    a.completed_tasks.append({"number": 1})

    assert a.completed_tasks == [{"number": 1}]
    assert b.completed_tasks == []  # second instance unaffected → independent default


def test_revision_baseline_sets_are_independent_per_instance() -> None:
    """The ``revision_baseline_*`` sets default to independent empty ``set()`` instances."""
    a = ExecutionContext(run_id="a", owner_id="anon")
    b = ExecutionContext(run_id="b", owner_id="anon")

    a.revision_baseline_static.add("sig-1")
    a.revision_baseline_console.add("err-1")

    assert a.revision_baseline_static == {"sig-1"}
    assert a.revision_baseline_console == {"err-1"}
    assert b.revision_baseline_static == set()
    assert b.revision_baseline_console == set()
    # Distinct identities (proves default_factory=set, not a shared module-level set).
    assert a.revision_baseline_static is not b.revision_baseline_static


def test_module_imports_no_legacy_factory_or_engine_internals() -> None:
    """``context.py`` defines data only — it must not import factory / engine internals.

    Keeps the import-direction clean (the Phase-1 import-linter kernel→ports scaffold).
    Scan only the module's actual ``import`` / ``from … import`` lines (prose mentions of
    ``agents.factory`` in the docstring are fine — it is the import EDGE that is banned),
    mirroring the plan's acceptance grep ``from agents\\.factory|execution_engine\\.engine``.
    """
    mod = importlib.import_module("agents.execution_engine.context")
    src = open(mod.__file__, encoding="utf-8").read()

    import_lines = [
        ln.strip()
        for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    offenders = [
        ln
        for ln in import_lines
        if "agents.factory" in ln or "execution_engine.engine" in ln or "engine" in ln
    ]
    assert offenders == [], f"context.py imports legacy engine/factory internals: {offenders}"
    # Positive: the only imports are stdlib dataclasses + __future__ annotations.
    assert any("from dataclasses import" in ln for ln in import_lines)


def test_trigger_depth_propagates_correctly_across_multi_level_chain() -> None:
    """``trigger_depth`` propagates as parent+1 across a mocked chain (R-18 / T10).

    ExecutionContext is a plain value object — the trigger depth is a constructor-time
    parameter, not computed internally. This test confirms that a chain of explicit
    trigger_depth values (0 → 1 → 2) is threaded correctly through construction.
    """
    # Parent run: non-triggered (the default).
    parent = ExecutionContext(run_id="parent_run", owner_id="user", trigger_depth=0)
    assert parent.trigger_depth == 0

    # Child run triggered by parent: passes parent.trigger_depth + 1.
    child = ExecutionContext(
        run_id="child_run",
        owner_id="user",
        parent_run_id="parent_run",
        trigger_depth=parent.trigger_depth + 1,
    )
    assert child.trigger_depth == 1
    assert child.trigger_depth == parent.trigger_depth + 1

    # Grandchild run triggered by child: passes child.trigger_depth + 1.
    grandchild = ExecutionContext(
        run_id="grandchild_run",
        owner_id="user",
        parent_run_id="child_run",
        trigger_depth=child.trigger_depth + 1,
    )
    assert grandchild.trigger_depth == 2
    assert grandchild.trigger_depth == child.trigger_depth + 1

    # Verify the chain: each level is exactly parent+1.
    assert parent.trigger_depth < child.trigger_depth < grandchild.trigger_depth
    assert child.trigger_depth - parent.trigger_depth == 1
    assert grandchild.trigger_depth - child.trigger_depth == 1
