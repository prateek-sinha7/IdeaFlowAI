"""Unit tests for ``agents/authz.py`` ``ScopedStore`` sync twins and the type filter.

No real I/O: the store is built either without a session (the twins must refuse
to run) or with a ``MagicMock`` session (an empty allow-list must never reach
the database).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agents.authz import ScopedStore


def test_read_events_page_in_session_raises_when_no_session_injected() -> None:
    store = ScopedStore(owner_id="user-1", workspace_id="ws-1")

    with pytest.raises(RuntimeError, match="requires an injected session"):
        store.read_events_page_in_session("run-1", 0, limit=10)


def test_get_run_in_session_raises_when_no_session_injected() -> None:
    store = ScopedStore(owner_id="user-1", workspace_id="ws-1")

    with pytest.raises(RuntimeError, match="requires an injected session"):
        store.get_run_in_session("run-1")


async def test_read_events_page_returns_empty_when_types_is_empty() -> None:
    session = MagicMock()
    store = ScopedStore(owner_id="user-1", workspace_id="ws-1", session=session)

    async_rows = await store.read_events_page("run-1", 0, limit=10, types=())
    sync_rows = store.read_events_page_in_session("run-1", 0, limit=10, types=[])

    assert async_rows == []
    assert sync_rows == []
    session.query.assert_not_called()
