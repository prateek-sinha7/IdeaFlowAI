"""app/api/composition_order.py — app-layer produces/consumes pre-sort entry point.

A thin adapter over the KERNEL resolver's ADDITIVE, order-independent
``WorkflowResolver.presort`` (``agents/execution_engine/resolver.py``). It keys ONLY
on generic ``produces`` / ``consumes`` artifact-type contracts — never a
workflow-name or ``pipeline_type`` literal (SC-001 / INV-1). This module is the
single app-layer boundary the SAVE path (``user_workflows.create_user_workflow``)
and the LAUNCH path (``run_commands.launch_run``) call to reorder a USER composition
producer-first — or reject a genuinely-unsatisfiable one — at COMPOSE time, BEFORE a
``WorkflowRun`` is ever minted. It does NOT re-implement any DAG logic (INV-12): it
delegates to the resolver's reused ``_detect_cycles`` / ``_topological_sort`` helpers.

Import direction: this module lives in ``app.*`` and imports
``agents.execution_engine.resolver`` — the LEGAL ``app → agents`` direction
(``run_commands.py`` already imports ``agents.execution_engine.engine``; no
import-linter contract forbids ``app.api → agents.execution_engine``). Callers that
must honor a "no direct ``agents.execution_engine`` import" module convention (e.g.
``user_workflows.py``) import THIS helper instead of the resolver directly.
"""

from __future__ import annotations


class UnsatisfiableComposition(ValueError):
    """A user composition whose produces/consumes contracts can never be satisfied.

    Raised when a consumed non-exempt type is produced by no selected agent, or when
    a real produces/consumes cycle exists. A DISTINCT exception type so call sites can
    catch ONLY this and map it to a 422 rejection (never swallowing an unrelated
    ``ValueError``).
    """


def presort_specs(specs: list) -> list:
    """Return ``specs`` reordered producer-first (topological execution order).

    Delegates to the kernel resolver's additive order-independent ``presort``.
    Re-raises its ``ValueError`` as ``UnsatisfiableComposition`` so the call site
    catches a single, purpose-built type.
    """
    from agents.execution_engine.resolver import WorkflowResolver

    try:
        return WorkflowResolver().presort(specs)
    except ValueError as exc:
        raise UnsatisfiableComposition(str(exc)) from exc


def presort_agent_ids(agent_ids: list[str]) -> list[str]:
    """Load each agent's spec, presort producer-first, and return the sorted ids.

    Raises ``UnsatisfiableComposition`` on a genuinely-unsatisfiable set. The caller
    is expected to have already allow-list-validated ``agent_ids`` (so ``load_agent_spec``
    resolves).
    """
    from agents.loader import load_agent_spec

    specs = [load_agent_spec(a) for a in agent_ids]
    return [s.id for s in presort_specs(specs)]
