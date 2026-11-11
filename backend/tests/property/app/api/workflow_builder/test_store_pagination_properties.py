"""Property tests for the session list pagination of the builder store.

# Feature: ai-workflow-builder, Property 27: Pagination is complete and ordered

For any set of sessions and page size, walking the list page by page with the
returned cursors yields every session of the caller exactly once, newest
activity first, and no other user's session.

**Validates: Requirements 2.8, 12.1, 31.1**

The walk runs against ``InMemoryBuilderStore``, which reuses the real store's
cursor helpers and keyset rule ``(updated_at DESC, id ASC)``. The fixed-example
walk against PostgreSQL lives in the store integration test (task 6.8).

``updated_at`` is drawn from a small set of minute offsets so that many sessions
tie on it and the ``id`` tie-break is exercised on every run.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.api.workflow_builder.store import (
    MAX_SESSION_PAGE_SIZE,
    SessionPage,
    clamp_page_size,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore

CALLER = "caller"
_OTHER_USERS = ("other-1", "other-2")
_BASE_TIME = datetime(2025, 1, 1, tzinfo=timezone.utc)

# (owner, minute offset). Few distinct offsets force ties on ``updated_at``.
_SESSION_SPECS = st.lists(
    st.tuples(
        st.sampled_from([CALLER, CALLER, *_OTHER_USERS]),
        st.integers(min_value=0, max_value=6),
    ),
    max_size=70,
)
# ``None`` is the default size; values outside 1..50 are clamped by the store.
_LIMITS = st.none() | st.integers(min_value=-3, max_value=MAX_SESSION_PAGE_SIZE + 10)


def _populate(
    store: InMemoryBuilderStore, specs: list[tuple[str, int]]
) -> dict[str, tuple[str, int]]:
    """Create one session per spec; return ``{session_id: (owner, minute offset)}``."""
    created: dict[str, tuple[str, int]] = {}
    for owner, offset in specs:
        row = store.create_session(owner, **BuilderSessionFactory.create_kwargs())
        row.updated_at = _BASE_TIME + timedelta(minutes=offset)  # type: ignore[assignment]
        created[str(row.id)] = (owner, offset)
    return created


def _walk(
    store: InMemoryBuilderStore, user_id: str, limit: int | None
) -> list[SessionPage]:
    """Follow ``next_cursor`` from the first page until it is None."""
    pages: list[SessionPage] = []
    cursor: str | None = None
    # A correct walk ends within one page per session; the bound stops a loop bug.
    for _ in range(200):
        page = store.list_sessions(user_id, limit=limit, cursor=cursor)
        pages.append(page)
        if page.next_cursor is None:
            return pages
        cursor = page.next_cursor
    raise AssertionError("pagination did not terminate")


def _expected_order(created: dict[str, tuple[str, int]], user_id: str) -> list[str]:
    """Caller's session ids, newest activity first, ties broken by id ascending."""
    mine = [
        (offset, sid) for sid, (owner, offset) in created.items() if owner == user_id
    ]
    mine.sort(key=lambda pair: (-pair[0], pair[1]))
    return [sid for _, sid in mine]


# Feature: ai-workflow-builder, Property 27: Pagination is complete and ordered
@settings(max_examples=100, deadline=None)
@given(specs=_SESSION_SPECS, limit=_LIMITS)
def test_list_sessions_yields_every_session_once_newest_first_when_walked_by_cursor(
    specs: list[tuple[str, int]], limit: int | None
) -> None:
    store = InMemoryBuilderStore()
    created = _populate(store, specs)

    pages = _walk(store, CALLER, limit)

    walked = [str(item.id) for page in pages for item in page.items]
    assert walked == _expected_order(created, CALLER)


# Feature: ai-workflow-builder, Property 27: Pagination is complete and ordered
@settings(max_examples=100, deadline=None)
@given(specs=_SESSION_SPECS, limit=_LIMITS)
def test_list_sessions_returns_no_foreign_session_when_other_users_have_sessions(
    specs: list[tuple[str, int]], limit: int | None
) -> None:
    store = InMemoryBuilderStore()
    created = _populate(store, specs)

    pages = _walk(store, CALLER, limit)

    for page in pages:
        for item in page.items:
            assert item.user_id == CALLER
            assert created[str(item.id)][0] == CALLER


# Feature: ai-workflow-builder, Property 27: Pagination is complete and ordered
@settings(max_examples=100, deadline=None)
@given(specs=_SESSION_SPECS, limit=_LIMITS)
def test_list_sessions_fills_every_page_but_the_last_when_walked_by_cursor(
    specs: list[tuple[str, int]], limit: int | None
) -> None:
    store = InMemoryBuilderStore()
    _populate(store, specs)
    page_size = clamp_page_size(limit)

    pages = _walk(store, CALLER, limit)

    for page in pages[:-1]:
        assert len(page.items) == page_size
        assert page.next_cursor is not None
    assert len(pages[-1].items) <= page_size
    assert pages[-1].next_cursor is None


# Feature: ai-workflow-builder, Property 27: Pagination is complete and ordered
@settings(max_examples=100, deadline=None)
@given(specs=_SESSION_SPECS, limit=_LIMITS)
def test_list_sessions_keeps_the_walk_stable_when_each_user_is_walked(
    specs: list[tuple[str, int]], limit: int | None
) -> None:
    store = InMemoryBuilderStore()
    created = _populate(store, specs)

    for user_id in (CALLER, *_OTHER_USERS):
        pages = _walk(store, user_id, limit)
        walked = [str(item.id) for page in pages for item in page.items]
        assert walked == _expected_order(created, user_id)
        assert len(walked) == len(set(walked))
