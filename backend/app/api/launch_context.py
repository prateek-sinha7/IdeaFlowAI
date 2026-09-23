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

import json
import logging

logger = logging.getLogger(__name__)


def _write_od_context_to_sandbox(sandbox: object, od_context: dict) -> None:
    """Write the OpenDesign context to ``.context/`` in the run sandbox.

    Layout (Requirement 23 AC 2–3):
    - ``.context/selections.json``          — wizard choices (template_id, ds_id, …)
    - ``.context/design/design-system.md``  — design-system token body
    - ``.context/design/craft.md``          — concatenated craft rules (may be empty)
    - ``.context/design/template/SKILL.md`` — template skill body (if present)
    - ``.context/design/template/<path>``   — seed + reference files from template_files

    Best-effort, never-raising: a write failure logs a warning and continues.
    The writer attribute is probed via duck-typing so harness paths (where
    sandbox may be None or a bare mock) are always safe.
    """
    writer = getattr(sandbox, "write", None)
    if not callable(writer):
        return

    def _safe_write(relpath: str, content: str) -> None:
        try:
            writer(relpath, content)
        except Exception:  # noqa: BLE001
            logger.warning(
                "_write_od_context_to_sandbox: failed to write %s",
                relpath,
                exc_info=True,
            )

    # ── selections.json — the wizard choices persisted for resume/restart ────
    selections: dict = {
        "template_id": od_context.get("template_id"),
        "ds_id": od_context.get("ds_id"),
        "template_name": od_context.get("template_name"),
        "ds_name": od_context.get("ds_name"),
        "no_template": od_context.get("no_template", False),
        "is_design_system_required": od_context.get("is_design_system_required"),
    }
    _safe_write(".context/selections.json", json.dumps(selections, indent=2))

    # ── .context/design/ — the full design material ──────────────────────────
    ds_body = od_context.get("ds_body") or ""
    if ds_body:
        _safe_write(".context/design/design-system.md", ds_body)

    craft_block = od_context.get("craft_block") or ""
    if craft_block:
        _safe_write(".context/design/craft.md", craft_block)

    template_body = od_context.get("template_body") or ""
    if template_body:
        _safe_write(".context/design/template/SKILL.md", template_body)

    # template_files: seed (assets/template.html) + references/*.md
    for rel, content in (od_context.get("template_files") or {}).items():
        if content:
            _safe_write(f".context/design/template/{rel}", content)


def context_already_present(sandbox: object) -> bool:
    """Return True if ``.context/`` already has design inputs written.

    Checks for ``.context/selections.json`` — that is the sentinel file
    ``write_od_context_to_sandbox`` always writes first. Its presence means
    the root run already seeded the shared sandbox's ``.context/`` directory.

    A revision run that shares the physical sandbox with its root must not
    silently overwrite the family's design inputs (Requirement 8 AC 3 — the
    inheritance rule). The function is duck-typed on the ``read`` attribute so
    harness paths where ``sandbox`` is None or a bare mock are safe.
    """
    reader = getattr(sandbox, "read", None)
    if not callable(reader):
        return False
    try:
        content = reader(".context/selections.json")
        return bool(content)
    except Exception:  # noqa: BLE001 — treat any read failure as absent
        return False


def write_od_context_to_sandbox(
    sandbox: object,
    od_context: dict | None,
    *,
    explicit_selection: bool = False,
) -> None:
    """Public entry point: write ``od_context`` into ``.context/`` if non-None.

    Called by the engine's ``_execute_impl`` immediately after the sandbox is
    provisioned (before step 1) and before any agent receives its context
    (Requirement 23 AC 1). Also the rebuild target for ``resume_run``
    (Requirement 23 AC 6): when the DB column is no longer the source of truth,
    rebuild_od_context_from_sandbox() reads back the same files this writes.

    No-op when ``od_context`` is None (non-OD runs) — byte/event-identical
    to the pre-task-8.1 behavior (INV-3).

    Inheritance guard (Requirement 8 AC 3 / SGV2-task-6.8): a revision run
    shares the physical sandbox with its root, so ``.context/`` is ONE directory
    per sandbox — the same design inputs the root wrote are the inputs the
    revision sees. If the directory is already populated and the caller did NOT
    supply an explicit template/design-system selection, skip the write entirely.
    ``explicit_selection=True`` is set only when the launch request carried a
    resolved template or design-system choice (i.e. ``od_context`` was loaded
    from a non-trivial template_id / design_system_id), letting a deliberate
    override on a revision replace the family's inherited inputs.
    """
    if not od_context:
        return
    # Inheritance guard: do not overwrite a parent run's design inputs unless
    # the caller explicitly requested a new template/design-system selection.
    if context_already_present(sandbox) and not explicit_selection:
        logger.debug(
            "write_od_context_to_sandbox: .context/ already present and "
            "no explicit selection — preserving inherited design inputs"
        )
        return
    _write_od_context_to_sandbox(sandbox, od_context)


def rebuild_od_context_from_sandbox(sandbox: object) -> dict | None:
    """Rebuild ``od_context`` from ``.context/`` files after a backend restart.

    Reads the files written by ``write_od_context_to_sandbox`` and reconstructs
    the ``od_context`` dict so ``resume_run`` can pass it to ``_execute_impl``
    without relying on the ``od_context_json`` DB column (Requirement 23 AC 6).

    Returns ``None`` when ``.context/selections.json`` is absent (non-OD run or
    the sandbox pre-dates task 8.1) — callers fall back to the DB column in that
    case so existing resumed runs are unaffected (INV-3 backward compat).

    The reader attribute is probed via duck-typing so harness paths are safe.
    """
    reader = getattr(sandbox, "read", None)
    if not callable(reader):
        return None

    selections_raw = reader(".context/selections.json")
    if not selections_raw:
        # No .context/ written — either a non-OD run or a pre-task-8.1 sandbox.
        return None

    try:
        selections: dict = json.loads(selections_raw)
    except Exception:  # noqa: BLE001
        logger.warning(
            "rebuild_od_context_from_sandbox: failed to parse .context/selections.json",
            exc_info=True,
        )
        return None

    # Rebuild the dict from the individual files. Missing files produce empty
    # strings, which is the same as the loader returning empty — safe to pass.
    ds_body = reader(".context/design/design-system.md") or ""
    craft_block = reader(".context/design/craft.md") or ""
    template_body = reader(".context/design/template/SKILL.md") or ""

    # Rebuild template_files: the seed + reference files under .context/design/template/
    # excluding SKILL.md itself (that is template_body above).
    template_files: dict[str, str] = {}
    list_fn = getattr(sandbox, "list_files", None)
    if callable(list_fn):
        try:
            listed, _ = list_fn()
            template_prefix = ".context/design/template/"
            for entry in listed:
                path: str = entry["path"]
                if (
                    path.startswith(template_prefix)
                    and path != f"{template_prefix}SKILL.md"
                ):
                    rel = path[len(template_prefix) :]  # e.g. "assets/template.html"
                    content = reader(path)
                    if content:
                        template_files[rel] = content
        except Exception:  # noqa: BLE001
            pass  # best-effort; missing template_files degrades to inline inject

    od_context: dict = {
        "template_id": selections.get("template_id"),
        "ds_id": selections.get("ds_id"),
        "template_name": selections.get("template_name"),
        "ds_name": selections.get("ds_name"),
        "no_template": selections.get("no_template", False),
        "is_design_system_required": selections.get("is_design_system_required"),
        "ds_body": ds_body,
        "craft_block": craft_block,
        "template_body": template_body,
        "template_files": template_files,
    }
    return od_context


def resolve_launch_od_context(
    pipeline_type: str,
    template_id: str | None,
    design_system_id: str | None,
    *,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
    fatal: bool,
    context_providers: list[str] | None = None,
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

    return base_pipeline_type, od_context
