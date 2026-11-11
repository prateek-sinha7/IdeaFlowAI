"""``ToolSchemaCache``: TTL, LRU, keying, single-flight and invalidation."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.connectors.tools.schema_cache import (
    CacheKey,
    ToolListing,
    ToolSchemaCache,
    scope_fingerprint,
)
from tests.fakes.connector_store import MutableClock


def _listing(clock: MutableClock) -> ToolListing:
    return ToolListing(tools=(), listed_at=clock())


class _Loader:
    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.calls = 0
        self.gate: asyncio.Event | None = None
        self.fail_next = False

    async def __call__(self) -> ToolListing:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("provider down")
        return _listing(self.clock)


KEY = CacheKey("github", "user-a", "abc")


class TestScopeFingerprint:
    def test_scope_fingerprint_ignores_order_when_same_scopes(self) -> None:
        assert scope_fingerprint(["repo", "read:org"]) == scope_fingerprint(
            ["read:org", "repo"]
        )

    def test_scope_fingerprint_differs_when_scopes_differ(self) -> None:
        assert scope_fingerprint(["repo"]) != scope_fingerprint(["repo", "read:org"])

    def test_scope_fingerprint_is_sixteen_hex_characters_when_computed(self) -> None:
        assert len(scope_fingerprint(["repo"])) == 16


class TestGetOrLoad:
    @pytest.mark.asyncio
    async def test_get_or_load_returns_cached_listing_when_within_ttl(self) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)

        first = await cache.get_or_load(KEY, loader)
        clock.advance(599)
        second = await cache.get_or_load(KEY, loader)

        assert first is second
        assert loader.calls == 1

    @pytest.mark.asyncio
    async def test_get_or_load_reloads_when_ttl_elapsed(self) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)

        await cache.get_or_load(KEY, loader)
        clock.advance(600)
        reloaded = await cache.get_or_load(KEY, loader)

        assert loader.calls == 2
        assert reloaded.listed_at == clock()

    @pytest.mark.asyncio
    async def test_get_or_load_keeps_users_apart_when_keys_differ(self) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)

        await cache.get_or_load(KEY, loader)
        await cache.get_or_load(CacheKey("github", "user-b", "abc"), loader)
        await cache.get_or_load(CacheKey("github", "user-a", "other-scopes"), loader)

        assert loader.calls == 3

    @pytest.mark.asyncio
    async def test_get_or_load_calls_loader_once_when_twenty_callers_race(
        self,
    ) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)
        loader.gate = asyncio.Event()

        tasks = [asyncio.create_task(cache.get_or_load(KEY, loader)) for _ in range(20)]
        await asyncio.sleep(0)
        loader.gate.set()
        results = await asyncio.gather(*tasks)

        assert loader.calls == 1
        assert len({id(r) for r in results}) == 1

    @pytest.mark.asyncio
    async def test_get_or_load_stores_nothing_when_loader_raises(self) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)
        loader.fail_next = True

        with pytest.raises(RuntimeError):
            await cache.get_or_load(KEY, loader)
        await cache.get_or_load(KEY, loader)

        assert loader.calls == 2
        assert len(cache) == 1

    @pytest.mark.asyncio
    async def test_get_or_load_evicts_least_recently_used_when_over_capacity(
        self,
    ) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, max_entries=2, clock=clock)
        loader = _Loader(clock)
        a, b, c = (CacheKey("github", u, "s") for u in ("a", "b", "c"))

        await cache.get_or_load(a, loader)
        await cache.get_or_load(b, loader)
        await cache.get_or_load(a, loader)  # a is now most recent
        await cache.get_or_load(c, loader)  # evicts b
        calls_before = loader.calls
        await cache.get_or_load(a, loader)
        await cache.get_or_load(b, loader)

        assert len(cache) == 2
        assert loader.calls == calls_before + 1  # only b was reloaded


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_drops_every_fingerprint_of_user_and_connector_when_called(
        self,
    ) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)
        await cache.get_or_load(CacheKey("github", "user-a", "s1"), loader)
        await cache.get_or_load(CacheKey("github", "user-a", "s2"), loader)
        await cache.get_or_load(CacheKey("github", "user-b", "s1"), loader)

        dropped = cache.invalidate("user-a", "github")

        assert dropped == 2
        assert len(cache) == 1

    @pytest.mark.asyncio
    async def test_invalidate_user_drops_all_connectors_of_user_when_called(
        self,
    ) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        loader = _Loader(clock)
        await cache.get_or_load(CacheKey("github", "user-a", "s"), loader)
        await cache.get_or_load(CacheKey("other", "user-a", "s"), loader)
        await cache.get_or_load(CacheKey("github", "user-b", "s"), loader)

        assert cache.invalidate_user("user-a") == 2
        assert len(cache) == 1

    @pytest.mark.asyncio
    async def test_clear_empties_the_cache_when_called(self) -> None:
        clock = MutableClock()
        cache = ToolSchemaCache(600, clock=clock)
        await cache.get_or_load(KEY, _Loader(clock))

        cache.clear()

        assert len(cache) == 0


def test_listing_keeps_fetch_time_when_constructed() -> None:
    moment = datetime(2026, 1, 1, 12, 0, 0)

    assert ToolListing(tools=(), listed_at=moment).listed_at == moment
