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

Eligibility is the declared signal and nothing else. It briefly carried a second
clause: while the ``od_prototype`` alias existed, a base with a dedicated ``od_``
flavor was excluded from its own declared capability, so a bare ``prototype``
launch got od_context=None and was rejected downstream by the 13-06
``missing_template_context`` guard — you had to launch the alias to get the
template. That clause was there to byte-preserve the legacy split; the split is
gone (``agents.registry._OD_ALIAS_BASE`` is empty), so the clause is gone with
it. Any deliverable declaring ``opendesign`` now opts in under its own name —
which is what D-15/C was for.

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
    base_pipeline_type = resolve_alias(pipeline_type)

    # ── ELIGIBILITY (name-free — the SC-001 win) ──────────────────────────────
    # Peek the compiled manifest. An unknown id has no manifest: return the base
    # with no od_context and let the caller's SUPPORTED_PIPELINE_TYPES gate reject
    # (the closed-set resolver means no path traversal via the run label).
    try:
        compiled = compile_for_run(pipeline_type)
    except FileNotFoundError:
        return base_pipeline_type, None

    # Eligibility is now the declared signal ALONE — which is what D-15/C set out
    # to achieve. It used to carry a second clause: a base whose OpenDesign flavor
    # had a dedicated ``od_`` alias was excluded from its OWN declared capability,
    # so bare ``prototype`` resolved to od_context=None and was then rejected
    # downstream by the 13-06 ``missing_template_context`` guard. That clause
    # existed to byte-preserve the od_prototype-vs-prototype split; with the alias
    # collapsed (``agents/registry._OD_ALIAS_BASE`` is empty) there is no split to
    # preserve, and a pipeline that declares ``opendesign`` simply gets it.
    if "opendesign" not in (compiled.context_providers or []):
        return base_pipeline_type, None

    # Nothing was ASKED for: no template id and no inline body. This is the
    # blank-canvas / no-template mode — pass template_id="" through to the loader,
    # which handles it explicitly (od_context.py: `template_id in (None, "", "none")`
    # → blank-canvas mode with design-system tokens only). Returning None here would
    # trigger the downstream missing_template_context 400 guard, which is wrong:
    # the user DID make a choice (no template), they just want a blank-canvas build.
    # The accurate path: let the loader produce a no-template od_context (design
    # system only) so agents run in blank-canvas mode with DS tokens injected.
    # Exception: if there is no design_system_id either, the loader has nothing to
    # inject — return None only in that case (both template AND design system absent).
    if not (template_id or custom_template_body):
        if not (design_system_id or custom_ds_body):
            # Truly nothing — let the downstream missing_template_context guard
            # produce the right error message.
            return base_pipeline_type, None
        # Has a design system but no template → blank-canvas mode.
        # Fall through to the loader with template_id="" so it enters blank-canvas
        # path (od_context.py line 123: `template_id in (None, "", "none")`).
        template_id = ""

    # ── LOADER PROFILE (preserved compatibility shim) ─────────────────────────
    # FIXME(ISS-046 / D-15/C v1): generic loader-profile *declaration* is deferred
    # — tracked in .planning/ISSUES-REGISTER.md (ISS-046); see RESEARCH Open
    # Question 2. Only prototype / ppt / ppt_revision declare
    # opendesign today, so this base-family mapping is byte-preserving. The
    # per-family argument shaping reproduces the OLD name-branch verbatim
    # (prototype: ``design_system_id or ""``; ppt-family: raw ``design_system_id``).
    try:
        if base_pipeline_type == "prototype":
            od_context = load_prototype_od_context(
                template_id or "",
                design_system_id or "",
                custom_ds_body=custom_ds_body,
                custom_template_body=custom_template_body,
            )
        else:  # ppt-family (ppt, ppt_revision)
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
