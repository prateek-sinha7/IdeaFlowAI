"""Phase 15 prompt output-contract pins (LV-02 / F4-residual / F5-residual).

Durable upgrade of 13-03's grep-only acceptance. Per D-04.

13-03 shipped its prompt output-contracts with shell-grep acceptance gates that
lived ONLY in the plan's verify blocks — no persistent test pinned the contract
lines, so a future prompt rewrite could silently drop them. This module makes
the Phase-15 contract lines durable:

  * ``test_od_ppt_validator_deck_reemission_contract`` — LV-02 (D-01): the
    od-ppt-validator body carries the exactly-ONE-artifact complete-deck
    re-emission contract, positioned ABOVE the validation checklist, with no
    duplicate contract heading (the old bottom contract was deleted).
  * ``test_sdlc_governance_anti_fabrication_contract`` — F4-residual (D-02):
    all three sdlc-governance bodies carry the no-tools / never-emit-tool-XML /
    begin-directly contract, with the deliverable-start line tailored per
    pipeline (app = filename: fenced block; dotnet/mulesoft = first Markdown
    heading) and the app fabrication trigger ("Read the concrete choices")
    defused.
  * ``test_infra_generator_api_v1_contract`` — F5-residual (D-03): the
    app-infra-generator body carries the top-of-body API PATH CONTRACT with
    concrete /api/v1 examples, positioned above OUTPUT FORMAT.
  * ``test_contract_agents_frontmatter_frozen`` — T-15-01 mitigation made
    durable: the five edited agents' behavior-bearing frontmatter (order /
    pipeline_type / tools / guardrails / context_from / max_tokens / injects /
    gate) is frozen; 15-01 was bodies-only.
  * ``test_od_ppt_deck_resolution_with_contract_shaped_validator`` — the LV-02
    composition pin: a contract-shaped scripted validator (multi-sentence QA
    narration FIRST, then a single artifact-wrapped COMPLETE deck — the live
    LV-02 evidence shape) driven through the REAL engine + REAL PptResolver +
    REAL prompts resolves ``final_output`` to the deck, not the narration.

All pins assert on ``load_agent_spec(id).prompt_body`` — the parser the factory
composes from (test_guardrails.py precedent) — so a pinned line is proven to
survive frontmatter parsing, not just to exist in the file.
"""

from __future__ import annotations

import pytest

from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
    _ScriptedTurn,
    _scripts_for,
)
from tests.agents.live_harness import drive_engine_pipeline

from agents.loader import load_agent_spec


# ===========================================================================
# LV-02 (D-01) — od-ppt-validator deck re-emission contract.
# ===========================================================================


def test_od_ppt_validator_deck_reemission_contract() -> None:
    """The validator body demands exactly ONE artifact = the complete deck."""
    body = load_agent_spec("od-ppt-validator").prompt_body

    # The exactly-one-artifact rule (unwrap_artifact is FIRST-match — a small
    # status artifact before the deck would win the unwrap; RESEARCH Pitfall 2).
    assert "exactly ONE <artifact>" in body
    # The artifact content is the full corrected deck...
    assert "complete corrected HTML deck" in body
    # ...even on a clean pass (re-emit, never report).
    assert "even when you change nothing" in body

    # Positional prominence: the contract sits ABOVE the validation checklist
    # (live evidence showed a bottom-of-body contract losing to the checklist
    # framing above it).
    assert body.index("exactly ONE <artifact>") < body.index("## VALIDATION CHECKLIST")

    # No dual-contract drift: the old bottom `## OUTPUT CONTRACT` was deleted;
    # exactly one contract heading exists.
    assert body.count("## OUTPUT CONTRACT") == 1


# ===========================================================================
# F4-residual (D-02) — sdlc-governance family anti-fabrication contract.
# ===========================================================================

_SDLC_AGENT_IDS = (
    "app-sdlc-governance",
    "dotnet-sdlc-governance",
    "mulesoft-sdlc-governance",
)


@pytest.mark.parametrize("agent_id", _SDLC_AGENT_IDS)
def test_sdlc_governance_anti_fabrication_contract(agent_id: str) -> None:
    """Each sdlc-governance body carries the no-tools / no-tool-XML contract."""
    body = load_agent_spec(agent_id).prompt_body

    # Shared contract lines (byte-identical anti-tool-XML sentence across the
    # family).
    assert "You have NO tools" in body
    assert "Begin your response DIRECTLY with" in body

    # Pitfall 7: forbidden tokens named exactly ONCE, tersely — repeating
    # tool-XML tokens through the body re-primes the fabrication F4 fixed.
    for token in ("<function_calls>", "<invoke>", "write_todos"):
        assert body.count(token) == 1, f"{token!r} must appear exactly once"

    if agent_id == "app-sdlc-governance":
        # app_builder deliverable = filename: fenced blocks.
        assert "fenced block" in body
        # The F4 fabrication trigger is defused: the read-priming phrasing that
        # elicited simulated <invoke name="read_file"> calls is gone.
        assert "Read the concrete choices" not in body
    else:
        # dotnet/mulesoft deliverable = structured Markdown (Pitfall 5: no
        # filename-block contamination of the migration pipelines — their
        # bodies must never grow app-style `filename:` blocks).
        assert "the first Markdown heading" in body
        assert "filename:" not in body


# ===========================================================================
# F5-residual (D-03) — app-infra-generator /api/v1 path contract.
# ===========================================================================


def test_infra_generator_api_v1_contract() -> None:
    """The infra body carries a forceful top-of-body /api/v1 contract."""
    body = load_agent_spec("app-infra-generator").prompt_body

    # Contract + concrete examples + reinforcement bullet (15-01 shipped 8
    # literals; >= 6 is the gate so cosmetic edits have headroom).
    assert body.count("/api/v1") >= 6
    assert "API PATH CONTRACT" in body

    # Positional prominence: the contract precedes the OUTPUT FORMAT spec
    # (the old bottom-of-body RULES bullet was ignored live — 0x in 3,083 lines).
    assert body.index("API PATH CONTRACT") < body.index("OUTPUT FORMAT")

    # Concrete examples survive: healthcheck curl + nginx location block.
    assert "/api/v1/health" in body
    assert "location /api/v1/" in body


# ===========================================================================
# ISS-006 (Phase 19) — shared canonical getDatabase DB-accessor literal across
# the app_builder producer (app-code-generator) + consumer
# (app-test-implementation) prompt bodies.
#
# Root cause: producer emitted the DB module exporting `getDatabase`; consumer
# emitted `tests/setup.ts` importing a model-invented `getDb` → TS2305 at test
# build. The 13-03 shared-literal fix threads ONE canonical named-export literal
# `getDatabase` through both bodies (and the consumer's Contract-fidelity rule
# now explicitly names the global-setup file). This pin fails if either side
# drops the literal or the global-setup contract — the regression backstop a
# non-deterministic model can't talk its way past.
#
# Asserts on load_agent_spec(id).prompt_body (the parser the factory composes
# from — the established pin pattern), NOT the raw file.
# ===========================================================================


def test_getdatabase_accessor_contract_shared() -> None:
    """Producer + consumer bodies share the canonical `getDatabase` literal.

    Reverting EITHER side trips an explicit assert below:
      * drop it from the producer  → first assert fails;
      * drop it from the consumer  → second assert fails;
      * drop the global-setup file token from the consumer → third assert fails.
    """
    producer = load_agent_spec("app-code-generator").prompt_body
    consumer = load_agent_spec("app-test-implementation").prompt_body

    # Producer: the DB module exports the accessor as the canonical NAMED export.
    assert "getDatabase" in producer, (
        "app-code-generator body must carry the canonical DB-accessor literal "
        "`getDatabase` (the named-export contract the consumer imports against)"
    )
    # The contract is a NAMED export, never a default — the exact phrasing the
    # producer must keep so the consumer's named import compiles.
    assert "NAMED export" in producer and "default export" in producer, (
        "app-code-generator body must state the accessor is a NAMED export and "
        "never a default export"
    )

    # Consumer: the same literal — single source of truth (13-03 pattern).
    assert "getDatabase" in consumer, (
        "app-test-implementation body must carry the SAME canonical literal "
        "`getDatabase` (a divergent name re-introduces the ISS-006 TS2305 drift)"
    )
    # Consumer: the Contract-fidelity rule now explicitly names the Jest/Vitest
    # global-setup file — the scope gap that was the ISS-006 root cause.
    assert ("tests/setup.ts" in consumer) or ("globalSetup" in consumer), (
        "app-test-implementation body must name the global-setup file "
        "(`tests/setup.ts` / `globalSetup`) inside the Contract-fidelity rule"
    )


# ===========================================================================
# Frontmatter freeze — T-15-01 mitigation made durable.
# 15-01 edited bodies ONLY; the five agents' identity/ordering/tool grants are
# frozen here so a future "cleanup" cannot silently change behavior.
# NOTE: od-ppt-validator's tools=[workspace] is INTENTIONAL (frontmatter is
# authoritative); do not "normalize" it to [] (RESEARCH Pitfall 4).
# ===========================================================================


# Frozen expectations captured from the current frontmatter. Every field here
# is behavior-bearing: guardrails change the composed system prompt the
# contract lines live in; context_from changes what "already included in this
# message as context" actually contains; max_tokens / injects / gate change
# output limits, template injection, and gating identity.
_FROZEN_FRONTMATTER = {
    "od-ppt-validator": {
        "order": 3,
        "pipeline_type": "od_ppt",
        "tools": ["workspace"],
        "guardrails": [],
        "context_from": ["$previous"],
        "max_tokens": 32768,
        "injects": [],
        "gate": None,
    },
    "app-sdlc-governance": {
        "order": 15,
        "pipeline_type": "app_builder",
        "tools": [],
        "guardrails": [],
        "context_from": [
            "material-analyzer",
            "app-system-design",
            "app-security-architecture",
            "app-code-compliance",
            "app-devops",
            "app-test-compliance",
        ],
        "max_tokens": 12000,
        "injects": [],
        "gate": None,
    },
    "dotnet-sdlc-governance": {
        "order": 13,
        "pipeline_type": "dotnet_to_azure",
        "tools": [],
        "guardrails": ["dotnet"],
        "context_from": [
            "dotnet-security-architecture",
            "dotnet-azure-bicep",
            "dotnet-code-compliance",
            "dotnet-test-compliance",
            "dotnet-validation",
        ],
        "max_tokens": 12000,
        "injects": [],
        "gate": None,
    },
    "mulesoft-sdlc-governance": {
        "order": 13,
        "pipeline_type": "mulesoft_to_springboot",
        "tools": [],
        "guardrails": ["mulesoft", "java-spring"],
        "context_from": [
            "mulesoft-security-architecture",
            "mulesoft-aws-infra",
            "mulesoft-code-compliance",
            "mulesoft-test-compliance",
            "mulesoft-validation",
        ],
        "max_tokens": 12000,
        "injects": [],
        "gate": None,
    },
    "app-infra-generator": {
        "order": 10,
        "pipeline_type": "app_builder",
        "tools": ["workspace"],
        "guardrails": [],
        "context_from": ["material-analyzer", "app-code-generator"],
        "max_tokens": 16000,
        "injects": [],
        "gate": None,
    },
}


@pytest.mark.parametrize("agent_id", sorted(_FROZEN_FRONTMATTER))
def test_contract_agents_frontmatter_frozen(agent_id: str) -> None:
    """All behavior-bearing frontmatter fields are frozen (bodies-only phase).

    Pins order / pipeline_type / tools / guardrails / context_from /
    max_tokens / injects / gate so a future "cleanup" cannot silently change
    the composed prompt, context routing, or runtime identity the Phase-15
    contract lines depend on.
    """
    spec = load_agent_spec(agent_id)
    frozen = _FROZEN_FRONTMATTER[agent_id]
    assert spec.order == frozen["order"]
    assert spec.pipeline_type == frozen["pipeline_type"]
    assert list(spec.tools) == frozen["tools"]
    assert list(spec.guardrails) == frozen["guardrails"]
    assert list(spec.context_from) == frozen["context_from"]
    assert spec.max_tokens == frozen["max_tokens"]
    assert list(spec.injects) == frozen["injects"]
    assert spec.gate == frozen["gate"]


# ===========================================================================
# LV-02 composition pin — contract-shaped validator output resolves to the
# deck through the REAL engine + REAL PptResolver + REAL prompts (only the
# model is scripted). Reproduces the live LV-02 evidence shape: multi-sentence
# QA narration FIRST, single artifact-wrapped COMPLETE deck second — and
# asserts the narration does NOT win the unwrap.
#
# ZERO edits to _scripted_model.py / live_harness.py (the od_ppt goldens pin
# that module's validator bytes — RESEARCH Pitfall 1): the contract-shaped
# validator is a PER-TEST model injected via the per-agent model factory.
# ===========================================================================

# A small COMPLETE deck on the LV-02 evidence shape: full <!DOCTYPE html>
# document, <section class="slide"> elements (first one active), minimal nav
# script. No <style> block → sanitize_carousel_deck_html is a no-op on it.
_DECK = (
    "<!DOCTYPE html><html><head><title>Phase 15 LV-02 pin</title></head><body>"
    '<section class="slide active"><h1>Title</h1></section>'
    '<section class="slide"><h2>Closing</h2></section>'
    "<script>document.addEventListener('keydown',()=>{});</script>"
    "</body></html>"
)

# Multi-sentence QA commentary FIRST — the live LV-02 failure shape (the
# validator streamed 1,350 chars of narration before a small artifact).
# Contains no `<artifact` token, so it cannot win the first-match unwrap.
_NARRATION = "Running the final QA pass. P0 checks complete - one fix applied.\n"


def _model_for(agent_id: str) -> ScriptedFakeChatModel:
    """Per-agent factory: contract-shaped validator, stock scripts otherwise."""
    if agent_id == "od-ppt-validator":
        return ScriptedFakeChatModel(
            [
                _ScriptedTurn(
                    texts=[
                        _NARRATION,
                        '<artifact identifier="deck" type="text/html" title="Deck">'
                        + _DECK
                        + "</artifact>",
                    ],
                    usage=(22, 14),
                )
            ]
        )
    return ScriptedFakeChatModel(_scripts_for(agent_id))


@pytest.mark.asyncio
async def test_od_ppt_deck_resolution_with_contract_shaped_validator() -> None:
    """Contract-shaped validator output → resolved final_output IS the deck."""
    result = await drive_engine_pipeline(
        "od_ppt",
        model=_model_for,
        fake_planner=True,
        gate_agent_ids=(),
        # The od_ppt agents declare injects=[template, design_system]; seed the
        # od_context exactly as _scripted_model._drive does so _compose_injection
        # does not raise TemplateMissingError.
        od_context={
            "template_body": "## Workflow\nUse .card and .grid classes. Build pages into <section data-page>.",
            "template_id": "web-prototype",
            "ds_id": "default",
            "ds_body": ":root{--bg:#fff;--fg:#111;--accent:#06f;--surface:#f6f6f6;--border:#ddd;--muted:#888;}",
            "craft_block": "Keep markup semantic; wire every nav link.",
            "is_design_system_required": True,
        },
    )

    assert result.completed is True
    assert result.error is None

    fo = result.final_output
    assert isinstance(fo, str)
    # The resolver unwrapped the single artifact → the deck, from byte one.
    assert fo.lstrip().startswith("<!DOCTYPE html>")
    assert '<section class="slide"' in fo
    # The QA narration did NOT win — the LV-02 failure mode.
    assert "Running the final QA pass" not in fo
    # Engine world mirrors deliverable == final_output.
    assert result.deliverable == fo
