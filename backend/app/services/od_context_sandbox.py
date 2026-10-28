"""app/services/od_context_sandbox.py — the run sandbox's ``.context/`` design inputs.

Writes the OpenDesign ``od_context`` (template + design system) into
``.context/`` at sandbox open, and rebuilds it from there on resume
(Requirement 23). Moved here from ``app/api/launch_context.py`` (move, not copy —
INV-12) because the execution kernel is its caller — ``_execute_impl`` seeds
``.context/`` and ``resume_run`` rebuilds from it — and the import-linter
contract "kernel imports only capability ports (scaffold)" forbids
``agents.execution_engine -> app.api``. This module is plain sandbox file I/O over
a duck-typed sandbox (``read`` / ``write`` / ``list_files``) and imports nothing
from the web layer.
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
    - ``.context/design/template/<path>``   — the template's files (example.html,
      assets/template.html, references/*.md, …) from template_files
    - ``.context/design/<name>``            — the design system's tokens.css /
      components.html from ds_files

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
        # Phase 1 (design-ingestor): present when source_type is set; None for
        # pre-Phase-1 od_contexts that did not include these keys. Written as
        # JSON null for catalog runs (backward-compatible — old code ignores it).
        "source_type": od_context.get("source_type"),
        "figma_frame_count": od_context.get("figma_frame_count"),
    }
    _safe_write(".context/selections.json", json.dumps(selections, indent=2))

    # ── .context/design/ — the full design material ──────────────────────────
    # For figma/html source types, the Design Ingestor agent writes files to
    # `context/design/` (WITHOUT the leading dot) because the sandbox write guard
    # blocks agent writes to `.context/` (reserved for the engine). After the
    # Ingestor step, we copy from `context/design/` → `.context/design/` here.
    # This copy runs at write_od_context_to_sandbox call time (before step 1),
    # so it only seeds what the engine knows at launch; the actual ingestor copy
    # is handled by rebuild_od_context_from_sandbox (post-ingestor-step reads).
    # For figma/html source types, the Design Ingestor agent writes all design files
    # to context/design/ (WITHOUT the leading dot) because the sandbox write guard
    # blocks agent writes to .context/. The reader layer (rebuild_od_context_from_sandbox)
    # bridges context/design/ → .context/design/ for downstream agents.
    # We do NOT pre-create sentinel files in .context/design/ — the Ingestor agent
    # owns that tree entirely and writes it after running.

    ds_body = od_context.get("ds_body") or ""
    if ds_body:
        _safe_write(".context/design/design-system.md", ds_body)

    craft_block = od_context.get("craft_block") or ""
    if craft_block:
        _safe_write(".context/design/craft.md", craft_block)

    template_body = od_context.get("template_body") or ""
    if template_body:
        _safe_write(".context/design/template/SKILL.md", template_body)

    # template_files: example.html, assets/template.html, references/*.md, …
    for rel, content in (od_context.get("template_files") or {}).items():
        if content:
            _safe_write(f".context/design/template/{rel}", content)

    # ds_files: the design system's tokens.css / components.html, beside its body
    for name, content in (od_context.get("ds_files") or {}).items():
        if content:
            _safe_write(f".context/design/{name}", content)


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
    # For figma/html runs, the Design Ingestor agent writes to context/design/
    # (no dot) because .context/ is write-protected for agents. Read from
    # context/design/ first for ingestor source types, fall back to .context/design/.
    source_type = selections.get("source_type")
    _is_ingestor = source_type in ("figma", "html")

    def _read_design(relpath_no_dot: str, relpath_dot: str) -> str:
        """Read from no-dot path first (ingestor writes), fall back to dot path (engine writes)."""
        if _is_ingestor:
            val = reader(relpath_no_dot)
            if val:
                return val
        return reader(relpath_dot) or ""

    ds_body = _read_design(
        "context/design/design-system.md", ".context/design/design-system.md"
    )
    craft_block = _read_design("context/design/craft.md", ".context/design/craft.md")
    template_body = _read_design(
        "context/design/template/SKILL.md", ".context/design/template/SKILL.md"
    )

    # Rebuild template_files from the correct location based on source_type.
    template_files: dict[str, str] = {}
    list_fn = getattr(sandbox, "list_files", None)
    if callable(list_fn):
        try:
            listed, _ = list_fn()
            template_prefix = (
                "context/design/template/"
                if _is_ingestor
                else ".context/design/template/"
            )
            for entry in listed:
                path: str = entry["path"]
                if (
                    path.startswith(template_prefix)
                    and not path.endswith("/SKILL.md")
                    and not path.endswith("/.ingestor")
                ):
                    rel = path[len(template_prefix) :]
                    content = reader(path)
                    if content:
                        template_files[rel] = content
        except Exception:  # noqa: BLE001
            pass  # best-effort; missing template_files degrades to inline inject

    ds_files = {
        name: body
        for name in ("tokens.css", "components.html")
        if (
            body := reader(f".context/design/{name}")
            or reader(f"context/design/{name}")
        )
    }

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
        "ds_files": ds_files,
        # Phase 1 (design-ingestor): None for old sandboxes lacking the field.
        # Backward-compatible — .get() returns None when key is absent (INV-3).
        "source_type": selections.get("source_type"),
        "figma_frame_count": selections.get("figma_frame_count"),
    }
    return od_context
