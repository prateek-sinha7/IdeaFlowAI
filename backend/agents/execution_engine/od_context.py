"""agents/execution_engine/od_context.py — OD template/design-system loader.

Loads template skill body, design system tokens, and craft rules for agents
that declare an `injects` capability (od_prototype / od_ppt pipelines).

Prototype context loading has moved to agents/prototype/context.py.
This file re-exports load_prototype_od_context for backward compatibility
and contains load_ppt_od_context (PPT-specific, stays here).
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import od_loader

# Re-export prototype context loader from its new home
from agents.prototype.context import load_prototype_context as load_prototype_od_context  # noqa: F401

logger = logging.getLogger(__name__)


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

    return {
        "template_id": template_id,
        "template_body": template.get("body", ""),
        "ds_id": ds_id,
        "ds_body": ds_body,
        "craft_block": "",  # decks do not inject craft rules
        "is_design_system_required": is_design_system_required,
    }
