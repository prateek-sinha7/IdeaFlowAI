"""tests/agents/test_text_only_prompt_hygiene.py — F4 (13-02) text-only prompt hygiene.

Live Haiku fabricates Claude-internal tool syntax (``<function_calls>``/``<invoke>``/
``write_todos`` XML) as plain text when a composed prompt implies file/tool actions
without bound tools. Two offline-verifiable defenses are pinned here:

1. **Prompt hygiene**: agents resolved to ZERO callable tools (``tools: []`` text-only
   agents) get an explicit ``tool_availability`` no-tools preamble FIRST in the composed
   system prompt forbidding fabricated tool-call syntax. Tool-having agents (workspace /
   planning / MCP-bound) never carry the block — their composition is byte-identical.

2. **Output sanitation** (defense-in-depth): ``_strip_fabricated_tool_xml`` removes
   fabricated ``<function_calls>``/``<invoke>`` spans from the terminal done output of
   tool-less agents; clean strings pass through unchanged (identity).

3. **Engine-path sanitation** (WR-01, 13 review fix): the engine assembles each
   agent's authoritative output from ``chunk`` events (never ``done``), so the
   runner-level sanitizer alone never protected the pipeline path. The engine now
   applies ``DeepAgentRunner.sanitize_output`` (duck-typed) to its chunk-joined
   output — pinned by driving the PUBLIC ``engine.execute()`` with a scripted
   model that emits fabricated XML in its chunks. Truncated (unterminated) spans
   are stripped to end-of-string.

   That engine-driving proof lives in
   ``tests/integration/agents/test_text_only_prompt_hygiene_db.py``: ``execute()``
   opens a ``SessionLocal()`` to persist run events, which the unit-isolation guard
   rejects. The ``_strip_fabricated_tool_xml`` unit coverage of the SAME sanitizer
   stays here (sections 1-3), so the helper and the engine path are both pinned.
"""

from __future__ import annotations

import pytest

from agents.factory import (
    _NO_TOOLS_PREAMBLE,
    AgentContext,
    _compose_system_prompt,
    _resolve_runner_tools,
)
from agents.loader import load_agent_spec
from app.agents.deep_agent_runner import _strip_fabricated_tool_xml


def _compose_as_create_runner_would(agent_id: str) -> tuple[str, bool]:
    """Mirror ``create_runner``'s derivation: resolve tools FIRST, thread no_tools.

    Returns ``(composed_prompt, no_tools)``.
    """
    ctx = AgentContext(user_request="test request")
    spec = load_agent_spec(agent_id)
    custom_tools, exclude_builtin = _resolve_runner_tools(spec, ctx)
    no_tools = exclude_builtin and not custom_tools
    return _compose_system_prompt(spec, ctx, no_tools=no_tools), no_tools


# ---------------------------------------------------------------------------
# 1. Preamble ABSENT for a tools:[] text-only agent (spec 012 / R-22, D-07: the
#    universal fs grant means NO agent resolves to zero callable tools anymore,
#    so ``no_tools`` never fires and the preamble is dead for every agent).
# ---------------------------------------------------------------------------


class TestNoToolsPreamblePresence:
    def test_tools_empty_agent_gets_no_preamble(self):
        """epic-architect (tools: []) — universal fs grant means the no-tools
        preamble is now ABSENT (it no longer has zero callable tools)."""
        spec = load_agent_spec("epic-architect")
        assert spec.tools == [], "precondition: epic-architect is a tools:[] agent"

        prompt, no_tools = _compose_as_create_runner_would("epic-architect")
        assert no_tools is False
        assert _NO_TOOLS_PREAMBLE not in prompt

    def test_preamble_still_defined_and_would_be_positioned_first(self):
        """The preamble constant is retained (forward surface) and, if composed
        explicitly with ``no_tools=True``, is still ordered before guardrails and
        the prompt body — the block's OWN ordering is unchanged even though no
        live agent triggers it anymore."""
        import copy

        spec = copy.copy(load_agent_spec("epic-architect"))
        assert "agile" in spec.guardrails, "precondition: epic-architect carries agile"
        # epic-architect's AGENT.md now selects the ``governance`` policy, which
        # intentionally drops ``tool_availability``. This test pins the block's
        # position in the DEFAULT order, so select that policy explicitly.
        spec.prompt_policy = "default"

        ctx = AgentContext(user_request="test request")
        prompt = _compose_system_prompt(spec, ctx, no_tools=True)
        preamble_at = prompt.index(_NO_TOOLS_PREAMBLE)
        guardrail_at = prompt.index("## Guardrail: agile")
        body_at = prompt.index(spec.prompt_body[:80])
        assert preamble_at < guardrail_at, "preamble must precede guardrails"
        assert preamble_at < body_at, "preamble must precede the prompt body"
        assert preamble_at == 0, "tool_availability is FIRST in the default order"

    def test_preamble_forbids_fabricated_tool_syntax(self):
        """The preamble text itself still names the fabricated constructs the live
        failure produced (unchanged content, even though it no longer fires)."""
        for construct in ("<function_calls>", "<invoke>", "write_todos"):
            assert construct in _NO_TOOLS_PREAMBLE, construct


# ---------------------------------------------------------------------------
# 2. Preamble ABSENT for tool-having agents (workspace / planning)
# ---------------------------------------------------------------------------


class TestNoToolsPreambleAbsence:
    def test_workspace_agent_has_no_preamble(self):
        """app-code-generator (workspace) — native fs tools bind; preamble ABSENT."""
        spec = load_agent_spec("app-code-generator")
        assert "workspace" in spec.tools, "precondition: workspace agent"

        prompt, no_tools = _compose_as_create_runner_would("app-code-generator")
        assert no_tools is False
        assert _NO_TOOLS_PREAMBLE not in prompt
        assert "tool_availability" not in prompt

    def test_planning_agent_has_no_preamble(self):
        """deep-planner (planning) — PLANNING_TOOLS bind; preamble ABSENT."""
        spec = load_agent_spec("deep-planner")
        assert "planning" in spec.tools, "precondition: planning agent"

        prompt, no_tools = _compose_as_create_runner_would("deep-planner")
        assert no_tools is False
        assert _NO_TOOLS_PREAMBLE not in prompt

    def test_tool_having_composition_byte_identical_to_pre_f4(self):
        """A tool-having agent's blocks never carry the key — composition unchanged."""
        ctx = AgentContext(user_request="test request")
        spec = load_agent_spec("app-code-generator")
        # The pre-F4 call signature (no kwarg) and an explicit no_tools=False must
        # both equal the create_runner-derived composition, byte for byte.
        assert (
            _compose_system_prompt(spec, ctx)
            == _compose_system_prompt(spec, ctx, no_tools=False)
            == _compose_as_create_runner_would("app-code-generator")[0]
        )


# ---------------------------------------------------------------------------
# 3. Runner-level fabricated-XML sanitizer (defense-in-depth)
# ---------------------------------------------------------------------------


class TestStripFabricatedToolXml:
    def test_function_calls_span_removed(self):
        polluted = (
            "Here is the epic breakdown.\n"
            "<function_calls>\n"
            '<invoke name="write_file">\n'
            '<parameter name="path">epics.md</parameter>\n'
            "</invoke>\n"
            "</function_calls>\n"
            "## Epic 1: Onboarding\n"
        )
        cleaned = _strip_fabricated_tool_xml(polluted)
        assert "<function_calls>" not in cleaned
        assert "</function_calls>" not in cleaned
        assert "<invoke" not in cleaned
        assert "Here is the epic breakdown." in cleaned
        assert "## Epic 1: Onboarding" in cleaned

    def test_standalone_invoke_span_removed(self):
        polluted = 'before <invoke name="write_todos">{"todos": []}</invoke> after'
        cleaned = _strip_fabricated_tool_xml(polluted)
        assert "<invoke" not in cleaned
        assert "before " in cleaned and " after" in cleaned

    def test_clean_string_returned_unchanged_identity(self):
        """No pattern ⇒ the SAME object comes back (characterization byte-parity)."""
        clean = "## Epic 1\n\nAs a user, I want to sign in.\n"
        result = _strip_fabricated_tool_xml(clean)
        assert result is clean

    def test_multiple_spans_all_removed(self):
        polluted = (
            "<function_calls><invoke name='a'></invoke></function_calls>"
            "kept"
            "<function_calls><invoke name='b'></invoke></function_calls>"
        )
        assert _strip_fabricated_tool_xml(polluted) == "kept"

    def test_unterminated_function_calls_span_stripped_to_eos(self):
        """WR-01: output cut at max_tokens mid-span — no closing tag exists."""
        truncated = (
            "## Epic 1: Onboarding\nProse kept.\n"
            '<function_calls>\n<invoke name="write_file">\n<parameter name="pa'
        )
        cleaned = _strip_fabricated_tool_xml(truncated)
        assert cleaned == "## Epic 1: Onboarding\nProse kept.\n"

    def test_unterminated_invoke_cut_mid_attribute_stripped(self):
        """WR-01: truncation can land mid-attribute (no closing ``>`` either)."""
        truncated = 'Summary done.\n<invoke name="wri'
        cleaned = _strip_fabricated_tool_xml(truncated)
        assert cleaned == "Summary done.\n"

    def test_paired_spans_still_removed_before_unterminated_pass(self):
        """A closed span followed by a truncated one — both go, prose between stays."""
        polluted = (
            "<function_calls><invoke name='a'></invoke></function_calls>"
            "kept prose"
            "<function_calls><invoke name='b'>"
        )
        assert _strip_fabricated_tool_xml(polluted) == "kept prose"
