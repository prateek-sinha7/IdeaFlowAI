"""Prompt-surface tests — WHAT actually goes into the model (offline, 0 tokens).

The scenario evals deliberately ignore the prompt (scripted model). These
tests close that gap for the composition half: for both revision-pipeline
agents they assert, against the REAL loader + REAL prompt-composition path
(`agents.factory._compose_system_prompt` — the exact function `create_runner`
calls), that the model would receive the right thing:

  * the right agents, in the right order, with the right tool-sets;
  * the `html-prototype` guardrail injected VERBATIM (file content ⊂ prompt);
  * each agent's AGENT.md body present (distinctive, load-bearing lines);
  * the revision agent's critical behavioral instructions intact (the
    read-context mandate, the wiring mandate, the don't-paste-HTML contract);
  * the runtime dispatch message (user turn): instruction verbatim + the
    file pointer, with the giant inline HTML slimmed away.

Use `./run-eval.sh prompts` to DUMP the fully composed prompts to files for
human review — these tests are the machine-checked subset of that surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.eval

INSTRUCTION = "Make the Save button on Settings actually save"

# Inline rather than a fixtures/*.html file — this test only needs SOME
# prototype HTML to exercise the slimming path, not real page content.
_MINI_HTML = (
    '<!doctype html><html><body><section id="dashboard">'
    "<h2>Dashboard</h2></section></body></html>"
)

_BACKEND_ROOT = Path(__file__).resolve().parents[5]
GUARDRAIL_PATH = _BACKEND_ROOT / "agents" / "guardrails" / "html-prototype.md"

AGENTS = ("prototype-revision-agent", "prototype-revision-validate")


def _compose(agent_id: str) -> str:
    """Compose the system prompt exactly as create_runner would (no model call)."""
    from agents.factory import AgentContext, _compose_system_prompt
    from agents.loader import load_agent_spec

    spec = load_agent_spec(agent_id)
    ctx = AgentContext(user_request=INSTRUCTION)
    return _compose_system_prompt(spec, ctx)


# ── Right agents, right specs ────────────────────────────────────────────────


def test_pipeline_has_exactly_the_two_revision_agents() -> None:
    """Registry membership == compiled manifest steps == the two known agents."""
    from agents.execution_engine.engine import compile_for_run
    from agents.registry import get_pipeline_agents

    registry_ids = [s.id for s in get_pipeline_agents("prototype_revision")]
    compiled_ids = [s.agent_id for s in compile_for_run("prototype_revision").steps]
    assert registry_ids == compiled_ids == list(AGENTS)


@pytest.mark.parametrize("agent_id", AGENTS)
def test_agent_spec_declares_workspace_tools_and_guardrail(agent_id) -> None:
    from agents.loader import load_agent_spec

    spec = load_agent_spec(agent_id)
    assert spec.pipeline_type == "prototype_revision"
    assert spec.tools == ["workspace"]           # native fs tools → edits real files
    assert spec.guardrails == ["html-prototype"]  # the one guardrail both must carry


# ── Guardrail injected verbatim ──────────────────────────────────────────────


@pytest.mark.parametrize("agent_id", AGENTS)
def test_html_prototype_guardrail_injected_verbatim(agent_id) -> None:
    """The guardrail FILE content appears verbatim in the composed prompt —
    not a summary, not a reference, the actual rules the model must follow."""
    guardrail_text = GUARDRAIL_PATH.read_text(encoding="utf-8").strip()
    assert guardrail_text, "guardrail file is empty/missing"

    prompt = _compose(agent_id)
    assert guardrail_text in prompt


# ── AGENT.md bodies present, load-bearing lines intact ───────────────────────


@pytest.mark.parametrize("agent_id", AGENTS)
def test_current_agent_md_body_injected_verbatim(agent_id) -> None:
    """The ENTIRE current AGENT.md body (text after the frontmatter) appears
    verbatim in the composed prompt — what's on disk right now IS what the
    model gets, byte-for-byte, not a summary or a stale cache.

    Caveat this test pins around: `_compose_system_prompt` swaps the body for a
    per-user prompt OVERRIDE when `ctx.user_id` has one saved (KAN-76). We
    compose with no user_id (the canonical path); a second check uses a
    throwaway user_id to prove that an override-less user gets the same body.
    """
    import frontmatter

    from agents.factory import AgentContext, _compose_system_prompt
    from agents.loader import load_agent_spec

    agent_md = _BACKEND_ROOT / "agents" / "prompts" / agent_id / "AGENT.md"
    body_on_disk = frontmatter.loads(agent_md.read_text(encoding="utf-8")).content
    assert body_on_disk.strip(), f"{agent_md} has an empty body"

    spec = load_agent_spec(agent_id)
    # Loader parses the same file → same body (guards a stale _SPEC_CACHE).
    assert spec.prompt_body.strip() == body_on_disk.strip()

    # Canonical path (no user_id): body verbatim in the composed prompt.
    prompt = _compose_system_prompt(spec, AgentContext(user_request=INSTRUCTION))
    assert spec.prompt_body.strip() in prompt

    # Override path: a user with NO saved override still gets the disk body.
    prompt_u = _compose_system_prompt(
        spec,
        AgentContext(user_request=INSTRUCTION, user_id="eval-no-override-user"),
    )
    assert spec.prompt_body.strip() in prompt_u


def test_revision_agent_prompt_carries_its_behavioral_contract() -> None:
    """The distinctive, load-bearing instructions of prototype-revision-agent —
    the ones a prompt-tuning pass must not silently lose."""
    prompt = _compose("prototype-revision-agent")

    # Mandatory read-context sequence (design.md before any style change).
    assert "FIRST TOOL CALLS" in prompt
    assert 'read_file("design.md")' in prompt
    # The wiring mandate — the #1 failure mode its own prompt warns about.
    assert "make the change actually WORK" in prompt
    assert "routes" in prompt and "navigateTo" in prompt
    # The delivery contract: edit the file, never paste HTML into the reply.
    assert "edit_file" in prompt
    assert "is the deliverable" in prompt


def test_validate_agent_prompt_carries_its_checklist() -> None:
    prompt = _compose("prototype-revision-validate")

    assert "Revision Validation Agent" in prompt
    assert "DESIGN SYSTEM TOKEN COMPLIANCE" in prompt
    assert "EMPTY PAGES" in prompt
    # Must not undo the revision agent's work.
    assert "Do NOT undo changes the revision agent made" in prompt


def test_prompts_are_distinct_per_agent() -> None:
    """Guard against a composition bug collapsing both agents onto one body."""
    a = _compose("prototype-revision-agent")
    b = _compose("prototype-revision-validate")
    assert a != b
    assert "FIRST TOOL CALLS" not in b          # revision-agent body not leaked
    assert "DESIGN SYSTEM TOKEN COMPLIANCE" not in a


# ── The dispatch message (the user turn the model actually receives) ─────────


def test_dispatch_message_is_instruction_plus_file_pointer() -> None:
    """After the previous_run provider slims the framed request, the model's
    user turn is: the instruction verbatim + a pointer to prototype.html —
    NOT the 60–100k-char inline HTML."""
    from agents.capabilities.context_providers.previous_run import (
        _slim_revision_message,
    )

    framed = (
        "=== REVISION REQUEST ===\n"
        f"{INSTRUCTION}\n"
        "=== END REQUEST ===\n\n"
        "=== EXISTING PROTOTYPE HTML ===\n"
        f"{_MINI_HTML}\n"
        "=== END EXISTING HTML ==="
    )
    slimmed = _slim_revision_message(framed, "prototype.html")

    assert INSTRUCTION in slimmed                       # instruction verbatim
    assert "prototype.html" in slimmed                  # the file pointer
    assert "read_file" in slimmed                       # told HOW to get it
    assert "<!doctype html>" not in slimmed             # inline HTML gone
    assert len(slimmed) < 600                           # pointer-sized, not file-sized
