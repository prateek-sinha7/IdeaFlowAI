"""tests/agents/test_hooks_catalog_agent_ids.py — ISS-290.

``hooks_catalog.list_global_hooks()`` loads each hook's ``compatible_agents``
straight from ``HOOK.md`` YAML frontmatter with no cross-validation against
the real agent roster (``agents.registry.get_all_agents_flat()``). Several
``HOOK.md`` files under ``backend/hooks/global/`` list agent ids that were
renamed/retired (``html-prototype-builder``, ``prototype-polisher``,
``ppt-slide-architect``, ``requirements-analyst``) and are absent from every
real agent id. The frontend renders that array verbatim as "Compatible
agents" chips, presenting fictional agents as fact.
"""

from __future__ import annotations

import pytest

from agents.registry import get_all_agents_flat
from app.agents import hooks_catalog


@pytest.fixture(autouse=True)
def _fresh_hooks_cache():
    hooks_catalog.clear_cache()
    yield
    hooks_catalog.clear_cache()


@pytest.mark.issue("ISS-290")
def test_every_hooks_compatible_agents_id_is_a_real_agent():
    """Every id in every hook's compatible_agents must resolve to a real agent."""
    real_agent_ids = {agent.id for agent in get_all_agents_flat()}

    stale = {
        hook.id: sorted(set(hook.compatible_agents) - real_agent_ids)
        for hook in hooks_catalog.list_global_hooks()
        if set(hook.compatible_agents) - real_agent_ids
    }

    assert stale == {}, f"hooks reference nonexistent agent ids: {stale}"
