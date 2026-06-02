"""T016 — Golden-reference test for factory.py `injects` composition.

Verifies that the factory's `_compose_injection` produces system prompt
sections in the correct order, matching the od_runner.py composition contract
documented in tests/fixtures/golden_injection_logic.md:

  critical rules → design system → craft rules → template skill body → role prompt

Also verifies:
  - TemplateMissingError raised when template declared but not loaded
  - od_ppt deck conditional: design_system only when is_design_system_required
  - section order is deterministic
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from agents.factory import (
    AgentContext,
    TemplateMissingError,
    _compose_injection,
    _compose_system_prompt,
)


@dataclass
class _Spec:
    id: str = "test-agent"
    prompt_body: str = "ROLE PROMPT BODY"
    guardrails: list[str] = field(default_factory=list)
    injects: list[str] = field(default_factory=list)


def _od_context() -> dict:
    return {
        "template_id": "web-prototype",
        "template_body": "TEMPLATE SKILL BODY",
        "ds_id": "minimal",
        "ds_body": "DESIGN SYSTEM TOKENS",
        "craft_block": "CRAFT RULES BLOCK",
    }


# ---------------------------------------------------------------------------
# Composition order
# ---------------------------------------------------------------------------


def test_full_injection_order():
    """critical → design_system → craft → template, in that order."""
    spec = _Spec(injects=["template", "design_system", "craft"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    block = _compose_injection(spec, ctx, spec.injects)

    # All sections present
    assert "CRITICAL OUTPUT RULES" in block
    assert "ACTIVE DESIGN SYSTEM: minimal" in block
    assert "DESIGN SYSTEM TOKENS" in block
    assert "CRAFT RULES BLOCK" in block
    assert "ACTIVE TEMPLATE SKILL: web-prototype" in block
    assert "TEMPLATE SKILL BODY" in block

    # Order: critical < design_system < craft < template
    assert block.index("CRITICAL OUTPUT RULES") < block.index("ACTIVE DESIGN SYSTEM")
    assert block.index("ACTIVE DESIGN SYSTEM") < block.index("CRAFT RULES BLOCK")
    assert block.index("CRAFT RULES BLOCK") < block.index("ACTIVE TEMPLATE SKILL")


def test_full_system_prompt_role_last():
    """The role prompt body must come AFTER the injection block."""
    spec = _Spec(injects=["template", "design_system", "craft"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    prompt = _compose_system_prompt(spec, ctx)
    assert prompt.index("ACTIVE TEMPLATE SKILL") < prompt.index("ROLE PROMPT BODY")
    assert prompt.index("CRITICAL OUTPUT RULES") < prompt.index("ROLE PROMPT BODY")


def test_brief_analyst_no_craft():
    """Brief analyst (injects without craft) gets critical + design + template, no craft."""
    spec = _Spec(injects=["template", "design_system"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    block = _compose_injection(spec, ctx, spec.injects)
    assert "CRITICAL OUTPUT RULES" in block
    assert "ACTIVE DESIGN SYSTEM" in block
    assert "ACTIVE TEMPLATE SKILL" in block
    assert "CRAFT RULES BLOCK" not in block


# ---------------------------------------------------------------------------
# Template missing error
# ---------------------------------------------------------------------------


def test_template_missing_raises():
    spec = _Spec(injects=["template"])
    ctx = AgentContext(user_request="x", od_context={})  # no template_body
    with pytest.raises(TemplateMissingError, match="template"):
        _compose_injection(spec, ctx, spec.injects)


def test_no_od_context_raises_for_template():
    spec = _Spec(injects=["template"])
    ctx = AgentContext(user_request="x", od_context=None)
    with pytest.raises(TemplateMissingError):
        _compose_injection(spec, ctx, spec.injects)


# ---------------------------------------------------------------------------
# od_ppt deck conditional design system
# ---------------------------------------------------------------------------


def test_deck_design_system_included_when_required():
    spec = _Spec(injects=["template", "design_system"])
    od = _od_context()
    od["is_design_system_required"] = True
    ctx = AgentContext(user_request="x", od_context=od)

    block = _compose_injection(spec, ctx, spec.injects)
    # The design-system SECTION header includes the ds_id
    assert "ACTIVE DESIGN SYSTEM: minimal" in block


def test_deck_design_system_excluded_when_not_required():
    spec = _Spec(injects=["template", "design_system"])
    od = _od_context()
    od["is_design_system_required"] = False
    ctx = AgentContext(user_request="x", od_context=od)

    block = _compose_injection(spec, ctx, spec.injects)
    # design system SECTION excluded for decks that don't require it.
    # (Note: the phrase "ACTIVE DESIGN SYSTEM" without the ds_id appears in the
    #  CRITICAL RULES text — we check for the section header with the ds_id.)
    assert "ACTIVE DESIGN SYSTEM: minimal" not in block
    assert "DESIGN SYSTEM TOKENS" not in block
    # but template still present
    assert "ACTIVE TEMPLATE SKILL" in block


# ---------------------------------------------------------------------------
# No injects = no injection block
# ---------------------------------------------------------------------------


def test_no_injects_no_injection_block():
    spec = _Spec(injects=[])
    ctx = AgentContext(user_request="x", od_context=_od_context())
    prompt = _compose_system_prompt(spec, ctx)
    assert "CRITICAL OUTPUT RULES" not in prompt
    assert prompt.strip().startswith("ROLE PROMPT BODY") or "ROLE PROMPT BODY" in prompt
