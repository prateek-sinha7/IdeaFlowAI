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
kernel/web contracts stay green.

The sandbox helpers this module used to hold have moved out, because the
execution kernel is their caller and import-linter's "kernel imports only
capability ports (scaffold)" contract forbids ``agents.execution_engine.engine ->
app.api``:

* the ``.context/`` design-input writer/reader (``write_od_context_to_sandbox`` /
  ``rebuild_od_context_from_sandbox`` / ``context_already_present``) lives in
  ``app.services.od_context_sandbox``;
* the ``.context/user-prompt.md`` writer and the inline-attachment stripper
  (``write_user_prompt_to_sandbox`` / ``strip_inline_attachments`` /
  ``USER_PROMPT_PATH``) live kernel-side in
  ``agents.execution_engine.user_prompt`` (stdlib-only, so the dependency points
  inward).
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
    context_providers: list[str] | None = None,
    figma_frame_count: int | None = None,
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
    from app.services import od_loader

    base_pipeline_type = resolve_alias(pipeline_type)

    # ── ELIGIBILITY (name-free — the SC-001 win) ──────────────────────────────
    # Peek the compiled manifest. An unknown id has no manifest: return the base
    # with no od_context and let the caller's SUPPORTED_PIPELINE_TYPES gate reject
    # (the closed-set resolver means no path traversal via the run label).
    #
    # ``context_providers`` OVERRIDE: a COMPOSED workflow (Composer manifest,
    # LaunchSource.USER_WORKFLOW_MANIFEST) has no file behind its label — its
    # ``pipeline_type`` is the generic "custom", whose workflow.yaml declares
    # ``context_providers: []``. Peeking the file would therefore return None for
    # every composed run, no matter what the composition itself declares. The
    # launch boundary has ALREADY compiled the real manifest by the time it calls
    # this, so it passes those providers in and this peek is skipped. Default
    # ``None`` ⇒ the file peek, i.e. byte-identical behaviour for every built-in
    # pipeline (INV-3). Still eligibility-by-DECLARED-SIGNAL — no name branch.
    if context_providers is None:
        try:
            compiled = compile_for_run(pipeline_type)
        except FileNotFoundError:
            return base_pipeline_type, None
        context_providers = list(compiled.context_providers or [])

    # Eligibility is now the declared signal ALONE — which is what D-15/C set out
    # to achieve. It used to carry a second clause: a base whose OpenDesign flavor
    # had a dedicated ``od_`` alias was excluded from its OWN declared capability,
    # so bare ``prototype`` resolved to od_context=None and was then rejected
    # downstream by the 13-06 ``missing_template_context`` guard. That clause
    # existed to byte-preserve the od_prototype-vs-prototype split; with the alias
    # collapsed (``agents/registry._OD_ALIAS_BASE`` is empty) there is no split to
    # preserve, and a pipeline that declares ``opendesign`` simply gets it.
    if "opendesign" not in context_providers:
        return base_pipeline_type, None

    # ── SOURCE TYPE DETECTION (design-ingestor / Phase 1) ────────────────────
    # First-match wins. Figma takes priority so a run with uploaded frames is
    # never mis-classified as catalog even when template_id is absent.
    # source_type is carried into od_context so selections.json captures it for
    # every downstream agent (opendesign context provider, ingestor step).
    if figma_frame_count is not None and figma_frame_count > 0:
        source_type: str = "figma"
    elif custom_template_body:
        source_type = "html"
    else:
        source_type = "catalog"

    # ── FIGMA SHORTCUT (design-ingestor / Phase 1) ────────────────────────────
    # A figma-frames run carries no catalog template_id and no custom_template_body
    # — the "nothing was asked for" guard below would return None, triggering the
    # missing_template_context 400. Bypass that path: the Design Ingestor agent
    # owns .context/design/ for figma runs; we only need a sentinel od_context
    # so write_od_context_to_sandbox writes selections.json (context_already_present
    # returns True after launch, preventing a revision from overwriting it).
    if source_type == "figma":
        from agents.execution_engine.od_context import load_figma_ingest_context
        return base_pipeline_type, load_figma_ingest_context(
            frame_count=figma_frame_count or 0
        )

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
    # Question 2. The set that declares opendesign has since grown past the original
    # three (prototype / ppt / ppt_revision) to include prototype_feature_revision and
    # ppt_v2, and each addition has had to be hand-sorted into a family below — which
    # is exactly the drift ISS-046 predicted. The mapping is still byte-preserving for
    # every one of them; it is the SHAPE that should become a declaration. The
    # per-family argument shaping reproduces the OLD name-branch verbatim
    # (prototype: ``design_system_id or ""``; ppt-family: raw ``design_system_id``).
    # A COMPOSED workflow's base is the generic "custom", so neither arm of the
    # preserved shim below describes it. Derive its profile from the DECLARED
    # `mode` of the template the user actually picked — the same field the two
    # catalog endpoints filter on (`list_prototype_templates`: mode == "prototype";
    # `list_ppt_templates`: mode in {"deck","slides"}), read from the ONE
    # `design-templates/` directory both families share. This is ISS-046's
    # "generic loader-profile declaration" for the only label that needs it: the
    # template says what it is, so nothing can drift out of sync with it, and no
    # second manifest key has to be kept honest. A blank-canvas launch (no
    # template) has no mode to read and falls to the web profile, which is the
    # only one with a `no_template` path.
    # Resolve the loader FAMILY, not the pipeline name. The two named families are
    # listed explicitly; anything else — a composed `custom` run, or a file workflow
    # that declares opendesign without being one of these — derives its family from
    # the picked template's own `mode`, since the template is the thing that knows
    # whether it is a page or a deck.
    #
    # An exclusion list was the first cut and it was wrong twice over. `ppt_v2` and
    # `prototype_feature_revision` also declare `context_providers: [opendesign]`
    # but appeared in no tuple, so they fell into the derivation: for a `ppt_v2`
    # launch carrying a design system and NO template the blank-canvas branch above
    # sets template_id = "", leaving no mode to read, so a DECK pipeline would have
    # been handed a web od_context where it previously raised LookupError → a clean
    # 400 template_not_found. Narrowing the derivation to `custom` fixed that but
    # broke the other direction: `pdf_to_prototype` (a web workflow) would have
    # fallen to `base_profile = "pdf_to_prototype"`, which is not "prototype", and
    # landed on the DECK loader. Naming the families is the only form that survives
    # a new workflow being added on either side.
    _WEB_PIPELINES = {"prototype", "prototype_feature_revision"}
    _DECK_PIPELINES = {"ppt", "ppt_revision", "ppt_v2"}
    if base_pipeline_type in _WEB_PIPELINES:
        base_profile = "prototype"
    elif base_pipeline_type in _DECK_PIPELINES:
        base_profile = "ppt"
    else:
        _tmpl = od_loader.get_template(template_id) if template_id else None
        _deck = (_tmpl or {}).get("mode") in ("deck", "slides")
        base_profile = "ppt" if _deck else "prototype"

    try:
        if base_profile == "prototype":
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

    # Stamp source_type onto the returned dict so od_context_sandbox.py writes
    # it into selections.json. Catalog and html runs have no figma_frame_count.
    od_context["source_type"] = source_type
    od_context["figma_frame_count"] = None  # only figma runs carry a count

    return base_pipeline_type, od_context
