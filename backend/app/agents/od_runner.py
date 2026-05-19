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

from app.agents.base import BaseAgent
from app.agents.registry import get_pipeline_agents
from app.services import od_loader

logger = logging.getLogger("app.agents.od_runner")


_SPEC_RE = re.compile(r"<spec>\s*(.*?)\s*</spec>", re.DOTALL)
_ARTIFACT_RE = re.compile(r"<artifact[^>]*>\s*(.*?)\s*</artifact>", re.DOTALL)


def _extract_spec(raw: str) -> str:
    m = _SPEC_RE.search(raw)
    return (m.group(1) if m else raw).strip()


def _extract_artifact(raw: str) -> str:
    m = _ARTIFACT_RE.search(raw)
    return (m.group(1) if m else raw).strip()


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


def _load_od_context(template_id: str, design_system_id: str) -> dict[str, Any]:
    template = od_loader.get_template(template_id)
    if template is None:
        raise LookupError(f"Template '{template_id}' not found")
    ds = od_loader.get_design_system(design_system_id)
    if ds is None:
        raise LookupError(f"Design system '{design_system_id}' not found")

    example_path = od_loader.get_template_preview_path(template_id)
    example_html = ""
    if example_path is not None:
        try:
            example_html = example_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read example.html for %s: %s", template_id, exc)

    # Template's own seed (assets/template.html) — present in 11 of 43 templates.
    # When present, the SKILL.md workflow instructs "Copy assets/template.html as
    # your starting point." We inject it so the Composer uses the right scaffolding
    # instead of the generic Flowin SPA seed.
    template_seed = od_loader.get_template_seed(template_id)

    craft_required = template.get("craft_required") or []
    craft_rules = od_loader.get_craft_rules(craft_required)
    craft_block = (
        "\n\n---\n\n".join(f"## craft/{n}\n\n{b}" for n, b in craft_rules.items())
        if craft_rules
        else "(no craft rules required by this template)"
    )

    # Single-screen flag: mobile and certain design-scenario templates produce
    # one screen, not a multi-page SPA. The Flowin SPA seed (hash router +
    # data-page sections) must not be applied to these.
    platform = template.get("platform") or ""
    is_single_screen = platform == "mobile" or not template.get("has_own_seed") is False

    # More precise: single-screen if platform is mobile OR if the template's
    # SKILL.md workflow describes one self-contained screen (no navigation graph).
    # We approximate: templates with their own seed that are NOT dashboard-type
    # are typically single-screen. Dashboard/kanban templates without a seed are
    # multi-page candidates.
    is_single_screen = (
        platform == "mobile"
        or (template_seed is not None and platform != "desktop")
    )

    return {
        "template_id": template_id,
        "template_body": template["body"],
        "ds_id": design_system_id,
        "ds_body": ds["body"],
        "example_html": example_html or "(no example.html available)",
        "template_seed": template_seed,  # None if template doesn't ship a seed
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
    The user message carries only: spec, brief, example.html (visual ref), and seed.
    """
    disc = _format_discovery(discovery) or "(none provided)"
    template_seed = od.get("template_seed")
    is_single_screen = od.get("is_single_screen", False)

    if is_single_screen:
        structure_note = (
            "⚠️  SINGLE-SCREEN: This template produces ONE self-contained screen. "
            "Do NOT add multi-page hash routing or data-page sections. "
            "Follow the SKILL.md Workflow steps exactly.\n\n"
        )
    else:
        structure_note = ""

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
            "  <script>\n"
            "    const store=(()=>{let s={};const l=new Set();return{get:k=>k?s[k]:s,set:p=>{s={...s,...p};l.forEach(f=>f(s));},on:(_,f)=>{l.add(f);return()=>l.delete(f);}};})();\n"
            "    const routes={};\n"
            "    function route(){const h=location.hash||'#/';const p=h.slice(1);let id=null,params={};for(const[i,pat]of Object.entries(routes)){const re=new RegExp('^'+pat.replace(/:[a-z]+/gi,'([^/]+)')+'$');const m=p.match(re);if(m){id=i;(pat.match(/:[a-z]+/gi)||[]).forEach((k,j)=>{params[k.slice(1)]=m[j+1]});break;}}document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('is-active',el.dataset.page===id));store.set({_route:{id,params}});}\n"
            "    window.addEventListener('hashchange',route);window.addEventListener('DOMContentLoaded',route);\n"
            "  </script>\n</body>\n</html>\n"
        )

    return (
        f"{structure_note}"
        "SPEC FROM BRIEF ANALYST (execute this literally):\n\n"
        f"{spec_json}\n\n"
        f"USER BRIEF (context only — the spec above takes precedence):\n{brief.strip() or '(no brief)'}\n\n"
        f"DISCOVERY ANSWERS:\n{disc}\n\n"
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
    User message carries: the HTML to lint + example.html as visual reference.
    """
    return (
        "PRIOR ARTIFACT (patch in place — do not rewrite, only fix violations):\n\n"
        f"{prior_html}\n\n"
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
) -> AsyncGenerator[dict[str, Any], None]:
    """4-stage pipeline streaming events in real time.

    Each Bedrock token is yielded as an ``agent_chunk`` event immediately —
    no buffering. This gives the frontend live spinner animation, accurate
    per-agent wall-clock durations, and visible thinking text while agents run.

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
        od = _load_od_context(template_id, design_system_id)
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
    # System prompt: DESIGN.md + SKILL.md + base role (no craft — analyst only
    # needs to understand the template's shape and DS to produce the right spec)
    yield {"type": "agent_start", "agent_id": analyst.id, "name": analyst.name,
           "role": analyst.role, "icon": analyst.icon, "index": 0}
    t0 = time.monotonic()
    spec_raw = ""
    try:
        a1 = BaseAgent(
            system_prompt=_compose_system_prompt(analyst.system_prompt, od, include_craft=False),
            max_tokens=analyst.max_tokens,
        )
        async for chunk in a1.astream(_user_message_brief_analyst(brief, discovery, od)):
            spec_raw += chunk
            yield {"type": "agent_chunk", "agent_id": analyst.id, "chunk": chunk}
    except Exception as exc:
        logger.exception("Brief Analyst failed")
        yield {"type": "agent_error", "agent_id": analyst.id, "error": str(exc)}
        return
    yield {"type": "agent_complete", "agent_id": analyst.id,
           "output_size": len(spec_raw), "duration": time.monotonic() - t0}

    spec_json = _extract_spec(spec_raw)

    # ── Agent 2: SPA Composer ─────────────────────────────────────────────
    # System prompt: DESIGN.md + craft + SKILL.md + base role — matching exactly
    # how OpenDesign's daemon composes the system prompt before invoking the agent.
    yield {"type": "agent_start", "agent_id": composer.id, "name": composer.name,
           "role": composer.role, "icon": composer.icon, "index": 1}
    t0 = time.monotonic()
    composer_raw = ""
    try:
        a2 = BaseAgent(
            system_prompt=_compose_system_prompt(composer.system_prompt, od, include_craft=True),
            max_tokens=composer.max_tokens,
        )
        async for chunk in a2.astream(_user_message_spa_composer(spec_json, brief, discovery, od)):
            composer_raw += chunk
            yield {"type": "agent_chunk", "agent_id": composer.id, "chunk": chunk}
    except Exception as exc:
        logger.exception("SPA Composer failed")
        yield {"type": "agent_error", "agent_id": composer.id, "error": str(exc)}
        return
    composer_html = _extract_artifact(composer_raw)
    yield {"type": "artifact", "stage": "composer", "html": composer_html}
    yield {"type": "agent_complete", "agent_id": composer.id,
           "output_size": len(composer_raw), "duration": time.monotonic() - t0}

    # ── Agent 3: Craft Linter ─────────────────────────────────────────────
    # System prompt: DESIGN.md + craft + SKILL.md + base role — same composition
    # so the linter sees the same constraints as the composer did.
    yield {"type": "agent_start", "agent_id": polisher.id, "name": polisher.name,
           "role": polisher.role, "icon": polisher.icon, "index": 2}
    t0 = time.monotonic()
    linter_raw = ""
    try:
        a3 = BaseAgent(
            system_prompt=_compose_system_prompt(polisher.system_prompt, od, include_craft=True),
            max_tokens=polisher.max_tokens,
        )
        async for chunk in a3.astream(_user_message_craft_linter(composer_html, od)):
            linter_raw += chunk
            yield {"type": "agent_chunk", "agent_id": polisher.id, "chunk": chunk}
    except Exception as exc:
        logger.exception("Craft Linter failed")
        yield {"type": "agent_error", "agent_id": polisher.id, "error": str(exc)}
        return
    linter_html = _extract_artifact(linter_raw)
    yield {"type": "artifact", "stage": "linter", "html": linter_html}
    yield {"type": "agent_complete", "agent_id": polisher.id,
           "output_size": len(linter_raw), "duration": time.monotonic() - t0}

    # ── Agent 4: Delivery Validator ───────────────────────────────────────
    yield {"type": "agent_start", "agent_id": finalizer.id, "name": finalizer.name,
           "role": finalizer.role, "icon": finalizer.icon, "index": 3}
    t0 = time.monotonic()
    validator_raw = ""
    try:
        a4 = BaseAgent(system_prompt=finalizer.system_prompt, max_tokens=finalizer.max_tokens)
        async for chunk in a4.astream(_user_message_delivery_validator(linter_html)):
            validator_raw += chunk
            yield {"type": "agent_chunk", "agent_id": finalizer.id, "chunk": chunk}
    except Exception as exc:
        logger.exception("Delivery Validator failed")
        yield {"type": "agent_error", "agent_id": finalizer.id, "error": str(exc)}
        return
    final_html = _extract_artifact(validator_raw)
    yield {"type": "artifact", "stage": "final", "html": final_html}
    yield {"type": "agent_complete", "agent_id": finalizer.id,
           "output_size": len(validator_raw), "duration": time.monotonic() - t0}

    yield {
        "type": "pipeline_complete",
        "final_html": final_html,
        "duration": time.monotonic() - pipeline_start,
    }
