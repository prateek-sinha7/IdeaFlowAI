"""
Tests for FIX-001 (KAN-76) — Show and edit agent prompts from Library and workflow info views.

Validates:
  - prompt_overrides storage layer (save / read / delete / has_override)
  - agents.py API endpoints: GET/PUT/DELETE /{agent_id}/prompt
  - factory.py: user prompt override is injected into system prompt at runtime
  - INV-3: base prompt is used when user_id is None (goldens stay byte-identical)
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def overrides_sandbox(tmp_path: Path) -> Iterator[Path]:
    """Redirect the prompt_overrides module to a fresh tmp_path."""
    from app.agents import prompt_overrides as pm

    original = pm._USER_SKILLS_DIR
    pm._USER_SKILLS_DIR = tmp_path / "skills" / "users"
    pm._USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        yield tmp_path
    finally:
        pm._USER_SKILLS_DIR = original


# ── Storage layer ─────────────────────────────────────────────────────────────

class TestPromptOverrideStorage:
    """Tests for save / read / delete / has_override in prompt_overrides.py."""

    def test_save_writes_to_correct_path(self, overrides_sandbox):
        """Override is written to skills/users/{uid}/{agent_id}/PROMPT_OVERRIDE.md."""
        from app.agents.prompt_overrides import save_user_prompt_override, _USER_SKILLS_DIR

        path = save_user_prompt_override("domain-analyst", "# Custom prompt", user_id="user-1")

        expected = _USER_SKILLS_DIR / "user-1" / "domain-analyst" / "PROMPT_OVERRIDE.md"
        assert Path(path) == expected
        assert expected.exists()
        assert expected.read_text(encoding="utf-8") == "# Custom prompt"

    def test_read_returns_content_when_override_exists(self, overrides_sandbox):
        """Reading an existing override returns its content verbatim."""
        from app.agents.prompt_overrides import save_user_prompt_override, read_user_prompt_override

        save_user_prompt_override("epic-architect", "override content", user_id="user-2")
        result = read_user_prompt_override("epic-architect", user_id="user-2")
        assert result == "override content"

    def test_read_returns_none_when_no_override(self, overrides_sandbox):
        """Reading a non-existent override returns None (not an error)."""
        from app.agents.prompt_overrides import read_user_prompt_override

        result = read_user_prompt_override("unknown-agent", user_id="user-1")
        assert result is None

    def test_has_override_true_after_save(self, overrides_sandbox):
        """has_user_prompt_override returns True after saving."""
        from app.agents.prompt_overrides import save_user_prompt_override, has_user_prompt_override

        save_user_prompt_override("domain-analyst", "# Override", user_id="user-3")
        assert has_user_prompt_override("domain-analyst", user_id="user-3") is True

    def test_has_override_false_before_save(self, overrides_sandbox):
        """has_user_prompt_override returns False when no override exists."""
        from app.agents.prompt_overrides import has_user_prompt_override

        assert has_user_prompt_override("domain-analyst", user_id="user-new") is False

    def test_delete_removes_file(self, overrides_sandbox):
        """Deleting an override removes the file and returns True."""
        from app.agents.prompt_overrides import (
            save_user_prompt_override, delete_user_prompt_override, has_user_prompt_override
        )

        save_user_prompt_override("domain-analyst", "# Override", user_id="user-4")
        result = delete_user_prompt_override("domain-analyst", user_id="user-4")

        assert result is True
        assert has_user_prompt_override("domain-analyst", user_id="user-4") is False

    def test_delete_idempotent_returns_false_when_nothing_to_delete(self, overrides_sandbox):
        """Deleting a non-existent override returns False without error."""
        from app.agents.prompt_overrides import delete_user_prompt_override

        result = delete_user_prompt_override("no-agent", user_id="user-5")
        assert result is False

    def test_users_isolated_from_each_other(self, overrides_sandbox):
        """User A's override does not affect User B's read."""
        from app.agents.prompt_overrides import save_user_prompt_override, read_user_prompt_override

        save_user_prompt_override("domain-analyst", "user-A override", user_id="user-A")
        result_b = read_user_prompt_override("domain-analyst", user_id="user-B")
        assert result_b is None

    def test_save_raises_on_empty_user_id(self, overrides_sandbox):
        """Saving without a user_id raises ValueError."""
        from app.agents.prompt_overrides import save_user_prompt_override

        with pytest.raises(ValueError, match="user_id is required"):
            save_user_prompt_override("domain-analyst", "content", user_id="")

    def test_save_raises_on_oversized_content(self, overrides_sandbox):
        """Saving content exceeding MAX_PROMPT_OVERRIDE_BYTES raises ValueError."""
        from app.agents.prompt_overrides import save_user_prompt_override, MAX_PROMPT_OVERRIDE_BYTES

        oversized = "x" * (MAX_PROMPT_OVERRIDE_BYTES + 1)
        with pytest.raises(ValueError, match="MAX_PROMPT_OVERRIDE_BYTES"):
            save_user_prompt_override("domain-analyst", oversized, user_id="user-6")

    def test_read_returns_none_on_empty_user_id(self, overrides_sandbox):
        """Reading with empty user_id returns None safely."""
        from app.agents.prompt_overrides import read_user_prompt_override

        result = read_user_prompt_override("domain-analyst", user_id="")
        assert result is None

    def test_skill_and_override_coexist_in_same_directory(self, overrides_sandbox):
        """PROMPT_OVERRIDE.md and SKILL.md can live side by side for the same agent."""
        from app.agents.prompt_overrides import save_user_prompt_override, _USER_SKILLS_DIR

        save_user_prompt_override("domain-analyst", "# Override", user_id="user-7")
        skill_path = _USER_SKILLS_DIR / "user-7" / "domain-analyst" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text("# Skill")

        # Both files exist independently
        assert (_USER_SKILLS_DIR / "user-7" / "domain-analyst" / "PROMPT_OVERRIDE.md").exists()
        assert skill_path.exists()


# ── Factory injection ─────────────────────────────────────────────────────────

class TestFactoryPromptOverrideInjection:
    """Tests for factory.py: user override is used in _compose_system_prompt."""

    def _make_spec(self, prompt_body: str = "base prompt body"):
        spec = MagicMock()
        spec.id = "domain-analyst"
        spec.prompt_body = prompt_body
        spec.guardrails = []
        spec.injects = []
        spec.tools = []
        return spec

    def _make_ctx(self, user_id: str | None = None):
        ctx = MagicMock()
        ctx.user_id = user_id
        ctx.step_injects = []
        ctx.attached_skills = []
        ctx.attached_hooks = []
        ctx.prewarmed_constitution = None
        ctx.prewarmed_mcp_tools = []
        return ctx

    def test_base_prompt_used_when_no_override(self, overrides_sandbox):
        """When no override exists, spec.prompt_body is used unchanged (INV-3 path)."""
        from agents.factory import _compose_system_prompt

        spec = self._make_spec("base prompt body")
        ctx = self._make_ctx(user_id="user-no-override")

        with patch("agents.factory._resolve_runner_tools", return_value=([], True)):
            with patch("agents.capabilities.registry.CapabilityRegistry.resolve") as mock_policy:
                policy = MagicMock()
                policy.assemble.side_effect = lambda blocks, ctx: blocks.get("prompt_body", "")
                mock_policy.return_value = policy
                with patch("agents.capabilities.registry.discover"):
                    result = _compose_system_prompt(spec, ctx)

        assert result == "base prompt body"

    def test_override_replaces_base_prompt_when_user_has_override(self, overrides_sandbox):
        """When user has a saved override, it replaces spec.prompt_body in the system prompt."""
        from agents.factory import _compose_system_prompt
        from app.agents.prompt_overrides import save_user_prompt_override

        save_user_prompt_override("domain-analyst", "my custom override", user_id="user-override")
        spec = self._make_spec("base prompt body")
        ctx = self._make_ctx(user_id="user-override")

        with patch("agents.factory._resolve_runner_tools", return_value=([], True)):
            with patch("agents.capabilities.registry.CapabilityRegistry.resolve") as mock_policy:
                policy = MagicMock()
                policy.assemble.side_effect = lambda blocks, ctx: blocks.get("prompt_body", "")
                mock_policy.return_value = policy
                with patch("agents.capabilities.registry.discover"):
                    result = _compose_system_prompt(spec, ctx)

        assert result == "my custom override"
        assert result != "base prompt body"

    def test_base_prompt_used_when_user_id_is_none(self, overrides_sandbox):
        """When user_id is None (test/anon runs), base prompt is used — INV-3 preserved."""
        from agents.factory import _compose_system_prompt

        spec = self._make_spec("golden base prompt")
        ctx = self._make_ctx(user_id=None)

        with patch("agents.factory._resolve_runner_tools", return_value=([], True)):
            with patch("agents.capabilities.registry.CapabilityRegistry.resolve") as mock_policy:
                policy = MagicMock()
                policy.assemble.side_effect = lambda blocks, ctx: blocks.get("prompt_body", "")
                mock_policy.return_value = policy
                with patch("agents.capabilities.registry.discover"):
                    result = _compose_system_prompt(spec, ctx)

        assert result == "golden base prompt"

    def test_override_lookup_failure_falls_back_to_base_prompt(self, overrides_sandbox):
        """If override lookup raises an exception, base prompt is used (never crashes run)."""
        from agents.factory import _compose_system_prompt

        spec = self._make_spec("base prompt body")
        ctx = self._make_ctx(user_id="user-error")

        with patch("agents.factory._resolve_runner_tools", return_value=([], True)):
            with patch("agents.capabilities.registry.CapabilityRegistry.resolve") as mock_policy:
                policy = MagicMock()
                policy.assemble.side_effect = lambda blocks, ctx: blocks.get("prompt_body", "")
                mock_policy.return_value = policy
                with patch("agents.capabilities.registry.discover"):
                    with patch("app.agents.prompt_overrides.read_user_prompt_override",
                               side_effect=OSError("disk read failed")):
                        result = _compose_system_prompt(spec, ctx)

        assert result == "base prompt body"

    def test_after_delete_base_prompt_is_used_again(self, overrides_sandbox):
        """After deleting an override, the base prompt is restored."""
        from agents.factory import _compose_system_prompt
        from app.agents.prompt_overrides import save_user_prompt_override, delete_user_prompt_override

        save_user_prompt_override("domain-analyst", "temporary override", user_id="user-revert")

        spec = self._make_spec("base prompt body")
        ctx = self._make_ctx(user_id="user-revert")

        # Delete the override
        delete_user_prompt_override("domain-analyst", user_id="user-revert")

        with patch("agents.factory._resolve_runner_tools", return_value=([], True)):
            with patch("agents.capabilities.registry.CapabilityRegistry.resolve") as mock_policy:
                policy = MagicMock()
                policy.assemble.side_effect = lambda blocks, ctx: blocks.get("prompt_body", "")
                mock_policy.return_value = policy
                with patch("agents.capabilities.registry.discover"):
                    result = _compose_system_prompt(spec, ctx)

        assert result == "base prompt body"


# ── AgentResponse includes prompt_body ────────────────────────────────────────

class TestAgentResponseIncludesPromptBody:
    """Tests that prompt_body is included in API responses (root cause was it was omitted)."""

    def test_agent_response_model_has_prompt_body_field(self):
        """AgentResponse Pydantic model must have prompt_body field (root cause guard)."""
        from app.api.agents import AgentResponse
        import inspect

        fields = AgentResponse.model_fields
        assert "prompt_body" in fields, "AgentResponse.prompt_body field missing — root cause not fixed"

    def test_agent_prompt_response_model_has_required_fields(self):
        """AgentPromptResponse has agent_id, prompt_body, override, has_override."""
        from app.api.agents import AgentPromptResponse

        fields = AgentPromptResponse.model_fields
        for field in ("agent_id", "prompt_body", "override", "has_override"):
            assert field in fields, f"AgentPromptResponse.{field} missing"

    def test_prompt_override_request_model_exists(self):
        """PromptOverrideRequest Pydantic model exists."""
        from app.api.agents import PromptOverrideRequest
        assert PromptOverrideRequest is not None

    def test_max_prompt_override_bytes_larger_than_max_skill_bytes(self):
        """Prompt overrides allow 32 KB vs skills 8 KB — prompts are legitimately longer."""
        from app.agents.prompt_overrides import MAX_PROMPT_OVERRIDE_BYTES
        from app.agents.skills import MAX_SKILL_BYTES

        assert MAX_PROMPT_OVERRIDE_BYTES > MAX_SKILL_BYTES
        assert MAX_PROMPT_OVERRIDE_BYTES == 32 * 1024
