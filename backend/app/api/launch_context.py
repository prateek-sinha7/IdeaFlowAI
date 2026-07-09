"""app/api/launch_context.py — the declared-signal run-launch od_context seam.

D-15/C (SC-001 / INV-1): the ONE architectural change of Phase 37. Both launch
boundaries — ``run_commands.py::_resolve_launch_agents`` (REST) and
``websocket.py::_handle_workflow_execution`` (WS) — used to decide whether to load
template/design-system ``od_context`` by branching on the workflow-name literals
``pipeline_type == "od_prototype"`` / ``== "od_ppt"``. That name-branch was the
SC-001/INV-1 leak: a new deliverable could not gain template/DS acceptance without
an engine/boundary edit.

This module replaces that leak with a single shared, app-side seam that keys
eligibility on the DECLARED manifest signal ``context_providers: [opendesign]``
(compiled into ``CompiledWorkflow.context_providers``). A deliverable opts into
template/DS context by declaring one manifest line — zero engine edit (INV-13),
zero new manifest key (INV-5), additive and boundary-only (INV-3).

Byte-identity (INV-3): the OLD name-branch loaded od_context for the OpenDesign
LAUNCH LABELS ``{od_prototype, od_ppt, od_ppt_revision}`` and NOT for the plain
base ``prototype`` (whose bare launch is rejected downstream by the 13-06
``missing_template_context`` guard). The plain ``prototype`` manifest ALSO declares
``opendesign`` (its OD flavor is requested via the dedicated ``od_prototype``
alias), so a pure declared-signal check would newly load od_context for a bare
``prototype`` run and change that guard's behavior. To byte-preserve the legacy
split WITHOUT a name literal, eligibility additionally excludes any base that has a
dedicated ``od_`` alias — sourced from ``agents.registry._OD_ALIAS_BASE`` (the
single source of truth for those aliases). A brand-new deliverable that declares
``opendesign`` and has NO legacy ``od_`` alias still opts in when launched by its
own name — which is exactly the D-15/C win.

Import discipline: this seam is app-side and imports ONLY ``agents.*`` ports (the
alias resolver, the manifest compiler) and the ``od_context`` loaders — never the
execution kernel's private internals or a web-layer module — so import-linter's
kernel/web contracts stay 4 kept / 0 broken.
"""

from __future__ import annotations


def resolve_launch_od_context(
    pipeline_type: str,
    template_id: str | None,
    design_system_id: str | None,
    *,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
    fatal: bool,
) -> tuple[str, dict | None]:
    """Resolve ``(base_pipeline_type, od_context)`` for a run launch.

    ``base_pipeline_type`` is the alias-resolved manifest id (``od_prototype`` ->
    ``prototype``; every other label resolves to itself). ``od_context`` is the
    template/design-system dict the OpenDesign loaders build, or ``None`` when the
    resolved manifest does not declare the ``opendesign`` context provider (or the
    label is a plain base with a dedicated ``od_`` alias — see the module docstring).

    Fatality:
        * ``fatal=True``  — a template/DS ``LookupError`` PROPAGATES so the caller
          shapes the rejection (V5 input-validation preserved). Used by the
          prototype / od_ppt launch arms on both boundaries.
        * ``fatal=False`` — a ``LookupError`` is SWALLOWED and ``od_context`` is
          ``None`` (no raise), reproducing websocket.py:1741-1753 exactly. Used by
          the WS ``od_ppt_revision`` arm.

    Loader-profile selection is a PRESERVED compatibility shim keyed on the
    resolved base family (see the FIXME below).
    """
    from agents.execution_engine.engine import compile_for_run, resolve_alias
    from agents.execution_engine.od_context import (
        load_ppt_od_context,
        load_prototype_od_context,
    )
    from agents.registry import _OD_ALIAS_BASE

    base_pipeline_type = resolve_alias(pipeline_type)

    # ── ELIGIBILITY (name-free — the SC-001 win) ──────────────────────────────
    # Peek the compiled manifest. An unknown id has no manifest: return the base
    # with no od_context and let the caller's SUPPORTED_PIPELINE_TYPES gate reject
    # (the closed-set resolver means no path traversal via the run label).
    try:
        compiled = compile_for_run(pipeline_type)
    except FileNotFoundError:
        return base_pipeline_type, None

    declared_opendesign = "opendesign" in (compiled.context_providers or [])
    # A plain base whose OpenDesign flavor is a dedicated ``od_`` alias is NOT
    # self-OD-eligible; its OD context is requested by launching the alias. This
    # byte-preserves the legacy od_prototype-vs-prototype split (bare ``prototype``
    # stays od_context=None -> the 13-06 missing_template_context guard) without a
    # name literal — ``_OD_ALIAS_BASE`` is the single source of truth.
    has_dedicated_od_alias = pipeline_type in set(_OD_ALIAS_BASE.values())
    if not declared_opendesign or has_dedicated_od_alias:
        return base_pipeline_type, None

    # ── LOADER PROFILE (preserved compatibility shim) ─────────────────────────
    # FIXME(ISS-046 / D-15/C v1): generic loader-profile *declaration* is deferred
    # — tracked in .planning/ISSUES-REGISTER.md (ISS-046); see RESEARCH Open
    # Question 2. Only prototype / od_ppt / od_ppt_revision declare
    # opendesign today, so this base-family mapping is byte-preserving. The
    # per-family argument shaping reproduces the OLD name-branch verbatim
    # (prototype: ``design_system_id or ""``; od_ppt-family: raw ``design_system_id``).
    try:
        if base_pipeline_type == "prototype":
            od_context = load_prototype_od_context(
                template_id or "",
                design_system_id or "",
                custom_ds_body=custom_ds_body,
                custom_template_body=custom_template_body,
            )
        else:  # od_ppt-family (od_ppt, od_ppt_revision)
            od_context = load_ppt_od_context(
                template_id or "",
                design_system_id,
                custom_ds_body=custom_ds_body,
                custom_template_body=custom_template_body,
            )
    except LookupError:
        if fatal:
            raise
        return base_pipeline_type, None

    return base_pipeline_type, od_context
