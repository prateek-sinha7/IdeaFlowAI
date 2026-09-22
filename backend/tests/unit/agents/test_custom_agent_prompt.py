"""spec 012 T11 — custom-agent prompt composition (R-14, F-06).

Pins two shapes of ``_compose_system_prompt``'s ``prompt_body`` block:

  * a ``custom-agent:<instance_id>`` spec — the composed prompt_body is the
    baked preamble, then the instance's own ``prompt`` (``ctx.step_prompt``),
    then an artifact instruction naming the exact filename ``artifact_name``
    produces, in that order (R-14).
  * a built-in agent — composition is BYTE-IDENTICAL to today (R-16 parity);
    the new ``step_prompt``/``topic`` fields are pure no-ops when absent.
"""

from __future__ import annotations

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec
from agents.workflows.artifacts import artifact_name

_BUILTIN_AGENT_ID = "domain-analyst"


def _compose(agent_id: str, ctx: AgentContext) -> str:
    spec = load_agent_spec(agent_id)
    return _compose_system_prompt(spec, ctx, no_tools=False)


def test_custom_agent_composes_preamble_then_instance_prompt_then_artifact_instruction():
    ctx = AgentContext(
        user_request="Build a CRM",
        step_prompt="Research the competitive landscape.",
        topic="crm-rollout",
    )
    composed = _compose("custom-agent:research-a", ctx)

    preamble = load_agent_spec("custom-agent").prompt_body
    expected_filename = artifact_name("research-a", "crm-rollout")

    assert preamble in composed
    assert "Research the competitive landscape." in composed
    assert expected_filename in composed

    preamble_idx = composed.index(preamble)
    instance_idx = composed.index("Research the competitive landscape.")
    filename_idx = composed.index(expected_filename)
    assert preamble_idx < instance_idx < filename_idx


def test_custom_agent_with_roster_orders_preamble_then_prompt_then_roster_then_artifact():
    """spec 012 T35 (R-14, R-15, AC-10): when the engine sets ``ctx.roster`` (a
    custom agent with children), it lands AFTER the instance prompt and BEFORE the
    artifact instruction — preamble -> instance prompt -> roster -> artifact."""
    roster_block = (
        "Earlier steps produced:\n"
        "- Research A → research-a.crm-rollout.md\n"
        "Read the files you need before you start."
    )
    ctx = AgentContext(
        user_request="Build a CRM",
        step_prompt="Research the competitive landscape.",
        topic="crm-rollout",
        roster=roster_block,
    )
    composed = _compose("custom-agent:research-a", ctx)

    preamble = load_agent_spec("custom-agent").prompt_body
    expected_filename = artifact_name("research-a", "crm-rollout")

    assert preamble in composed
    assert "Research the competitive landscape." in composed
    assert roster_block in composed
    assert expected_filename in composed

    preamble_idx = composed.index(preamble)
    instance_idx = composed.index("Research the competitive landscape.")
    roster_idx = composed.index(roster_block)
    filename_idx = composed.index(expected_filename)
    assert preamble_idx < instance_idx < roster_idx < filename_idx


def test_custom_agent_with_no_roster_is_byte_identical_to_baseline():
    """R-16: a step with no children (``ctx.roster == ""``, the default) composes
    identically to before ``roster`` existed on ``AgentContext``."""
    ctx_no_roster = AgentContext(
        user_request="Build a CRM",
        step_prompt="Research the competitive landscape.",
        topic="crm-rollout",
    )
    ctx_explicit_empty = AgentContext(
        user_request="Build a CRM",
        step_prompt="Research the competitive landscape.",
        topic="crm-rollout",
        roster="",
    )

    baseline = _compose("custom-agent:research-a", ctx_no_roster)
    explicit_empty = _compose("custom-agent:research-a", ctx_explicit_empty)

    assert baseline == explicit_empty
    assert "Earlier steps produced" not in baseline


def test_custom_agent_synthetic_id_yields_instance_derived_filename():
    ctx = AgentContext(user_request="Build a CRM", topic="crm-rollout")
    composed = _compose("custom-agent:research-a", ctx)

    expected_filename = artifact_name("research-a", "crm-rollout")
    assert expected_filename in composed
    # The synthetic agent id's colon must never leak into the filename (F-02).
    assert "custom-agent:research-a." not in composed
    assert ":" not in expected_filename


def test_builtin_agent_composition_is_byte_identical_to_baseline():
    ctx_baseline = AgentContext(user_request="Build a todo app")
    ctx_with_new_fields_defaulted = AgentContext(
        user_request="Build a todo app", step_prompt="", topic=""
    )

    baseline = _compose(_BUILTIN_AGENT_ID, ctx_baseline)
    with_defaults = _compose(_BUILTIN_AGENT_ID, ctx_with_new_fields_defaulted)

    assert baseline == with_defaults
