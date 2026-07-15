"""agents/execution_engine/clarify_engine.py — Clarify_Engine (Human_Gate management).

Runs the Clarify_Agent, emits `questionnaire_ready`, awaits the user's answers
via an asyncio.Event from the ArtifactStore, merges answers into the
planning_context, and runs one clarification round by default (one-round-then-run).

Phase 2: full pause/resume implementation.

Mode:
  - brief-grounded  : standard pipelines (prototype, user_stories, od_ppt, ...)
                      where no Specify_Agent has produced a `spec` artifact
  - spec-grounded   : Spec_Kit_Agent workflows where a `spec` artifact exists

Rounds: the questionnaire is asked at most `max_rounds` times (default 1, threaded
from `clarify.rounds` in the manifest). After a subset answer or skip the run
PROCEEDs with no re-ask; on the terminal round with unresolved items,
`clarification_limit_reached` is emitted and the run proceeds with best available
context. `MAX_CLARIFICATION_ROUNDS` (=3) is the hard safety ceiling on `max_rounds`.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agents.artifact_store.store import get_artifact_store
from agents.artifacts.graph import ArtifactGraph
from agents.authz import ScopedStore
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_CLARIFICATION_ROUNDS = 3


def _classify_ambiguity(item: str, taxonomy: list[str]) -> str:
    """Classify an ambiguity item into one of the 11 taxonomy categories.

    Uses keyword matching as a lightweight heuristic. In a full implementation
    the Clarify_Agent LLM would perform this classification.
    """
    item_lower = item.lower()
    keyword_map = {
        "Functional Scope": ["feature", "scope", "functionality", "what", "capability"],
        "User Roles": ["user", "role", "persona", "actor", "who", "audience"],
        "Data Model": ["data", "entity", "field", "schema", "model", "database", "store"],
        "UX Flow": ["flow", "journey", "screen", "page", "navigation", "ux", "ui"],
        "Performance": ["performance", "latency", "speed", "throughput", "scale", "load"],
        "Security": ["security", "auth", "permission", "access", "encrypt", "compliance"],
        "Integration": ["integration", "api", "external", "third-party", "service", "connect"],
        "Edge Cases": ["edge", "error", "failure", "exception", "negative", "invalid"],
        "Terminology": ["term", "definition", "meaning", "concept", "glossary"],
        "Acceptance Criteria": ["criteria", "acceptance", "test", "verify", "measure"],
        "Constraints": ["constraint", "limit", "budget", "timeline", "technology", "stack"],
    }
    for category, keywords in keyword_map.items():
        if any(kw in item_lower for kw in keywords):
            return category
    return taxonomy[0]  # Default to Functional Scope


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_llm_json_array(raw: str) -> list | None:
    """Tolerantly extract + repair a JSON array from LLM output (KAN-82 / FIX-024).

    Haiku 4.5 frequently returns slightly-malformed JSON (markdown fences, trailing
    commas, missing commas between objects, smart quotes, truncation). This helper
    strips fences, extracts the outermost array, then progressively repairs and
    re-parses. It uses ``json.loads`` ONLY — never ``eval``/``exec``/``literal_eval``
    on model text (T-v1f-01). On unrecoverable input it returns ``None`` so the
    caller falls back to the static question library (the gate never crashes, INV-3).

    Returns a non-empty list on success, else ``None``.
    """
    if not raw or not isinstance(raw, str):
        return None

    text = raw.strip()

    # (a) Strip markdown code fences (```json ... ``` or ``` ... ```).
    if text.startswith("```"):
        # drop the opening fence line
        text = re.sub(r'^```[a-zA-Z0-9]*\s*\n?', '', text)
        # drop a trailing fence
        text = re.sub(r'\n?```\s*$', '', text).strip()

    # (b) Locate the array opener; if none, give up. A closing ']' may be
    #     missing (truncation) — the balanced-scan in (e) handles that case.
    lb = text.find('[')
    if lb == -1:
        return None
    match = re.search(r'\[[\s\S]*\]', text)
    span = match.group() if match else text[lb:]

    # (c) First attempt: parse the extracted span verbatim.
    if match:
        try:
            parsed = json.loads(span)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass

    # (d) Repair pass: normalize smart quotes, strip trailing commas, insert
    #     missing commas between adjacent objects, then re-parse.
    repaired = span
    for bad, good in (
        ("“", '"'), ("”", '"'),   # curly double quotes
        ("‘", "'"), ("’", "'"),   # curly single quotes
    ):
        repaired = repaired.replace(bad, good)
    repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)   # trailing commas
    repaired = re.sub(r'}\s*{', '},{', repaired)          # missing comma between objects
    if match:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass

    # (e) Truncation recovery: collect the complete top-level {...} objects by
    #     scanning brace depth over the array body, then rebuild a closed array.
    body = repaired
    # strip the leading '[' so we scan the object list
    obr = body.find('[')
    if obr != -1:
        body = body[obr + 1:]
    objects: list[str] = []
    depth = 0
    start = None
    in_string = False
    escape = False
    for idx, ch in enumerate(body):
        if in_string:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == '{':
            if depth == 0:
                start = idx
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(body[start:idx + 1])
                    start = None
    if objects:
        try:
            parsed = json.loads('[' + ','.join(objects) + ']')
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass

    # (f) Everything failed.
    return None


class ClarifyEngine:
    """Manages the Clarify_Agent Human_Gate: pause, present questions, resume."""

    def __init__(self) -> None:
        # The HITL half of the thin store stays live (resume events / questionnaire
        # responses) — only the clarifications PAYLOAD write is migrated to
        # artifact_refs in 05-06. owner_id/workspace_id are threaded in via run().
        self._store = get_artifact_store()
        # Set to the real owner principal in run() (AUTHZ-03 — never None once
        # run() has validated owner_id); None only before the gate runs.
        self._owner_id: str | None = None
        self._workspace_id: str | None = None
        # ISS-033: optional run-usage sink. When the engine sets it, the clarify
        # question-generation model call routes its tokens into the run's usage
        # accounting (via the shared cached_invoke). None → counting is a no-op.
        self._usage_sink = None

    async def run(
        self,
        pipeline_run_id: str,
        planning_context: dict[str, Any],
        websocket_send_fn: Callable[[dict], Awaitable[None]],
        clarify_agent=None,
        owner_id: str | None = None,
        workspace_id: str | None = None,
        max_rounds: int = 1,
    ) -> dict[str, Any]:
        """Run the clarification gate. Returns the (possibly updated) planning_context.

        Args:
            pipeline_run_id: The run identifier (used for resume event keying).
            planning_context: The Planning_Context produced by the Deep_Planner_Agent.
            websocket_send_fn: Async callable to emit WS events to the client.
            clarify_agent: Optional DeepAgent instance for the Clarify_Agent.
                           When None (Phase 2 default), questions are derived from
                           the planning_context's missing_information list.
            owner_id: REQUIRED real owner principal (user.id or anon:<session_id>).
                      The signature keeps a keyword default for back-compat, but a
                      falsy value raises ValueError at entry (AUTHZ-03) rather than
                      silently persisting an owner-None row. The clarifications
                      payload is owner-scoped so the reconnect read (websocket.py)
                      returns nothing for a non-owner (T-5-IDOR).
            workspace_id: The run's workspace id (paired with owner_id for the
                          artifact_refs row).
            max_rounds: Max clarification rounds (default 1 = one-round-then-run),
                        threaded from `compiled.clarify.rounds`. Clamped to at least
                        1 and at most MAX_CLARIFICATION_ROUNDS (the safety ceiling).

        Returns:
            The planning_context with merged clarification answers and an
            updated execution_gate (set to PROCEED once clarification completes).
        """
        # AUTHZ-03 / CR-02: a real owner principal is required. The clarifications
        # payload is owner-scoped (artifact_refs.owner_id is nullable=False and the
        # default-deny filter must always have a real owner); a falsy owner would
        # otherwise be caught only at the DB layer (IntegrityError) and silently
        # swallowed, dropping the clarifications row. Fail loud at the seam instead.
        if not owner_id:
            raise ValueError(
                "ClarifyEngine.run requires a real owner_id (AUTHZ-03)"
            )
        self._owner_id = owner_id
        self._workspace_id = workspace_id
        round_num = 0
        merged_context = dict(planning_context)

        # One-round-then-run by default; a workflow can opt into more rounds via
        # clarify.rounds, but never past the MAX_CLARIFICATION_ROUNDS safety ceiling.
        effective_rounds = max(1, min(max_rounds, MAX_CLARIFICATION_ROUNDS))

        while round_num < effective_rounds:
            round_num += 1

            questions = await self._generate_questions(
                merged_context, round_num, clarify_agent
            )

            if not questions:
                # No more ambiguities — proceed
                merged_context["execution_gate"] = "PROCEED"
                return merged_context

            # Pause: await the resume event (set when the user submits answers).
            # Clear the event BEFORE emitting questionnaire_ready so a fast
            # responder (or a reconnect that already has answers) cannot have
            # its set() wiped by a later clear(). No automatic timeout —
            # Human_Gate stays open indefinitely.
            event = await self._store.get_resume_event(pipeline_run_id)
            event.clear()

            # Emit questionnaire_ready and pause for the user
            await websocket_send_fn(
                {
                    "type": "questionnaire_ready",
                    "data": {
                        "pipeline_run_id": pipeline_run_id,
                        "questions": questions,
                        "round": round_num,
                        "timestamp": _now_iso(),
                    },
                }
            )

            await event.wait()

            responses = await self._store.get_questionnaire_responses(pipeline_run_id)
            responses = responses or []
            # ISS-027: did the user click "Skip all & run directly"? That submit
            # carries a force-proceed flag the FE sets explicitly; here it means
            # "stop clarifying and run now", regardless of how many ambiguities
            # remain. Ordinary answer submissions leave it False (byte-identical).
            force_proceed = await self._store.get_questionnaire_force_proceed(
                pipeline_run_id
            )

            # Persist Q&A pairs and merge answers into the planning_context
            await self._persist_qa(pipeline_run_id, questions, responses, round_num)
            merged_context = self._merge_answers(merged_context, questions, responses)

            await websocket_send_fn(
                {
                    "type": "questionnaire_complete",
                    "data": {
                        "pipeline_run_id": pipeline_run_id,
                        "responses": responses,
                        "updated_gate": "PROCEED",
                        "timestamp": _now_iso(),
                    },
                }
            )

            # ISS-027 force-proceed: the user explicitly asked to skip remaining
            # clarification, so bypass the rest of the loop (no re-ask) and run
            # with the best-available context. This is the real behavior the
            # "Skip all & run directly" label promises; before, an empty submit
            # left missing_information unchanged and the loop re-asked up to 3×.
            if force_proceed:
                merged_context["execution_gate"] = "PROCEED"
                return merged_context

            # Re-evaluate: if no more missing information, proceed
            if not merged_context.get("missing_information"):
                merged_context["execution_gate"] = "PROCEED"
                return merged_context

        # Max rounds reached — proceed with best available context
        await websocket_send_fn(
            {
                "type": "clarification_limit_reached",
                "data": {
                    "pipeline_run_id": pipeline_run_id,
                    "unresolved_items": merged_context.get("missing_information", []),
                    "timestamp": _now_iso(),
                },
            }
        )
        merged_context["execution_gate"] = "PROCEED"
        return merged_context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_questions_via_llm(
        self,
        planning_context: dict[str, Any],
        round_num: int,
        pipeline_type: str,
        is_no_template: bool,
    ) -> list[dict] | None:
        """Generate Spec Kit-style content-aware clarification questions via LLM.

        Follows the GitHub Spec Kit clarify.md approach:
        - Reads the actual brief and coverage_map from planning_context
        - Generates targeted questions only for genuinely unresolved areas
        - Supports mixed answer types: single_choice, multi_select, short_text, hybrid
        - Always provides a recommended answer with brief reasoning
        - Deduplicates against already-answered topics
        - Stops early if no critical gaps remain
        """
        user_request = planning_context.get("user_request", "")
        inferred_intent = planning_context.get("inferred_intent", "")
        missing = planning_context.get("missing_information", [])
        topic = planning_context.get("topic") or ""
        domain_insights = planning_context.get("domain_insights") or []
        coverage_map = planning_context.get("coverage_map") or {}
        user_request_summary = planning_context.get("user_request_summary", "")
        # Already-answered topics (from previous rounds) — never re-ask these
        clarified_topics = planning_context.get("clarified_topics") or []

        if not user_request and not inferred_intent:
            return None

        brief_sample = user_request[:settings.BRIEF_MAX_CHARS] if user_request else inferred_intent[:2000]
        topic_label = topic or (user_request_summary or inferred_intent or "")[:60]

        # Pipeline-specific question priorities
        pipeline_guidance_map = {
            "prototype": (
                "This is a prototype pipeline. Priority questions:\n"
                "1. UI/Layout: sidebar navigation vs topbar vs cards vs single-page?\n"
                "2. Visual style: minimal SaaS, consumer/marketing, data dashboard, dark admin?\n"
                "3. Key pages/screens: which ones are essential for this product?\n"
                "4. Primary interactions: read-only browsing, form inputs, data tables, modals?\n"
                "5. Target device: desktop-first, mobile-first, responsive?\n"
                "6. Colour/brand: light neutral, dark mode, brand colour, monochrome?"
            ),
            "od_prototype": (
                "This is a prototype pipeline. Priority questions:\n"
                "1. UI/Layout: sidebar navigation vs topbar vs cards vs single-page?\n"
                "2. Visual style: minimal SaaS, consumer/marketing, data dashboard, dark admin?\n"
                "3. Key pages/screens: which ones are essential for this product?\n"
                "4. Primary interactions: read-only browsing, form inputs, data tables, modals?\n"
                "5. Target device: desktop-first, mobile-first, responsive?\n"
                "6. Colour/brand: light neutral, dark mode, brand colour, monochrome?"
            ),
            "user_stories": (
                "Priority: user roles/personas, key journeys, business rules, scope (MVP vs full), "
                "acceptance criteria style, compliance requirements."
            ),
            "od_ppt": (
                "Priority: presentation purpose (inform/persuade/report), target audience, "
                "content depth, number of slides, visual style, key sections/chapters."
            ),
            "ppt": (
                "Priority: presentation purpose, target audience, content depth, "
                "slide count, visual style, key sections."
            ),
            "app_builder": (
                "Priority: tech stack, core features, data model, integrations needed, "
                "security/auth requirements, deployment target, performance requirements."
            ),
        }
        pipeline_guidance = pipeline_guidance_map.get(
            pipeline_type,
            "Focus on scope, audience, objectives, key deliverables, and output format."
        )

        no_template_extra = ""
        if is_no_template:
            no_template_extra = """
CRITICAL — BLANK CANVAS MODE:
The user chose NOT to use a pre-made visual template. You MUST generate at least 4 UI design questions covering:
1. Layout architecture (sidebar/topbar/cards/single-page/split-pane)
2. Visual style personality (minimal SaaS, consumer/spacious, data-heavy, dark/admin)
3. Navigation pattern (persistent sidebar, hamburger, tabs, breadcrumb)
4. Colour mood (light neutral, dark mode, colourful brand, monochrome)
These 4 questions are MANDATORY regardless of what else is in the brief."""

        # Build coverage context for the prompt
        coverage_summary = ""
        if coverage_map:
            unclear = [k for k, v in coverage_map.items() if v in ("partial", "missing")]
            clear = [k for k, v in coverage_map.items() if v == "clear"]
            coverage_summary = f"\nCoverage scan: CLEAR={clear}, NEEDS_CLARIFICATION={unclear}"

        already_answered = ""
        if clarified_topics:
            already_answered = f"\nALREADY ANSWERED in previous rounds — do NOT ask again: {clarified_topics}"

        prompt = f"""You are a product clarification expert following the GitHub Spec Kit clarify.md approach.
Analyze the user's brief and generate targeted, content-aware clarification questions.

## Pipeline: {pipeline_type}
## Topic: {topic_label}

## User Brief
{brief_sample}

## Planner analysis
- Intent: {inferred_intent}
- Missing: {json.dumps(missing)}
- Domain insights: {json.dumps(domain_insights)}
{coverage_summary}
{already_answered}

## Question guidelines (Spec Kit style)
{pipeline_guidance}
{no_template_extra}

## Rules
1. Generate {4 if is_no_template else 2}-{7 if is_no_template else 5} questions ONLY for genuinely unclear/missing areas
2. Each question must be SPECIFIC to this brief — reference the actual domain/topic
3. Do NOT ask about things already stated in the brief
4. Do NOT repeat questions from already-answered topics
5. Choose the most appropriate answer type per question:
   - "single_choice": exactly one option (layout type, visual style, audience)
   - "multi_select": multiple may apply (features needed, interactions to demo, compliance areas)
   - "short_text": free-form answer better than fixed options (specific tech name, team size, deadline)
   - "hybrid": MCQ suggestions + free-text override (topic, domain, specific requirement)
6. Always provide a "recommended_answer" — the best default based on context + brief practices
7. Add "recommended_reasoning": 1-2 sentences WHY this is the best default
8. Options should be specific and relevant — NOT generic "Option A / Option B"
9. For single_choice/multi_select: 3-6 options max, all domain-relevant
10. Stop early: if fewer than 2 genuine gaps exist, generate only those questions (don't pad)

Return ONLY a JSON array:
[
  {{
    "question_text": "Specific question referencing the actual content/domain?",
    "answer_type": "single_choice|multi_select|short_text|hybrid",
    "options": ["Specific Option A", "Specific Option B", "Specific Option C"],
    "recommended_answer": "The specific option or text you recommend",
    "recommended_reasoning": "Why this is the best default for this brief",
    "ambiguity_category": "UX Flow",
    "impact_level": "high"
  }}
]

For short_text questions, options can be [] (empty — user types freely).
For hybrid questions, include 3-5 MCQ suggestions plus the free-text field will be shown automatically.

Valid ambiguity_category values: Functional Scope, User Roles, Data Model, UX Flow, Performance, Security, Integration, Edge Cases, Terminology, Acceptance Criteria, Constraints
Valid impact_level: high, medium

OUTPUT FORMAT (strict): return ONLY the raw JSON array. No markdown code fences, no
prose before or after. Your response MUST start with `[` and end with `]`."""

        try:
            from langchain_core.messages import HumanMessage

            from app.agents.cached_invoke import cached_invoke

            # ISS-033: route the direct build_model().ainvoke through the ONE shared
            # cached-invoke helper — Bedrock-cache-eligible + tokens counted. The
            # message + parse are unchanged (INV-3: same model text → same parsed
            # output); only the invoke path changes. build_model(max_tokens=1500) is
            # done inside the helper (identical to before), so a provider-misconfig
            # still degrades to the static fallback via this try/except.
            raw, _usage = await cached_invoke(
                [HumanMessage(content=prompt)],
                max_tokens=1500,
                usage_sink=self._usage_sink,
            )

            # Tolerant extract + repair (fences / trailing+missing commas / smart
            # quotes / truncation), json.loads-only. None -> static fallback (INV-3).
            items = _parse_llm_json_array(raw)
            if not items:
                logger.warning("ClarifyEngine LLM: no parseable JSON array in response")
                return None

            questions = []
            for i, item in enumerate(items):
                if not isinstance(item, dict) or not item.get("question_text"):
                    continue
                answer_type = item.get("answer_type", "single_choice")
                options = item.get("options") or []
                recommended = item.get("recommended_answer", options[-1] if options else "")
                reasoning = item.get("recommended_reasoning", "")
                # Embed reasoning into recommended_answer for display
                recommended_display = f"{recommended} — {reasoning}" if reasoning else recommended

                questions.append({
                    "question_id": f"r{round_num}_q{i + 1}",
                    "question_text": item["question_text"],
                    "impact_level": item.get("impact_level", "high" if i < 2 else "medium"),
                    "answer_type": answer_type,
                    "options": options,
                    "recommended_answer": recommended,
                    "recommended_reasoning": reasoning,
                    "recommended_display": recommended_display,
                    "ambiguity_category": item.get("ambiguity_category", "Functional Scope"),
                })

            logger.info(
                "ClarifyEngine LLM: %d questions for pipeline=%s no_template=%s round=%d",
                len(questions), pipeline_type, is_no_template, round_num,
            )
            return questions if questions else None

        except Exception as exc:
            logger.warning("ClarifyEngine LLM generation failed: %s — falling back to static library", exc)
            return None



    async def _generate_questions(
        self,
        planning_context: dict[str, Any],
        round_num: int,
        clarify_agent,
    ) -> list[dict]:
        """Generate Spec Kit-style content-aware clarification questions.

        Primary path: LLM call that reads the brief, coverage_map, and
        domain insights to generate specific, targeted questions with mixed
        answer types (single_choice, multi_select, short_text, hybrid) and
        recommended answers with reasoning.
        Fallback: static library when LLM call fails.
        """
        missing = planning_context.get("missing_information", [])
        if not missing:
            return []

        pipeline_type = planning_context.get("pipeline_type", "custom")
        is_no_template = bool(planning_context.get("no_template_mode", False))

        # ── Primary path: Spec Kit-style LLM question generation ──────────
        llm_questions = await self._generate_questions_via_llm(
            planning_context, round_num, pipeline_type, is_no_template
        )
        if llm_questions:
            return llm_questions

        # ── Fallback: static library (when LLM call fails) ─────────────────
        logger.info("ClarifyEngine: falling back to static library for pipeline=%s", pipeline_type)

        inferred_intent = planning_context.get("inferred_intent", "")
        topic = planning_context.get("topic") or ""
        user_request_summary = planning_context.get("user_request_summary", "")
        content_hint = (user_request_summary or inferred_intent or "").strip()
        if len(content_hint) > 120:
            content_hint = content_hint[:117] + "..."

        TOPIC_BY_PIPELINE: dict[str, tuple[str, list[str]]] = {
            "od_ppt": (
                "What is the main topic or subject of this presentation?",
                ["Product / service overview", "Market research & competitive analysis", "Business strategy & roadmap", "Technical deep-dive", "Sales pitch / proposal", "Training & education"],
            ),
            "ppt": (
                "What is the main topic or subject of this presentation?",
                ["Product / service overview", "Market research & competitive analysis", "Business strategy & roadmap", "Technical deep-dive", "Sales pitch / proposal", "Training & education"],
            ),
            "user_stories": (
                "What product or feature are you building user stories for?",
                ["Web application / SaaS product", "Mobile app (iOS / Android)", "Internal business tool / dashboard", "API / backend service", "E-commerce platform", "Data / analytics platform"],
            ),
            "od_prototype": (
                "What type of product or interface are you prototyping?",
                ["Web app / dashboard", "Mobile app", "Landing page / marketing site", "Admin panel / back-office", "E-commerce storefront", "Data visualization / analytics"],
            ),
            "prototype": (
                "What type of product or interface are you prototyping?",
                ["Web app / dashboard", "Mobile app", "Landing page / marketing site", "Admin panel / back-office", "E-commerce storefront", "Data visualization / analytics"],
            ),
            "app_builder": (
                "What type of application are you building?",
                ["SaaS web application", "Mobile app (React Native / Flutter)", "Internal enterprise tool", "E-commerce platform", "API / microservice", "Data pipeline / analytics platform"],
            ),
        }

        STYLE_BY_PIPELINE: dict[str, tuple[str, list[str]]] = {
            "od_prototype": (
                "What visual style and UI type should the prototype follow?",
                [
                    "Clean / minimal SaaS web app (dense, functional, blue-on-white)",
                    "Consumer / marketing — spacious, visual, hero sections",
                    "Mobile-first — card-based, touch-friendly, compact",
                    "Data-heavy dashboard — tables, charts, sidebar navigation",
                    "Dark-mode admin panel — dark background, accent colours",
                    "No preference — let the AI decide based on the brief",
                ],
            ),
            "prototype": (
                "What visual style and UI type should the prototype follow?",
                [
                    "Clean / minimal SaaS web app (dense, functional, blue-on-white)",
                    "Consumer / marketing — spacious, visual, hero sections",
                    "Mobile-first — card-based, touch-friendly, compact",
                    "Data-heavy dashboard — tables, charts, sidebar navigation",
                    "Dark-mode admin panel — dark background, accent colours",
                    "No preference — let the AI decide based on the brief",
                ],
            ),
        }

        QUESTION_LIBRARY: dict[str, tuple[str, list[str]]] = {
            "topic": TOPIC_BY_PIPELINE.get(pipeline_type, (
                "What is the main topic or subject of this?",
                ["Product / service feature", "Business process / workflow", "Technical system / architecture", "Market / competitive analysis", "Internal tool / dashboard", "Customer-facing product"],
            )),
            "subject": TOPIC_BY_PIPELINE.get(pipeline_type, (
                "What is the main topic or subject of this?",
                ["Product / service feature", "Business process / workflow", "Technical system / architecture", "Market / competitive analysis", "Internal tool / dashboard", "Customer-facing product"],
            )),
            "target_audience": (
                "Who is the primary audience for this?",
                ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
            ),
            "audience": (
                "Who is the primary audience for this?",
                ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
            ),
            "style": STYLE_BY_PIPELINE.get(pipeline_type, (
                "What tone and style should be used?",
                ["Professional & formal", "Casual & conversational", "Data-driven & analytical", "Creative & visual", "Concise & minimal"],
            )),
            "ui_style": STYLE_BY_PIPELINE.get(pipeline_type, (
                "What visual style and UI type should this follow?",
                ["Clean / minimal SaaS web app", "Consumer / marketing — spacious, visual", "Data-heavy dashboard — tables, charts", "Dark-mode admin panel", "No preference"],
            )),
            "scope": (
                "What is the scope of this project?",
                ["MVP / proof of concept", "Full production feature", "Internal tool only", "Customer-facing product", "Research & exploration"],
            ),
            "priority": (
                "What should be prioritized in this output?",
                ["Speed of delivery", "Quality & completeness", "Cost efficiency", "Scalability & future-proofing", "User experience"],
            ),
            "key_screens": (
                "What are the key screens or pages the prototype must include?",
                ["Home / landing page", "Dashboard / main workspace", "Onboarding / sign-up flow", "Detail / item view", "Settings / profile page"],
            ),
            "interactions": (
                "What types of interactions should the prototype demonstrate?",
                ["Click-through navigation only", "Form inputs and validation", "Data tables with filtering/sorting", "Modals, drawers, and overlays", "Full interactive flows with state changes"],
            ),
            "personas": (
                "What user roles or personas will use this product?",
                ["Registered end users", "Admins / back-office staff", "Guest / anonymous users", "API consumers / developers", "Multiple roles with different permissions"],
            ),
            "user_journeys": (
                "What are the main user journeys or workflows to cover?",
                ["Onboarding / sign-up flow", "Core transactional flow", "Account management / settings", "Search, browse, and filter", "Reporting / analytics / export"],
            ),
            "business_rules": (
                "Are there important business rules, validations, or constraints?",
                ["Approval workflows or authorisation checks", "Data validation rules", "Pricing / discount / calculation logic", "Status / state-machine transitions", "No specific business rules"],
            ),
            "technology": (
                "What technology stack should be used?",
                ["React / Next.js (web)", "React Native / Flutter (mobile)", "Node.js / Python (backend)", "Cloud-native (AWS / Azure / GCP)", "No preference"],
            ),
            "target_audience": (
                "Who is the primary audience for this?",
                ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
            ),
            "tone_and_style": (
                "What tone and style should be used?",
                ["Professional & formal", "Casual & conversational", "Data-driven & analytical", "Creative & visual", "Concise & minimal"],
            ),
            "key_objectives": (
                "What is the primary goal or objective?",
                ["Inform & educate", "Persuade & sell", "Report results & metrics", "Propose a solution", "Compare options & recommend"],
            ),
            "slide_count": (
                "How many slides should the presentation have?",
                ["5–8 slides (concise)", "10–12 slides (standard)", "15–20 slides (detailed)", "20+ slides (comprehensive)", "No preference"],
            ),
            "content_depth": (
                "How detailed should the content be?",
                ["High-level summary only", "Moderate detail with supporting points", "Deep-dive with data and evidence", "Executive brief (one key message per slide)", "No preference"],
            ),
            "data_availability": (
                "Do you have data, charts, or statistics to include?",
                ["Yes — I have specific data/numbers to include", "Use realistic representative data", "Qualitative insights only", "Both qualitative and quantitative", "No preference"],
            ),
            "visual_style": (
                "What visual style should follow?",
                ["Clean and minimal (lots of white space)", "Data-rich (charts, tables, graphs)", "Story-driven (narrative with visuals)", "Brand-aligned", "No preference"],
            ),
            "key_sections": (
                "What sections should the output include?",
                ["Executive summary + key findings", "Problem / opportunity + solution", "Data analysis + recommendations", "Roadmap or timeline", "Standard structure — leave it to the AI"],
            ),
            "data_model": (
                "What key data entities does the application need?",
                ["Users / accounts and profiles", "Products / items / catalogue", "Orders / transactions / payments", "Content / documents / media", "Custom domain-specific entities"],
            ),
            "integrations": (
                "What external integrations are needed?",
                ["None / standalone application", "Payment gateway (Stripe, PayPal)", "Authentication provider (Auth0, Google)", "Email / SMS / notification service", "Multiple integrations"],
            ),
            "compliance_security": (
                "What security or compliance requirements apply?",
                ["Standard authentication (email/password)", "SSO / OAuth / enterprise identity", "GDPR / data-privacy compliance", "Industry regulation (HIPAA, PCI-DSS)", "No specific requirements"],
            ),
        }

        _TAXONOMY = [
            "Functional Scope", "User Roles", "Data Model", "UX Flow",
            "Performance", "Security", "Integration", "Edge Cases",
            "Terminology", "Acceptance Criteria", "Constraints",
        ]

        capped = missing[:5]
        questions: list[dict] = []

        for i, item in enumerate(capped):
            item_lower = item.lower().replace(" ", "_").replace("-", "_")

            matched_key = None
            for key in QUESTION_LIBRARY:
                if key in item_lower or item_lower in key:
                    matched_key = key
                    break
            if not matched_key:
                item_words = set(item_lower.replace("_", " ").replace("-", " ").split())
                for key in QUESTION_LIBRARY:
                    key_words = set(key.replace("_", " ").split())
                    if item_words & key_words:
                        matched_key = key
                        break

            if matched_key:
                base_question, options = QUESTION_LIBRARY[matched_key]
            else:
                readable = item.replace("_", " ").replace("-", " ").title()
                base_question = f"How would you describe the {readable}?"
                options = [
                    f"Standard {readable}",
                    f"Minimal {readable}",
                    f"Comprehensive {readable}",
                    "Custom / specific requirements",
                    "No preference",
                ]

            question_text = base_question
            if content_hint and matched_key not in ("topic", "subject"):
                subject_label = topic or content_hint
                if subject_label and len(subject_label) < 80:
                    question_text = f"{base_question} (for: {subject_label})"

            category = _classify_ambiguity(item, _TAXONOMY)
            is_topic = matched_key in ("topic", "subject") if matched_key else False
            questions.append({
                "question_id": f"r{round_num}_q{i + 1}",
                "question_text": question_text,
                "impact_level": "high" if i < 2 else "medium",
                "answer_type": "hybrid" if is_topic else "single_choice",
                "options": options,
                "recommended_answer": options[-1],
                "recommended_reasoning": "",
                "recommended_display": options[-1],
                "ambiguity_category": category,
            })
        return questions

    async def _persist_qa(
        self,
        pipeline_run_id: str,
        questions: list[dict],
        responses: list[dict],
        round_num: int,
    ) -> None:
        """Persist each Q&A pair as a typed ``clarifications`` ArtifactRef."""
        answer_map = {r.get("question_id"): r.get("answer") for r in responses}
        qa_pairs = []
        for q in questions:
            qa_pairs.append({
                "question_id": q["question_id"],
                "question_text": q["question_text"],
                "impact_level": q.get("impact_level", "medium"),
                "answer": answer_map.get(q["question_id"]),
                "round": round_num,
            })
        graph = ArtifactGraph()
        ref = graph.write_ref(
            run_id=pipeline_run_id,
            owner_id=self._owner_id,
            workspace_id=self._workspace_id or "",
            kind="clarifications",
            producer_step=f"clarify_round_{round_num}",
            producer_agent="clarify-agent",
            task_id=None,
            content=json.dumps(qa_pairs),
            location="artifact_refs/clarifications",
            visibility="workspace",
        )
        store = ScopedStore(owner_id=self._owner_id, workspace_id=self._workspace_id)
        from sqlalchemy.exc import SQLAlchemyError
        try:
            await store.write_ref(ref, force_db_version=True)
        except SQLAlchemyError as exc:
            logger.warning(
                "clarifications persist failed for run %s round %d (%s) — degraded",
                pipeline_run_id, round_num, exc,
            )

    def _merge_answers(
        self,
        planning_context: dict[str, Any],
        questions: list[dict],
        responses: list[dict],
    ) -> dict[str, Any]:
        """Merge answers into planning_context, track clarified topics for deduplication."""
        merged = dict(planning_context)
        answer_map = {r.get("question_id"): r.get("answer") for r in responses}

        explicit = list(merged.get("explicit_constraints", []))
        clarified_topics = list(merged.get("clarified_topics") or [])

        for q in questions:
            ans = answer_map.get(q["question_id"])
            if ans:
                explicit.append(f"{q['question_text']} → {ans}")
                # Track the category/question as answered for deduplication
                cat = q.get("ambiguity_category", "")
                if cat and cat not in clarified_topics:
                    clarified_topics.append(cat)

        merged["explicit_constraints"] = explicit
        merged["clarified_topics"] = clarified_topics

        answered_count = sum(1 for q in questions if answer_map.get(q["question_id"]))
        remaining = list(merged.get("missing_information", []))
        answered_to_remove = answered_count
        while answered_to_remove > 0 and remaining:
            remaining.pop(0)
            answered_to_remove -= 1
        merged["missing_information"] = remaining

        return merged
