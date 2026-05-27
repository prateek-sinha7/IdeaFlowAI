"""Runner for the OpenDesign-style PPT/deck pipeline.

Streams events in real time â€” each Bedrock token is forwarded to the
WebSocket immediately as it arrives.

Three-agent pipeline:
  1. Presentation Strategist (od-ppt-brief-analyst) â€” slide plan JSON
  2. Deck Engineer (od-ppt-composer) â€” complete HTML deck
  3. Deck QA Agent (od-ppt-validator) â€” validated HTML deck

Mirrors od_runner.py architecture exactly. Uses DeepAgent.astream_with_usage
for all three agents (text-only, tools=[]).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, AsyncGenerator

from app.agents.deep_agent import DeepAgent
# od_ppt_runner uses the NEW agents.registry (slim registry with AgentSpec objects
# that have .prompt_body). This is different from od_runner.py which uses the OLD
# app.agents.registry for backward compatibility. The od_ppt agents are only in
# the new registry.
from agents.registry import get_pipeline_agents
from app.services import od_loader

logger = logging.getLogger("app.agents.od_ppt_runner")


_SPEC_RE = re.compile(r"<spec>\s*(.*?)\s*</spec>", re.DOTALL)
_ARTIFACT_RE = re.compile(r"<artifact[^>]*>\s*(.*?)\s*</artifact>", re.DOTALL)


def _extract_spec(raw: str) -> str:
    m = _SPEC_RE.search(raw)
    return (m.group(1) if m else raw).strip()


def _extract_artifact(raw: str) -> str:
    """Extract HTML content from an artifact-tagged response."""
    m = _ARTIFACT_RE.search(raw)
    if m:
        return m.group(1).strip()
    # Fallback: search for HTML start
    html_match = re.search(r'(<!DOCTYPE\s+html[\s\S]*|<html[\s>][\s\S]*)', raw, re.DOTALL | re.IGNORECASE)
    if html_match:
        return html_match.group(1).strip()
    return raw.strip()


def _format_discovery(discovery: dict[str, Any] | None) -> str:
    if not discovery:
        return ""
    lines: list[str] = []
    for key in ("audience", "tone", "slide_count", "goal", "data_vs_visual", "surface", "constraints"):
        value = discovery.get(key) if isinstance(discovery, dict) else None
        if value:
            lines.append(f"  {key}: {value}")
    # Also include any template-specific answers
    template_extras = discovery.get("template") if isinstance(discovery, dict) else None
    if isinstance(template_extras, dict):
        for k, v in template_extras.items():
            if v:
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _load_ppt_context(
    template_id: str,
    design_system_id: str | None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> dict[str, Any]:
    """Load template and (optionally) design system context for the PPT pipeline.

    Key difference from prototype: most deck templates are self-contained and
    do NOT require a design system. We only load the DS when:
    - The template has design_system.requires == True (simple-deck, ib-pitch-book)
    - OR custom_ds_body is explicitly provided by the user
    """
    # Load template â€” fall back to any template if not found as a deck template
    template = od_loader.get_ppt_template(template_id)
    if template is None:
        # For custom templates, try the generic loader
        if custom_template_body:
            template = od_loader.get_ppt_template("html-ppt") or {}
            template = dict(template) if template else {}
            template["id"] = template_id
        else:
            raise LookupError(f"PPT template '{template_id}' not found")

    # Determine if design system is needed
    ds_requires = template.get("design_system", {}).get("requires", False)
    is_design_system_required = ds_requires or bool(custom_ds_body)

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
            logger.info("Using custom design system body (%d chars)", len(ds_body))
        elif design_system_id:
            ds = od_loader.get_design_system(design_system_id)
            if ds is None:
                logger.warning("Design system '%s' not found â€” proceeding without it", design_system_id)
                is_design_system_required = False
            else:
                ds_body = ds["body"]
        else:
            is_design_system_required = False

    # Example HTML (visual reference)
    example_html = ""
    if custom_template_body:
        example_html = custom_template_body
        logger.info("Using custom template body (%d chars) as example_html", len(custom_template_body))
    else:
        example_path = od_loader.get_template_preview_path(template_id)
        if example_path is not None:
            try:
                example_html = example_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read example.html for %s: %s", template_id, exc)

    # Template seed (assets/template.html)
    template_seed = od_loader.get_template_seed(template_id)

    # Reference files (references/*.md)
    template_references = od_loader.get_template_references(template_id)

    return {
        "template_id": template_id,
        "template_body": template.get("body", ""),
        "ds_id": ds_id,
        "ds_body": ds_body,
        "is_design_system_required": is_design_system_required,
        "example_html": example_html or "(no example.html available)",
        "template_seed": template_seed,
        "template_references": template_references,
        "is_custom_template": bool(custom_template_body),
    }


def _compose_ppt_system_prompt(
    base_prompt: str,
    od: dict[str, Any],
    include_design_system: bool = False,
) -> str:
    """Build the system prompt for a PPT pipeline agent.

    Stack order:
      0. CRITICAL RULES (deck-specific)
      1. DESIGN.md (only when required)
      2. SKILL.md body
      3. Agent role prompt
    """
    sections: list[str] = []

    # 0. Critical rules â€” deck-specific
    sections.append(
        "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
        "CRITICAL OUTPUT RULES â€” READ BEFORE ANYTHING ELSE\n"
        "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
        "1. OUTPUT FORMAT: Emit ONE complete HTML file inside <artifact>...</artifact> tags.\n\n"
        "2. SLIDES: Every slide must be a <section class=\"slide\"> element.\n"
        "   The first slide gets class=\"slide active\". All others start hidden.\n"
        "   Slide count must match the spec exactly.\n\n"
        "3. NAVIGATION: Arrow keys (â†/â†’), click buttons, and touch swipe must all work.\n"
        "   NEVER rewrite the navigation script from the template â€” copy it verbatim.\n"
        "   It solves 5 iframe-specific bugs. Only add per-slide handlers on top.\n\n"
        "4. CONTENT: No placeholder text. No lorem ipsum. Every slide has real content\n"
        "   from the spec. No empty slides.\n\n"
        "5. SELF-CONTAINED: No external image URLs. Single file. Works offline.\n"
        "   (PptxGenJS CDN is allowed if the template uses it.)\n\n"
        "6. THEME LOCK: Apply the theme_choice from the spec consistently.\n"
        "   Never mix themes or palettes mid-deck.\n"
    )

    # 1. Design system (only when required)
    if include_design_system and od.get("ds_body"):
        sections.append(
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
            f"ACTIVE DESIGN SYSTEM: {od['ds_id']}\n"
            f"Use these tokens for colors, fonts, and spacing.\n"
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
            f"{od['ds_body']}"
        )

    # 2. SKILL.md body
    if od.get("template_body"):
        sections.append(
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
            f"ACTIVE TEMPLATE SKILL: {od['template_id']}\n"
            f"The Workflow section below is your primary instruction.\n"
            f"Follow each numbered step in order.\n"
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
            f"{od['template_body']}"
        )

    # 3. Agent role prompt
    sections.append(base_prompt)

    return "\n\n---\n\n".join(sections)


def _user_message_brief_analyst(
    brief: str, discovery: dict[str, Any] | None, od: dict[str, Any]
) -> str:
    disc = _format_discovery(discovery) or "(none provided)"
    return (
        "USER BRIEF:\n\n"
        f"{brief.strip() or '(no brief)'}\n\n"
        f"DISCOVERY ANSWERS:\n{disc}\n"
    )


def _user_message_deck_composer(
    spec_json: str, brief: str, discovery: dict[str, Any] | None, od: dict[str, Any]
) -> str:
    disc = _format_discovery(discovery) or "(none provided)"
    template_seed = od.get("template_seed")
    template_references = od.get("template_references") or {}
    is_custom_template = od.get("is_custom_template", False)

    # Reference files block
    refs_parts = []
    for name, body in template_references.items():
        refs_parts.append(
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
            f"TEMPLATE REFERENCE: references/{name}.md\n"
            f"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
            f"{body}"
        )
    references_block = "\n\n".join(refs_parts) + "\n\n" if refs_parts else ""

    # Template seed or example
    example_label = (
        "CUSTOM TEMPLATE (user-supplied â€” use as structural reference)\n"
        "Extract: slide layouts, navigation script, theme system.\n"
        "Apply the spec's theme_choice â€” do NOT copy the custom template's content."
        if is_custom_template else
        "TEMPLATE EXAMPLE (example.html â€” visual reference)\n"
        "Extract: slide class system, navigation script, theme palettes, layout patterns.\n"
        "Do NOT copy its content â€” use the spec's content instead."
    )

    seed_section = ""
    if template_seed:
        seed_section = (
            "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
            "TEMPLATE SEED (assets/template.html â€” start from this)\n"
            "Apply the theme_choice from the spec. Replace placeholder content.\n"
            "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
            f"{template_seed}\n"
        )

    return (
        "SPEC FROM PRESENTATION STRATEGIST (execute this literally):\n\n"
        f"{spec_json}\n\n"
        f"USER BRIEF (context only â€” the spec above takes precedence):\n{brief.strip() or '(no brief)'}\n\n"
        f"DISCOVERY ANSWERS:\n{disc}\n\n"
        f"{references_block}"
        "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n"
        f"{example_label}\n"
        "â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•\n\n"
        f"{od['example_html']}\n\n"
        f"{seed_section}"
    )


def _user_message_delivery_validator(prior_html: str) -> str:
    return (
        "PRIOR ARTIFACT (HTML deck from the Deck Engineer â€” validate and finalise):\n\n"
        f"{prior_html}\n"
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_od_ppt_pipeline(
    template_id: str,
    design_system_id: str | None,
    brief: str,
    discovery: dict[str, Any] | None,
    custom_ds_body: str | None = None,
    custom_template_body: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """3-stage PPT pipeline streaming events in real time.

    Event shapes yielded (same as od_runner.py):
      {type: "pipeline_start",   agents: [...]}
      {type: "agent_start",      agent_id, name, role, icon, index}
      {type: "agent_chunk",      agent_id, chunk}
      {type: "agent_complete",   agent_id, output_size, duration}
      {type: "agent_error",      agent_id, error}
      {type: "artifact",         stage, html}
      {type: "pipeline_complete", final_html, duration}
      {type: "pipeline_error",   error}
    """
    pipeline_start = time.monotonic()

    try:
        od = _load_ppt_context(
            template_id, design_system_id,
            custom_ds_body=custom_ds_body,
            custom_template_body=custom_template_body,
        )
    except LookupError as exc:
        yield {"type": "pipeline_error", "error": str(exc)}
        return

    agents = get_pipeline_agents("od_ppt")
    if len(agents) != 3:
        yield {"type": "pipeline_error", "error": f"Expected 3 od_ppt agents, got {len(agents)}"}
        return

    strategist, composer, validator = agents

    yield {
        "type": "pipeline_start",
        "pipeline_type": "od_ppt",
        "agents": [
            {"id": a.id, "name": a.name, "role": a.role, "icon": a.icon, "index": i}
            for i, a in enumerate(agents)
        ],
    }

    from app.agents.base import TokenUsage, estimate_cost_usd

    pipeline_usage = TokenUsage()
    agent_token_usage: dict[str, TokenUsage] = {}

    # â”€â”€ Agent 1: Presentation Strategist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    yield {"type": "agent_start", "agent_id": strategist.id, "name": strategist.name,
           "role": strategist.role, "icon": strategist.icon, "index": 0}
    t0 = time.monotonic()
    spec_raw = ""
    a1_usage = TokenUsage()
    try:
        a1 = DeepAgent(
            system_prompt=_compose_ppt_system_prompt(
                strategist.prompt_body, od, include_design_system=False
            ),
            tools=[],
            max_tokens=strategist.max_tokens,
        )
        async for item in a1.astream_with_usage(_user_message_brief_analyst(brief, discovery, od)):
            if isinstance(item, TokenUsage):
                a1_usage = item
                break
            spec_raw += item
            yield {"type": "agent_chunk", "agent_id": strategist.id, "chunk": item}
    except Exception as exc:
        logger.exception("Presentation Strategist failed")
        yield {"type": "agent_error", "agent_id": strategist.id, "error": str(exc)}
        return
    agent_token_usage[strategist.id] = a1_usage
    pipeline_usage = pipeline_usage + a1_usage
    yield {"type": "agent_complete", "agent_id": strategist.id,
           "output_length": len(spec_raw), "duration": time.monotonic() - t0,
           "input_tokens": a1_usage.input_tokens, "output_tokens": a1_usage.output_tokens}

    spec_json = _extract_spec(spec_raw)

    # â”€â”€ Agent 2: Deck Engineer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    yield {"type": "agent_start", "agent_id": composer.id, "name": composer.name,
           "role": composer.role, "icon": composer.icon, "index": 1}
    t0 = time.monotonic()
    composer_raw = ""
    a2_usage = TokenUsage()
    try:
        a2 = DeepAgent(
            system_prompt=_compose_ppt_system_prompt(
                composer.prompt_body, od,
                include_design_system=od["is_design_system_required"],
            ),
            tools=[],
            max_tokens=composer.max_tokens,
        )
        async for item in a2.astream_with_usage(
            _user_message_deck_composer(spec_json, brief, discovery, od)
        ):
            if isinstance(item, TokenUsage):
                a2_usage = item
                break
            composer_raw += item
            yield {"type": "agent_chunk", "agent_id": composer.id, "chunk": item}
    except Exception as exc:
        logger.exception("Deck Engineer failed")
        yield {"type": "agent_error", "agent_id": composer.id, "error": str(exc)}
        return
    agent_token_usage[composer.id] = a2_usage
    pipeline_usage = pipeline_usage + a2_usage
    composer_html = _extract_artifact(composer_raw)
    logger.info("Deck Engineer: raw=%d chars, extracted html=%d chars", len(composer_raw), len(composer_html))
    yield {"type": "artifact", "stage": "composer", "html": composer_html}
    yield {"type": "agent_complete", "agent_id": composer.id,
           "output_length": len(composer_raw), "duration": time.monotonic() - t0,
           "input_tokens": a2_usage.input_tokens, "output_tokens": a2_usage.output_tokens}

    # â”€â”€ Agent 3: Deck QA Agent â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    yield {"type": "agent_start", "agent_id": validator.id, "name": validator.name,
           "role": validator.role, "icon": validator.icon, "index": 2}
    t0 = time.monotonic()
    validator_raw = ""
    a3_usage = TokenUsage()
    try:
        a3 = DeepAgent(
            system_prompt=validator.prompt_body,
            tools=[],
            max_tokens=validator.max_tokens,
        )
        async for item in a3.astream_with_usage(_user_message_delivery_validator(composer_html)):
            if isinstance(item, TokenUsage):
                a3_usage = item
                break
            validator_raw += item
            yield {"type": "agent_chunk", "agent_id": validator.id, "chunk": item}
    except Exception as exc:
        logger.exception("Deck QA Agent failed")
        yield {"type": "agent_error", "agent_id": validator.id, "error": str(exc)}
        return
    agent_token_usage[validator.id] = a3_usage
    pipeline_usage = pipeline_usage + a3_usage
    final_html = _extract_artifact(validator_raw)
    logger.info("Deck QA Agent: raw=%d chars, final html=%d chars", len(validator_raw), len(final_html))
    yield {"type": "artifact", "stage": "final", "html": final_html}
    yield {"type": "agent_complete", "agent_id": validator.id,
           "output_length": len(validator_raw), "duration": time.monotonic() - t0,
           "input_tokens": a3_usage.input_tokens, "output_tokens": a3_usage.output_tokens}

    pipeline_cost = estimate_cost_usd(pipeline_usage, a1.model_id)
    yield {
        "type": "pipeline_complete",
        "final_html": final_html,
        "duration": time.monotonic() - pipeline_start,
        "total_input_tokens": pipeline_usage.input_tokens,
        "total_output_tokens": pipeline_usage.output_tokens,
        "total_tokens": pipeline_usage.total_tokens,
        "estimated_cost_usd": round(pipeline_cost, 6),
        "token_usage_per_agent": {aid: u.to_dict() for aid, u in agent_token_usage.items()},
    }

