"""Unit tests for agents/loader.py — load_agent_spec and list_agent_ids.

Tests cover:
  - Successful parsing of a valid AGENT.md
  - Default values for optional fields
  - Optional `description` (explicit verbatim / absent → fallback to role)
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


def _discover_agent_ids() -> list[str]:
    """Return all agent IDs discoverable in the real agents/prompts/ directory."""
    import agents.loader as _loader
    prompts_dir = _loader._PROMPTS_DIR
    ids = []
    for entry in sorted(prompts_dir.iterdir()):
        if entry.is_dir() and (entry / "AGENT.md").exists():
            ids.append(entry.name)
    return ids


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
# Optional `description` field (frontmatter; falls back to `role` when absent)
# ---------------------------------------------------------------------------


class TestLoadAgentSpecDescription:
    def test_description_absent_falls_back_to_role(self, tmp_agent_dir):
        """The common case: no `description:` frontmatter key → spec.description == spec.role."""
        _write_agent(
            tmp_agent_dir,
            "no-desc-agent",
            role="Market Research",
        )
        spec = load_agent_spec("no-desc-agent")

        # The generated AGENT.md has no `description` key at all.
        assert spec.description == "Market Research"
        assert spec.description == spec.role

    def test_explicit_description_used_verbatim(self, tmp_agent_dir):
        """An explicit `description:` frontmatter value is used verbatim (not the role)."""
        explicit = "Researches the target market and surfaces competitor gaps."
        _write_agent(
            tmp_agent_dir,
            "desc-agent",
            role="Market Research",
            extra_fields={"description": explicit},
        )
        spec = load_agent_spec("desc-agent")

        assert spec.description == explicit
        assert spec.description != spec.role

    def test_blank_description_falls_back_to_role(self, tmp_agent_dir):
        """A present-but-blank/whitespace `description` falls back to `role`."""
        content = make_agent_md(id="blank-desc", role="Effort Scoring")
        # Inject an empty-quoted description into the frontmatter.
        content = content.replace(
            "estimated_duration: 3.0",
            'estimated_duration: 3.0\ndescription: "   "',
        )
        create_agent_file(tmp_agent_dir, "blank-desc", content)

        spec = load_agent_spec("blank-desc")
        assert spec.description == "Effort Scoring"
        assert spec.description == spec.role

    def test_non_string_description_raises_spec_error(self, tmp_agent_dir):
        """A non-string `description` (absence never raises, but a wrong type does)."""
        content = make_agent_md(id="bad-desc")
        content = content.replace(
            "estimated_duration: 3.0",
            "estimated_duration: 3.0\ndescription: 42",
        )
        create_agent_file(tmp_agent_dir, "bad-desc", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("bad-desc")
        assert "description" in str(exc_info.value)

    def test_default_description_is_role_for_minimal_agent(self, tmp_agent_dir):
        """A minimal agent (only required fields) gets description == role."""
        _write_agent(tmp_agent_dir, "minimal-desc-agent", role="Testing")
        spec = load_agent_spec("minimal-desc-agent")
        assert spec.description == spec.role == "Testing"


# ---------------------------------------------------------------------------
# Optional `model` field (D-09; tier-3 agent-default for the resolver, MODEL-01)
# ---------------------------------------------------------------------------


class TestLoadAgentSpecModel:
    """The optional `model` frontmatter field (str | None, fully additive).

    The loader enforces a type guard only (string-or-null → else AgentSpecError);
    catalog-membership validation of an AGENT.md `model` is deferred to RESOLVE
    time in the resolver (06-03), so the loader gains no catalog import.
    """

    def test_model_field_parses(self, tmp_agent_dir):
        """An explicit `model:` frontmatter value is parsed verbatim onto spec.model."""
        model_id = "eu.anthropic.claude-sonnet-4-6"
        _write_agent(
            tmp_agent_dir,
            "model-agent",
            extra_fields={"model": model_id},
        )
        spec = load_agent_spec("model-agent")
        assert spec.model == model_id

    def test_model_absent_is_none(self, tmp_agent_dir):
        """No `model:` key at all → spec.model is None (fully additive default)."""
        _write_agent(tmp_agent_dir, "no-model-agent")
        spec = load_agent_spec("no-model-agent")
        assert spec.model is None

    def test_model_invalid_type_raises(self, tmp_agent_dir):
        """A non-string, non-null `model` (e.g. an int) raises AgentSpecError."""
        content = make_agent_md(id="bad-model")
        content = content.replace(
            "estimated_duration: 3.0",
            "estimated_duration: 3.0\nmodel: 123",
        )
        create_agent_file(tmp_agent_dir, "bad-model", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("bad-model")
        assert "model" in str(exc_info.value)


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
# Synthetic ids (custom-agent:<instance_id>) — R-03a
# ---------------------------------------------------------------------------


class TestLoadAgentSpecSyntheticId:
    def test_synthetic_id_resolves_base_spec(self, tmp_agent_dir):
        _write_agent(
            tmp_agent_dir,
            "custom-agent",
            pipeline_type="custom",
            order=10,
        )
        spec = load_agent_spec("custom-agent:research-a")
        assert spec.id == "custom-agent:research-a"
        assert spec.pipeline_type == load_agent_spec("custom-agent").pipeline_type

    def test_two_instances_are_distinct_cached_objects(self, tmp_agent_dir):
        _write_agent(
            tmp_agent_dir,
            "custom-agent",
            pipeline_type="custom",
            order=10,
        )
        a = load_agent_spec("custom-agent:a")
        b = load_agent_spec("custom-agent:b")
        assert a is not b and a.id != b.id

    def test_base_spec_cache_entry_unaffected_by_replace(self, tmp_agent_dir):
        _write_agent(
            tmp_agent_dir,
            "custom-agent",
            pipeline_type="custom",
            order=10,
        )
        base = load_agent_spec("custom-agent")
        load_agent_spec("custom-agent:a")
        assert load_agent_spec("custom-agent") is base
        assert base.id == "custom-agent"

    def test_unknown_base_raises_file_not_found_naming_base(self, tmp_agent_dir):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_agent_spec("no-such-agent:x")
        assert "no-such-agent" in str(exc_info.value)


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

    def test_unknown_pipeline_type_loads_and_round_trips(self, tmp_agent_dir):
        """An arbitrary/unknown `pipeline_type` is no longer an allow-list check —
        that validation was deliberately removed from `_build_spec` because
        SUPPORTED_PIPELINE_TYPES is partly DERIVED from agents' own declared
        pipeline_type values, so validating against it would be circular. The
        AGENT.md now loads successfully and the value round-trips onto the spec.
        """
        content = make_agent_md(pipeline_type="not_a_real_pipeline")
        create_agent_file(tmp_agent_dir, "bad-pipeline", content)

        spec = load_agent_spec("bad-pipeline")
        assert spec.pipeline_type == "not_a_real_pipeline"

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
        # pipeline_type is no longer validated (see
        # test_unknown_pipeline_type_loads_and_round_trips); re-point at a
        # validation that still exists — max_tokens out of range — to keep
        # this test's real intent: error messages name the offending file.
        content = make_agent_md(max_tokens=32769)
        create_agent_file(tmp_agent_dir, "path-check", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("path-check")
        # File path should appear in the error message
        assert "path-check" in str(exc_info.value)

    def test_template_non_bool_raises(self, tmp_agent_dir):
        """A string `template` (e.g. "yes") must NOT be coerced — strict bool only."""
        content = make_agent_md(id="bad-template")
        content = content.replace(
            "estimated_duration: 3.0",
            'estimated_duration: 3.0\ntemplate: "yes"',
        )
        create_agent_file(tmp_agent_dir, "bad-template", content)

        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("bad-template")
        assert "template" in str(exc_info.value)


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
        return _discover_agent_ids()

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
            # description is always non-empty (explicit value, or the role fallback).
            assert spec.description, f"Agent {agent_id!r}: spec.description is empty"

    def test_all_agents_description_defaults_to_role(self):
        """Most AGENT.md files have since had a real `description` authored in
        (e.g. spec 011's analyze-agent, and a broad follow-on pass across the
        app/dotnet/mulesoft/chat/prototype/ppt agents) — so the old blanket
        "no agent declares description" assumption no longer holds. Check the
        fallback per-agent against its own raw frontmatter instead of a
        hand-maintained exempt list: an agent WITHOUT an explicit `description`
        key must fall back to `role`; an agent WITH one must keep its own value
        (and it must differ from role, or the frontmatter value is redundant)."""
        import frontmatter as _frontmatter

        import agents.loader as _loader

        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found"

        for agent_id in agent_ids:
            spec = load_agent_spec(agent_id)
            raw = _frontmatter.load(_loader._PROMPTS_DIR / agent_id / "AGENT.md")
            if "description" in raw.metadata:
                assert spec.description == raw.metadata["description"], (
                    f"Agent {agent_id!r}: spec.description={spec.description!r} "
                    f"!= its own frontmatter description={raw.metadata['description']!r}"
                )
            else:
                assert spec.description == spec.role, (
                    f"Agent {agent_id!r}: spec.description={spec.description!r} "
                    f"!= spec.role={spec.role!r} (expected the role fallback for an "
                    f"agent with no explicit `description` in frontmatter)"
                )

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
        """Every agent's pipeline_type must be one of SUPPORTED_PIPELINE_TYPES.

        Handles both the legacy string form and the new list form (task 1 of the
        revision-pipeline-agent-reuse spec): if pipeline_type is a list, each
        element must be in SUPPORTED_PIPELINE_TYPES; if it is a string, the string
        itself must be in SUPPORTED_PIPELINE_TYPES.
        """
        from agents.loader import SUPPORTED_PIPELINE_TYPES

        agent_ids = self._discover_agent_ids()
        assert agent_ids, "No agent directories found"

        for agent_id in agent_ids:
            spec = load_agent_spec(agent_id)
            if isinstance(spec.pipeline_type, list):
                for pt in spec.pipeline_type:
                    assert pt in SUPPORTED_PIPELINE_TYPES, (
                        f"Agent {agent_id!r}: pipeline_type element {pt!r} "
                        f"is not in SUPPORTED_PIPELINE_TYPES"
                    )
            else:
                assert spec.pipeline_type in SUPPORTED_PIPELINE_TYPES, (
                    f"Agent {agent_id!r}: pipeline_type={spec.pipeline_type!r} "
                    f"is not in SUPPORTED_PIPELINE_TYPES"
                )


class TestArchivedPromptsAreInvisible:
    """Spec 007 R-10 — `AGENT.vN.md` archive files must not register as agents.

    THIS IS A TRIPWIRE, not a nicety. `grade.sh apply-advice` archives the old
    prompt body beside the live one as `AGENT.vN.md`. That is safe for exactly one
    reason: both `load_agent_spec` and `list_agent_ids` test the literal filename
    `AGENT.md` (loader.py) — they never glob.

    Change either to `glob("AGENT*.md")` and every archive registers as a second
    copy of its agent: `PIPELINE_AGENTS` doubles, and `list_agent_ids` raises
    `AgentSpecError` on the duplicate `order`. The whole backward-compatibility
    argument for prompt archiving rests on the literal match, so if this test
    starts failing, do not "fix" it by updating the expectation — fix the scan.
    """

    def _archive(self, prompts_dir: Path, agent_id: str, number: int, body: str) -> Path:
        path = prompts_dir / agent_id / f"AGENT.v{number}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_agent_count_is_unchanged_by_archives(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "agent-a", order=1, pipeline_type="user_stories")
        _write_agent(tmp_agent_dir, "agent-b", order=2, pipeline_type="user_stories")
        before = list_agent_ids("user_stories")

        self._archive(tmp_agent_dir, "agent-a", 1, "an older prompt body")
        self._archive(tmp_agent_dir, "agent-a", 2, "an even older prompt body")
        self._archive(tmp_agent_dir, "agent-b", 1, "another archived body")

        assert list_agent_ids("user_stories") == before

    def test_archives_never_trip_the_duplicate_order_check(self, tmp_agent_dir):
        """A globbing scan would raise here, because an archive shares its agent's order."""
        _write_agent(tmp_agent_dir, "agent-a", order=1, pipeline_type="user_stories")
        self._archive(tmp_agent_dir, "agent-a", 1, "an older prompt body")

        assert list_agent_ids("user_stories") == ["agent-a"]

    def test_load_agent_spec_returns_the_live_body_not_an_archive(self, tmp_agent_dir):
        _write_agent(tmp_agent_dir, "agent-a", order=1, pipeline_type="user_stories")
        self._archive(tmp_agent_dir, "agent-a", 1, "ARCHIVED BODY — must never load")

        spec = load_agent_spec("agent-a")

        assert "ARCHIVED BODY" not in spec.prompt_body

    def test_an_archive_alone_is_not_an_agent(self, tmp_agent_dir):
        """A folder holding only archives has no live prompt and must not register."""
        (tmp_agent_dir / "orphan-agent").mkdir(parents=True, exist_ok=True)
        self._archive(tmp_agent_dir, "orphan-agent", 1, "body with no AGENT.md beside it")

        assert list_agent_ids("user_stories") == []

    def test_real_pipeline_membership_survives_archives_on_disk(self):
        """The same property against the real prompts dir and the real registry."""
        import agents.loader as _loader
        import agents.registry as registry

        prompts_dir = _loader._PROMPTS_DIR
        target = prompts_dir / "prototype-build"
        if not (target / "AGENT.md").is_file():
            pytest.skip("prototype-build not present")

        expected = {name: list(ids) for name, ids in registry.PIPELINE_AGENTS.items()}
        archive = target / "AGENT.v99.md"
        archive.write_text("a temporary archive body", encoding="utf-8")
        try:
            rebuilt = {
                name: list_agent_ids(name) for name in expected if name in ("prototype",)
            }
            assert rebuilt["prototype"] == expected["prototype"]
        finally:
            archive.unlink()
    def test_all_agents_declare_an_explicit_icon(self):
        """TEST-008 / ISS-068 C2: every AGENT.md must DECLARE an explicit ``icon:``.

        This reads the RAW frontmatter, deliberately NOT ``spec.icon`` — the loader
        substitutes a default ``"🤖"`` for a missing key, so a ``spec.icon`` assertion
        is true by construction and pins nothing.

        Why this pin exists: commit ``f608e4bc`` (FIX-190) appended an ``accessibility``
        guardrail to four prototype-family agents. In three of them the ``+`` line was a
        pure insertion; in ``prototype-build/AGENT.md`` it landed ON TOP OF the
        ``icon: "🏗️"`` line, silently deleting it. The agent then fell through to the
        ``"🤖"`` default, changing the icon in ``pipeline_start.agents[]`` and every
        ``agent_start`` — a user-visible UI regression that config review, code review
        and CI all missed. Only the ``prototype``/``od_prototype`` characterization event
        goldens caught it, ~6 days later. ``icon`` is contractual: it is a member of
        ``_REQUIRED_DATA_KEYS["agent_start"]``.

        An icon-less agent is therefore always a mistake, never a design choice: it makes
        the UI silently lie and it moves a golden. Adding a new agent means giving it an
        icon.
        """
        import frontmatter  # python-frontmatter — same parser agents/loader.py uses
        import agents.loader as _loader

        agent_ids = _discover_agent_ids()
        assert agent_ids, "No agent directories found"

        missing: list[str] = []
        for agent_id in agent_ids:
            raw = (_loader._PROMPTS_DIR / agent_id / "AGENT.md").read_text(encoding="utf-8")
            declared = frontmatter.loads(raw).metadata.get("icon")
            if not isinstance(declared, str) or not declared.strip():
                missing.append(agent_id)

        assert not missing, (
            f"{len(missing)} of {len(agent_ids)} AGENT.md files do not declare an "
            f"explicit `icon:` and will silently fall back to the loader default '🤖', "
            f"changing what the UI shows and moving the characterization event goldens: "
            f"{sorted(missing)}. Add an `icon:` line to each — do NOT relax this test."
        )


# ---------------------------------------------------------------------------
# pipeline_type: list[str] — load_agent_spec parsing (Requirements 6.1, 6.5)
# ---------------------------------------------------------------------------


class TestLoadAgentSpecPipelineTypeList:
    """Verify that _build_spec / _parse_pipeline_type correctly handles the
    new ``pipeline_type: list[str]`` shape.

    Requirements: 6.1, 6.5
    """

    def _write_raw(self, prompts_dir: Path, agent_id: str, pipeline_type_yaml: str) -> None:
        """Write an AGENT.md with an arbitrary pipeline_type YAML snippet."""
        content = (
            "---\n"
            f"id: {agent_id}\n"
            "name: Test Agent\n"
            "role: Testing\n"
            f"pipeline_type: {pipeline_type_yaml}\n"
            "order: 1\n"
            "max_tokens: 4000\n"
            'icon: "🤖"\n'
            "estimated_duration: 3.0\n"
            "---\n"
            "\n"
            "You are a test agent.\n"
        )
        create_agent_file(prompts_dir, agent_id, content)

    def _write_raw_multiline(self, prompts_dir: Path, agent_id: str, pipeline_type_block: str) -> None:
        """Write an AGENT.md with a multiline pipeline_type YAML block."""
        content = (
            "---\n"
            f"id: {agent_id}\n"
            "name: Test Agent\n"
            "role: Testing\n"
            f"{pipeline_type_block}\n"
            "order: 1\n"
            "max_tokens: 4000\n"
            'icon: "🤖"\n'
            "estimated_duration: 3.0\n"
            "---\n"
            "\n"
            "You are a test agent.\n"
        )
        create_agent_file(prompts_dir, agent_id, content)

    def test_pipeline_type_list_parses(self, tmp_agent_dir):
        """A YAML list ``[prototype, prototype_revision]`` parses to a Python list."""
        self._write_raw(tmp_agent_dir, "list-agent", "[prototype, prototype_revision]")
        spec = load_agent_spec("list-agent")
        assert spec.pipeline_type == ["prototype", "prototype_revision"]

    def test_pipeline_type_list_empty_raises(self, tmp_agent_dir):
        """An empty list ``[]`` must raise AgentSpecError."""
        self._write_raw(tmp_agent_dir, "empty-list-agent", "[]")
        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("empty-list-agent")
        assert "pipeline_type" in str(exc_info.value)

    def test_pipeline_type_list_element_empty_raises(self, tmp_agent_dir):
        """A list with a blank element raises AgentSpecError naming the file."""
        self._write_raw(tmp_agent_dir, "blank-elem-agent", '["prototype", ""]')
        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("blank-elem-agent")
        error_msg = str(exc_info.value)
        assert "pipeline_type" in error_msg
        # Error should name the file (agent id appears in the path)
        assert "blank-elem-agent" in error_msg

    def test_pipeline_type_list_element_non_string_raises(self, tmp_agent_dir):
        """A list containing a non-string element (e.g. 42) raises AgentSpecError."""
        self._write_raw(tmp_agent_dir, "non-str-elem-agent", "[prototype, 42]")
        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("non-str-elem-agent")
        assert "pipeline_type" in str(exc_info.value)

    def test_pipeline_type_null_raises(self, tmp_agent_dir):
        """``pipeline_type: null`` must raise AgentSpecError."""
        self._write_raw(tmp_agent_dir, "null-pt-agent", "null")
        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("null-pt-agent")
        assert "pipeline_type" in str(exc_info.value)

    def test_pipeline_type_int_raises(self, tmp_agent_dir):
        """``pipeline_type: 1`` (an integer) must raise AgentSpecError."""
        self._write_raw(tmp_agent_dir, "int-pt-agent", "1")
        with pytest.raises(AgentSpecError) as exc_info:
            load_agent_spec("int-pt-agent")
        assert "pipeline_type" in str(exc_info.value)


# ---------------------------------------------------------------------------
# list_agent_ids with list pipeline_type agents (Requirements 6.1, 6.4, 6.5)
# ---------------------------------------------------------------------------


class TestListAgentIdsWithListPipelineType:
    """Verify that list_agent_ids handles agents whose pipeline_type is a list.

    Requirements: 6.1, 6.4, 6.5
    """

    def _write_list_agent(
        self,
        prompts_dir: Path,
        agent_id: str,
        pipeline_types: list[str],
        order: int = 1,
    ) -> None:
        """Write an AGENT.md whose pipeline_type is a YAML list."""
        pt_items = "\n".join(f"  - {pt}" for pt in pipeline_types)
        content = (
            "---\n"
            f"id: {agent_id}\n"
            "name: Test Agent\n"
            "role: Testing\n"
            "pipeline_type:\n"
            f"{pt_items}\n"
            f"order: {order}\n"
            "max_tokens: 4000\n"
            'icon: "🤖"\n'
            "estimated_duration: 3.0\n"
            "---\n"
            "\n"
            "You are a test agent.\n"
        )
        create_agent_file(prompts_dir, agent_id, content)

    def _write_str_agent(
        self,
        prompts_dir: Path,
        agent_id: str,
        pipeline_type: str,
        order: int = 1,
    ) -> None:
        """Write an AGENT.md whose pipeline_type is a plain string."""
        _write_agent(prompts_dir, agent_id, pipeline_type=pipeline_type, order=order)

    def test_agent_with_list_appears_in_both_buckets(self, tmp_agent_dir):
        """An agent with ``pipeline_type: [user_stories, ppt]`` appears in both buckets."""
        self._write_list_agent(tmp_agent_dir, "multi-pt-agent", ["user_stories", "ppt"], order=1)

        us_ids = list_agent_ids("user_stories")
        ppt_ids = list_agent_ids("ppt")

        assert "multi-pt-agent" in us_ids
        assert "multi-pt-agent" in ppt_ids

    def test_agent_with_list_absent_from_unrelated_bucket(self, tmp_agent_dir):
        """The same agent must NOT appear in an unrelated bucket (``prototype``)."""
        self._write_list_agent(tmp_agent_dir, "multi-pt-agent", ["user_stories", "ppt"], order=1)

        prototype_ids = list_agent_ids("prototype")

        assert "multi-pt-agent" not in prototype_ids

    def test_duplicate_order_within_list_pipeline_bucket_raises(self, tmp_agent_dir):
        """Two agents both listing ``prototype_revision`` and sharing order=2 must raise
        AgentSpecError that names the offending pipeline bucket."""
        self._write_list_agent(tmp_agent_dir, "rev-agent-a", ["prototype_revision"], order=2)
        self._write_list_agent(tmp_agent_dir, "rev-agent-b", ["prototype_revision"], order=2)

        with pytest.raises(AgentSpecError) as exc_info:
            list_agent_ids("prototype_revision")

        assert "prototype_revision" in str(exc_info.value)

    def test_string_and_list_agents_coexist_in_bucket(self, tmp_agent_dir):
        """A string-typed agent and a list-typed agent that share a bucket both appear."""
        self._write_str_agent(tmp_agent_dir, "str-us-agent", "user_stories", order=1)
        self._write_list_agent(tmp_agent_dir, "list-us-agent", ["user_stories", "ppt"], order=2)

        us_ids = list_agent_ids("user_stories")

        assert "str-us-agent" in us_ids
        assert "list-us-agent" in us_ids


# ---------------------------------------------------------------------------
# Property tests — pipeline_type list parsing (task 1.5)
# Validates: Requirements 6.4, 6.5
# ---------------------------------------------------------------------------


class TestOrderUniquenessProperty:
    """Property 3: Order uniqueness.

    For every pipeline_type in SUPPORTED_PIPELINE_TYPES, no two agents in
    list_agent_ids(pt) share the same ``order`` value.

    The parametric variant runs against the REAL filesystem so it catches any
    future authoring mistake across all pipelines — it is the cheapest guard
    against a duplicate-order regression slipping in.

    The tmp-dir variant confirms the duplicate-order guard fires specifically
    when two agents share a pipeline via the NEW list form of ``pipeline_type``.

    **Validates: Requirements 6.4, 6.5**
    """

    @pytest.mark.parametrize("pipeline_type", sorted(loader_module.SUPPORTED_PIPELINE_TYPES))
    def test_no_two_agents_share_order_in_any_pipeline(self, pipeline_type: str):
        """Property 3 (real filesystem): list_agent_ids must not raise AgentSpecError
        for any supported pipeline type — meaning no duplicate orders exist on disk.
        """
        # If this raises AgentSpecError, two agents share the same order value in
        # the given pipeline; that is the bug this property guards against.
        try:
            ids = list_agent_ids(pipeline_type)
        except AgentSpecError as exc:
            pytest.fail(
                f"Duplicate order detected in pipeline '{pipeline_type}': {exc}"
            )

        # Additionally assert the returned ids are strictly ordered (order values
        # are globally unique per pipeline — the sort is deterministic).
        # We cannot check the order values directly here (list_agent_ids only
        # returns ids), but a successful call already proves uniqueness.
        assert isinstance(ids, list), (
            f"list_agent_ids('{pipeline_type}') returned {type(ids).__name__}, expected list"
        )

    def test_list_pipeline_type_duplicate_order_raises(self, tmp_agent_dir):
        """Property 3 (tmp dir, list pipeline_type form): two agents that BOTH declare
        the same pipeline type inside a list AND share the same order value must cause
        list_agent_ids to raise AgentSpecError naming the conflicting pipeline type.

        This exercises the NEW code path: pipeline_type as a list where the
        membership check is ``pipeline_type in spec.pipeline_type``.
        """
        # Agent 1: pipeline_type is a list that includes "shared_pipeline"
        content_a = (
            "---\n"
            "id: list-agent-alpha\n"
            "name: List Agent Alpha\n"
            "role: Alpha Role\n"
            "pipeline_type:\n"
            "  - shared_pipeline\n"
            "  - other_pipeline\n"
            "order: 2\n"
            "max_tokens: 4000\n"
            'icon: "🅰️"\n'
            "estimated_duration: 3.0\n"
            "---\n"
            "\n"
            "System prompt for alpha.\n"
        )
        # Agent 2: pipeline_type is also a list that includes "shared_pipeline"
        # and shares order=2 with agent alpha → duplicate order in that bucket
        content_b = (
            "---\n"
            "id: list-agent-beta\n"
            "name: List Agent Beta\n"
            "role: Beta Role\n"
            "pipeline_type:\n"
            "  - shared_pipeline\n"
            "  - yet_another_pipeline\n"
            "order: 2\n"
            "max_tokens: 4000\n"
            'icon: "🅱️"\n'
            "estimated_duration: 3.0\n"
            "---\n"
            "\n"
            "System prompt for beta.\n"
        )
        create_agent_file(tmp_agent_dir, "list-agent-alpha", content_a)
        create_agent_file(tmp_agent_dir, "list-agent-beta", content_b)

        with pytest.raises(AgentSpecError) as exc_info:
            list_agent_ids("shared_pipeline")

        error_msg = str(exc_info.value)
        # The error must name the conflicting pipeline type so the author knows
        # which bucket has the collision.
        assert "shared_pipeline" in error_msg, (
            f"AgentSpecError should mention 'shared_pipeline' but got: {error_msg!r}"
        )
        # The error must also mention the shared order value.
        assert "2" in error_msg, (
            f"AgentSpecError should mention order value '2' but got: {error_msg!r}"
        )
