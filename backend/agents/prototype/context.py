"""agents/prototype/context.py — Prototype OD context loader.

Loads the template SKILL.md body, design system DESIGN.md body, and craft
rules for the prototype pipeline. The result is an `od_context` dict that
the execution engine threads into every agent's AgentContext.

Also provides helpers for pre-injecting template files into the agent's
context message (saves 3 LLM round-trips per agent).
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
