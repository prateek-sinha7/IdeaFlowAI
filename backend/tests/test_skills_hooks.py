"""
Tests for skills and hooks injection into agent system prompts.

Covers:
1. Skills content is prepended to agent system prompt
2. Hooks metadata is converted to behavioral guidelines and injected
3. Multiple skills/hooks are all injected
4. Empty skills/hooks produce no extra blocks
5. Guardrails + skills + hooks stack in the correct order
6. Hooks with no content field (the original bug) now work
7. Custom skill content (user-pasted) is injected correctly
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add backend root to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.factory import AgentContext, _compose_system_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(
    prompt_body: str = "## Agent prompt body",
    guardrails: list[str] | None = None,
    tools: list[str] | None = None,
) -> MagicMock:
    spec = MagicMock()
    spec.prompt_body = prompt_body
    spec.guardrails = guardrails or []
    spec.tools = tools or []
    return spec


def _make_ctx(
    attached_skills: list[dict] | None = None,
    attached_hooks: list[dict] | None = None,
    disk_skill: str | None = None,
) -> AgentContext:
    return AgentContext(
        user_request="test request",
        agent_outputs={},
        attached_skills=attached_skills or [],
        attached_hooks=attached_hooks or [],
        disk_skill=disk_skill,
    )


# ---------------------------------------------------------------------------
# 1. Skills injection
# ---------------------------------------------------------------------------

class TestSkillsInjection:

    def test_attached_skill_body_is_not_injected(self):
        """spec 011 R-03: attached-skill bodies are no longer concatenated into the
        system prompt. Run-attached skills are STAGED to <sandbox>/skills/<id>/SKILL.md
        (``skill_staging.stage_skills``, called from ``create_runner``) and ADVERTISED
        to the model by the deepagents SkillsMiddleware as two lines each; the model
        loads a body on demand with ``read_file``. So the body must be ABSENT from the
        composed prompt, while the agent's own prompt body is still present."""
        spec = _make_spec(prompt_body="## My Agent\nDo the thing.")
        ctx = _make_ctx(attached_skills=[{
            "id": "ecc-python-patterns",
            "name": "Python Patterns",
            "content": "## Python Patterns Skill\nAlways use type hints.",
            "source": "ECC",
        }])

        result = _compose_system_prompt(spec, ctx)

        assert "## Python Patterns Skill" not in result, (
            "Attached skill body must NOT be injected into the system prompt (spec 011 R-03)"
        )
        assert "## My Agent" in result

    def test_skill_content_not_present_in_prompt(self):
        """spec 011 R-03: attached-skill content is staged/advertised, never concatenated
        into the composed prompt — so it must be absent here."""
        skill_content = "## Deep Research Skill\nSearch before answering.\nCite sources."
        spec = _make_spec()
        ctx = _make_ctx(attached_skills=[{"content": skill_content}])

        result = _compose_system_prompt(spec, ctx)

        assert skill_content not in result, "Attached skill content must not be in system prompt"

    def test_multiple_skills_none_injected(self):
        """spec 011 R-03: no attached skill's body reaches the prompt, no matter how many
        are attached — they are all staged to disk and advertised instead."""
        spec = _make_spec()
        ctx = _make_ctx(attached_skills=[
            {"content": "## Skill A\nContent A"},
            {"content": "## Skill B\nContent B"},
            {"content": "## Skill C\nContent C"},
        ])

        result = _compose_system_prompt(spec, ctx)

        assert "## Skill A" not in result
        assert "## Skill B" not in result
        assert "## Skill C" not in result

    def test_skill_with_no_content_field_does_not_crash(self):
        """spec 011 R-03: attached-skill bodies are never read into the prompt anymore, so
        a skill dict missing 'content' must still not crash the composer — and neither
        skill's body appears (they are staged/advertised, not injected)."""
        spec = _make_spec(prompt_body="## Agent")
        ctx = _make_ctx(attached_skills=[
            {"id": "broken-skill", "name": "Broken"},  # no 'content' key
            {"content": "## Good Skill\nWorks fine."},
        ])

        result = _compose_system_prompt(spec, ctx)

        assert "## Good Skill" not in result
        assert "## Agent" in result

    def test_empty_skill_content_skipped(self):
        """A skill with empty string content must not add a blank block."""
        spec = _make_spec(prompt_body="## Agent")
        ctx = _make_ctx(attached_skills=[{"content": ""}])

        result = _compose_system_prompt(spec, ctx)

        # Should just be the prompt body with no extra blank sections
        assert result.strip() == "## Agent"

    def test_no_skills_produces_only_prompt_body(self):
        """With no skills, the result is just the prompt body."""
        spec = _make_spec(prompt_body="## Agent\nDo work.")
        ctx = _make_ctx()

        result = _compose_system_prompt(spec, ctx)

        assert result.strip() == "## Agent\nDo work."

    def test_custom_user_pasted_skill_body_not_injected(self):
        """spec 011 R-03: user-pasted custom skill content (from AgentsPopup) is staged
        to disk and advertised, not concatenated into the system prompt."""
        custom_content = (
            "# My Custom Skill\n\n"
            "Always respond in bullet points.\n"
            "Use markdown headers for sections.\n"
        )
        spec = _make_spec()
        ctx = _make_ctx(attached_skills=[{
            "id": "custom-user-skill",
            "name": "My Custom Skill",
            "content": custom_content,
            "source": "custom",
        }])

        result = _compose_system_prompt(spec, ctx)

        assert "# My Custom Skill" not in result
        assert "Always respond in bullet points." not in result


# ---------------------------------------------------------------------------
# 2. Hooks injection (the main bug fix)
# ---------------------------------------------------------------------------

class TestHooksInjection:

    def test_hook_metadata_converted_to_behavioral_guideline(self):
        """Hooks must be converted to a behavioral guidelines block — not silently dropped."""
        spec = _make_spec()
        ctx = _make_ctx(attached_hooks=[{
            "id": "ecc-post-quality-gate",
            "name": "Quality Gate",
            "event": "PostToolUse",
            "trigger": "After Edit / Write / MultiEdit",
            "description": "Quality Gate: After Edit / Write / MultiEdit",
        }])

        result = _compose_system_prompt(spec, ctx)

        assert "Quality Gate" in result, (
            "Hook name must appear in system prompt — hooks were silently dropped before the fix"
        )
        assert "Active Behavioral Hooks" in result or "Quality Gate" in result

    def test_hook_with_no_content_field_still_injected(self):
        """The original bug: hooks have no 'content' field. They must still be injected."""
        spec = _make_spec()
        # This is exactly what the frontend sends — no 'content' key
        hook_without_content = {
            "id": "ecc-post-quality-gate",
            "name": "Quality Gate",
            "event": "PostToolUse",
            "trigger": "After Edit / Write / MultiEdit",
            "description": "Quality Gate: After Edit / Write / MultiEdit",
            # NOTE: no 'content' key — this was the bug
        }
        ctx = _make_ctx(attached_hooks=[hook_without_content])

        result = _compose_system_prompt(spec, ctx)

        # Before the fix, this would produce just the prompt body with no hook info
        assert "Quality Gate" in result, (
            "BUG REGRESSION: Hook with no 'content' field is being silently dropped. "
            "The fix in factory.py must synthesize guidelines from hook metadata."
        )

    def test_multiple_hooks_all_injected(self):
        """All attached hooks must appear in the system prompt."""
        spec = _make_spec()
        ctx = _make_ctx(attached_hooks=[
            {"name": "Quality Gate", "event": "PostToolUse", "trigger": "After edit", "description": "Quality Gate: After edit"},
            {"name": "Config Protection", "event": "PreToolUse", "trigger": "Before write", "description": "Config Protection: Before write"},
            {"name": "Session Loader", "event": "SessionStart", "trigger": "On start", "description": "Session Loader: On start"},
        ])

        result = _compose_system_prompt(spec, ctx)

        assert "Quality Gate" in result
        assert "Config Protection" in result
        assert "Session Loader" in result

    def test_hooks_section_header_present(self):
        """The hooks block must have a clear header so agents know to apply them."""
        spec = _make_spec()
        ctx = _make_ctx(attached_hooks=[{
            "name": "Design Quality Check",
            "event": "PostToolUse",
            "trigger": "After Edit on frontend files",
            "description": "Design Quality Check: After Edit on frontend files",
        }])

        result = _compose_system_prompt(spec, ctx)

        assert "Behavioral Hooks" in result or "behavioral" in result.lower(), (
            "Hooks block must have a header indicating these are behavioral guidelines"
        )

    def test_empty_hooks_produces_no_hooks_section(self):
        """With no hooks, no hooks section should appear."""
        spec = _make_spec(prompt_body="## Agent")
        ctx = _make_ctx(attached_hooks=[])

        result = _compose_system_prompt(spec, ctx)

        assert "Behavioral Hooks" not in result
        assert result.strip() == "## Agent"

    def test_hooks_appear_before_prompt_body(self):
        """Hooks must appear before the agent's own prompt body."""
        spec = _make_spec(prompt_body="## My Agent\nDo the thing.")
        ctx = _make_ctx(attached_hooks=[{
            "name": "Quality Gate",
            "event": "PostToolUse",
            "trigger": "After edit",
            "description": "Quality Gate: After edit",
        }])

        result = _compose_system_prompt(spec, ctx)

        hook_pos = result.index("Quality Gate")
        prompt_pos = result.index("## My Agent")
        assert hook_pos < prompt_pos, "Hooks must appear before the agent prompt body"


# ---------------------------------------------------------------------------
# 3. Ordering: guardrails → skills → hooks → prompt body
# ---------------------------------------------------------------------------

class TestInjectionOrdering:

    def test_ordering_guardrails_skills_hooks_prompt(self):
        """Injection order must be: guardrails → skills → hooks → prompt body. The
        attached-skill body slot no longer exists (spec 011 R-03) — the surviving
        skills slot is the per-user ``disk_skill`` block (D6), so it is used here to
        exercise the ordering of that slot relative to guardrails/hooks/prompt."""
        spec = _make_spec(
            prompt_body="## PROMPT BODY",
            guardrails=["html-prototype"],
        )
        ctx = _make_ctx(
            disk_skill="## DISK SKILL CONTENT",
            attached_hooks=[{"name": "HOOK NAME", "event": "Stop", "trigger": "t", "description": "HOOK NAME: t"}],
        )

        guardrail_content = "## Guardrail: html-prototype\n\nsome guardrail rules"  # noqa: F841

        with patch("agents.factory._GUARDRAILS_DIR") as mock_dir:
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_file.read_text.return_value = "some guardrail rules"
            mock_dir.__truediv__ = lambda self, name: mock_file

            result = _compose_system_prompt(spec, ctx)

        # Check relative ordering
        guardrail_pos = result.index("Guardrail: html-prototype")
        skill_pos = result.index("DISK SKILL CONTENT")
        hook_pos = result.index("HOOK NAME")
        prompt_pos = result.index("## PROMPT BODY")

        assert guardrail_pos < skill_pos < hook_pos < prompt_pos, (
            f"Expected guardrails({guardrail_pos}) < skills({skill_pos}) < "
            f"hooks({hook_pos}) < prompt({prompt_pos})"
        )

    def test_disk_skill_and_hooks_both_present_together(self):
        """The disk skill (D6, the surviving skills slot) and hooks must both appear
        when both are attached. Run-attached skill bodies (spec 011 R-03) are no
        longer a slot in the composed prompt, so this exercises ``disk_skill`` instead."""
        spec = _make_spec(prompt_body="## Agent")
        ctx = _make_ctx(
            disk_skill="## Python Patterns\nUse type hints.",
            attached_hooks=[{"name": "Quality Gate", "event": "PostToolUse", "trigger": "t", "description": "Quality Gate: t"}],
        )

        result = _compose_system_prompt(spec, ctx)

        assert "## Python Patterns" in result
        assert "Quality Gate" in result
        assert "## Agent" in result


# ---------------------------------------------------------------------------
# 4. WebSocket payload serialization (frontend → backend contract)
# ---------------------------------------------------------------------------

class TestWebSocketPayloadContract:
    """
    Tests that verify the shape of the WebSocket payload matches what
    the backend expects. These test the contract between useWorkflow.ts
    (frontend) and websocket.py / orchestrator_v2.py (backend).
    """

    def test_skill_payload_has_content_field(self):
        """The WebSocket payload for a skill must include 'content'."""
        # Simulate what useWorkflow.ts sends
        attached_skill = {
            "id": "ecc-python-patterns",
            "name": "Python Patterns",
            "content": "## Python Patterns\nUse type hints.",
            "source": "ECC",
            "compatible_agents": [],
        }
        # Backend reads it as:
        content = attached_skill.get("content", "")
        assert content == "## Python Patterns\nUse type hints.", (
            "Skill payload must have 'content' field with SKILL.md text"
        )

    def test_hook_payload_has_description_field(self):
        """The WebSocket payload for a hook must include 'description'."""
        # Simulate what useWorkflow.ts sends
        attached_hook = {
            "id": "ecc-post-quality-gate",
            "name": "Quality Gate",
            "event": "PostToolUse",
            "trigger": "After Edit / Write / MultiEdit",
            "description": "Quality Gate: After Edit / Write / MultiEdit",
        }
        # Backend reads name + description to build guideline
        assert attached_hook.get("name") == "Quality Gate"
        assert attached_hook.get("description") == "Quality Gate: After Edit / Write / MultiEdit"
        # Critically: no 'content' field — backend must handle this
        assert "content" not in attached_hook, (
            "Hook payload must NOT have 'content' — backend synthesizes it from metadata"
        )

    def test_backend_hook_injection_from_metadata_only(self):
        """Backend must inject hook guidelines using only name/event/description — no content field."""
        spec = _make_spec()
        # Exactly what the backend receives from the WebSocket message
        hook_from_ws = {
            "id": "ecc-post-quality-gate",
            "name": "Quality Gate",
            "event": "PostToolUse",
            "trigger": "After Edit / Write / MultiEdit",
            "description": "Quality Gate: After Edit / Write / MultiEdit",
            # No 'content' key — this is the real payload shape
        }
        ctx = _make_ctx(attached_hooks=[hook_from_ws])

        result = _compose_system_prompt(spec, ctx)

        assert "Quality Gate" in result, (
            "Backend must inject hook guidelines from metadata even without 'content' field"
        )


# ---------------------------------------------------------------------------
# 5. Integration: full pipeline context simulation
# ---------------------------------------------------------------------------

class TestFullPipelineContext:

    def test_user_stories_pipeline_with_skill_and_hook(self):
        """Simulate a user_stories pipeline run with one attached skill and one hook.

        spec 011 R-03: the attached skill's body is staged to
        ``<sandbox>/skills/<id>/SKILL.md`` and advertised by the deepagents
        SkillsMiddleware — it no longer enters the composed system prompt. The hook
        expectations are unchanged (hooks are unaffected by spec 011)."""
        spec = _make_spec(
            prompt_body=(
                "You are the Domain Analyst. Analyse the user's request "
                "and extract domain entities."
            )
        )
        ctx = _make_ctx(
            attached_skills=[{
                "id": "ecc-deep-research",
                "name": "Deep Research",
                "content": (
                    "## Deep Research Skill\n\n"
                    "Before answering, search for relevant information.\n"
                    "Cite all sources with [1], [2] notation."
                ),
                "source": "ECC",
            }],
            attached_hooks=[{
                "id": "ecc-session-start",
                "name": "Session Context Loader",
                "event": "SessionStart",
                "trigger": "Every new agent session",
                "description": "Session Context Loader: Loads previous session state on new session start.",
            }],
        )

        result = _compose_system_prompt(spec, ctx)

        # Skill content NOT present — staged/advertised, not injected
        assert "Deep Research Skill" not in result
        assert "Cite all sources" not in result
        # Hook guideline present (unchanged)
        assert "Session Context Loader" in result
        # Agent prompt body present
        assert "Domain Analyst" in result
        # Correct ordering: hook before prompt
        hook_pos = result.index("Session Context Loader")
        prompt_pos = result.index("Domain Analyst")
        assert hook_pos < prompt_pos

    def test_prototype_pipeline_with_design_quality_hook(self):
        """Simulate prototype pipeline with the Design Quality Check hook."""
        spec = _make_spec(
            prompt_body="You are the SPA Composer. Build the HTML prototype."
        )
        ctx = _make_ctx(
            attached_hooks=[{
                "id": "ecc-post-design-quality",
                "name": "Design Quality Check",
                "event": "PostToolUse",
                "trigger": "After Edit / Write on frontend files",
                "description": (
                    "Design Quality Check: Warns when frontend edits drift toward "
                    "generic template-looking UI. Keeps visual output distinctive."
                ),
            }]
        )

        result = _compose_system_prompt(spec, ctx)

        assert "Design Quality Check" in result
        assert "SPA Composer" in result

    def test_no_skills_no_hooks_clean_prompt(self):
        """With nothing attached, the system prompt is exactly the agent's prompt body."""
        prompt_body = "You are the Epic Architect. Create epics from the domain analysis."
        spec = _make_spec(prompt_body=prompt_body)
        ctx = _make_ctx()

        result = _compose_system_prompt(spec, ctx)

        assert result.strip() == prompt_body
        assert "Skill" not in result
        assert "Hook" not in result
        assert "Behavioral" not in result


# ---------------------------------------------------------------------------
# 6. D6 protection: attached-skill staging and disk_skill injection are independent
# ---------------------------------------------------------------------------

class TestAttachedSkillAndDiskSkillAreIndependent:

    def test_attached_skill_body_absent_while_disk_skill_present(self):
        """D6: an attached (run) skill's body must be ABSENT from the composed prompt
        even when a ``disk_skill`` is set on the same context — proving the two paths
        are provably independent. Attached skills are staged to
        ``<sandbox>/skills/<id>/SKILL.md`` and advertised by the deepagents
        SkillsMiddleware (spec 011 R-03); ``disk_skill`` (the per-user, per-agent disk
        SKILL.md) keeps its own, unrelated eager injection (spec 011 §5 / D6)."""
        spec = _make_spec(prompt_body="## Agent")
        ctx = _make_ctx(
            attached_skills=[{
                "id": "ecc-python-patterns",
                "name": "Python Patterns",
                "content": "## ATTACHED SKILL BODY\nShould not appear.",
                "source": "ECC",
            }],
            disk_skill="DISK SKILL BODY\n\nAlways answer in exactly one sentence.",
        )

        result = _compose_system_prompt(spec, ctx)

        assert "## ATTACHED SKILL BODY" not in result, (
            "Attached-skill body must not be injected, even alongside a disk_skill"
        )
        assert "DISK SKILL BODY" in result, (
            "disk_skill must still be eagerly injected regardless of attached_skills"
        )
        assert "## Agent" in result
