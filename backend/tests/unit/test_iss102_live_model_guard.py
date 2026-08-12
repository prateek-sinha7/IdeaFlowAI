"""tests/unit/test_iss102_live_model_guard.py — the guard guards itself (ISS-102 / FIX-238).

``tests/conftest.py::_forbid_live_model_clients`` is the only thing standing between the
offline suite and a real AWS bill: the Bedrock ids and region are **hardcoded code defaults**
(``app/core/config.py:118/:123/:130``) and there is no ``backend/.env``, so no amount of env
unsetting makes ``build_model()`` offline.

A guard with no coverage of its own is a guard-shaped comment — it rots silently the first time
someone edits the conftest. These cases pin the four properties the guard's design depends on,
plus the one that makes its allow-list safe over time.

Deliberately NOT covered here: that the guard is *reached* from any particular production seam.
That is proven by the suite as a whole — a trip anywhere fails that test by name.
"""

from __future__ import annotations

import pytest

from tests.conftest import _CONSTRUCTS_BUT_NEVER_INVOKES, LiveModelClientConstructed


def test_guard_blocks_bedrock_client_construction():
    """The Bedrock client is the one that bills. Constructing it must raise."""
    from langchain_aws import ChatBedrockConverse

    with pytest.raises(LiveModelClientConstructed) as exc:
        ChatBedrockConverse(model="anthropic.claude-haiku-4-5-20251001-v1:0",
                            region_name="eu-central-1")
    # The message must name the offending test, or a CI failure is unactionable.
    assert "test_guard_blocks_bedrock_client_construction" in str(exc.value)
    assert "ChatBedrockConverse" in str(exc.value)


def test_guard_blocks_anthropic_client_construction():
    """The second reachable provider — ``create_deep_agent(model="anthropic:...")``
    constructs this one via langchain's ``init_chat_model``, bypassing ``build_model``."""
    from langchain_anthropic import ChatAnthropic

    with pytest.raises(LiveModelClientConstructed):
        ChatAnthropic(model="claude-haiku-4-5-20251001", api_key="not-a-real-key")


def test_guard_blocks_the_build_model_factory_path():
    """The ISS-102 path itself: the sanctioned factory must not yield a live client."""
    from app.agents.model_factory import build_model

    with pytest.raises(LiveModelClientConstructed):
        build_model()


def test_guard_blocks_the_smart_planner_bypass_path():
    """``SmartPlanner._build_llm`` (agents/planner/smart_planner.py:167) builds its client
    WITHOUT going through ``build_model``. This is why the guard patches the provider
    classes rather than the factory — a ``build_model`` guard would miss this entirely."""
    from agents.planner.smart_planner import SmartPlanner

    with pytest.raises(LiveModelClientConstructed):
        SmartPlanner()


def test_guard_preserves_isinstance_and_object_new():
    """The guard patches ``__init__``, never the class object.

    Replacing the class would break ``isinstance`` at
    ``deep_agent_runner._maybe_apply`` and ``cached_invoke._cache_control``, and would break
    ``tests/agents/test_bedrock_cache_and_thinking.py::_bedrock_instance``, which builds an
    uninitialised instance with ``object.__new__``. Both must keep working under the guard.
    """
    from langchain_aws import ChatBedrockConverse

    uninitialised = object.__new__(ChatBedrockConverse)
    assert isinstance(uninitialised, ChatBedrockConverse)


def test_allow_list_entries_all_still_exist():
    """The allow-list FAILS CLOSED — prove it, don't assume it.

    ``_CONSTRUCTS_BUT_NEVER_INVOKES`` exempts by EXACT nodeid. If an exempted test is renamed,
    moved or deleted, its entry becomes a stale exemption that silently protects nothing while
    looking like due diligence. This case turns that into a loud failure: every entry must
    resolve to a file that exists and contain the referenced test function name.
    """
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[2]
    stale: list[str] = []
    for nodeid, reason in _CONSTRUCTS_BUT_NEVER_INVOKES.items():
        assert reason.strip(), f"{nodeid} has no reason recorded"
        path_part, _, selector = nodeid.partition("::")
        test_path = backend_root / path_part
        if not test_path.is_file():
            stale.append(f"{nodeid} — file {path_part} no longer exists")
            continue
        func_name = selector.rsplit("::", 1)[-1].split("[", 1)[0]
        if func_name not in test_path.read_text(encoding="utf-8"):
            stale.append(f"{nodeid} — {func_name} not found in {path_part}")

    assert not stale, (
        "Stale entries in _CONSTRUCTS_BUT_NEVER_INVOKES (backend/tests/conftest.py). Each of "
        "these exempts a test that no longer exists under that nodeid, so the exemption is "
        "dead weight — delete it, or correct it to the new nodeid:\n  "
        + "\n  ".join(stale)
    )
