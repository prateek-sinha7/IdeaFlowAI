"""T073 — Unit tests for agents/workflow_memory/memory.py (Phase 8 / FR-012).

Tests:
  - Per-user isolation: user A's entries not accessible to user B
  - Key/value round-trip
  - Constitution retrieval (get/set/delete)
  - 1000-entry limit enforcement
  - Cross-session persistence (in-memory fallback)
  - Key length validation (1–255 chars)
  - Value length validation (up to 1,048,576 chars)
"""

from __future__ import annotations

import pytest

from agents.workflow_memory.memory import WorkflowMemory, WorkflowMemoryError


@pytest.fixture
def memory() -> WorkflowMemory:
    return WorkflowMemory(use_db=False)


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_entry(memory: WorkflowMemory) -> None:
    await memory.set_entry("user-a", "my-key", "my-value")
    result = await memory.get_entry("user-a", "my-key")
    assert result == "my-value"


@pytest.mark.asyncio
async def test_get_missing_entry_returns_none(memory: WorkflowMemory) -> None:
    result = await memory.get_entry("user-a", "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_overwrite_entry(memory: WorkflowMemory) -> None:
    await memory.set_entry("user-a", "key", "v1")
    await memory.set_entry("user-a", "key", "v2")
    result = await memory.get_entry("user-a", "key")
    assert result == "v2"


# ---------------------------------------------------------------------------
# Per-user isolation (FR-012: entries MUST NOT be exposed to other users)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_user_isolation(memory: WorkflowMemory) -> None:
    await memory.set_entry("user-a", "secret", "user-a-value")
    await memory.set_entry("user-b", "secret", "user-b-value")

    a_val = await memory.get_entry("user-a", "secret")
    b_val = await memory.get_entry("user-b", "secret")

    assert a_val == "user-a-value"
    assert b_val == "user-b-value"
    assert a_val != b_val


@pytest.mark.asyncio
async def test_user_a_cannot_read_user_b_entry(memory: WorkflowMemory) -> None:
    await memory.set_entry("user-b", "private-key", "private-value")
    result = await memory.get_entry("user-a", "private-key")
    assert result is None


# ---------------------------------------------------------------------------
# Constitution helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_and_get_constitution(memory: WorkflowMemory) -> None:
    constitution = "# My Constitution\n\n## Principle 1\nBe helpful."
    await memory.set_constitution("user-a", constitution)
    result = await memory.get_constitution("user-a")
    assert result == constitution


@pytest.mark.asyncio
async def test_get_constitution_returns_none_when_not_set(memory: WorkflowMemory) -> None:
    result = await memory.get_constitution("user-no-constitution")
    assert result is None


@pytest.mark.asyncio
async def test_delete_constitution(memory: WorkflowMemory) -> None:
    await memory.set_constitution("user-a", "# Constitution")
    deleted = await memory.delete_constitution("user-a")
    assert deleted is True
    result = await memory.get_constitution("user-a")
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent_constitution_returns_false(memory: WorkflowMemory) -> None:
    deleted = await memory.delete_constitution("user-no-constitution")
    assert deleted is False


# ---------------------------------------------------------------------------
# Entry limit (1000 per user)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_1000_entry_limit_enforced(memory: WorkflowMemory) -> None:
    user_id = "user-limit"
    # Add 1000 entries
    for i in range(1000):
        await memory.set_entry(user_id, f"key-{i}", f"value-{i}")

    # 1001st entry should raise
    with pytest.raises(WorkflowMemoryError, match="limit"):
        await memory.set_entry(user_id, "key-overflow", "value")


@pytest.mark.asyncio
async def test_overwriting_existing_key_does_not_count_toward_limit(memory: WorkflowMemory) -> None:
    user_id = "user-overwrite"
    for i in range(1000):
        await memory.set_entry(user_id, f"key-{i}", f"value-{i}")

    # Overwriting an existing key should NOT raise
    await memory.set_entry(user_id, "key-0", "updated-value")
    result = await memory.get_entry(user_id, "key-0")
    assert result == "updated-value"


# ---------------------------------------------------------------------------
# Key/value validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_key_raises(memory: WorkflowMemory) -> None:
    with pytest.raises(WorkflowMemoryError, match="Key"):
        await memory.set_entry("user-a", "", "value")


@pytest.mark.asyncio
async def test_key_too_long_raises(memory: WorkflowMemory) -> None:
    with pytest.raises(WorkflowMemoryError, match="Key"):
        await memory.set_entry("user-a", "k" * 256, "value")


@pytest.mark.asyncio
async def test_key_at_max_length_accepted(memory: WorkflowMemory) -> None:
    await memory.set_entry("user-a", "k" * 255, "value")
    result = await memory.get_entry("user-a", "k" * 255)
    assert result == "value"


@pytest.mark.asyncio
async def test_value_too_long_raises(memory: WorkflowMemory) -> None:
    with pytest.raises(WorkflowMemoryError, match="Value"):
        await memory.set_entry("user-a", "key", "v" * (1_048_576 + 1))


@pytest.mark.asyncio
async def test_value_at_max_length_accepted(memory: WorkflowMemory) -> None:
    big_value = "v" * 1_048_576
    await memory.set_entry("user-a", "big-key", big_value)
    result = await memory.get_entry("user-a", "big-key")
    assert result == big_value
