"""011 characterization baseline — the system prompt around SKILLS (spec 011 T1).

Pins the composed system prompt for a text-only agent in the two configurations
spec 011 must not change:

    prompt_text_only_no_skills — nothing attached. The R-04 regression guard: a run
        with no attached skills must produce a BYTE-IDENTICAL prompt after skills
        move to native progressive disclosure.
    prompt_disk_skill_only — the per-user disk ``SKILL.md`` (``ectx.disk_skills``),
        which stays EAGERLY injected (spec 011 §5 / D6). Deleting the attached-skill
        block must not take this block with it — this golden is the only thing that
        catches that, because the disk skill reaches the prompt through the SAME
        ``attached_skills`` field today.

Goldens are committed under ``characterization/golden/`` and regenerated only
DELIBERATELY with ``SNAPSHOT_UPDATE=1`` — never as a way to make a failure go away.
"""

from __future__ import annotations

import pytest

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec

from .characterization import (
    SNAPSHOT_UPDATE,
    read_golden_bytes,
    write_golden_bytes,
)

# A text-only agent (tools: []) — the class that carries _NO_TOOLS_PREAMBLE and the
# class spec 011 changes most (61 of 87 agents are text-only).
_AGENT_ID = "domain-analyst"

# Stand-in for ``ectx.disk_skills[agent_id]``, which the engine appends to
# attached_skills as a name-less ``{"content": ...}`` entry (engine.py ~3453).
_DISK_SKILL_BODY = "DISK SKILL BODY\n\nAlways answer in exactly one sentence."


def _compose(ctx: AgentContext) -> bytes:
    spec = load_agent_spec(_AGENT_ID)
    return _compose_system_prompt(spec, ctx, no_tools=True).encode("utf-8")


def _assert_golden(name: str, actual: bytes) -> None:
    if SNAPSHOT_UPDATE:
        assert actual, "refusing to write an empty golden"
        write_golden_bytes(name, actual)
        pytest.skip(f"golden {name} regenerated ({len(actual)} bytes)")
    expected = read_golden_bytes(name)
    assert expected is not None, (
        f"golden {name} missing — generate it once with SNAPSHOT_UPDATE=1"
    )
    assert actual == expected, (
        f"composed system prompt changed for {name}. If this is spec 011 work, the "
        f"change is a REGRESSION (R-04 / D6), not a golden to re-baseline."
    )


def test_text_only_no_skills_prompt_is_stable():
    """R-04: nothing attached ⇒ the prompt must not move at all."""
    ctx = AgentContext(user_request="Build a todo app", attached_skills=[])
    _assert_golden("prompt_text_only_no_skills.txt", _compose(ctx))


def test_disk_skill_only_prompt_is_stable():
    """D6: the per-user disk skill keeps its eager block, now delivered via its own
    ``disk_skill`` field rather than ``attached_skills``, after the attached-skill block goes."""
    ctx = AgentContext(user_request="Build a todo app", disk_skill=_DISK_SKILL_BODY)
    _assert_golden("prompt_disk_skill_only.txt", _compose(ctx))
