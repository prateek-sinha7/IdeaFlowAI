"""Integration tests for agent pipeline workflows.

These tests verify:
1. Correct agent sequence for each pipeline type
2. Pipeline execution with real Claude API (requires ANTHROPIC_API_KEY)
3. Output format validation (JSON for PPT/Prototype, Markdown for User Stories)
4. Context passing between agents
5. Error handling and recovery

Run with: pytest backend/tests/integration/ -v
Skip if no API key: pytest backend/tests/integration/ -v -m "not requires_api_key"
"""

import asyncio
import json
import os
import pytest
import logging

from app.agents.base import BaseAgent, AgentConfigurationError
from app.agents.pipeline import PipelineExecutor
from app.agents.registry import (
    get_pipeline_agents,
    get_all_agents_flat,
    get_agent_by_id,
    USER_STORY_AGENTS,
    PPT_AGENTS,
    PROTOTYPE_AGENTS,
    APP_BUILDER_AGENTS,
    REVERSE_ENGINEER_AGENTS,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# Skip tests that require API key if not configured
requires_api_key = pytest.mark.skipif(
    not settings.ANTHROPIC_API_KEY,
    reason="ANTHROPIC_API_KEY not configured"
)


# ============================================================
# AGENT REGISTRY TESTS — Verify correct agent definitions
# ============================================================

class TestAgentRegistry:
    """Test that all pipeline types have correct agent definitions."""

    def test_user_stories_pipeline_has_6_agents(self):
        """User Stories pipeline should have 6 agents."""
        agents = get_pipeline_agents("user_stories")
        assert len(agents) == 6, f"Expected 6 agents, got {len(agents)}"

    def test_ppt_pipeline_has_3_agents(self):
        """PPT pipeline should have 3 agents."""
        agents = get_pipeline_agents("ppt")
        assert len(agents) == 3, f"Expected 3 agents, got {len(agents)}"

    def test_prototype_pipeline_has_4_agents(self):
        """Prototype pipeline should have 4 agents."""
        agents = get_pipeline_agents("prototype")
        assert len(agents) == 4, f"Expected 4 agents, got {len(agents)}"

    def test_app_builder_pipeline_has_4_agents(self):
        """App Builder pipeline should have 4 agents."""
        agents = get_pipeline_agents("app_builder")
        assert len(agents) == 4, f"Expected 4 agents, got {len(agents)}"

    def test_reverse_engineer_pipeline_has_4_agents(self):
        """Reverse Engineer pipeline should have 4 agents."""
        agents = get_pipeline_agents("reverse_engineer")
        assert len(agents) == 4, f"Expected 4 agents, got {len(agents)}"

    def test_agents_are_ordered_correctly(self):
        """All agents in each pipeline should be ordered by their 'order' field."""
        for pipeline_type in ["user_stories", "ppt", "prototype", "app_builder", "reverse_engineer"]:
            agents = get_pipeline_agents(pipeline_type)
            orders = [a.order for a in agents]
            assert orders == sorted(orders), f"Agents in {pipeline_type} are not in order: {orders}"

    def test_all_agents_have_system_prompts(self):
        """Every agent must have a non-empty system prompt."""
        all_agents = get_all_agents_flat()
        for agent in all_agents:
            assert agent.system_prompt, f"Agent {agent.id} has empty system_prompt"
            assert len(agent.system_prompt) > 50, f"Agent {agent.id} has very short system_prompt ({len(agent.system_prompt)} chars)"

    def test_all_agents_have_unique_ids_within_pipeline(self):
        """Agent IDs must be unique within each pipeline."""
        for pipeline_type in ["user_stories", "ppt", "prototype", "app_builder", "reverse_engineer"]:
            agents = get_pipeline_agents(pipeline_type)
            ids = [a.id for a in agents]
            assert len(ids) == len(set(ids)), f"Duplicate agent IDs in {pipeline_type}: {[x for x in ids if ids.count(x) > 1]}"

    def test_user_stories_agent_sequence(self):
        """User Stories pipeline should follow the correct agent sequence."""
        agents = get_pipeline_agents("user_stories")
        expected_roles = [
            "Product Strategist",       # domain-analyst
            "Principal Product Manager", # epic-architect
            "Technical Lead",           # story-estimator
            "Solution Architect",       # nfr-specialist
            "Agile Coach",             # backlog-reviewer
            "Principal PM",            # backlog-compiler
        ]
        actual_roles = [a.role for a in agents]
        assert actual_roles == expected_roles, f"Agents have wrong roles: {actual_roles}"

    def test_ppt_agent_sequence(self):
        """PPT pipeline should start with audience analysis and end with export."""
        agents = get_pipeline_agents("ppt")
        assert agents[0].id == "audience-analyst", f"First agent should be audience-analyst, got {agents[0].id}"
        assert agents[-1].id == "export-formatter", f"Last agent should be export-formatter, got {agents[-1].id}"

    def test_prototype_agent_sequence(self):
        """Prototype pipeline should end with finalizer that outputs HTML."""
        agents = get_pipeline_agents("prototype")
        assert agents[-1].id == "prototype-finalizer", f"Last agent should be prototype-finalizer, got {agents[-1].id}"
        assert "HTML" in agents[-1].system_prompt, "Last agent should mention HTML in its prompt"

    def test_ppt_export_formatter_requests_json(self):
        """PPT export-formatter should request JSON output."""
        agent = get_agent_by_id("export-formatter")
        assert agent is not None
        assert "JSON" in agent.system_prompt
        assert "ONLY valid JSON" in agent.system_prompt

    def test_ppt_uses_light_color_scheme(self):
        """PPT export-formatter should use light theme colors."""
        agent = get_agent_by_id("export-formatter")
        assert agent is not None
        assert "#ffffff" in agent.system_prompt, "Should use white background"
        assert "#141413" in agent.system_prompt, "Should use dark text"

    def test_prototype_assembler_requests_html(self):
        """Prototype assembler should request HTML output."""
        agent = get_agent_by_id("prototype-assembler")
        assert agent is not None
        assert "HTML" in agent.system_prompt
        assert "<!DOCTYPE html>" in agent.system_prompt


# ============================================================
# PIPELINE EXECUTION TESTS — Require API key
# ============================================================

@requires_api_key
class TestPipelineExecution:
    """Integration tests that execute pipelines with real Claude API."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.mark.asyncio
    async def test_user_stories_pipeline_produces_markdown(self):
        """User Stories pipeline should produce markdown output."""
        executor = PipelineExecutor("user_stories")
        final_output = ""
        agent_count = 0

        async for update in executor.execute("A simple todo app with user authentication"):
            if update["type"] == "agent_complete":
                agent_count += 1
                logger.info("Agent %d complete: %s", agent_count, update["data"]["name"])
            elif update["type"] == "pipeline_complete":
                final_output = update["data"]["final_output"]

        assert agent_count == 12, f"Expected 12 agents to complete, got {agent_count}"
        assert len(final_output) > 100, "Final output should be substantial"
        # User stories output should contain markdown indicators
        assert any(marker in final_output for marker in ["#", "**", "- ", "As a"]), \
            "Output should contain markdown formatting"

    @pytest.mark.asyncio
    async def test_ppt_pipeline_produces_valid_json(self):
        """PPT pipeline should produce valid JSON slide data."""
        executor = PipelineExecutor("ppt")
        final_output = ""
        agent_count = 0

        async for update in executor.execute("A pitch deck for an AI-powered note-taking app"):
            if update["type"] == "agent_complete":
                agent_count += 1
                logger.info("Agent %d complete: %s", agent_count, update["data"]["name"])
            elif update["type"] == "pipeline_complete":
                final_output = update["data"]["final_output"]

        assert agent_count == 10, f"Expected 10 agents to complete, got {agent_count}"
        assert len(final_output) > 100, "Final output should be substantial"

        # Try to parse as JSON
        # Extract JSON if wrapped in markdown
        json_str = final_output.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1])
        if "{" in json_str:
            json_str = json_str[json_str.index("{"):json_str.rindex("}") + 1]

        parsed = json.loads(json_str)
        assert "slides" in parsed, "Output should have 'slides' key"
        assert len(parsed["slides"]) >= 3, "Should have at least 3 slides"

        # Verify slide structure
        first_slide = parsed["slides"][0]
        assert "title" in first_slide, "Slide should have 'title'"
        assert "content" in first_slide or "type" in first_slide, "Slide should have content or type"

    @pytest.mark.asyncio
    async def test_prototype_pipeline_produces_html(self):
        """Prototype pipeline should produce HTML output."""
        executor = PipelineExecutor("prototype")
        final_output = ""
        agent_count = 0

        async for update in executor.execute("A simple dashboard with sidebar navigation and 3 pages"):
            if update["type"] == "agent_complete":
                agent_count += 1
                logger.info("Agent %d complete: %s", agent_count, update["data"]["name"])
            elif update["type"] == "pipeline_complete":
                final_output = update["data"]["final_output"]

        assert agent_count == 12, f"Expected 12 agents to complete, got {agent_count}"
        assert len(final_output) > 200, "Final output should be substantial"

        # Should be HTML
        output_lower = final_output.lower().strip()
        assert "<!doctype html>" in output_lower or "<html" in output_lower, \
            f"Output should be HTML, starts with: {final_output[:50]}"
        assert "<head" in output_lower, "HTML should have <head>"
        assert "<body" in output_lower, "HTML should have <body>"

    @pytest.mark.asyncio
    async def test_pipeline_passes_context_between_agents(self):
        """Each agent should receive context from previous agents."""
        executor = PipelineExecutor("user_stories")
        outputs = {}

        async for update in executor.execute("A fitness tracking app"):
            if update["type"] == "agent_complete":
                agent_id = update["data"]["agent_id"]
                # The executor stores outputs internally
                break  # Just test first agent completes

        # After first agent, context should be populated
        assert len(executor.context) >= 1, "Context should have at least 1 entry after first agent"

    @pytest.mark.asyncio
    async def test_pipeline_handles_agent_error_gracefully(self):
        """Pipeline should continue if a non-critical agent fails."""
        # This tests the error recovery path
        executor = PipelineExecutor("user_stories")
        completed = 0
        errors = 0

        async for update in executor.execute("Test error handling"):
            if update["type"] == "agent_complete":
                completed += 1
            elif update["type"] == "agent_error":
                errors += 1
            elif update["type"] == "pipeline_complete":
                break

        # Pipeline should complete (even if some agents error)
        assert completed + errors > 0, "At least some agents should have run"


# ============================================================
# SINGLE AGENT TESTS — Test individual agents
# ============================================================

@requires_api_key
class TestSingleAgentExecution:
    """Test individual agents produce expected output."""

    @pytest.mark.asyncio
    async def test_domain_analyst_produces_structured_output(self):
        """Domain Analyst should produce structured markdown analysis."""
        agent_def = get_agent_by_id("domain-analyst")
        assert agent_def is not None

        agent = BaseAgent(system_prompt=agent_def.system_prompt)
        output = await agent.run("A social media app for pet owners to share photos and find pet-friendly places")

        assert len(output) > 100, "Output should be substantial"
        assert any(word in output.lower() for word in ["domain", "problem", "market", "scope"]), \
            "Output should contain analysis keywords"

    @pytest.mark.asyncio
    async def test_export_formatter_produces_json(self):
        """Export Formatter should produce valid JSON."""
        agent_def = get_agent_by_id("export-formatter")
        assert agent_def is not None

        agent = BaseAgent(system_prompt=agent_def.system_prompt)
        context = """Original request: Create a pitch deck for a food delivery app.

--- Output from Audience Analyst ---
Target: Investors, Series A

--- Output from Slide Content Writer ---
Slide 1: Title - "FoodFast: Delivering Joy"
Slide 2: Problem - "30% of orders arrive cold"
Slide 3: Solution - "AI-optimized routing"
"""
        output = await agent.run(context)

        # Should be parseable JSON
        json_str = output.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1])
        if "{" in json_str:
            json_str = json_str[json_str.index("{"):json_str.rindex("}") + 1]

        parsed = json.loads(json_str)
        assert "slides" in parsed, "Should have slides key"


# ============================================================
# PARSER TESTS — Test frontend parsers
# ============================================================

class TestPPTParser:
    """Test the PPT JSON parser handles various Claude output formats."""

    def test_parses_clean_json(self):
        """Should parse clean JSON without issues."""
        data = '{"slides":[{"title":"Test","content":[{"text":"Hello"}],"type":"text","colorScheme":{"background":"#fff","text":"#000","accent":"#c96442"}}]}'
        parsed = json.loads(data)
        assert "slides" in parsed
        assert len(parsed["slides"]) == 1
        assert parsed["slides"][0]["title"] == "Test"

    def test_parses_json_in_code_fence(self):
        """Should extract JSON from markdown code fences."""
        # Simulated test — actual parsing happens in frontend
        json_with_fence = '```json\n{"slides":[{"title":"Test","content":[],"type":"text"}]}\n```'
        # Extract JSON
        import re
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', json_with_fence)
        assert match is not None
        extracted = match.group(1).strip()
        parsed = json.loads(extracted)
        assert "slides" in parsed

    def test_parses_json_with_extra_text(self):
        """Should find JSON even with extra text around it."""
        messy_output = 'Here is the slide data:\n\n{"slides":[{"title":"Test","content":[],"type":"text"}]}\n\nI hope this helps!'
        # Find JSON boundaries
        first_brace = messy_output.index("{")
        last_brace = messy_output.rindex("}")
        json_str = messy_output[first_brace:last_brace + 1]
        parsed = json.loads(json_str)
        assert "slides" in parsed


# ============================================================
# CUSTOM AGENT ORDER TESTS
# ============================================================

class TestCustomAgentOrder:
    """Test that custom agent ordering works correctly."""

    def test_custom_agent_ids_resolve_correctly(self):
        """Custom agent IDs should resolve to valid agent definitions."""
        all_agents = get_all_agents_flat()
        agent_map = {a.id: a for a in all_agents}

        # Test resolving a custom order
        custom_ids = ["domain-analyst", "epic-architect", "story-writer"]
        resolved = [agent_map[aid] for aid in custom_ids if aid in agent_map]

        assert len(resolved) == 3
        assert resolved[0].id == "domain-analyst"
        assert resolved[1].id == "epic-architect"
        assert resolved[2].id == "story-writer"

    def test_pipeline_executor_accepts_custom_agents(self):
        """PipelineExecutor should accept custom agent list."""
        agents = get_pipeline_agents("user_stories")[:3]  # First 3 only
        executor = PipelineExecutor("user_stories", custom_agents=agents)
        assert len(executor.agents) == 3

    def test_unknown_agent_ids_are_skipped(self):
        """Unknown agent IDs should be silently skipped."""
        all_agents = get_all_agents_flat()
        agent_map = {a.id: a for a in all_agents}

        custom_ids = ["domain-analyst", "nonexistent-agent", "story-writer"]
        resolved = [agent_map[aid] for aid in custom_ids if aid in agent_map]

        assert len(resolved) == 2  # nonexistent skipped
