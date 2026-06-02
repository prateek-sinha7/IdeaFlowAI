"""Guardrail injection tests for agents/factory.py.

Verifies that when create_agent is called for an agent that declares guardrails,
the full content of each guardrail file appears verbatim in the DeepAgent's
system_prompt.

Uses domain-analyst (guardrails: [agile]) as the reference agent.

Requirements: 9.4
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.factory import AgentContext, create_agent
from agents.loader import load_agent_spec


# ---------------------------------------------------------------------------
# Task 19.5 — Guardrail injection test
# ---------------------------------------------------------------------------


class TestGuardrailInjection:
    """Assert guardrail file content appears verbatim in the system_prompt.

    Requirements: 9.4, 3.2
    """

    _DEEP_AGENT_PATCH = "app.agents.deep_agent.DeepAgent"

    def _capture_system_prompt(self, agent_id: str, ctx: AgentContext) -> str:
        """Call create_agent and return the system_prompt passed to DeepAgent."""
        captured: dict = {}

        def _fake_deep_agent(system_prompt, tools, max_tokens, **kwargs):
            captured["system_prompt"] = system_prompt
            return MagicMock()

        with patch(self._DEEP_AGENT_PATCH, side_effect=_fake_deep_agent):
            create_agent(agent_id, ctx)

        assert "system_prompt" in captured, "DeepAgent was never instantiated"
        return captured["system_prompt"]

    def test_domain_analyst_agile_guardrail_appears_verbatim(self):
        """domain-analyst declares guardrails: [agile]; agile.md content must appear verbatim."""
        # Confirm domain-analyst has the agile guardrail
        spec = load_agent_spec("domain-analyst")
        assert "agile" in spec.guardrails, (
            "domain-analyst must declare 'agile' in its guardrails list"
        )

        # Read the actual guardrail file content
        from agents.factory import _GUARDRAILS_DIR
        agile_file = _GUARDRAILS_DIR / "agile.md"
        assert agile_file.exists(), f"agile.md not found at {agile_file}"
        agile_content = agile_file.read_text(encoding="utf-8")
        assert agile_content.strip(), "agile.md is empty"

        ctx = AgentContext(user_request="Test guardrail injection")
        system_prompt = self._capture_system_prompt("domain-analyst", ctx)

        assert agile_content in system_prompt, (
            "Full content of agile.md must appear verbatim in the system_prompt.\n"
            f"Expected to find:\n{agile_content[:200]}...\n\n"
            f"Actual system_prompt start:\n{system_prompt[:200]}..."
        )

    def test_guardrail_section_header_present(self):
        """Requirement 3.2: guardrail block must be preceded by ## Guardrail: {name}."""
        spec = load_agent_spec("domain-analyst")
        assert "agile" in spec.guardrails

        ctx = AgentContext(user_request="Test guardrail header")
        system_prompt = self._capture_system_prompt("domain-analyst", ctx)

        assert "## Guardrail: agile" in system_prompt, (
            "Expected '## Guardrail: agile' heading in system_prompt"
        )

    def test_guardrail_appears_before_prompt_body(self):
        """Requirement 3.2: guardrail content must precede the prompt body."""
        spec = load_agent_spec("domain-analyst")
        assert "agile" in spec.guardrails

        from agents.factory import _GUARDRAILS_DIR
        agile_content = (_GUARDRAILS_DIR / "agile.md").read_text(encoding="utf-8")

        ctx = AgentContext(user_request="Test guardrail ordering")
        system_prompt = self._capture_system_prompt("domain-analyst", ctx)

        guardrail_pos = system_prompt.find(agile_content)
        body_pos = system_prompt.find(spec.prompt_body)

        assert guardrail_pos != -1, "agile.md content not found in system_prompt"
        assert body_pos != -1, "prompt_body not found in system_prompt"
        assert guardrail_pos < body_pos, (
            "Guardrail content must appear before the prompt body in system_prompt"
        )

    def test_all_agents_with_guardrails_inject_content_verbatim(self):
        """For every agent that declares guardrails, each guardrail file appears verbatim."""
        from agents.factory import _GUARDRAILS_DIR
        from agents.loader import SUPPORTED_PIPELINE_TYPES, list_agent_ids

        # Agents declaring `injects` (prototype / od_ppt) need an od_context;
        # supply a stub so the composer reaches the guardrail blocks instead of
        # tripping the FR-008 missing-template guard.
        stub_od_context = {
            "template_id": "guardrail-check",
            "template_body": "TEMPLATE BODY",
            "ds_id": "ds",
            "ds_body": "DS TOKENS",
            "craft_block": "CRAFT",
            "is_design_system_required": True,
        }

        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            for agent_id in list_agent_ids(pipeline_type):
                spec = load_agent_spec(agent_id)
                if not spec.guardrails:
                    continue

                ctx = AgentContext(
                    user_request="Guardrail verbatim check",
                    od_context=stub_od_context if getattr(spec, "injects", []) else None,
                )
                system_prompt = self._capture_system_prompt(agent_id, ctx)

                for guardrail_name in spec.guardrails:
                    guardrail_file = _GUARDRAILS_DIR / f"{guardrail_name}.md"
                    if not guardrail_file.exists():
                        # Missing guardrail files are handled gracefully (warning + skip)
                        continue

                    guardrail_content = guardrail_file.read_text(encoding="utf-8")
                    assert guardrail_content in system_prompt, (
                        f"Agent {agent_id!r}: guardrail {guardrail_name!r} content "
                        f"not found verbatim in system_prompt"
                    )
