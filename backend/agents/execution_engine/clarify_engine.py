"""agents/execution_engine/clarify_engine.py — Clarify_Engine (Human_Gate management).

Runs the Clarify_Agent, emits `questionnaire_ready`, awaits the user's answers
via an asyncio.Event from the ArtifactStore, merges answers into the
planning_context, and supports up to 3 clarification rounds.

Phase 2: full pause/resume implementation.

Mode:
  - brief-grounded  : standard pipelines (prototype, user_stories, od_ppt, ...)
                      where no Specify_Agent has produced a `spec` artifact
  - spec-grounded   : Spec_Kit_Agent workflows where a `spec` artifact exists

Max 3 rounds — after the third round, emit `clarification_limit_reached` and
proceed with best available context.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agents.artifact_store.store import get_artifact_store
from agents.artifacts.graph import ArtifactGraph
from agents.authz import ScopedStore

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

    async def run(
        self,
        pipeline_run_id: str,
        planning_context: dict[str, Any],
        websocket_send_fn: Callable[[dict], Awaitable[None]],
        clarify_agent=None,
        owner_id: str | None = None,
        workspace_id: str | None = None,
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

        while round_num < MAX_CLARIFICATION_ROUNDS:
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
        """Use an LLM to generate content-aware clarification questions.

        Reads the user brief from planning_context and asks the model to
        generate specific, targeted questions based on what's genuinely
        missing — not generic MCQ options. Returns None on failure so the
        caller can fall back to the static library.
        """
        user_request = planning_context.get("user_request", "")
        inferred_intent = planning_context.get("inferred_intent", "")
        missing = planning_context.get("missing_information", [])
        topic = planning_context.get("topic") or ""
        domain_insights = planning_context.get("domain_insights") or []

        if not user_request and not inferred_intent:
            return None

        # Build a concise brief description for the prompt
        brief_sample = user_request[:2000] if user_request else inferred_intent[:500]

        # Pipeline-specific question guidance
        pipeline_guidance = {
            "prototype": (
                "Focus on UI/UX design questions: layout type (sidebar/topnav/cards), "
                "visual style (minimal SaaS, consumer, data-heavy dashboard, dark admin), "
                "key pages/screens needed, primary user interactions, colour palette preference, "
                "navigation pattern, and target device (desktop/mobile/responsive)."
            ),
            "od_prototype": (
                "Focus on UI/UX design questions: layout type (sidebar/topnav/cards), "
                "visual style (minimal SaaS, consumer, data-heavy dashboard, dark admin), "
                "key pages/screens needed, primary user interactions, colour palette preference, "
                "navigation pattern, and target device (desktop/mobile/responsive)."
            ),
            "user_stories": (
                "Focus on product scope, user roles/personas, key user journeys, "
                "business rules, acceptance criteria style, and any compliance needs."
            ),
            "od_ppt": (
                "Focus on presentation purpose, target audience, content depth, "
                "number of slides, visual style preference, and key sections to cover."
            ),
            "ppt": (
                "Focus on presentation purpose, target audience, content depth, "
                "number of slides, visual style preference, and key sections to cover."
            ),
            "app_builder": (
                "Focus on tech stack, core features, data model, integrations, "
                "security requirements, and deployment target."
            ),
        }.get(pipeline_type, "Focus on scope, audience, objectives, and output format.")

        no_template_extra = ""
        if is_no_template:
            no_template_extra = """
IMPORTANT: The user chose NOT to use a pre-made visual template (blank canvas mode).
You MUST ask several UI design questions to establish the visual direction:
- What layout pattern? (sidebar navigation, top navigation bar, card-based, single-page)
- What visual style? (clean minimal SaaS, consumer/marketing, data-heavy dashboard, dark admin panel)
- What colour scheme? (light neutral, dark mode, brand colours, monochrome)
- What navigation structure? (sidebar with sub-items, flat topnav, hamburger menu)
- What primary interactions? (data tables, forms, charts, modals, wizard flows)
Ask AT LEAST 4 UI design questions — these are the most critical for blank-canvas output.
"""

        prompt = f"""You are a product clarification expert. Analyze the user's brief and generate targeted clarification questions.

## Pipeline Type
{pipeline_type}

## User Brief
{brief_sample}

## What the planner identified as missing or unclear
{json.dumps(missing)}

## Inferred intent
{inferred_intent}

{f"## Domain insights{chr(10)}" + chr(10).join(f"- {i}" for i in domain_insights) if domain_insights else ""}

## Guidance for this pipeline type
{pipeline_guidance}
{no_template_extra}

## Your task
Generate {4 if is_no_template else 3}-{7 if is_no_template else 5} targeted clarification questions based on what is GENUINELY missing or ambiguous in the brief above.

Rules:
1. Questions must be SPECIFIC to the brief content — reference the actual topic/domain
2. Do NOT ask about things already clearly stated in the brief
3. Each question must have 4-6 MCQ options that are RELEVANT to the domain/brief
4. Include a "No preference — let the AI decide" option where appropriate
5. Questions should directly improve the output quality if answered
6. For prototype pipelines, prioritize UI/layout/visual style questions

Return ONLY a JSON array, no other text:
[
  {{
    "question_text": "Specific question referencing the actual content?",
    "answer_type": "single_choice",
    "options": ["Option A", "Option B", "Option C", "Option D", "No preference"],
    "ambiguity_category": "UX Flow",
    "impact_level": "high"
  }},
  ...
]

Valid ambiguity_category values: Functional Scope, User Roles, Data Model, UX Flow, Performance, Security, Integration, Edge Cases, Terminology, Acceptance Criteria, Constraints
Valid impact_level values: high, medium, low
"""
        try:
            from app.agents.model_factory import build_model
            from langchain_core.messages import HumanMessage

            llm = build_model(max_tokens=1024)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)

            # Extract JSON array
            import re
            json_match = re.search(r'\[[\s\S]*\]', raw)
            if not json_match:
                logger.warning("ClarifyEngine LLM: no JSON array found in response")
                return None

            items = json.loads(json_match.group())
            if not isinstance(items, list) or not items:
                return None

            questions = []
            for i, item in enumerate(items):
                if not isinstance(item, dict) or not item.get("question_text"):
                    continue
                options = item.get("options") or ["No preference"]
                questions.append({
                    "question_id": f"r{round_num}_q{i + 1}",
                    "question_text": item["question_text"],
                    "impact_level": item.get("impact_level", "high" if i < 2 else "medium"),
                    "answer_type": item.get("answer_type", "single_choice"),
                    "options": options,
                    "recommended_answer": options[-1],
                    "ambiguity_category": item.get("ambiguity_category", "Functional Scope"),
                })

            logger.info(
                "ClarifyEngine LLM: generated %d content-aware questions for pipeline=%s no_template=%s",
                len(questions), pipeline_type, is_no_template,
            )
            return questions if questions else None

        except Exception as exc:
            logger.warning("ClarifyEngine LLM question generation failed: %s — falling back to static library", exc)
            return None

    async def _generate_questions(
        self,
        planning_context: dict[str, Any],
        round_num: int,
        clarify_agent,
    ) -> list[dict]:
        """Generate content-aware clarification questions.

        Primary path: LLM call that reads the actual brief and generates
        targeted questions specific to the content.
        Fallback: static library lookup keyed on missing_information items.
        """
        missing = planning_context.get("missing_information", [])
        if not missing:
            return []

        pipeline_type = planning_context.get("pipeline_type", "custom")
        is_no_template = bool(planning_context.get("no_template_mode", False))

        # ── Primary path: LLM-generated content-aware questions ───────────
        llm_questions = await self._generate_questions_via_llm(
            planning_context, round_num, pipeline_type, is_no_template
        )
        if llm_questions:
            return llm_questions

        # ── Fallback: static library (used when LLM call fails) ───────────
        logger.info("ClarifyEngine: falling back to static question library for pipeline=%s", pipeline_type)

        # Content-aware context for personalising static question text
        inferred_intent = planning_context.get("inferred_intent", "")
        topic = planning_context.get("topic") or ""
        user_request_summary = planning_context.get("user_request_summary", "")
        content_hint = (user_request_summary or inferred_intent or "").strip()
        if len(content_hint) > 120:
            content_hint = content_hint[:117] + "..."

        # ── Pipeline-specific topic questions ─────────────────────────────
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

        # ── Pipeline-specific style/UI questions ──────────────────────────
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

        # ── Full question library ──────────────────────────────────────────
        QUESTION_LIBRARY: dict[str, tuple[str, list[str]]] = {
            "topic": TOPIC_BY_PIPELINE.get(pipeline_type, (
                "What is the main topic or subject of this?",
                ["Product / service feature", "Business process / workflow", "Technical system / architecture", "Market / competitive analysis", "Internal tool / dashboard", "Customer-facing product", "Other — I'll describe in the notes below"],
            )),
            "subject": TOPIC_BY_PIPELINE.get(pipeline_type, (
                "What is the main topic or subject of this?",
                ["Product / service feature", "Business process / workflow", "Technical system / architecture", "Market / competitive analysis", "Internal tool / dashboard", "Customer-facing product", "Other — I'll describe in the notes below"],
            )),
            "target_audience": (
                "Who is the primary audience for this?",
                ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
            ),
            "audience": (
                "Who is the primary audience for this?",
                ["Executive / C-Suite", "Technical team / Engineers", "Business stakeholders / Managers", "General public / Consumers", "Sales & Marketing team"],
            ),
            "tone_and_style": (
                "What tone and style should be used?",
                ["Professional & formal", "Casual & conversational", "Data-driven & analytical", "Creative & visual", "Concise & minimal"],
            ),
            "tone": (
                "What tone and style should be used?",
                ["Professional & formal", "Casual & conversational", "Data-driven & analytical", "Creative & visual", "Concise & minimal"],
            ),
            "style": STYLE_BY_PIPELINE.get(pipeline_type, (
                "What tone and style should be used?",
                ["Professional & formal", "Casual & conversational", "Data-driven & analytical", "Creative & visual", "Concise & minimal"],
            )),
            "key_objectives": (
                "What is the primary goal or objective?",
                ["Inform & educate", "Persuade & sell", "Report results & metrics", "Propose a solution", "Compare options & recommend"],
            ),
            "objective": (
                "What is the primary goal or objective?",
                ["Inform & educate", "Persuade & sell", "Report results & metrics", "Propose a solution", "Compare options & recommend"],
            ),
            "slide_count": (
                "How many slides should the presentation have?",
                ["5–8 slides (concise)", "10–12 slides (standard)", "15–20 slides (detailed)", "20+ slides (comprehensive)", "No preference"],
            ),
            "depth": (
                "How deep should the content go?",
                ["High-level overview only", "Moderate detail", "Deep technical detail", "Executive summary only", "No preference"],
            ),
            "length": (
                "How long / detailed should the output be?",
                ["Very concise (key points only)", "Standard length", "Detailed & comprehensive", "As long as needed", "No preference"],
            ),
            "format": (
                "What output format do you prefer?",
                ["Bullet points & lists", "Narrative paragraphs", "Tables & comparisons", "Charts & visuals", "Mixed format"],
            ),
            "technology": (
                "What technology stack or platform should be used?",
                ["React / Next.js (web)", "React Native / Flutter (mobile)", "Node.js / Python (backend)", "Cloud-native (AWS / Azure / GCP)", "No preference"],
            ),
            "tech_stack": (
                "What technology stack or platform should be used?",
                ["React / Next.js (web)", "React Native / Flutter (mobile)", "Node.js / Python (backend)", "Cloud-native (AWS / Azure / GCP)", "No preference"],
            ),
            "timeline": (
                "What is the expected timeline or urgency?",
                ["ASAP / urgent", "Within 1 week", "Within 1 month", "Long-term project", "No specific deadline"],
            ),
            "scope": (
                "What is the scope of this project?",
                ["MVP / proof of concept", "Full production feature", "Internal tool only", "Customer-facing product", "Research & exploration"],
            ),
            "priority": (
                "What should be prioritized in this output?",
                ["Speed of delivery", "Quality & completeness", "Cost efficiency", "Scalability & future-proofing", "User experience"],
            ),
            "industry": (
                "What industry or domain is this for?",
                ["Technology / SaaS", "Finance / Banking", "Healthcare / Life sciences", "Retail / E-commerce", "Other / General"],
            ),
            "persona": (
                "Who are the end users of this product?",
                ["Enterprise employees", "Small business owners", "Developers / Technical users", "Consumers / General public", "Specific niche audience"],
            ),
            "user": (
                "Who are the end users of this product?",
                ["Enterprise employees", "Small business owners", "Developers / Technical users", "Consumers / General public", "Specific niche audience"],
            ),
            "security": (
                "What level of security and compliance is required?",
                ["Standard (basic auth)", "Enterprise (SSO / RBAC)", "Regulated (HIPAA / SOC2 / GDPR)", "High security (E2E encryption)", "No specific requirements"],
            ),
            "integration": (
                "What external integrations are needed?",
                ["None / standalone", "REST APIs only", "Third-party SaaS (Salesforce, Slack, etc.)", "Legacy systems / databases", "Multiple integrations"],
            ),
            "data": (
                "What kind of data will this system handle?",
                ["User profiles & accounts", "Transactional / financial data", "Content & media", "Analytics & metrics", "Sensitive / regulated data"],
            ),
            "performance": (
                "What are the performance requirements?",
                ["Low traffic (< 1k users)", "Medium traffic (1k–100k users)", "High traffic (100k+ users)", "Real-time / sub-second response", "No specific requirements"],
            ),
            # ── Prototype-specific questions ───────────────────────────────
            "key_screens": (
                "What are the key screens or pages the prototype must include?",
                ["Home / landing page", "Dashboard / main workspace", "Onboarding / sign-up flow", "Detail / item view", "Settings / profile page"],
            ),
            "interactions": (
                "What types of interactions should the prototype demonstrate?",
                ["Click-through navigation only", "Form inputs and validation", "Data tables with filtering/sorting", "Modals, drawers, and overlays", "Full interactive flows with state changes"],
            ),
            # ── User-stories-specific questions ───────────────────────────
            "personas": (
                "What user roles or personas will use this product?",
                ["Registered end users", "Admins / back-office staff", "Guest / anonymous users", "API consumers / developers", "Multiple roles with different permissions"],
            ),
            "user_journeys": (
                "What are the main user journeys or workflows to cover?",
                ["Onboarding / sign-up flow", "Core transactional flow (e.g. purchase, booking, submit)", "Account management / settings", "Search, browse, and filter", "Reporting / analytics / export"],
            ),
            "business_rules": (
                "Are there important business rules, validations, or constraints?",
                ["Approval workflows or authorisation checks", "Data validation rules (formats, limits, uniqueness)", "Pricing / discount / calculation logic", "Status / state-machine transitions", "No specific business rules — standard CRUD"],
            ),
            "compliance_security": (
                "What security or compliance requirements apply?",
                ["Standard authentication (email/password)", "SSO / OAuth / enterprise identity", "GDPR / data-privacy compliance", "Industry regulation (HIPAA, PCI-DSS, ISO 27001)", "No specific requirements"],
            ),
            # ── PPT-specific questions ─────────────────────────────────────
            "content_depth": (
                "How detailed should the content be?",
                ["High-level summary only", "Moderate detail with supporting points", "Deep-dive with data and evidence", "Executive brief (one key message per slide)", "No preference"],
            ),
            "data_availability": (
                "Do you have data, charts, or statistics to include?",
                ["Yes — I have specific data/numbers to include", "Use realistic representative data", "Qualitative insights only (no hard numbers)", "Both qualitative and quantitative", "No preference"],
            ),
            "visual_style": (
                "What visual style should the presentation follow?",
                ["Clean and minimal (lots of white space)", "Data-rich (charts, tables, graphs)", "Story-driven (narrative with visuals)", "Brand-aligned (company colours and fonts)", "No preference"],
            ),
            "key_sections": (
                "What sections or chapters should the deck include?",
                ["Executive summary + key findings", "Problem / opportunity + solution", "Data analysis + recommendations", "Roadmap or timeline", "Standard structure — I'll leave it to the AI"],
            ),
            # ── App-builder-specific questions ────────────────────────────
            "data_model": (
                "What key data entities or models does the application need?",
                ["Users / accounts and profiles", "Products / items / catalogue", "Orders / transactions / payments", "Content / documents / media", "Custom domain-specific entities"],
            ),
            "integrations": (
                "What external integrations or third-party services are needed?",
                ["None / standalone application", "Payment gateway (Stripe, PayPal)", "Authentication provider (Auth0, Okta, Google)", "Email / SMS / notification service", "Multiple — I'll describe in notes"],
            ),
            # ── Migration-specific questions ───────────────────────────────
            "integration_patterns": (
                "What integration patterns does the current application use?",
                ["REST APIs (synchronous HTTP calls)", "Message queues / event-driven (Kafka, SQS)", "SOAP / XML web services", "Database-level integration (shared DB)", "Multiple patterns — I'll describe in notes"],
            ),
            "target_infrastructure": (
                "What is the target infrastructure / cloud environment?",
                ["AWS (EKS / ECS / Lambda)", "Azure (AKS / App Service / Functions)", "GCP (GKE / Cloud Run)", "On-premises / private cloud", "Not decided yet"],
            ),
            "azure_services": (
                "Which Azure services should the migrated application use?",
                ["Azure App Service / AKS (containers)", "Azure Functions (serverless)", "Azure SQL / Cosmos DB (data)", "Azure Service Bus (messaging)", "Not decided — recommend best fit"],
            ),
            "data_migration": (
                "How should existing data be handled during migration?",
                ["Full data migration (all historical data)", "Cutover only (no historical data migration)", "Parallel run (both systems live temporarily)", "Gradual migration with feature flags", "Not applicable / greenfield"],
            ),
            # ── Custom workflow questions ──────────────────────────────────
            "output_format": (
                "What format should the output be in?",
                ["Structured document (headings, sections)", "Bullet-point list / checklist", "Table or comparison matrix", "Code or technical specification", "Free-form prose / narrative"],
            ),
            "constraints": (
                "Are there any constraints or limitations to be aware of?",
                ["Time / deadline constraints", "Budget or resource limits", "Technology or platform constraints", "Regulatory or compliance constraints", "No specific constraints"],
            ),
            "domain": (
                "What industry or domain does this task relate to?",
                ["Technology / Software", "Finance / Banking / Insurance", "Healthcare / Life Sciences", "Retail / E-commerce", "Other — I'll specify in notes"],
            ),
            "assumptions": (
                "What assumptions should be used if information is missing?",
                ["Use industry best-practice defaults", "Favour simplicity and speed", "Favour completeness and thoroughness", "Ask me before making assumptions", "No preference"],
            ),
        }

        # 11-category ambiguity taxonomy (FR-009)
        _TAXONOMY = [
            "Functional Scope", "User Roles", "Data Model", "UX Flow",
            "Performance", "Security", "Integration", "Edge Cases",
            "Terminology", "Acceptance Criteria", "Constraints",
        ]

        # Cap at min(5, detected_ambiguity_count)
        capped = missing[:5]
        questions: list[dict] = []

        for i, item in enumerate(capped):
            item_lower = item.lower().replace(" ", "_").replace("-", "_")

            # Find best matching question from library
            matched_key = None
            # First try exact substring match
            for key in QUESTION_LIBRARY:
                if key in item_lower or item_lower in key:
                    matched_key = key
                    break
            # Then try word-level match (e.g. "presentation_topic" → "topic")
            if not matched_key:
                item_words = set(item_lower.replace("_", " ").replace("-", " ").split())
                for key in QUESTION_LIBRARY:
                    key_words = set(key.replace("_", " ").split())
                    if item_words & key_words:  # any word overlap
                        matched_key = key
                        break

            if matched_key:
                base_question, options = QUESTION_LIBRARY[matched_key]
            else:
                # Fallback: generate a generic question with generic options
                readable = item.replace("_", " ").replace("-", " ").title()
                base_question = f"How would you describe the {readable}?"
                options = [
                    f"Standard {readable}",
                    f"Minimal {readable}",
                    f"Comprehensive {readable}",
                    "Custom / specific requirements",
                    "No preference",
                ]

            # ── Content-aware question personalisation ─────────────────────
            # When the planning context carries a content hint (inferred_intent,
            # topic, or user_request_summary), append it as context so the user
            # understands *why* we're asking and that the question is specifically
            # about their content — not a generic fixed question.
            question_text = base_question
            if content_hint and matched_key not in ("topic", "subject"):
                # Append a brief "For your [topic/content]..." prefix to ground
                # the question in the user's actual content.
                subject_label = topic or content_hint
                if subject_label and len(subject_label) < 80:
                    question_text = f"{base_question} (for: {subject_label})"

            category = _classify_ambiguity(item, _TAXONOMY)
            # Topic questions are hybrid: MCQ suggestions + free-text input
            is_topic = matched_key in ("topic", "subject") if matched_key else False
            questions.append(
                {
                    "question_id": f"r{round_num}_q{i + 1}",
                    "question_text": question_text,
                    "impact_level": "high" if i < 2 else "medium",
                    "answer_type": "hybrid" if is_topic else "single_choice",
                    "options": options,
                    "recommended_answer": options[-1],
                    "ambiguity_category": category,
                }
            )
        return questions

    async def _persist_qa(
        self,
        pipeline_run_id: str,
        questions: list[dict],
        responses: list[dict],
        round_num: int,
    ) -> None:
        """Persist each Q&A pair as a typed ``clarifications`` ArtifactRef.

        Migrated off the thin store in 05-06: the clarifications PAYLOAD now lands
        in ``artifact_refs`` (kind=clarifications) via the owner-scoped
        ``ScopedStore``, so the websocket reconnect read is served entirely from the
        typed layer. visibility="workspace" so the owner read resolves through the
        owner+visibility scope filter. Best-effort: a persist failure logs and never
        breaks the clarify flow (same shape as the prior thin-store write).
        """
        answer_map = {r.get("question_id"): r.get("answer") for r in responses}
        qa_pairs = []
        for q in questions:
            qa_pairs.append(
                {
                    "question_id": q["question_id"],
                    "question_text": q["question_text"],
                    "impact_level": q.get("impact_level", "medium"),
                    "answer": answer_map.get(q["question_id"]),
                    "round": round_num,
                }
            )
        # CR-01 / WR-01: a fresh throwaway ArtifactGraph is constructed per round,
        # so its in-memory per-(run, kind) count is always 0 and ref.version is
        # always 1. The DB — not this graph — is the cross-call versioning source
        # of truth here, so we pass force_db_version=True to ScopedStore.write_ref
        # so it stamps existing_count + 1. This keeps clarifications rows monotonic
        # per round (round 1→v1, round 2→v2, …) and makes the websocket reconnect
        # read (order_by version ASC, take [-1]) deterministically return the
        # newest round.
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
        store = ScopedStore(
            owner_id=self._owner_id, workspace_id=self._workspace_id
        )
        # WR-02 / CR-02: do NOT swallow the persist on a bare Exception. The
        # AUTHZ-03 guard in ScopedStore.write_ref raises ValueError on a falsy
        # owner — a real bug that must propagate. Only the offline-characterization
        # harness condition (no artifact_refs/workflow_runs schema → SQLAlchemy
        # OperationalError / IntegrityError) is degraded to a warning so the live
        # clarify flow is never broken; any non-DB exception propagates loudly.
        from sqlalchemy.exc import SQLAlchemyError

        try:
            await store.write_ref(ref, force_db_version=True)
        except SQLAlchemyError as exc:
            # Missing-table (OperationalError) / missing-FK (IntegrityError) —
            # the offline harness has no DB schema. Surfaced at warning with the
            # run context so a genuine prod persistence failure is observable
            # (not a silent debug no-op).
            logger.warning(
                "clarifications persist failed for run %s round %d (%s) — "
                "DB write degraded (offline harness / schema unavailable); "
                "live clarify flow unaffected",
                pipeline_run_id, round_num, exc,
            )

    def _merge_answers(
        self,
        planning_context: dict[str, Any],
        questions: list[dict],
        responses: list[dict],
    ) -> dict[str, Any]:
        """Merge answers into the planning_context, removing resolved missing items."""
        merged = dict(planning_context)
        answer_map = {r.get("question_id"): r.get("answer") for r in responses}

        # Record answered clarifications as explicit constraints
        explicit = list(merged.get("explicit_constraints", []))
        for q in questions:
            ans = answer_map.get(q["question_id"])
            if ans:
                explicit.append(f"{q['question_text']} → {ans}")
        merged["explicit_constraints"] = explicit

        # Remove resolved items from missing_information (all questions answered
        # in this round are considered resolved)
        answered_count = sum(1 for q in questions if answer_map.get(q["question_id"]))
        remaining_missing = list(merged.get("missing_information", []))
        merged["missing_information"] = remaining_missing[answered_count:]

        return merged
