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
    """design_system → craft → template, in that order.

    NOTE: the leading "CRITICAL OUTPUT RULES" section was deliberately removed
    from ``_compose_injection`` in commit d1a338fd ("fix: custom workflow with
    prototype/ppt agents now runs correctly", FIX-017 / 2026-06-17) — it was
    prototype-specific (single-page routing rules) and contradicted the PPT
    composer's deck output contract. Each injects-declaring agent now carries
    its own complete output contract in its AGENT.md body.
    """
    spec = _Spec(injects=["template", "design_system", "craft"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    block = _compose_injection(spec, ctx, spec.injects)

    # All sections present
    assert "ACTIVE DESIGN SYSTEM: minimal" in block
    assert "DESIGN SYSTEM TOKENS" in block
    assert "CRAFT RULES BLOCK" in block
    assert "ACTIVE TEMPLATE SKILL: web-prototype" in block
    assert "TEMPLATE SKILL BODY" in block

    # Order: design_system < craft < template
    assert block.index("ACTIVE DESIGN SYSTEM") < block.index("CRAFT RULES BLOCK")
    assert block.index("CRAFT RULES BLOCK") < block.index("ACTIVE TEMPLATE SKILL")


def test_full_system_prompt_role_last():
    """The role prompt body must come AFTER the injection block."""
    spec = _Spec(injects=["template", "design_system", "craft"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    prompt = _compose_system_prompt(spec, ctx)
    assert prompt.index("ACTIVE TEMPLATE SKILL") < prompt.index("ROLE PROMPT BODY")
    assert prompt.index("ACTIVE DESIGN SYSTEM") < prompt.index("ROLE PROMPT BODY")


def test_brief_analyst_no_craft():
    """Brief analyst (injects without craft) gets design + template, no craft."""
    spec = _Spec(injects=["template", "design_system"])
    ctx = AgentContext(user_request="x", od_context=_od_context())

    block = _compose_injection(spec, ctx, spec.injects)
    assert "ACTIVE DESIGN SYSTEM" in block
    assert "ACTIVE TEMPLATE SKILL" in block
    assert "CRAFT RULES BLOCK" not in block


# ---------------------------------------------------------------------------
# Template missing error
# ---------------------------------------------------------------------------


def test_template_missing_raises():
    """od_context is present (a real od_* run) but lacks template_body — this is
    a genuine configuration error and must still halt the run.

    NOTE: commit d1a338fd ("fix: custom workflow with prototype/ppt agents now
    runs correctly") narrowed this raise to only fire when od_context is
    non-empty (see test_no_od_context_skips_when_absent below) — a completely
    absent od_context now means "custom run with no template context" and is
    skipped silently rather than raising.
    """
    spec = _Spec(injects=["template"])
    ctx = AgentContext(user_request="x", od_context={"ds_id": "minimal"})  # no template_body
    with pytest.raises(TemplateMissingError, match="template"):
        _compose_injection(spec, ctx, spec.injects)


def test_no_od_context_skips_when_absent():
    """A completely absent od_context (custom workflow with no template
    context) skips injection silently instead of raising — see commit
    d1a338fd, point 3: "factory.py: _compose_injection() raised
    TemplateMissingError when od_context was empty. Now returns empty string
    (skips injection) when od_context is completely absent -- correct for
    custom runs that have no template context."
    """
    spec = _Spec(injects=["template"])
    ctx = AgentContext(user_request="x", od_context=None)
    assert _compose_injection(spec, ctx, spec.injects) == ""


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


# ---------------------------------------------------------------------------
# WIRE-03 — per-step injects merge (D-16, materialize-and-consume)
# ---------------------------------------------------------------------------
#
# The compiled ``Step.injects`` reach the factory via ``AgentContext.step_injects``
# (engine threads them off ``ectx.current_step``). ``_compose_system_prompt`` merges
# them order-stably with ``spec.injects`` (AGENT.md). The merge keys on the generic
# ``step_injects`` list — NO workflow/agent-name branch (SC-001).


def test_step_injects_empty_is_byte_identical_no_op():
    """step_injects == [] → composed prompt is byte-identical to the AGENT.md-only
    path. This IS the mechanical INV-3 proof (the goldens declare no per-step injects).
    """
    spec = _Spec(injects=["template", "design_system", "craft"])
    od = _od_context()
    baseline = _compose_system_prompt(
        spec, AgentContext(user_request="x", od_context=od)
    )
    with_empty = _compose_system_prompt(
        spec, AgentContext(user_request="x", od_context=od, step_injects=[])
    )
    assert with_empty == baseline


def test_step_injects_merge_adds_step_inject_no_duplication():
    """spec.injects=["template"] + step_injects=["craft"] → the effective inject SET
    is order-stable ["template", "craft"]: the step-declared craft is added (the
    AGENT.md-only path would render NO craft) exactly once.

    Note: the canonical SECTION render order inside ``_compose_injection`` is fixed
    (critical → design_system → craft → template) and independent of the effective
    list order — the merge's contract is SET membership + de-duplication, not section
    placement. So we assert craft is now present (it was absent in the spec-only path)
    and not doubled, NOT a template-vs-craft section position.
    """
    spec = _Spec(injects=["template"])
    od = _od_context()

    # Baseline: spec-only path renders template, NO craft.
    baseline = _compose_system_prompt(
        spec, AgentContext(user_request="x", od_context=od)
    )
    assert "CRAFT RULES BLOCK" not in baseline

    # Merge: the step adds craft.
    ctx = AgentContext(user_request="x", od_context=od, step_injects=["craft"])
    prompt = _compose_system_prompt(spec, ctx)

    # Both sections present (template from AGENT.md, craft from the step merge).
    assert "ACTIVE TEMPLATE SKILL: web-prototype" in prompt
    assert "CRAFT RULES BLOCK" in prompt
    # No duplication of the craft block.
    assert prompt.count("CRAFT RULES BLOCK") == 1


def test_step_injects_no_duplicate_when_already_in_spec():
    """A step inject already declared in spec.injects is NOT applied twice."""
    spec = _Spec(injects=["template", "craft"])
    od = _od_context()
    ctx = AgentContext(user_request="x", od_context=od, step_injects=["craft"])

    prompt = _compose_system_prompt(spec, ctx)
    assert prompt.count("CRAFT RULES BLOCK") == 1
