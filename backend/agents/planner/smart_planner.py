"""agents/planner/smart_planner.py — Smart Single-Call Planner.

Replaces the slow ReAct tool-loop planner with a fast, intelligent
single-call planner that:

1. Uses a rich domain knowledge base (built-in, no external API needed)
2. Makes ONE structured LLM call → returns JSON planning context in 2-5s
3. Detects topic presence intelligently
4. Generates pipeline-aware missing_information
5. Infers domain constraints, personas, NFRs from the brief
6. Produces quality targets and execution strategy

Architecture:
  SmartPlanner.plan(brief, pipeline_type) → PlanningContext dict

The LLM receives:
  - The user brief
  - The pipeline type
  - Relevant domain knowledge snippets (from the knowledge base)
  - A strict JSON output schema

No tool calls. No ReAct loop. One call, 2-5 seconds.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger("agents.planner.smart_planner")

# ---------------------------------------------------------------------------
# Domain Knowledge Base
# ---------------------------------------------------------------------------
# Structured knowledge about each pipeline type: what makes a good brief,
# what's typically missing, what constraints to infer, what quality targets matter.

DOMAIN_KB: dict[str, dict[str, Any]] = {
    "od_ppt": {
        "description": "OpenDesign presentation pipeline — generates a complete HTML slide deck",
        "what_makes_good_brief": "A specific topic, target audience, purpose/objective, and content depth",
        "common_missing": ["target_audience", "tone_and_style", "key_objectives", "slide_count", "content_depth", "data_availability", "visual_style", "key_sections"],
        "topic_indicators": ["comparison", "analysis", "overview", "strategy", "results", "report", "pitch", "proposal"],
        "quality_targets": ["Clear narrative arc", "Consistent visual style", "Data-backed claims", "Actionable takeaways"],
        "typical_personas": ["Executive", "Business stakeholder", "Technical team", "Sales team"],
        "nfrs": ["Visual consistency", "Readability", "Slide flow", "Brand alignment"],
    },
    "ppt": {
        "description": "Presentation pipeline — generates slide content",
        "what_makes_good_brief": "A specific topic, target audience, purpose/objective, and content depth",
        "common_missing": ["target_audience", "tone_and_style", "key_objectives", "slide_count", "content_depth", "data_availability", "visual_style", "key_sections"],
        "topic_indicators": ["comparison", "analysis", "overview", "strategy", "results", "report", "pitch"],
        "quality_targets": ["Clear narrative arc", "Consistent visual style", "Data-backed claims"],
        "typical_personas": ["Executive", "Business stakeholder", "Technical team"],
        "nfrs": ["Visual consistency", "Readability", "Slide flow"],
    },
    "user_stories": {
        "description": "User stories pipeline — generates product backlog with epics, stories, acceptance criteria",
        "what_makes_good_brief": "A specific product/feature name, target users, core functionality, business goals, and user journeys",
        "common_missing": ["target_audience", "scope", "priority", "technology", "personas", "user_journeys", "business_rules", "compliance_security"],
        "topic_indicators": ["app", "platform", "system", "portal", "dashboard", "service", "tool", "feature", "module"],
        "quality_targets": ["Complete acceptance criteria", "Testable stories", "Prioritized backlog", "Clear personas", "Covered business rules", "NFRs captured"],
        "typical_personas": ["End user", "Admin", "Developer", "Business owner"],
        "nfrs": ["Accessibility", "Performance", "Security", "Scalability"],
        "scope_hints": {
            "mvp": "Focus on core user journeys only",
            "full": "Include edge cases, admin flows, error states",
            "enterprise": "Add compliance, audit, SSO requirements",
        },
    },
    "od_prototype": {
        "description": "OpenDesign prototype pipeline — generates interactive HTML prototype",
        "what_makes_good_brief": "A specific product type, target users, key screens/flows, and interaction patterns",
        "common_missing": ["target_audience", "scope", "priority", "style", "user_journeys", "key_screens", "interactions", "personas"],
        "topic_indicators": ["app", "dashboard", "portal", "website", "interface", "screen", "flow", "checkout", "onboarding"],
        "quality_targets": ["Realistic interactions", "Consistent design system", "Complete user flows", "Responsive layout"],
        "typical_personas": ["End user", "Admin", "Mobile user", "Desktop user"],
        "nfrs": ["Accessibility (WCAG 2.1)", "Mobile responsiveness", "Performance", "Usability"],
    },
    "prototype": {
        "description": "Prototype pipeline — generates interactive HTML prototype",
        "what_makes_good_brief": "A specific product type, target users, key screens/flows, and interaction patterns",
        "common_missing": ["target_audience", "scope", "priority", "style", "user_journeys", "key_screens", "interactions", "personas"],
        "topic_indicators": ["app", "dashboard", "portal", "website", "interface", "screen", "flow"],
        "quality_targets": ["Realistic interactions", "Consistent design system", "Complete user flows"],
        "typical_personas": ["End user", "Admin", "Mobile user"],
        "nfrs": ["Accessibility", "Mobile responsiveness", "Performance"],
    },
    "app_builder": {
        "description": "Full-stack application builder — generates complete application architecture, code, and infrastructure",
        "what_makes_good_brief": "A specific application type, tech stack, core features, user journeys, and data model",
        "common_missing": ["technology", "scope", "target_audience", "security", "user_journeys", "data_model", "integrations", "performance"],
        "topic_indicators": ["app", "platform", "system", "service", "api", "backend", "frontend", "saas", "tool"],
        "quality_targets": ["Production-ready code", "Security best practices", "Test coverage", "CI/CD pipeline", "Documentation"],
        "typical_personas": ["Developer", "DevOps engineer", "Product manager", "End user"],
        "nfrs": ["Security (OWASP)", "Performance", "Scalability", "Maintainability", "Test coverage ≥80%"],
        "tech_defaults": {
            "web": "React/Next.js + Node.js/FastAPI + PostgreSQL",
            "mobile": "React Native or Flutter",
            "backend": "FastAPI or Express.js",
            "cloud": "AWS or Azure",
        },
    },
    "mulesoft_to_springboot": {
        "description": "Mulesoft → Spring Boot migration pipeline",
        "what_makes_good_brief": "The Mulesoft application name, integration patterns, target AWS infrastructure, and compliance requirements",
        "common_missing": ["scope", "technology", "timeline", "priority", "integration_patterns", "target_infrastructure", "data_migration", "compliance_security"],
        "topic_indicators": ["mulesoft", "integration", "api", "flow", "connector", "dataweave", "migration"],
        "quality_targets": ["Zero data loss", "API parity", "Performance equivalence", "Test coverage"],
        "typical_personas": ["Integration architect", "Backend developer", "DevOps engineer"],
        "nfrs": ["Zero downtime migration", "API backward compatibility", "Security compliance"],
    },
    "dotnet_to_azure": {
        "description": ".NET → Azure migration pipeline",
        "what_makes_good_brief": "The .NET application name, current architecture, Azure target services, and compliance requirements",
        "common_missing": ["scope", "technology", "timeline", "priority", "azure_services", "data_migration", "integration_patterns", "compliance_security"],
        "topic_indicators": [".net", "dotnet", "c#", "azure", "migration", "modernization", "cloud"],
        "quality_targets": ["Cloud-native architecture", "Cost optimization", "Security hardening", "Performance improvement"],
        "typical_personas": ["Cloud architect", ".NET developer", "DevOps engineer"],
        "nfrs": ["Zero downtime migration", "Cost efficiency", "Security compliance", "Scalability"],
    },
    "custom": {
        "description": "Custom AI workflow pipeline",
        "what_makes_good_brief": "A specific task, deliverable type, target audience, and output format requirements",
        "common_missing": ["target_audience", "key_objectives", "scope", "priority", "output_format", "constraints", "domain", "assumptions"],
        "topic_indicators": [],
        "quality_targets": ["Clear deliverable", "Actionable output", "Accurate information"],
        "typical_personas": ["Business user", "Technical user", "Decision maker"],
        "nfrs": ["Accuracy", "Completeness", "Clarity"],
    },
}


def _get_domain_knowledge(pipeline_type: str) -> dict[str, Any]:
    """Return domain knowledge for the given pipeline type."""
    return DOMAIN_KB.get(pipeline_type, DOMAIN_KB["custom"])


# ---------------------------------------------------------------------------
# Smart Planner
# ---------------------------------------------------------------------------

class SmartPlanner:
    """Single-call intelligent planner.

    Makes ONE LLM call with a rich prompt that includes:
    - The user brief
    - Pipeline type context
    - Domain knowledge (what makes a good brief, what's typically missing)
    - Strict JSON output schema

    Returns a complete PlanningContext in 2-5 seconds.
    """

    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id
        self._llm = self._build_llm()

    def _build_llm(self):
        """Build the LLM client — Anthropic direct, Bedrock bearer-token, or Bedrock IAM."""
        from app.core.config import settings
        if settings.ANTHROPIC_API_KEY:
            from langchain_anthropic import ChatAnthropic
            model = self.model_id or settings.ANTHROPIC_MODEL_ID or "claude-haiku-4-5-20251001"
            return ChatAnthropic(
                model=model,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=2048,
                temperature=0,
            )

        from langchain_aws import ChatBedrockConverse
        from botocore.config import Config
        from app.core.config import settings as s
        model = self.model_id or s.BEDROCK_INFERENCE_PROFILE_ID or s.BEDROCK_MODEL_ID
        botocore_cfg = Config(read_timeout=600, connect_timeout=30, retries={"max_attempts": 5, "mode": "adaptive"})

        if s.AWS_BEARER_TOKEN_BEDROCK:
            from app.agents.model_factory import _build_bedrock_bearer_session
            boto_session = _build_bedrock_bearer_session()
            return ChatBedrockConverse(
                model=model,
                region_name=s.AWS_REGION,
                max_tokens=2048,
                client=boto_session.client("bedrock-runtime", region_name=s.AWS_REGION, config=botocore_cfg),
            )

        return ChatBedrockConverse(
            model=model,
            region_name=s.AWS_REGION,
            max_tokens=2048,
            config=botocore_cfg,
        )

    def _build_prompt(self, brief: str, pipeline_type: str) -> str:
        """Build the rich planning prompt with domain knowledge and coverage scan."""
        kb = _get_domain_knowledge(pipeline_type)

        # For long briefs, intelligently sample so the LLM can scan what's covered.
        # Realistic briefs (including a full uploaded doc, <= settings.BRIEF_MAX_CHARS)
        # pass IN FULL; only pathological briefs beyond the ceiling are head+tail sampled.
        brief_for_prompt = brief
        if len(brief) > settings.BRIEF_MAX_CHARS:
            head_budget = settings.BRIEF_MAX_CHARS * 3 // 4
            tail_budget = settings.BRIEF_MAX_CHARS - head_budget
            head = brief[:head_budget].rstrip()
            tail = brief[-tail_budget:].lstrip()
            brief_for_prompt = (
                f"{head}\n\n[... document continues — {len(brief) - settings.BRIEF_MAX_CHARS} chars omitted ...]\n\n{tail}"
            )

        return f"""You are an expert pipeline planner. Analyze the user's brief and produce a structured planning context using a coverage scan approach.

## Pipeline Being Run
**Type**: {pipeline_type}
**Description**: {kb['description']}
**What makes a good brief**: {kb['what_makes_good_brief']}

## User Brief
"{brief_for_prompt}"

## Step 1 — Coverage Scan
For each taxonomy category below, mark status: "clear" (fully covered), "partial" (mentioned but vague), or "missing" (not addressed at all).

Categories:
1. Functional Scope — core user goals, success criteria, explicit out-of-scope
2. User Roles — personas, actors, who uses this
3. Domain & Data Model — entities, relationships, data volume, state transitions
4. UX Flow & Interactions — user journeys, error/empty/loading states, navigation
5. Non-Functional Quality — performance, scalability, reliability, observability, accessibility
6. Security & Compliance — auth/authz, data protection, regulatory constraints
7. Integration & Dependencies — external APIs, services, protocols
8. Edge Cases & Failure Handling — negative scenarios, conflict resolution
9. Constraints & Tradeoffs — technical constraints, rejected alternatives

## Step 2 — Missing Information
Based on the coverage scan, identify items that are GENUINELY MISSING or AMBIGUOUS in the brief.

**STRICT RULE**: Only include an item if:
1. Its category is "partial" or "missing" in the scan
2. It would materially change the output if answered differently
3. It is NOT already explicitly stated in the brief
4. It is NOT something that can be reasonably inferred or defaulted

**Common missing items for {pipeline_type}**: {json.dumps(kb['common_missing'])}

If the brief has no topic → add "topic" as the FIRST item.
If the brief is rich and covers most dimensions → missing_information may be 1-3 items or even empty.
A 100-page document likely covers most dimensions — be very selective.

## Step 3 — Infer Context
From the brief:
- Inferred intent (what the user wants to achieve)
- Explicit constraints (stated in brief)
- Implicit constraints (implied by domain)
- Personas (extracted from brief if mentioned)
- NFRs and quality targets
- Domain insights: 2-3 specific observations about THIS brief

## Step 4 — Gate Decision
- `CLARIFY_REQUIRED` if missing_information is non-empty
- `PROCEED` if brief is complete enough (missing_information empty)

## Output Format
Return ONLY valid JSON:

{{
  "inferred_intent": "concise description of what the user wants to achieve",
  "has_topic": true/false,
  "topic": "specific topic if found, or null",
  "explicit_constraints": ["stated in brief"],
  "implicit_constraints": ["implied by domain"],
  "coverage_map": {{
    "functional_scope": "clear|partial|missing",
    "user_roles": "clear|partial|missing",
    "domain_data_model": "clear|partial|missing",
    "ux_flow": "clear|partial|missing",
    "non_functional": "clear|partial|missing",
    "security_compliance": "clear|partial|missing",
    "integration": "clear|partial|missing",
    "edge_cases": "clear|partial|missing",
    "constraints": "clear|partial|missing"
  }},
  "missing_information": ["only items GENUINELY missing — may be 0-3 for a rich brief"],
  "execution_strategy": "sequential",
  "execution_gate": "PROCEED or CLARIFY_REQUIRED",
  "inferred_personas": ["from brief where possible"],
  "inferred_nfrs": ["non-functional requirements"],
  "quality_targets": ["quality goals"],
  "pipeline_type": "{pipeline_type}",
  "domain_insights": ["2-3 specific insights about THIS brief"],
  "user_request_summary": "1-2 sentence summary of what the user provided"
}}"""

        return f"""You are an expert pipeline planner. Analyze the user's brief and produce a structured planning context.

## Pipeline Being Run
**Type**: {pipeline_type}
**Description**: {kb['description']}
**What makes a good brief**: {kb['what_makes_good_brief']}

## User Brief
"{brief_for_prompt}"

## Your Analysis Tasks

### 1. Topic Detection
Does the brief contain a SPECIFIC topic/subject? 

A brief HAS a topic when it names something specific:
- ✅ "Apple vs Samsung comparison" → has topic
- ✅ "Q3 sales results for the board" → has topic  
- ✅ "hospital booking system" → has topic
- ✅ "climate change impact" → has topic

A brief does NOT have a topic:
- ❌ "make a presentation" → no topic
- ❌ "build something" → no topic
- ❌ "create a prototype" → no topic
- ❌ "generate user stories" → no topic

### 2. Missing Information — CRITICAL: only include items GENUINELY absent from the brief
Based on the brief and pipeline type, identify what's genuinely MISSING or AMBIGUOUS.

**Candidate missing items for {pipeline_type}**: {json.dumps(kb['common_missing'])}

**STRICT RULE**: Only include an item in missing_information if:
1. It is genuinely unclear or absent from the brief
2. It would materially change the output if answered differently
3. It is NOT already answered or clearly implied by the brief

If the brief mentions nurses in a hospital booking system → "target_audience" is CLEAR, do NOT add it.
If the brief is a 100-page user-story document → most standard items are likely already covered.
If the brief specifies a web app → "technology" may already be implied.
Read the brief carefully and SKIP any item that is already answered.

If the brief has no topic → add "topic" as the FIRST item.
If the brief is rich and covers most dimensions → missing_information may be short (1-2 items) or even empty.

### 3. Infer Context
From the brief, infer:
- Inferred intent (what the user actually wants to achieve)
- Explicit constraints (things explicitly stated in the brief)
- Implicit constraints (things implied by the domain/context)
- Relevant personas (extracted FROM the brief when possible)
- NFRs (non-functional requirements mentioned or implied)
- Quality targets
- Domain insights: 2-3 specific observations about THIS brief's content

**Typical personas for {pipeline_type}** (use only if not already specified in brief): {json.dumps(kb['typical_personas'])}
**Typical NFRs**: {json.dumps(kb['nfrs'])}
**Quality targets**: {json.dumps(kb['quality_targets'])}

### 4. Gate Decision
- `CLARIFY_REQUIRED` if missing_information is non-empty
- `PROCEED` if missing_information is empty (brief is complete enough)

## Output Format
Return ONLY valid JSON, no other text:

{{
  "inferred_intent": "concise description of what the user wants to achieve",
  "has_topic": true/false,
  "topic": "the specific topic if found, or null",
  "explicit_constraints": ["list of things explicitly stated in the brief"],
  "implicit_constraints": ["list of things implied by the domain/context"],
  "missing_information": ["only items GENUINELY missing — may be empty for a rich brief"],
  "execution_strategy": "sequential",
  "execution_gate": "PROCEED" or "CLARIFY_REQUIRED",
  "inferred_personas": ["list of relevant user personas — extracted from brief where possible"],
  "inferred_nfrs": ["list of non-functional requirements"],
  "quality_targets": ["list of quality goals for this pipeline run"],
  "pipeline_type": "{pipeline_type}",
  "domain_insights": ["2-3 specific insights about THIS brief that agents should know"],
  "user_request_summary": "1-2 sentence summary of what the user provided (useful for downstream context)"
}}"""

    async def plan(self, brief: str, pipeline_type: str) -> dict:
        """Run the smart planner. Returns a complete PlanningContext dict."""
        from langchain_core.messages import HumanMessage

        prompt = self._build_prompt(brief, pipeline_type)

        try:
            response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if not json_match:
                raise ValueError("No JSON found in planner response")

            ctx = json.loads(json_match.group())
            ctx["pipeline_type"] = pipeline_type  # ensure it's set
            # Store the original user request (capped at settings.BRIEF_MAX_CHARS for
            # context-window safety) so ClarifyEngine can generate content-aware questions.
            ctx["user_request"] = brief[:settings.BRIEF_MAX_CHARS] if len(brief) > settings.BRIEF_MAX_CHARS else brief

            logger.info(
                "SmartPlanner: pipeline=%s has_topic=%s gate=%s missing=%s",
                pipeline_type,
                ctx.get("has_topic"),
                ctx.get("execution_gate"),
                ctx.get("missing_information", []),
            )
            return ctx

        except Exception as exc:
            logger.warning("SmartPlanner failed: %s — using default context", exc)
            return self._default_context(brief, pipeline_type)

    def _default_context(self, brief: str, pipeline_type: str) -> dict:
        """Fallback context when LLM call fails."""
        kb = _get_domain_knowledge(pipeline_type)
        return {
            "inferred_intent": brief[:200],
            "has_topic": len(brief.split()) > 4,
            "topic": None,
            "explicit_constraints": [],
            "implicit_constraints": [],
            "missing_information": kb["common_missing"],  # use full list, not [:3]
            "execution_strategy": "sequential",
            "execution_gate": "CLARIFY_REQUIRED",
            "inferred_personas": kb["typical_personas"][:2],
            "inferred_nfrs": kb["nfrs"][:2],
            "quality_targets": kb["quality_targets"][:2],
            "pipeline_type": pipeline_type,
            "domain_insights": [],
            "user_request": brief[:settings.BRIEF_MAX_CHARS] if len(brief) > settings.BRIEF_MAX_CHARS else brief,
            "planner_fallback": True,
        }
