"""The factory must NOT prepend its own skills directive (retires spec 012 R-13).

R-13 originally had ``_compose_system_prompt`` emit a ``skill_directive`` block —
"Skills available at /skills/<id>/SKILL.md: <names>. Read the relevant ones…" —
as the first thing in the prompt whenever a step declared ``skills:``.

It was removed because deepagents already does the same job better. Its
``SKILLS_SYSTEM_PROMPT`` (``deepagents/middleware/skills.py:705``) lists every
staged skill with its description and the exact literal path::

    - **joke**: How to write a one-line joke about a given word. …
      -> Read `/skills/joke/SKILL.md` for full instructions

Ours printed the ``<id>`` pattern instead of the resolved path, and arrived first,
so the model met a vague version of an instruction it would meet again, precisely,
1,500 words later. Two instructions about the same files is worse than one.

These tests pin the ABSENCE. Without them the block is easy to reintroduce — it
looks like a helpful nudge in isolation, and the reason it is wrong lives in a
library file nobody reads.
"""

from __future__ import annotations

from agents.capabilities.prompt.policy import DEFAULT_ORDER
from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec

# A built-in, tool-having agent (not text-only) so ``tool_availability`` never
# competes for the "first block" slot.
_AGENT_ID = "domain-analyst"


def _compose(ctx: AgentContext) -> str:
    spec = load_agent_spec(_AGENT_ID)
    return _compose_system_prompt(spec, ctx, no_tools=False)


def test_step_skills_add_nothing_to_the_composed_prompt():
    """Declaring skills changes what is STAGED, not what the factory writes.

    The skills still reach the agent — ``stage_skills`` writes each SKILL.md into
    the sandbox and points deepagents at ``/skills`` — but that happens on the
    filesystem seam, not in this prompt.
    """
    with_skills = _compose(AgentContext(user_request="Build a todo app", step_skills=["some-skill"]))
    without = _compose(AgentContext(user_request="Build a todo app"))

    assert with_skills == without


def test_no_skills_directive_text_anywhere():
    composed = _compose(AgentContext(user_request="Build a todo app", step_skills=["some-skill"]))

    assert "Skills available at /skills/" not in composed
    assert "/skills/<id>/SKILL.md" not in composed
    # The skill id must not leak in either — naming it is what made the old block
    # read as an instruction to go find something.
    assert not composed.startswith("Skills available")


def test_the_slot_is_gone_from_the_policy_order():
    """Not merely unused — removed, so it cannot be quietly repopulated."""
    assert "skill_directive" not in DEFAULT_ORDER


def test_empty_and_absent_step_skills_are_identical():
    """Unchanged from the original R-16 guarantee."""
    baseline = _compose(AgentContext(user_request="Build a todo app"))
    explicit_empty = _compose(AgentContext(user_request="Build a todo app", step_skills=[]))

    assert baseline == explicit_empty
