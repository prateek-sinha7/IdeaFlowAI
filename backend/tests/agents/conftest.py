"""conftest.py for agents test suite.

Provides shared fixtures and helpers for testing the folder-per-agent
architecture (loader, factory, registry, orchestrator).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers for building AGENT.md content in tests
# ---------------------------------------------------------------------------


def make_agent_md(
    *,
    id: str = "test-agent",
    name: str = "Test Agent",
    role: str = "Testing",
    pipeline_type: str = "user_stories",
    order: int = 1,
    max_tokens: int = 4000,
    tools: list[str] | None = None,
    guardrails: list[str] | None = None,
    context_from: list[str] | None = None,
    icon: str = "🤖",
    estimated_duration: float = 3.0,
    prompt_body: str = "You are a test agent.",
    extra_fields: dict | None = None,
) -> str:
    """Build a valid AGENT.md string for use in tests."""
    lines = ["---"]
    lines.append(f"id: {id}")
    lines.append(f"name: {name}")
    lines.append(f"role: {role}")
    lines.append(f"pipeline_type: {pipeline_type}")
    lines.append(f"order: {order}")
    lines.append(f"max_tokens: {max_tokens}")

    if tools is not None:
        if tools:
            lines.append("tools:")
            for t in tools:
                lines.append(f"  - {t}")
        else:
            lines.append("tools: []")

    if guardrails is not None:
        if guardrails:
            lines.append("guardrails:")
            for g in guardrails:
                lines.append(f"  - {g}")
        else:
            lines.append("guardrails: []")

    if context_from is not None:
        if context_from:
            lines.append("context_from:")
            for c in context_from:
                lines.append(f"  - {c}")
        else:
            lines.append("context_from: []")

    lines.append(f'icon: "{icon}"')
    lines.append(f"estimated_duration: {estimated_duration}")

    if extra_fields:
        for k, v in extra_fields.items():
            lines.append(f"{k}: {v!r}")

    lines.append("---")
    lines.append("")
    lines.append(prompt_body)

    return "\n".join(lines)


@pytest.fixture
def tmp_agent_dir(tmp_path: Path):
    """Fixture that provides a temporary agents/prompts directory.

    Patches agents.loader._PROMPTS_DIR to point to the temp directory
    so tests don't touch the real filesystem.
    """
    import agents.loader as loader_module

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()

    original_prompts_dir = loader_module._PROMPTS_DIR
    original_cache = dict(loader_module._SPEC_CACHE)

    loader_module._PROMPTS_DIR = prompts_dir
    loader_module._SPEC_CACHE.clear()

    yield prompts_dir

    # Restore
    loader_module._PROMPTS_DIR = original_prompts_dir
    loader_module._SPEC_CACHE.clear()
    loader_module._SPEC_CACHE.update(original_cache)


def create_agent_file(prompts_dir: Path, agent_id: str, content: str) -> Path:
    """Create an AGENT.md file in the given prompts directory."""
    agent_dir = prompts_dir / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agent_dir / "AGENT.md"
    agent_file.write_text(content, encoding="utf-8")
    return agent_file
