"""Process-local cache of the tool lists a remote MCP server returns.

A GitHub tool list depends on the token and on organisation policy, so entries are
keyed by (connector, verified user, scope fingerprint) and never shared between
users. Entries live ``CONNECTOR_TOOL_SCHEMA_TTL_SECONDS`` (600 s default). Loads
are single-flight per key: parallel callers wait for one provider call. A second
process keeps its own cache, which stays correct because every entry expires.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import weakref
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, NamedTuple

from app.connectors.store import utcnow

DEFAULT_MAX_ENTRIES = 256


class CacheKey(NamedTuple):
    """Identifies one cached tool list."""

    connector_key: str
    user_id: str
    scope_fingerprint: str


def scope_fingerprint(granted_scopes: Iterable[str]) -> str:
    """Return a short stable hash of the granted scopes (order does not matter)."""
    joined = " ".join(sorted(granted_scopes))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ListedTool:
    """One tool from ``tools/list`` after the allow and deny rules.

    ``definition`` is the raw ``mcp.types.Tool`` so a later bind step can build the
    callable tool without listing again.
    """

    source_name: str
    name: str
    title: str
    description: str
    write_capable: bool
    definition: Any


@dataclass(frozen=True)
class ToolListing:
    """A tool list and when it was fetched from the provider."""

    tools: tuple[ListedTool, ...]
    listed_at: datetime


@dataclass(frozen=True)
class _Entry:
    listing: ToolListing
    expires_at: datetime


Loader = Callable[[], Awaitable[ToolListing]]


class ToolSchemaCache:
    """TTL + LRU cache with single-flight loads."""

    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[CacheKey, _Entry] = OrderedDict()
        self._guard = threading.Lock()
        # asyncio locks must not cross event loops: one table per loop.
        self._flight: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            weakref.WeakValueDictionary[CacheKey, asyncio.Lock],
        ] = weakref.WeakKeyDictionary()

    async def get_or_load(self, key: CacheKey, loader: Loader) -> ToolListing:
        """Return the live entry for ``key`` or load, store and return a new one.

        A failing ``loader`` stores nothing; its exception reaches the caller that
        ran it, and the next waiter tries again.
        """
        cached = self._peek(key)
        if cached is not None:
            return cached
        async with self._flight_lock(key):
            cached = self._peek(key)
            if cached is not None:
                return cached
            listing = await loader()
            self._store(key, listing)
            return listing

    def invalidate(self, user_id: str, connector_key: str) -> int:
        """Drop every entry of (user, connector) whatever its scope fingerprint."""
        with self._guard:
            stale = [
                key
                for key in self._entries
                if key.user_id == user_id and key.connector_key == connector_key
            ]
            for key in stale:
                del self._entries[key]
            return len(stale)

    def invalidate_user(self, user_id: str) -> int:
        """Drop every entry of ``user_id`` (account deletion)."""
        with self._guard:
            stale = [key for key in self._entries if key.user_id == user_id]
            for key in stale:
                del self._entries[key]
            return len(stale)

    def clear(self) -> None:
        """Drop every entry."""
        with self._guard:
            self._entries.clear()

    def __len__(self) -> int:
        with self._guard:
            return len(self._entries)

    def _peek(self, key: CacheKey) -> ToolListing | None:
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.listing

    def _store(self, key: CacheKey, listing: ToolListing) -> None:
        with self._guard:
            self._entries[key] = _Entry(listing, self._clock() + self._ttl)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def _flight_lock(self, key: CacheKey) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        table = self._flight.get(loop)
        if table is None:
            table = weakref.WeakValueDictionary()
            self._flight[loop] = table
        lock = table.get(key)
        if lock is None:
            lock = asyncio.Lock()
            table[key] = lock
        return lock
