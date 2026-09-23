"""tests/agents/test_m5_chat_migration.py — Phase M batch M5 (`chat`).

GIT_VERSIONING_TASKS.md Phase M row M5 migrates the 7 `chat-*` AGENT.md files
(the free-form chat pipeline, `agents/workflows/chat/`) onto `prompt_policy:
body_only` per the §3 recipe.

`chat` is NOT driven through the `ExecutionEngine` — it runs on the separate
`ChatRunner` sequencer (`app/agents/chat_runner.py`), which calls
`agents.factory.create_runner("chat-<x>", ctx)` directly for each of the 7
agents (text-only: `tools: []` → `exclude_builtin_tools=True` → no filesystem
tools bound) and folds prior-phase output into the next agent's task message
itself (`ChatRunner._compose_message`), never through a `.agents/` sandbox
file. So the world-block gate in `engine.py::_compose_context_message`
(`_is_migrated`) never applies to these agents — `test_seam2_gate_v3.py`
skips `chat` for exactly this reason (see its `_skip_reason`).

What DOES apply to `chat`, because `ChatRunner` reuses the shared
`agents.factory.create_runner` → `_compose_system_prompt` seam: `prompt_policy`
still governs SYSTEM PROMPT assembly (Requirement 29). For a tool-less agent
(`no_tools=True`, exactly what `create_runner` computes for every chat-*
agent), the `default` policy prepends a `## Tool Availability` preamble;
`body_only` must not. This is the real, load-bearing behavioural surface for
this batch — proven here through the production `_compose_system_prompt`
function (not reimplemented), with a same-agent default-policy contrast so
the check would fail if `prompt_policy` were unset (broken feature).

Offline-safe: no LLM calls, no Postgres, no Chromium.
"""

from __future__ import annotations

import dataclasses

import pytest

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec

_CHAT_AGENT_IDS: tuple[str, ...] = (
    "chat-discovery",
    "chat-requirements",
    "chat-user-stories",
    "chat-ppt",
    "chat-prototype",
    "chat-ui-design",
    "chat-preview",
)


def _ctx() -> AgentContext:
    return AgentContext(user_request="Build me a todo app")


@pytest.mark.parametrize("agent_id", _CHAT_AGENT_IDS)
def test_chat_agent_is_migrated_off_default(agent_id: str) -> None:
    """Every chat-* agent declares prompt_policy: body_only (none carry
    guardrails/hooks/a Constitution in practice, so body_only — not
    governance — is the correct §3 recipe choice)."""
    spec = load_agent_spec(agent_id)
    assert spec.prompt_policy == "body_only", (
        f"{agent_id}: expected prompt_policy=body_only, got {spec.prompt_policy!r}"
    )


@pytest.mark.parametrize("agent_id", _CHAT_AGENT_IDS)
def test_chat_agent_has_sandbox_reading_guide(agent_id: str) -> None:
    spec = load_agent_spec(agent_id)
    assert "## Sandbox Reading Guide" in (spec.prompt_body or ""), (
        f"{agent_id}: AGENT.md is missing the Sandbox Reading Guide"
    )


@pytest.mark.parametrize("agent_id", _CHAT_AGENT_IDS)
def test_chat_agent_composed_prompt_has_no_leaked_tool_preamble(agent_id: str) -> None:
    """The real production seam (`create_runner` -> `_compose_system_prompt`),
    called with `no_tools=True` (the value `create_runner` computes for every
    chat-* agent, since they all declare `tools: []`), must NOT prepend the
    '## Tool Availability' preamble now that they are on body_only — the
    composed prompt must be exactly the agent's AGENT.md body.
    """
    spec = load_agent_spec(agent_id)
    composed = _compose_system_prompt(spec, _ctx(), no_tools=True, has_write_access=False)
    assert composed == spec.prompt_body, (
        f"{agent_id}: body_only composition must equal the raw AGENT.md body; "
        f"got extra content (len {len(composed)} vs body len {len(spec.prompt_body or '')})"
    )
    assert "## Tool Availability" not in composed, (
        f"{agent_id}: body_only composition leaked the tool-availability preamble"
    )


def test_default_policy_control_would_leak_the_preamble() -> None:
    """Contrast case proving the check above is real, not vacuous: the SAME
    agent, with prompt_policy reset to default (the pre-migration state),
    DOES get the '## Tool Availability' preamble under no_tools=True — so
    the body_only assertion above would have failed before this batch set
    the switch.
    """
    spec = dataclasses.replace(load_agent_spec("chat-discovery"), prompt_policy=None)
    composed = _compose_system_prompt(spec, _ctx(), no_tools=True, has_write_access=False)
    assert "## Tool Availability" in composed, (
        "control: default policy must still emit the tool-availability preamble "
        "for a tool-less agent — otherwise the body_only assertions above prove nothing"
    )
