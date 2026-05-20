"""Unit tests for agents/loader.py — load_agent_spec and list_agent_ids.

Tests cover:
  - Successful parsing of a valid AGENT.md
  - Default values for optional fields
  - FileNotFoundError for missing directory / file
  - PermissionError for unreadable file
  - AgentSpecError for each invalid/missing required field
  - In-memory caching (second call returns cached instance)
  - list_agent_ids returns sorted IDs and detects duplicate orders
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

import agents.loader as loader_module
from agents.loader import AgentSpec, AgentSpecError, load_agent_spec, list_agent_ids

from tests.agents.conftest import make_agent_md, create_agent_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_agent(prompts_dir: Path, agent_id: str, **kwargs) -> Path:
    content = make_agent_md(id=agent_id, **kwargs)
    return create_agent_file(prompts_dir, agent_id, content)


# ---------------------------------------------------------------------------
# Happy-path: valid AGENT.md
# ---------------------------------------------------------------------------


class TestLoadAgentSpecValid:
    def test_required_fields_parsed(self, tmp_agent_dir):
        _write_agent(
            tmp_agent_dir,
            "domain-analyst",
            name="Domain Analyst",
            role="Market Research",
            pipeline_type="user_stories",
            order=1,
            max_tokens=4000,
            prompt_body="You are a domain analyst.",
        )
        spec = load_agent_spec("domain-analyst")

        assert spec.id == "domain-analyst"
        assert spec.name == "Domain Analyst"
        assert spec.role == "Market Research"
        assert spec.pipeline_type == "user_stories"
        assert spec.order == 1
        assert spec.max_tokens == 4000
        assert spec.prompt_body == "You are a domain analyst."

    def test_optional_field_defaults(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "minimal-agent")
        spec = load_agent_spec("minimal-agent")

        assert spec.tools == []
        assert spec.guardrails == []
        assert spec.context_from == []
        assert spec.icon == "🤖"
        assert spec.estimated_duration == 3.0

    def test_optional_fields_explicit(self, tmp_agent_dir):
        _write_agent(
            tmp_agent_dir,
            "full-agent",
            tools=["workspace"],
            guardrails=["agile"],
            context_from=["$previous"],
            icon="🔍",
            estimated_duration=5.0,
        )
        spec = load_agent_spec("full-agent")

        assert spec.tools == ["workspace"]
        assert spec.guardrails == ["agile"]
        assert spec.context_from == ["$previous"]
        assert spec.icon == "🔍"
        assert spec.estimated_duration == 5.0

    def test_max_tokens_boundary_values(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "min-tokens", max_tokens=1)
        spec_min = load_agent_spec("min-tokens")
        assert spec_min.max_tokens == 1

        _write_agent(tmp_agent_dir, "max-tokens", max_tokens=32768)
        spec_max = load_agent_spec("max-tokens")
        assert spec_max.max_tokens == 32768

    def test_all_supported_pipeline_types(self, tmp_agent_dir):
        from agents.loader import SUPPORTED_PIPELINE_TYPES
        for i, pt in enumerate(sorted(SUPPORTED_PIPELINE_TYPES), start=1):
            agent_id = f"agent-{pt.replace('_', '-')}"
            _write_agent(tmp_agent_dir, agent_id, pipeline_type=pt, order=i)
            spec = load_agent_spec(agent_id)
            assert spec.pipeline_type == pt


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestLoadAgentSpecCaching:
    def test_second_call_returns_cached_instance(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "cached-agent")
        spec1 = load_agent_spec("cached-agent")
        spec2 = load_agent_spec("cached-agent")
        assert spec1 is spec2

    def test_cache_not_invalidated_after_file_change(self, tmp_agent_dir):
        """Once cached, the spec is not re-read even if the file changes."""
        _write_agent(tmp_agent_dir, "stable-agent", name="Original Name")
        spec1 = load_agent_spec("stable-agent")

        # Overwrite the file
        _write_agent(tmp_agent_dir, "stable-agent", name="Changed Name")
        spec2 = load_agent_spec("stable-agent")

        # Should still be the cached (original) instance
        assert spec1 is spec2
        assert spec2.name == "Original Name"


# ---------------------------------------------------------------------------
# FileNotFoundError
# ---------------------------------------------------------------------------


class TestLoadAgentSpecFileNotFound:
    def test_missing_directory_raises_file_not_found(self, tmp_agent_dir):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_agent_spec("nonexistent-agent")
        assert "nonexistent-agent" in str(exc_info.value)

    def test_missing_agent_md_raises_file_not_found(self, tmp_agent_dir):
        # Create directory but no AGENT.md
        (tmp_agent_dir / "empty-agent").mkdir()
        with pytest.raises(FileNotFoundError) as exc_info:
            load_agent_spec("empty-agent")
        assert "AGENT.md" in str(exc_info.value)

    def test_error_message_includes_path(self, tmp_agent_dir):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_agent_spec("no-such-agent")
        # Path should be in the error message
        assert "no-such-agent" in str(exc_info.value)


# ---------------------------------------------------------------------------
# PermissionError (Unix only — skip on Windows)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="chmod not reliable on Windows")
class TestLoadAgentSpecPermissionError:
    def test_unreadable_file_raises_permission_error(self, tmp_agent_dir):
        agent_file = _write_agent(tmp_agent_dir, "locked-agent")
        agent_file.chmod(0o000)
        try:
            with pytest.raises(PermissionError) as exc_info:
                load_agent_spec("locked-agent")
            assert "locked-agent" in str(exc_info.value)
        finally:
            agent_file.chmod(0o644)


# ---------------------------------------------------------------------------
# AgentSpecError — missing required fields
# ---------------------------------------------------------------------------


class TestLoadAgentSpecMissingFields:
    @pytest.mark.parametrize("missing_field", ["id", "name", "role", "pipeline_type"])
    def test_missing_string_field_raises_spec_error(self, tmp_agent_dir, missing_field):
        # Build content without the missing field
        content = make_agent_md()
        # Remove the field line from the frontmatter
        lines = content.split("\n")
        filtered = [l for l in lines if not l.startswith(f"{missing_field}:")]
        content = "\n".join(filtered)
        create_agent_file(tmp_agent_dir, "bad-agent", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("bad-agent")
        assert missing_field in str(exc_info.value)

    def test_missing_order_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md()
        lines = [l for l in content.split("\n") if not l.startswith("order:")]
        create_agent_file(tmp_agent_dir, "no-order", "\n".join(lines))

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("no-order")
        assert "order" in str(exc_info.value)

    def test_missing_max_tokens_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md()
        lines = [l for l in content.split("\n") if not l.startswith("max_tokens:")]
        create_agent_file(tmp_agent_dir, "no-max-tokens", "\n".join(lines))

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("no-max-tokens")
        assert "max_tokens" in str(exc_info.value)

    def test_empty_prompt_body_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(prompt_body="   \n  \t  ")
        create_agent_file(tmp_agent_dir, "empty-body", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("empty-body")
        assert "prompt body" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# AgentSpecError — invalid field values
# ---------------------------------------------------------------------------


class TestLoadAgentSpecInvalidFields:
    def test_empty_id_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(id="")
        # Replace id line with empty value
        content = content.replace("id: ", "id: ")
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("id:"):
                new_lines.append("id: ''")
            else:
                new_lines.append(line)
        create_agent_file(tmp_agent_dir, "empty-id", "\n".join(new_lines))

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("empty-id")
        assert "id" in str(exc_info.value)

    def test_invalid_pipeline_type_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(pipeline_type="not_a_real_pipeline")
        create_agent_file(tmp_agent_dir, "bad-pipeline", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("bad-pipeline")
        assert "pipeline_type" in str(exc_info.value)

    def test_order_zero_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(order=0)
        create_agent_file(tmp_agent_dir, "zero-order", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("zero-order")
        assert "order" in str(exc_info.value)

    def test_negative_order_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(order=-1)
        create_agent_file(tmp_agent_dir, "neg-order", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("neg-order")
        assert "order" in str(exc_info.value)

    def test_max_tokens_zero_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(max_tokens=0)
        create_agent_file(tmp_agent_dir, "zero-tokens", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("zero-tokens")
        assert "max_tokens" in str(exc_info.value)

    def test_max_tokens_too_large_raises_spec_error(self, tmp_agent_dir):
        content = make_agent_md(max_tokens=32769)
        create_agent_file(tmp_agent_dir, "big-tokens", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("big-tokens")
        assert "max_tokens" in str(exc_info.value)

    def test_error_message_includes_file_path(self, tmp_agent_dir):
        content = make_agent_md(pipeline_type="invalid_type")
        create_agent_file(tmp_agent_dir, "path-check", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("path-check")
        # File path should appear in the error message
        assert "path-check" in str(exc_info.value)


# ---------------------------------------------------------------------------
# list_agent_ids
# ---------------------------------------------------------------------------


class TestListAgentIds:
    def test_returns_ids_sorted_by_order(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "agent-c", order=3, pipeline_type="user_stories")
        _write_agent(tmp_agent_dir, "agent-a", order=1, pipeline_type="user_stories")
        _write_agent(tmp_agent_dir, "agent-b", order=2, pipeline_type="user_stories")

        ids = list_agent_ids("user_stories")
        assert ids == ["agent-a", "agent-b", "agent-c"]

    def test_returns_empty_list_for_unknown_pipeline(self, tmp_agent_dir):
        ids = list_agent_ids("nonexistent_pipeline")
        assert ids == []

    def test_filters_by_pipeline_type(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "us-agent", order=1, pipeline_type="user_stories")
        _write_agent(tmp_agent_dir, "ppt-agent", order=1, pipeline_type="ppt")

        us_ids = list_agent_ids("user_stories")
        ppt_ids = list_agent_ids("ppt")

        assert us_ids == ["us-agent"]
        assert ppt_ids == ["ppt-agent"]

    def test_duplicate_order_raises_spec_error(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "dup-a", order=1, pipeline_type="user_stories")
        _write_agent(tmp_agent_dir, "dup-b", order=1, pipeline_type="user_stories")

        with pytest.raises(AgentSpecError) as exc_info:
            list_agent_ids("user_stories")
        error_msg = str(exc_info.value)
        # Should mention both agent IDs and the shared order value
        assert "1" in error_msg

    def test_empty_prompts_dir_returns_empty_list(self, tmp_agent_dir):
        ids = list_agent_ids("user_stories")
        assert ids == []

    def test_returns_only_matching_pipeline_agents(self, tmp_agent_dir):
        for i in range(1, 4):
            _write_agent(
                tmp_agent_dir,
                f"us-{i}",
                order=i,
                pipeline_type="user_stories",
            )
        _write_agent(tmp_agent_dir, "ppt-1", order=1, pipeline_type="ppt")

        ids = list_agent_ids("user_stories")
        assert len(ids) == 3
        assert "ppt-1" not in ids


# ---------------------------------------------------------------------------
# Task 19.1 — Schema validation: all real AGENT.md files on disk
# ---------------------------------------------------------------------------


class TestSchemaValidationAllAgents:
    """Validate every AGENT.md in agents/prompts/ against the AgentSpec schema.

    Uses the REAL filesystem (not tmp_agent_dir fixture).
    Requirements: 9.1, 9.8
    """

    def _discover_agent_ids(self) -> list[str]:
        """Return all agent IDs discoverable in the real agents/prompts/ directory."""
        import agents.loader as _loader
        prompts_dir = _loader._PROMPTS_DIR
        ids = []
        for entry in sorted(prompts_dir.iterdir()):
            if entry.is_dir() and (entry / "AGENT.md").exists():
                ids.append(entry.name)
        return ids

    def test_all_agents_load_without_error(self):
        """Every AGENT.md in agents/prompts/ must parse without raising."""
        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found in agents/prompts/ — check the path"

        for agent_id in agent_ids:
            # Use a fresh load (bypass cache) by temporarily clearing it
            import agents.loader as _loader
            _loader._SPEC_CACHE.pop(agent_id, None)
            spec = load_agent_spec(agent_id)
            assert spec is not None, f"load_agent_spec returned None for {agent_id!r}"

    def test_all_agents_have_required_fields(self):
        """Every AgentSpec must have all required fields populated (non-empty/non-zero)."""
        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found"

        for agent_id in agent_ids:
            spec = load_agent_spec(agent_id)

            assert spec.id, f"Agent {agent_id!r}: spec.id is empty"
            assert spec.name, f"Agent {agent_id!r}: spec.name is empty"
            assert spec.role, f"Agent {agent_id!r}: spec.role is empty"
            assert spec.pipeline_type, f"Agent {agent_id!r}: spec.pipeline_type is empty"
            assert spec.order >= 1, f"Agent {agent_id!r}: spec.order must be >= 1, got {spec.order}"
            assert 1 <= spec.max_tokens <= 32768, (
                f"Agent {agent_id!r}: spec.max_tokens={spec.max_tokens} out of range 1–32768"
            )
            assert spec.prompt_body.strip(), f"Agent {agent_id!r}: spec.prompt_body is blank"

    def test_all_agents_id_matches_directory_name(self):
        """Requirement 2.8: spec.id must equal the directory name for every agent."""
        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found"

        for agent_id in agent_ids:
            spec = load_agent_spec(agent_id)
            assert spec.id == agent_id, (
                f"spec.id={spec.id!r} does not match directory name {agent_id!r}"
            )

    def test_all_agents_have_supported_pipeline_type(self):
        """Every agent's pipeline_type must be one of SUPPORTED_PIPELINE_TYPES."""
        from agents.loader import SUPPORTED_PIPELINE_TYPES

        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found"

        for agent_id in agent_ids:
            spec = load_agent_spec(agent_id)
            assert spec.pipeline_type in SUPPORTED_PIPELINE_TYPES, (
                f"Agent {agent_id!r}: pipeline_type={spec.pipeline_type!r} "
                f"is not in SUPPORTED_PIPELINE_TYPES"
            )
