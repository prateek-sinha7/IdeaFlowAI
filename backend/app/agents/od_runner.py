"""Runner for the OpenDesign-style prototype pipeline.

Streams events in real time — each Bedrock token is forwarded to the
WebSocket immediately as it arrives. The previous version used a ``sink``
list that buffered all events and flushed them only after each agent
finished, causing the frontend to see agents jump from idle → done with
no intermediate state and all durations ≈ 0.

Python async generators cannot use ``yield from`` to compose sub-generators
while also returning an accumulated value, so each agent stage is written
inline with a direct ``async for chunk in agent.astream(...)`` loop.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, AsyncGenerator

from app.agents.deep_agent import DeepAgent
# NOTE: od_runner uses the OLD app.agents.registry intentionally — it needs
# AgentDefinition objects (with .system_prompt attribute) because it composes
# system prompts dynamically at runtime by injecting OpenDesign template and
# design-system content. The new slim agents.registry returns AgentSpec objects
# which have .prompt_body instead of .system_prompt. Do NOT change this import
# to agents.registry without also updating all .system_prompt references below.
from app.agents.registry import get_pipeline_agents
from app.services import od_loader

logger = logging.getLogger("app.agents.od_runner")


_SPEC_RE = re.compile(r"<spec>\s*(.*?)\s*</spec>", re.DOTALL)
_ARTIFACT_RE = re.compile(r"<artifact[^>]*>\s*(.*?)\s*</artifact>", re.DOTALL)


def _extract_spec(raw: str) -> str:
    m = _SPEC_RE.search(raw)
    return (m.group(1) if m else raw).strip()


def _extract_artifact(raw: str) -> str:
    """Extract HTML content from an artifact-tagged response.

    Tries in order:
    1. Content inside <artifact>...</artifact> tags (preferred)
    2. Content starting from <!DOCTYPE or <html anywhere in the response
       (handles responses where the model outputs HTML without wrapping tags,
       or with a preamble sentence before the HTML)
    3. Full raw text as fallback
    """
    m = _ARTIFACT_RE.search(raw)
    if m:
        return m.group(1).strip()

    # No artifact tags — search the FULL string for HTML start
    # (do NOT slice — the DOCTYPE may appear after a preamble sentence)
    html_match = re.search(r'(<!DOCTYPE\s+html[\s\S]*|<html[\s>][\s\S]*)', raw, re.DOTALL | re.IGNORECASE)
    if html_match:
        return html_match.group(1).strip()

    return raw.strip()


def _format_discovery(discovery: dict[str, Any] | None) -> str:
    if not discovery:
        return ""
    lines: list[str] = []
    template_extras = discovery.get("template") if isinstance(discovery, dict) else None
    if isinstance(template_extras, dict):
        for k, v in template_extras.items():
            if v:
                lines.append(f"  {k}: {v}")
    for key in ("surface", "audience", "tone", "scale", "constraints"):
        value = discovery.get(key) if isinstance(discovery, dict) else None
        if value:
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _load_od_context(
    template_id: str,
    design_system_id: str,
    custom_ds_body: str | None = None,
) -> dict[str, Any]:
    template = od_loader.get_template(template_id)
    if template is None:
        raise LookupError(f"Template '{template_id}' not found")

    # Custom design system: body is provided directly by the caller.
    # Skip the od_loader lookup entirely — no file on disk needed.
    if custom_ds_body:
        ds_id = design_system_id or "custom"
        ds_body = custom_ds_body.strip()
        # Validate minimum quality — a useful DESIGN.md has at least color tokens
        # and some structure. Warn but don't block if it looks thin.
        if len(ds_body) < 100:
            logger.warning(
                "Custom design system body is very short (%d chars) — "
                "agents may fall back to invented tokens. "
                "Recommend a full 9-section DESIGN.md.",
                len(ds_body),
            )
        # Prepend a clear label so agents know this is user-supplied
        ds_body = (
            f"# Custom Design System: {ds_id}\n\n"
            f"This design system was provided directly by the user. "
            f"Follow its tokens exactly — do not invent or substitute values.\n\n"
            f"{ds_body}"
        )
        logger.info("Using custom design system body (%d chars)", len(ds_body))
    else:
        ds = od_loader.get_design_system(design_system_id)
        if ds is None:
            raise LookupError(f"Design system '{design_system_id}' not found")
        ds_id = design_system_id
        ds_body = ds["body"]

    example_path = od_loader.get_template_preview_path(template_id)
    example_html = ""
    if example_path is not None:
        try:
            example_html = example_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read example.html for %s: %s", template_id, exc)

    # Template's own seed (assets/template.html) — present in several prototype
    # templates. When present, the SKILL.md workflow instructs "Copy
    # assets/template.html as your starting point." We inject it so the Composer
    # uses the right scaffolding instead of the generic Flowin SPA seed.
    template_seed = od_loader.get_template_seed(template_id)

    # Template reference files (references/*.md) — layout libraries, P0/P1/P2
    # checklists, component inventories, connector policies. The SKILL.md workflow
    # explicitly instructs the agent to read these before writing any HTML.
    # Without injecting them the agent writes CSS from scratch and ignores the
    # paste-ready section skeletons and quality gates the template ships.
    template_references = od_loader.get_template_references(template_id)

    craft_required = template.get("craft_required") or []
    craft_rules = od_loader.get_craft_rules(craft_required)
    craft_block = (
        "\n\n---\n\n".join(f"## craft/{n}\n\n{b}" for n, b in craft_rules.items())
        if craft_rules
        else "(no craft rules required by this template)"
    )

    # Single-screen flag: mobile templates produce one screen, not a multi-page SPA.
    # The Flowin SPA seed (hash router + data-page sections) must not be applied
    # to mobile templates.
    #
    # IMPORTANT: Do NOT flag desktop templates as single-screen just because they
    # ship their own seed (assets/template.html). Many desktop templates (web-prototype,
    # live-dashboard, etc.) ship a seed AND expect multi-page SPA output. Only
    # platform == "mobile" is a reliable single-screen signal.
    platform = template.get("platform") or ""
    is_single_screen = (platform == "mobile")

    return {
        "template_id": template_id,
        "template_body": template["body"],
        "ds_id": ds_id,
        "ds_body": ds_body,
        "example_html": example_html or "(no example.html available)",
        "template_seed": template_seed,       # None if template doesn't ship a seed
        "template_references": template_references,  # {} if no references/ folder
        "is_single_screen": is_single_screen,
        "craft_block": craft_block,
    }


# ---------------------------------------------------------------------------
# System prompt composer — mirrors OpenDesign's composeSystemPrompt()
# ---------------------------------------------------------------------------


def _compose_system_prompt(
    base_prompt: str,
    od: dict[str, Any],
    include_craft: bool = True,
) -> str:
    """Build a full system prompt in the same order OpenDesign uses.

    OpenDesign's daemon stacks:
        [DESIGN.md]          ← highest priority; token discipline
        [craft rules]        ← anti-slop checks
        [SKILL.md body]      ← numbered workflow steps
        [role/output prompt] ← our additions (schema, output contract, etc.)

    By putting DESIGN.md and the SKILL.md workflow in the system prompt
    rather than the user message, the model's entire behavioral conditioning
    comes from those files — exactly as OpenDesign intends.
    """
    sections: list[str] = []

    # 1. DESIGN.md — brand tokens; must be obeyed without exception
    sections.append(
        f"═══════════════════════════════════════════════════════════\n"
        f"ACTIVE DESIGN SYSTEM: {od['ds_id']}\n"
        f"All color, font, and spacing values in your output MUST come\n"
        f"from the tokens below. Do not invent new values.\n"
        f"═══════════════════════════════════════════════════════════\n\n"
        f"{od['ds_body']}"
    )

    # 2. Craft rules — universal quality gates
    if include_craft and od.get("craft_block"):
        sections.append(
            f"═══════════════════════════════════════════════════════════\n"
            f"CRAFT RULES (required by this template)\n"
            f"═══════════════════════════════════════════════════════════\n\n"
            f"{od['craft_block']}"
        )

    # 3. SKILL.md body — the template's numbered workflow IS the primary instruction
    sections.append(
        f"═══════════════════════════════════════════════════════════\n"
        f"ACTIVE TEMPLATE SKILL: {od['template_id']}\n"
        f"The Workflow section below is your primary instruction.\n"
        f"Follow each numbered step in order.\n"
        f"═══════════════════════════════════════════════════════════\n\n"
        f"{od['template_body']}"
    )

    # 4. Base role prompt — our additions (output contract, schema, seed, etc.)
    sections.append(base_prompt)

    return "\n\n---\n\n".join(sections)


# ---------------------------------------------------------------------------
# Per-agent user-message builders — task-specific input only
# (DESIGN.md, craft, and SKILL.md are now in the system prompt)
# ---------------------------------------------------------------------------


def _user_message_brief_analyst(brief: str, discovery: dict[str, Any] | None, od: dict[str, Any]) -> str:
    disc = _format_discovery(discovery) or "(none provided)"
    return (
        "USER BRIEF:\n\n"
        f"{brief.strip() or '(no brief)'}\n\n"
        f"DISCOVERY ANSWERS:\n{disc}\n"
    )


def _user_message_spa_composer(
    spec_json: str, brief: str, discovery: dict[str, Any] | None, od: dict[str, Any]
) -> str:
    """Task-specific input for the SPA Composer.

    DESIGN.md, craft rules, and SKILL.md are now in the system prompt.
    The user message carries: spec, brief, example.html (visual ref),
    references/*.md (layout library + checklists), and seed.
    """
    disc = _format_discovery(discovery) or "(none provided)"
    template_seed = od.get("template_seed")
    template_references = od.get("template_references") or {}
    is_single_screen = od.get("is_single_screen", False)

    if is_single_screen:
        structure_note = (
            "⚠️  SINGLE-SCREEN: This template produces ONE self-contained screen. "
            "Do NOT add multi-page hash routing or data-page sections. "
            "Follow the SKILL.md Workflow steps exactly.\n\n"
        )
    else:
        structure_note = ""

    # ── Reference files block (layouts.md, checklist.md, etc.) ──────────
    # These are the most important quality inputs — the SKILL.md workflow
    # explicitly instructs the agent to read them before writing any HTML.
    # layouts.md contains paste-ready section skeletons; checklist.md has
    # P0/P1/P2 quality gates the agent must pass before emitting.
    if template_references:
        refs_parts = []
        for name, body in template_references.items():
            refs_parts.append(
                f"═══════════════════════════════════════════════════════════\n"
                f"TEMPLATE REFERENCE: references/{name}.md\n"
                f"(The SKILL.md workflow instructs you to read this before writing HTML)\n"
                f"═══════════════════════════════════════════════════════════\n\n"
                f"{body}"
            )
        references_block = "\n\n".join(refs_parts) + "\n\n"
    else:
        references_block = ""

    if template_seed:
        seed_section = (
            "═══════════════════════════════════════════════════════════\n"
            "TEMPLATE SEED (assets/template.html — start from this)\n"
            "Replace :root tokens with the DESIGN.md tokens in your system prompt.\n"
            "Replace [REPLACE] placeholders with content from the spec.\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{template_seed}\n"
        )
    else:
        seed_section = (
            "═══════════════════════════════════════════════════════════\n"
            "FLOWIN SPA SEED (multi-page scaffolding)\n"
            "Replace :root tokens with DESIGN.md tokens. "
            "Add <section data-page='...'> per page in the spec.\n"
            "CRITICAL: Every nav link MUST use href='#/page-id' format.\n"
            "CRITICAL: The routes map MUST be populated with every page.\n"
            "═══════════════════════════════════════════════════════════\n\n"
            "<!doctype html>\n<html lang=\"en\">\n<head>\n  <style>\n    :root {\n"
            "      /* Replace ALL with DESIGN.md tokens from your system prompt */\n"
            "      --bg:#fff;--fg:#0f172a;--muted:#64748b;--surface:#f8fafc;\n"
            "      --border:#e2e8f0;--accent:#2563eb;--accent-fg:#fff;\n"
            "      --font-sans:ui-sans-serif,system-ui,sans-serif;\n"
            "    }\n"
            "    body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--font-sans);}\n"
            "    [data-page]{display:none;min-height:100vh;}[data-page].is-active{display:block;}\n"
            "  </style>\n</head>\n<body>\n"
            "  <!-- IMPORTANT: Every nav link must use href='#/page-id' -->\n"
            "  <!-- IMPORTANT: Every page must be wrapped in <section data-page='page-id'> -->\n\n"
            "  <script>\n"
            "    const store=(()=>{let s={};const l=new Set();return{get:k=>k?s[k]:s,set:p=>{s={...s,...p};l.forEach(f=>f(s));},on:(_,f)=>{l.add(f);return()=>l.delete(f);}};})();\n\n"
            "    // HASH ROUTER — MUST populate routes with every page from the spec\n"
            "    // Format: 'page-id': '/path'  (e.g. 'dashboard': '/dashboard')\n"
            "    // Nav links MUST use href='#/path' to trigger hashchange\n"
            "    const routes = {\n"
            "      // FILL IN: 'page-id': '/path' for every page in the spec\n"
            "      // Example: 'dashboard': '/dashboard', 'settings': '/settings'\n"
            "    };\n\n"
            "    function route(){\n"
            "      // Normalise hash: '#/dashboard' → 'dashboard', '#dashboard' → 'dashboard'\n"
            "      const raw = location.hash || '';\n"
            "      const path = raw.replace(/^#\\/?/, '');\n"
            "      const pages = document.querySelectorAll('[data-page]');\n"
            "      let matched = false;\n"
            "      // Try routes map first\n"
            "      for(const [id, pattern] of Object.entries(routes)){\n"
            "        const clean = pattern.replace(/^\\//, '');\n"
            "        if(path === clean || path === id){\n"
            "          pages.forEach(el => el.classList.toggle('is-active', el.dataset.page === id));\n"
            "          store.set({_route:{id,params:{}}});\n"
            "          matched = true;\n"
            "          break;\n"
            "        }\n"
            "      }\n"
            "      // Fallback: match data-page directly against path\n"
            "      if(!matched){\n"
            "        pages.forEach(el => {\n"
            "          const active = el.dataset.page === path;\n"
            "          el.classList.toggle('is-active', active);\n"
            "          if(active) matched = true;\n"
            "        });\n"
            "      }\n"
            "      // Final fallback: show first page when nothing matches (initial load)\n"
            "      if(!matched && pages.length > 0){\n"
            "        pages[0].classList.add('is-active');\n"
            "        store.set({_route:{id: pages[0].dataset.page, params:{}}});\n"
            "      }\n"
            "    }\n"
            "    window.addEventListener('hashchange', route);\n"
            "    window.addEventListener('DOMContentLoaded', route);\n"
            "    window.addEventListener('load', route);\n\n"
            "    // PER-PAGE HANDLERS — wire forms, buttons, modals per the spec's interactions.\n"
            "    // Use location.hash = '#/page-id' or <a href='#/page-id'> for navigation.\n"
            "  </script>\n</body>\n</html>\n"
        )

    return (
        f"{structure_note}"
        "SPEC FROM BRIEF ANALYST (execute this literally):\n\n"
        f"{spec_json}\n\n"
        f"USER BRIEF (context only — the spec above takes precedence):\n{brief.strip() or '(no brief)'}\n\n"
        f"DISCOVERY ANSWERS:\n{disc}\n\n"
        f"{references_block}"
        "═══════════════════════════════════════════════════════════\n"
        "NAVIGATION WIRING — NON-NEGOTIABLE REQUIREMENTS\n"
        "═══════════════════════════════════════════════════════════\n\n"
        "1. Every page in the spec's navigation_graph MUST have a corresponding\n"
        "   <section data-page='page-id'> element in the HTML.\n"
        "2. The routes map MUST be populated: routes = { 'page-id': '/path', ... }\n"
        "   for EVERY page. An empty routes = {} means NO navigation works.\n"
        "3. Every nav link MUST use href='#/path' format (e.g. href='#/dashboard').\n"
        "   Do NOT use onclick with location.href. Do NOT use <a href='#page-id'>\n"
        "   without the slash — it will not trigger hashchange.\n"
        "4. The chrome (sidebar/topbar) MUST appear identically in EVERY\n"
        "   <section data-page> block. Only the active nav item class differs.\n"
        "5. Test mentally: clicking each nav item must show the correct page.\n\n"
        "═══════════════════════════════════════════════════════════\n"
        "TEMPLATE EXAMPLE (example.html — visual reference only)\n"
        "Extract: class system, chrome pattern, density, accent budget.\n"
        "Do NOT copy its brand tokens — those are in your system prompt.\n"
        "═══════════════════════════════════════════════════════════\n\n"
        f"{od['example_html']}\n\n"
        f"{seed_section}"
    )


def _user_message_craft_linter(prior_html: str, od: dict[str, Any]) -> str:
    """Task-specific input for the Craft Linter.

    DESIGN.md, craft rules, and SKILL.md hard rules are in the system prompt.
    User message carries: the HTML to lint + checklist reference (if any) +
    example.html as visual reference.
    """
    template_references = od.get("template_references") or {}

    # Inject the checklist reference if the template ships one — this is the
    # P0/P1/P2 quality gate the Craft Linter must enforce.
    checklist_block = ""
    if "checklist" in template_references:
        checklist_block = (
            "═══════════════════════════════════════════════════════════\n"
            "TEMPLATE CHECKLIST (references/checklist.md — enforce all P0 items)\n"
            "═══════════════════════════════════════════════════════════\n\n"
            f"{template_references['checklist']}\n\n"
        )

    return (
        "PRIOR ARTIFACT (patch in place — do not rewrite, only fix violations):\n\n"
        f"{prior_html}\n\n"
        f"{checklist_block}"
        "═══════════════════════════════════════════════════════════\n"
        "TEMPLATE EXAMPLE (visual reference for intended chrome/density)\n"
        "═══════════════════════════════════════════════════════════\n\n"
        f"{od['example_html']}\n"
    )


def _user_message_delivery_validator(prior_html: str) -> str:
    return (
        "PRIOR ARTIFACT (HTML from the Craft Linter — validate and finalise):\n\n"
        f"{prior_html}\n"
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_od_prototype_pipeline(
    template_id: str,
    design_system_id: str,
    brief: str,
    discovery: dict[str, Any] | None,
    custom_ds_body: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """4-stage pipeline streaming events in real time.

    Each Bedrock token is yielded as an ``agent_chunk`` event immediately —
    no buffering. This gives the frontend live spinner animation, accurate
    per-agent wall-clock durations, and visible thinking text while agents run.

    Pass ``custom_ds_body`` to use a user-supplied DESIGN.md instead of a
    built-in design system. When set, ``design_system_id`` is used only as a
    display label and the od_loader lookup is skipped entirely.

    Event shapes yielded:
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
        od = _load_od_context(template_id, design_system_id, custom_ds_body=custom_ds_body)
    except LookupError as exc:
        yield {"type": "pipeline_error", "error": str(exc)}
        return

    agents = get_pipeline_agents("prototype")
    if len(agents) != 4:
        yield {"type": "pipeline_error", "error": f"Expected 4 prototype agents, got {len(agents)}"}
        return

    analyst, composer, polisher, finalizer = agents

    yield {
        "type": "pipeline_start",
        "pipeline_type": "od_prototype",
        "agents": [
            {"id": a.id, "name": a.name, "role": a.role, "icon": a.icon, "index": i}
            for i, a in enumerate(agents)
        ],
    }

    # ── Agent 1: Brief Analyst ────────────────────────────────────────────
    from app.agents.base import TokenUsage
    from app.agents.base import estimate_cost_usd

    # Token usage tracking across all 4 agents
    pipeline_usage = TokenUsage()
    agent_token_usage: dict[str, TokenUsage] = {}

    yield {"type": "agent_start", "agent_id": analyst.id, "name": analyst.name,
           "role": analyst.role, "icon": analyst.icon, "index": 0}
    t0 = time.monotonic()
    spec_raw = ""
    a1_usage = TokenUsage()
    try:
        a1 = DeepAgent(
            system_prompt=_compose_system_prompt(analyst.system_prompt, od, include_craft=False),
            tools=[],
            max_tokens=analyst.max_tokens,
        )
        # Use astream_with_usage (direct LLM call, no ReAct loop) for text-only agents.
        # astream_events goes through the ReAct loop which is unnecessary here and
        # can cause issues with large HTML outputs on some providers.
        async for item in a1.astream_with_usage(_user_message_brief_analyst(brief, discovery, od)):
            if isinstance(item, TokenUsage):
                a1_usage = item
                break
            spec_raw += item
            yield {"type": "agent_chunk", "agent_id": analyst.id, "chunk": item}
    except Exception as exc:
        logger.exception("Brief Analyst failed")
        yield {"type": "agent_error", "agent_id": analyst.id, "error": str(exc)}
        return
    agent_token_usage[analyst.id] = a1_usage
    pipeline_usage = pipeline_usage + a1_usage
    yield {"type": "agent_complete", "agent_id": analyst.id,
           "output_length": len(spec_raw), "duration": time.monotonic() - t0,
           "input_tokens": a1_usage.input_tokens, "output_tokens": a1_usage.output_tokens}

    spec_json = _extract_spec(spec_raw)

    # ── Agent 2: SPA Composer ─────────────────────────────────────────────
    yield {"type": "agent_start", "agent_id": composer.id, "name": composer.name,
           "role": composer.role, "icon": composer.icon, "index": 1}
    t0 = time.monotonic()
    composer_raw = ""
    a2_usage = TokenUsage()
    try:
        a2 = DeepAgent(
            system_prompt=_compose_system_prompt(composer.system_prompt, od, include_craft=True),
            tools=[],
            max_tokens=composer.max_tokens,
        )
        async for item in a2.astream_with_usage(_user_message_spa_composer(spec_json, brief, discovery, od)):
            if isinstance(item, TokenUsage):
                a2_usage = item
                break
            composer_raw += item
            yield {"type": "agent_chunk", "agent_id": composer.id, "chunk": item}
    except Exception as exc:
        logger.exception("SPA Composer failed")
        yield {"type": "agent_error", "agent_id": composer.id, "error": str(exc)}
        return
    agent_token_usage[composer.id] = a2_usage
    pipeline_usage = pipeline_usage + a2_usage
    composer_html = _extract_artifact(composer_raw)
    logger.info("SPA Composer: raw=%d chars, extracted html=%d chars", len(composer_raw), len(composer_html))
    yield {"type": "artifact", "stage": "composer", "html": composer_html}
    yield {"type": "agent_complete", "agent_id": composer.id,
           "output_length": len(composer_raw), "duration": time.monotonic() - t0,
           "input_tokens": a2_usage.input_tokens, "output_tokens": a2_usage.output_tokens}

    # ── Agent 3: Craft Linter ─────────────────────────────────────────────
    yield {"type": "agent_start", "agent_id": polisher.id, "name": polisher.name,
           "role": polisher.role, "icon": polisher.icon, "index": 2}
    t0 = time.monotonic()
    linter_raw = ""
    a3_usage = TokenUsage()
    try:
        a3 = DeepAgent(
            system_prompt=_compose_system_prompt(polisher.system_prompt, od, include_craft=True),
            tools=[],
            max_tokens=polisher.max_tokens,
        )
        async for item in a3.astream_with_usage(_user_message_craft_linter(composer_html, od)):
            if isinstance(item, TokenUsage):
                a3_usage = item
                break
            linter_raw += item
            yield {"type": "agent_chunk", "agent_id": polisher.id, "chunk": item}
    except Exception as exc:
        logger.exception("Craft Linter failed")
        yield {"type": "agent_error", "agent_id": polisher.id, "error": str(exc)}
        return
    agent_token_usage[polisher.id] = a3_usage
    pipeline_usage = pipeline_usage + a3_usage
    linter_html = _extract_artifact(linter_raw)
    logger.info("Craft Linter: raw=%d chars, extracted html=%d chars", len(linter_raw), len(linter_html))
    yield {"type": "artifact", "stage": "linter", "html": linter_html}
    yield {"type": "agent_complete", "agent_id": polisher.id,
           "output_length": len(linter_raw), "duration": time.monotonic() - t0,
           "input_tokens": a3_usage.input_tokens, "output_tokens": a3_usage.output_tokens}

    # ── Agent 4: Delivery Validator ───────────────────────────────────────
    yield {"type": "agent_start", "agent_id": finalizer.id, "name": finalizer.name,
           "role": finalizer.role, "icon": finalizer.icon, "index": 3}
    t0 = time.monotonic()
    validator_raw = ""
    a4_usage = TokenUsage()
    try:
        a4 = DeepAgent(system_prompt=finalizer.system_prompt, tools=[], max_tokens=finalizer.max_tokens)
        async for item in a4.astream_with_usage(_user_message_delivery_validator(linter_html)):
            if isinstance(item, TokenUsage):
                a4_usage = item
                break
            validator_raw += item
            yield {"type": "agent_chunk", "agent_id": finalizer.id, "chunk": item}
    except Exception as exc:
        logger.exception("Delivery Validator failed")
        yield {"type": "agent_error", "agent_id": finalizer.id, "error": str(exc)}
        return
    agent_token_usage[finalizer.id] = a4_usage
    pipeline_usage = pipeline_usage + a4_usage
    final_html = _extract_artifact(validator_raw)
    logger.info("Delivery Validator: raw=%d chars, final html=%d chars", len(validator_raw), len(final_html))
    yield {"type": "artifact", "stage": "final", "html": final_html}
    yield {"type": "agent_complete", "agent_id": finalizer.id,
           "output_length": len(validator_raw), "duration": time.monotonic() - t0,
           "input_tokens": a4_usage.input_tokens, "output_tokens": a4_usage.output_tokens}

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
