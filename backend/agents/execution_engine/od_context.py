"""agents/execution_engine/od_context.py — OD template/design-system loaders.

Loads template skill body, design system tokens, craft rules, and the pre-injected
template reference files for agents that declare an ``injects`` capability
(od_prototype / od_ppt pipelines). This module is the BOUNDARY loader: it imports
``app.services.od_loader`` (the heavy disk reads) and is called at the WS / NDJSON
boundary to build the ``od_context`` dict passed into ``execute()`` (Assumption
A6). The capability layer (``agents.capabilities.context_providers.opendesign``)
composes its injection blocks FROM the dict this module produces — it never
imports ``od_loader`` (import-linter: capabilities must not import ``app``).

The three prototype loaders below (``load_prototype_context``,
``get_template_injection_parts``, ``get_example_html``) were PHYSICALLY RELOCATED
here from ``agents/prototype/context.py`` (move-don't-copy, INV-12 — the old
home no longer defines them). ``load_ppt_od_context`` (PPT-specific) stays here.
``load_prototype_od_context`` is the long-standing public alias of
``load_prototype_context`` (kept for the existing boundary importers).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services import od_loader

logger = logging.getLogger(__name__)

# Root of the OpenDesign template folder. Single source of truth is od_loader,
# which resolves the dir across local-repo vs container layouts.
_TEMPLATES_DIR = od_loader._TEMPLATES_DIR


def load_prototype_context(
    template_id: str,
    design_system_id: str,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> dict[str, Any]:
    """Load OD context for the prototype pipeline.

    Returns a dict with:
        template_id       — the selected template slug
        template_body     — full SKILL.md body (workflow instructions)
        ds_id             — design system ID
        ds_body           — full DESIGN.md body (tokens, typography, spacing)
        craft_block       — concatenated craft rule bodies (if any)
        is_design_system_required — always None for prototype (always required)

    Raises:
        LookupError: if the template or design system cannot be found.

    Relocated verbatim from ``agents/prototype/context.py`` (INV-12 move-don't-copy).
    """
    # ── Load template ──────────────────────────────────────────────────────
    template = od_loader.get_template(template_id)
    if template is None:
        if custom_template_body:
            # Fall back to web-prototype as the base template
            template = od_loader.get_template("web-prototype")
            if template is None:
                raise LookupError(
                    f"Template '{template_id}' not found and 'web-prototype' fallback unavailable"
                )
            logger.warning(
                "Template '%s' not found — using 'web-prototype' as fallback", template_id
            )
        elif template_id in (None, "", "none"):
            # KAN-87: no-template mode — user explicitly chose not to select a template.
            # Return a minimal context with no template body so the spec writer
            # invents its own layout from the UI clarification answers.
            logger.info("No template selected — proceeding without template injection")
            # Still load the design system (required for color tokens).
            if custom_ds_body:
                ds_id = design_system_id or "custom"
                ds_body = (
                    f"# Custom Design System: {ds_id}\n\n"
                    f"This design system was provided directly by the user. "
                    f"Follow its tokens exactly — do not invent or substitute values.\n\n"
                    f"{custom_ds_body.strip()}"
                )
            else:
                ds = od_loader.get_design_system(design_system_id)
                if ds is None:
                    raise LookupError(f"Design system '{design_system_id}' not found")
                ds_id = design_system_id
                ds_body = ds["body"]
            return {
                "template_id": None,
                "template_body": None,
                "ds_id": ds_id,
                "ds_body": ds_body,
                "craft_block": "",
                "is_design_system_required": None,
                "no_template": True,  # signal to the opendesign provider to skip template injection
            }
        else:
            raise LookupError(f"Prototype template '{template_id}' not found")

    # ── Load design system ─────────────────────────────────────────────────
    if custom_ds_body:
        ds_id = design_system_id or "custom"
        ds_body = (
            f"# Custom Design System: {ds_id}\n\n"
            f"This design system was provided directly by the user. "
            f"Follow its tokens exactly — do not invent or substitute values.\n\n"
            f"{custom_ds_body.strip()}"
        )
    else:
        ds = od_loader.get_design_system(design_system_id)
        if ds is None:
            raise LookupError(f"Design system '{design_system_id}' not found")
        ds_id = design_system_id
        ds_body = ds["body"]

    # ── Load craft rules ───────────────────────────────────────────────────
    craft_required = template.get("craft_required") or []
    craft_rules = od_loader.get_craft_rules(craft_required)
    craft_block = (
        "\n\n---\n\n".join(f"## craft/{n}\n\n{b}" for n, b in craft_rules.items())
        if craft_rules
        else ""
    )

    return {
        "template_id": template_id,
        "template_body": template["body"],
        "ds_id": ds_id,
        "ds_body": ds_body,
        "craft_block": craft_block,
        "is_design_system_required": None,  # prototype always requires DS
    }


def get_template_injection_parts(template_id: str) -> list[str]:
    """Return pre-injected template file blocks for the agent context message.

    Pre-injecting these files saves 3 LLM round-trips per agent (read_template_seed,
    read_layout_reference, read_checklist tool calls are skipped).

    Returns a list of formatted strings to append to the context message.

    Relocated verbatim from ``agents/prototype/context.py`` (INV-12 move-don't-copy).
    """
    parts: list[str] = []

    # Template seed (assets/template.html)
    seed = od_loader.get_template_seed(template_id)
    if seed:
        parts.append(
            f"=== TEMPLATE SEED (assets/template.html) ===\n"
            f"This is the starter HTML for this template. Use it as your base.\n"
            f"{seed[:6000]}{'...[truncated]' if len(seed) > 6000 else ''}\n"
            f"=== END TEMPLATE SEED ==="
        )

    # Reference files (layouts.md, checklist.md, etc.)
    refs = od_loader.get_template_references(template_id)
    for ref_name, ref_body in refs.items():
        parts.append(
            f"=== TEMPLATE REFERENCE ({ref_name}.md) ===\n"
            f"{ref_body[:4000]}{'...[truncated]' if len(ref_body) > 4000 else ''}\n"
            f"=== END REFERENCE ==="
        )

    return parts


def get_example_html(template_id: str, max_chars: int = 8000) -> str | None:
    """Return the template's example.html content, truncated to max_chars.

    The example HTML gives agents a concrete visual reference for the
    template's class system, chrome, density, and accent budget.

    Relocated verbatim from ``agents/prototype/context.py`` (INV-12 move-don't-copy).
    """
    path = od_loader.get_template_preview_path(template_id)
    if path is None or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        if len(content) > max_chars:
            return content[:max_chars] + "\n...[truncated]"
        return content
    except OSError as exc:
        logger.debug("Could not read example.html for %s: %s", template_id, exc)
        return None


# Long-standing public alias used by the WS / NDJSON boundary importers.
load_prototype_od_context = load_prototype_context


def load_ppt_od_context(
    template_id: str,
    design_system_id: str | None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> dict[str, Any]:
    """Load OD context for the od_ppt deck pipeline.

    Design system is conditional: only loaded when the template declares
    design_system.requires == True OR a custom_ds_body is provided.

    Raises LookupError if the template cannot be found.
    """
    template = od_loader.get_ppt_template(template_id)
    if template is None:
        if custom_template_body:
            template = dict(od_loader.get_ppt_template("html-ppt") or {})
            template["id"] = template_id
        else:
            raise LookupError(f"PPT template '{template_id}' not found")

    ds_requires = template.get("design_system", {}).get("requires", False)
    is_design_system_required = bool(ds_requires or custom_ds_body)

    ds_id = design_system_id or "none"
    ds_body = ""
    if is_design_system_required:
        if custom_ds_body:
            ds_id = design_system_id or "custom"
            ds_body = (
                f"# Custom Design System: {ds_id}\n\n"
                f"This design system was provided directly by the user. "
                f"Follow its tokens exactly.\n\n"
                f"{custom_ds_body.strip()}"
            )
        elif design_system_id:
            ds = od_loader.get_design_system(design_system_id)
            if ds is None:
                logger.warning("Design system '%s' not found — proceeding without it", design_system_id)
                is_design_system_required = False
            else:
                ds_body = ds["body"]
        else:
            is_design_system_required = False

    # ── Template workspace resources (seeded into the run sandbox by the engine).
    # The template body is its SKILL.md, whose Workflow steps name file paths
    # ("read assets/template.html", "references/layouts.md"). Carrying the actual
    # files lets file-granted deck agents execute those steps instead of
    # fabricating tool syntax against a tool-less prompt (live-model failure mode).
    template_files: dict[str, str] = {}
    seed = od_loader.get_template_seed(template_id)
    if seed:
        template_files["assets/template.html"] = seed
    for _ref_name, _ref_content in (od_loader.get_template_references(template_id) or {}).items():
        # get_template_references keys by stem; the SKILL.md instructions name the
        # files with their .md extension — seed at the exact instructed paths.
        if not _ref_name.endswith(".md"):
            _ref_name = f"{_ref_name}.md"
        template_files[f"references/{_ref_name}"] = _ref_content

    return {
        "template_id": template_id,
        "template_body": template.get("body", ""),
        "ds_id": ds_id,
        "ds_body": ds_body,
        "craft_block": "",  # decks do not inject craft rules
        "is_design_system_required": is_design_system_required,
        "template_files": template_files,
    }
