"""Guardrail injection tests for agents/factory.py.

Verifies that for an agent that declares guardrails, the full content of each
guardrail file appears verbatim — preceded by its ``## Guardrail: {name}``
header and BEFORE the prompt body — in the system prompt composed by
``agents.factory._compose_system_prompt``.

Uses domain-analyst (guardrails: [agile]) as the reference agent.

SOURCE-OF-TRUTH NOTE (Phase 7a rewrite)
---------------------------------------
This file previously patched ``app.agents.deep_agent.DeepAgent`` and called
``create_agent`` to capture the ``system_prompt`` it passed to the (now-dead)
legacy ``DeepAgent``. ``create_agent`` / ``_build_tools`` / ``DeepAgent`` are
dead pipeline-legacy removed in Phase 7a. The prompt composition itself is
UNCHANGED and still LIVE: the Phase-3 ``create_runner`` path composes the system
prompt with the SAME ``_compose_system_prompt(spec, ctx)`` helper. So these
tests now call that helper DIRECTLY — the assertions (verbatim guardrail content,
the ``## Guardrail:`` header, guardrails-before-body ordering) are identical and
cover the live composition with no dependency on the deleted runtime.

Requirements: 9.4, 3.2
"""

from __future__ import annotations

import asyncio

import pytest

from agents.factory import AgentContext, _compose_system_prompt
from agents.loader import load_agent_spec


# ---------------------------------------------------------------------------
# Task 19.5 — Guardrail injection test
# ---------------------------------------------------------------------------


class TestGuardrailInjection:
    """Assert guardrail file content appears verbatim in the composed prompt.

    Requirements: 9.4, 3.2
    """

    def _compose(self, agent_id: str, ctx: AgentContext) -> str:
        """Compose the system prompt the LIVE ``create_runner`` path would use.

        ``create_runner`` (and the deleted ``create_agent``) both build the
        system prompt via ``_compose_system_prompt(load_agent_spec(id), ctx)`` —
        calling it directly is byte-identical to what the runner receives.
        """
        spec = load_agent_spec(agent_id)
        return _compose_system_prompt(spec, ctx)

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
        system_prompt = self._compose("domain-analyst", ctx)

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
        system_prompt = self._compose("domain-analyst", ctx)

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
        system_prompt = self._compose("domain-analyst", ctx)

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
                system_prompt = self._compose(agent_id, ctx)

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


# ---------------------------------------------------------------------------
# 08-05 — PromptAssemblyPolicy (F1) + skill_provider / hook_provider (F3)
#
# These prove the lifted capabilities reproduce the inline composition BYTE-IDENTICALLY
# (RESEARCH Pitfall 2 — NEVER re-baseline) BEFORE Task 3 rewires the factory onto them.
# ---------------------------------------------------------------------------


def _compose_blocks_for(spec, ctx: AgentContext) -> dict:
    """Reconstruct the named-block mapping the factory feeds the PromptAssemblyPolicy.

    Mirrors the inline ``_compose_system_prompt`` block sources so the policy parity
    test compares the policy's join against the live inline composition. Uses the SAME
    factory helpers (injection / guardrail read / constitution) plus the lifted skill +
    behavioral-hook providers — the exact wiring Task 3 installs.
    """
    from agents.factory import (
        _GUARDRAILS_DIR,
        _compose_injection,
        _inject_constitution,
    )
    from agents.capabilities.skills.providers import UiSkillProvider
    from agents.capabilities.hooks.behavioral import BehavioralHookProvider

    blocks: dict = {}

    injects = getattr(spec, "injects", []) or []
    if injects:
        injection_block = _compose_injection(spec, ctx, injects)
        if injection_block:
            blocks["injects"] = injection_block

    guardrail_items: list[str] = []
    for guardrail_name in spec.guardrails:
        gf = _GUARDRAILS_DIR / f"{guardrail_name}.md"
        if not gf.exists():
            continue
        content = gf.read_text(encoding="utf-8")
        if content:
            guardrail_items.append(f"## Guardrail: {guardrail_name}\n\n{content}")
    if guardrail_items:
        blocks["guardrails"] = guardrail_items

    skill_blocks = asyncio.run(UiSkillProvider().provide(ctx))
    skill_contents = [b.content for b in skill_blocks if b.content]
    if skill_contents:
        blocks["skills"] = skill_contents

    hook_blocks = asyncio.run(BehavioralHookProvider().provide(ctx))
    hook_contents = [b.content for b in hook_blocks if b.content]
    if hook_contents:
        blocks["hooks"] = hook_contents

    constitution = _inject_constitution(ctx)
    if constitution:
        blocks["constitution"] = constitution

    blocks["prompt_body"] = spec.prompt_body
    return blocks


class TestPromptAssemblyPolicyParity:
    """The default ``PromptAssemblyPolicy`` reproduces the inline composition byte-for-byte."""

    def _policy(self):
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry().resolve("prompt", "default")

    def test_policy_registered_with_default_order(self):
        policy = self._policy()
        assert policy.name == "default"
        assert tuple(policy.order) == (
            "injects",
            "guardrails",
            "skills",
            "hooks",
            "constitution",
            "prompt_body",
        )

    def test_policy_byte_identical_for_guardrail_agent(self):
        """domain-analyst (guardrails:[agile]) — policy join == inline composition."""
        spec = load_agent_spec("domain-analyst")
        ctx = AgentContext(user_request="byte-parity check")
        expected = _compose_system_prompt(spec, ctx)
        actual = self._policy().assemble(_compose_blocks_for(spec, ctx), ctx)
        assert actual == expected

    def test_policy_byte_identical_with_skills_and_hooks(self):
        """An agent WITH attached skills + behavioral hooks composes byte-identically.

        Exercises the skills + hooks slots together so the policy's ordered join is
        proven against the inline path with every category present."""
        spec = load_agent_spec("domain-analyst")
        ctx = AgentContext(
            user_request="full-block parity",
            attached_skills=[
                {"name": "brand", "content": "Use the brand voice.", "version": "1.2"},
                {"name": "empty", "content": ""},  # dropped (byte-parity guard)
            ],
            attached_hooks=[
                {"name": "concise", "event": "on_response", "description": "Be concise."},
                {"name": "", "event": "x", "description": "no name → skipped"},
            ],
        )
        expected = _compose_system_prompt(spec, ctx)
        actual = self._policy().assemble(_compose_blocks_for(spec, ctx), ctx)
        assert actual == expected
        # And the composed prompt carries both the skill content and the behavioral block.
        assert "Use the brand voice." in actual
        assert "## Active Behavioral Hooks" in actual

    def test_policy_byte_identical_across_all_agents(self):
        """For EVERY existing agent, the policy join equals the inline composition."""
        from agents.loader import SUPPORTED_PIPELINE_TYPES, list_agent_ids

        stub_od_context = {
            "template_id": "parity-check",
            "template_body": "TEMPLATE BODY",
            "ds_id": "ds",
            "ds_body": "DS TOKENS",
            "craft_block": "CRAFT",
            "is_design_system_required": True,
        }
        policy = self._policy()
        for pipeline_type in sorted(SUPPORTED_PIPELINE_TYPES):
            for agent_id in list_agent_ids(pipeline_type):
                spec = load_agent_spec(agent_id)
                ctx = AgentContext(
                    user_request="parity sweep",
                    od_context=stub_od_context if getattr(spec, "injects", []) else None,
                )
                expected = _compose_system_prompt(spec, ctx)
                actual = policy.assemble(_compose_blocks_for(spec, ctx), ctx)
                assert actual == expected, f"prompt drift for agent {agent_id!r}"


class TestSkillProviderVersioning:
    """SKILL-01 — the skill_provider returns versioned blocks (not a flattened list)."""

    def _resolve(self, kind_name: str):
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry().resolve("skill", kind_name)

    def test_ui_provider_returns_versioned_blocks(self):
        provider = self._resolve("ui")
        ctx = AgentContext(
            user_request="x",
            attached_skills=[
                {"name": "brand", "content": "Brand voice.", "version": "2.0"},
                {"name": "nover", "content": "No version."},  # defaults to "ui"
                {"name": "empty", "content": ""},  # dropped
            ],
        )
        blocks = asyncio.run(provider.provide(ctx))
        assert [b.content for b in blocks] == ["Brand voice.", "No version."]
        assert blocks[0].version == "2.0"
        assert blocks[1].version == "ui"  # default version metadata present
        assert blocks[0].name == "brand"

    def test_forward_providers_are_inert(self):
        """disk/template/repo contribute nothing today (byte-parity) but are registered."""
        ctx = AgentContext(user_request="x")
        for kind_name in ("disk", "template", "repo"):
            provider = self._resolve(kind_name)
            assert provider.name == kind_name
            assert asyncio.run(provider.provide(ctx)) == []


class TestBehavioralHookProvider:
    """F3 — the behavioral hook_provider renders the legacy block byte-identically."""

    def _provider(self):
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry().resolve("hook", "behavioral")

    def test_renders_active_behavioral_hooks_block(self):
        provider = self._provider()
        ctx = AgentContext(
            user_request="x",
            attached_hooks=[
                {"name": "concise", "event": "on_response", "description": "Be concise."},
                {"name": "fallback", "event": "post", "trigger": "use trigger"},
            ],
        )
        blocks = asyncio.run(provider.provide(ctx))
        assert len(blocks) == 1
        block = blocks[0]
        assert block.kind == "behavioral"
        assert block.content.startswith("## Active Behavioral Hooks")
        assert "- **concise** (on_response): Be concise." in block.content
        assert "- **fallback** (post): use trigger" in block.content  # description or trigger

    def test_block_matches_inline_synthesis_byte_for_byte(self):
        """The provider's block equals the factory's inline ``## Active Behavioral Hooks``."""
        attached = [
            {"name": "a", "event": "e1", "description": "desc a"},
            {"name": "b", "event": "e2", "trigger": "trig b"},
        ]
        # Inline synthesis (verbatim from the factory's pre-lift code path).
        hook_lines = [
            "- **a** (e1): desc a",
            "- **b** (e2): trig b",
        ]
        inline_block = (
            "## Active Behavioral Hooks\n\n"
            "The following behavioral guidelines are active for this run. "
            "Apply them throughout your response:\n\n" + "\n".join(hook_lines)
        )
        from agents.capabilities.hooks.behavioral import render_behavioral_block

        assert render_behavioral_block(attached) == inline_block

    def test_no_named_hook_renders_nothing(self):
        """No attached hook with a name ⇒ empty list (mirrors the inline guard)."""
        provider = self._provider()
        ctx = AgentContext(user_request="x", attached_hooks=[{"event": "e", "name": ""}])
        assert asyncio.run(provider.provide(ctx)) == []
