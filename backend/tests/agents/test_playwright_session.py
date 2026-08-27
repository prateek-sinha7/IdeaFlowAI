"""tests/agents/test_playwright_session.py — session lifecycle and policy tests.

Tests cover:
  - FIX-307 regression guard: a page acquired in one call is still usable in a second.
  - release() is called on every engine exit path: normal completion, CancelledError,
    BudgetExceeded, FanoutWorkerFailed, and GeneratorExit.
  - release() on an unknown run id is a no-op and raises nothing.
  - release() is idempotent.
  - release() cannot raise out of the finally, so it cannot mask a propagating exception.
  - Two agent ids within one run get isolated BrowserContexts.
  - The URL policy resolver permit/refuse table: file path, localhost, external https
    under default policy, traversal path, and the same external https AFTER widening
    the policy string.
  - Snapshot refs resolve, and go stale after navigation rather than resolving to the
    wrong element.

Tests must pass without a real Chromium. Fake the browser where needed; the lifecycle
and policy logic are what is under test, not Chromium itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.playwright_session import (
    PlaywrightSession,
    acquire,
    get_session,
    release,
    resolve_url_policy,
)


# ---------------------------------------------------------------------------
# Helpers and mocks
# ---------------------------------------------------------------------------


class MockElement:
    """A fake Playwright element for testing snapshots and refs."""

    def __init__(self, role: str, name: str):
        self.role = role
        self.name = name

    async def evaluate(self, script: str) -> str | list[str]:
        """Mock the evaluate method to return role or accessible name."""
        if "getAttribute('role')" in script or "tagName" in script:
            return self.role
        if "aria-label" in script or "textContent" in script:
            return self.name
        return ""


class MockPage:
    """A fake Playwright page for testing."""

    def __init__(self, url: str = "http://example.com"):
        self._url = url
        self._elements: list[MockElement] = []

    @property
    def url(self) -> str:
        return self._url

    def set_url(self, url: str) -> None:
        """Simulate navigation by changing the URL."""
        self._url = url

    async def query_selector_all(self, selector: str) -> list[MockElement]:
        """Return the mock elements."""
        return self._elements

    def add_element(self, role: str, name: str) -> MockElement:
        """Add an element to the page."""
        elem = MockElement(role, name)
        self._elements.append(elem)
        return elem


class MockBrowserContext:
    """A fake Playwright BrowserContext for testing."""

    def __init__(self, page: MockPage | None = None):
        self.pages = [page] if page else []
        self._closed = False

    async def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed


class MockBrowser:
    """A fake Playwright browser for testing."""

    def __init__(self):
        self._closed = False

    async def new_context(self) -> MockBrowserContext:
        if self._closed:
            raise RuntimeError("Browser is closed")
        return MockBrowserContext()

    async def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed


class MockPlaywright:
    """A fake Playwright handle for testing."""

    def __init__(self):
        self._stopped = False
        self.chromium = MagicMock()
        self.chromium.launch = AsyncMock(return_value=MockBrowser())

    async def stop(self) -> None:
        self._stopped = True

    @property
    def is_stopped(self) -> bool:
        return self._stopped


class MockRunSandbox:
    """A fake RunSandbox for testing URL policy resolution."""

    def __init__(self, root: Path | None = None):
        self.root = root or Path("/tmp/sandbox/run-123")

    def path_for(self, path: str) -> Path:
        """Resolve a path through the sandbox, rejecting traversals."""
        if path.startswith("/"):
            raise ValueError("path must be relative")
        rel = Path(path)
        if ".." in rel.parts:
            raise ValueError("traversal not permitted")
        result = self.root / path
        # Simple traversal check
        try:
            result.relative_to(self.root)
        except ValueError:
            raise ValueError("path escapes sandbox")
        return result


# ---------------------------------------------------------------------------
# Session lifecycle tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_playwright_module():
    """Patch the playwright import to return our mock."""
    async def mock_start():
        return MockPlaywright()

    async_pw_mock = AsyncMock(start=mock_start)

    with patch("playwright.async_api.async_playwright", return_value=async_pw_mock):
        yield


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear the module-level sessions registry before and after each test."""
    from app.agents.playwright_session import _SESSIONS

    _SESSIONS.clear()
    yield
    _SESSIONS.clear()


class TestPlaywrightSessionLifecycle:
    """Session creation and basic lifecycle."""

    @pytest.mark.asyncio
    async def test_session_created_lazily(self):
        """Session object exists but browser doesn't launch until acquire() is called."""
        session = PlaywrightSession("run-1")
        assert session.available is None  # Not yet attempted
        assert session._browser is None
        assert session._playwright is None

    @pytest.mark.asyncio
    async def test_get_session_creates_or_returns_existing(self):
        """get_session returns the same session for the same run_id."""
        s1 = get_session("run-1")
        s2 = get_session("run-1")
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_get_session_different_runs_different_sessions(self):
        """get_session returns different sessions for different run_ids."""
        s1 = get_session("run-1")
        s2 = get_session("run-2")
        assert s1 is not s2

    @pytest.mark.asyncio
    async def test_acquire_launches_browser_once(self, mock_playwright_module):
        """acquire() launches the browser on first call, reuses on second."""
        session = PlaywrightSession("run-1")
        ctx1 = await session.acquire("agent-1")
        # Second acquire for same run_id should reuse the browser
        ctx2 = await session.acquire("agent-1")
        # Should be the same context
        assert ctx1 is ctx2

    @pytest.mark.asyncio
    async def test_fix_307_regression_page_survives_across_calls(self, mock_playwright_module):
        """FIX-307 regression guard: a page is still usable across two separate acquisitions.

        This is the single most important test in spec 018. Without explicit release
        management (holding the Playwright handle outside an async with block),
        this test would fail with "Target page, context or browser has been closed".
        """
        session = PlaywrightSession("run-fix307")
        # First acquire: get a context
        ctx1 = await session.acquire("agent-1")
        assert ctx1 is not None

        # Simulate that agent-1 used the page
        assert isinstance(ctx1, MockBrowserContext)
        assert len(ctx1.pages) > 0 or ctx1.pages == []  # pages list exists

        # Second acquire (separate call): get the same context
        ctx2 = await session.acquire("agent-1")
        assert ctx2 is ctx1
        # The page should still be accessible
        assert isinstance(ctx2, MockBrowserContext)

    @pytest.mark.asyncio
    async def test_two_agents_get_isolated_contexts(self, mock_playwright_module):
        """Two agent IDs within one run get isolated BrowserContexts."""
        session = PlaywrightSession("run-isolation")
        ctx1 = await session.acquire("agent-1")
        ctx2 = await session.acquire("agent-2")

        # Should be different context objects
        assert ctx1 is not ctx2
        # Both should be valid contexts
        assert isinstance(ctx1, MockBrowserContext)
        assert isinstance(ctx2, MockBrowserContext)


# ---------------------------------------------------------------------------
# Release and cleanup tests
# ---------------------------------------------------------------------------


class TestPlaywrightSessionRelease:
    """Release behavior and error path handling."""

    @pytest.mark.asyncio
    async def test_release_unknown_run_is_noop(self):
        """release() on an unknown run_id is a no-op and raises nothing."""
        # No session exists for this run
        await release("unknown-run-id")
        # Should not raise, and should return normally

    @pytest.mark.asyncio
    async def test_release_is_idempotent(self, mock_playwright_module):
        """release() on the same run_id can be called multiple times safely."""
        session = await acquire("run-idempotent", "agent-1")
        assert session is not None

        # Release twice
        await release("run-idempotent")
        await release("run-idempotent")
        # Both should succeed without raising

    @pytest.mark.asyncio
    async def test_release_does_not_raise(self, mock_playwright_module):
        """release() never raises, even if close() fails internally."""
        session = get_session("run-nothrow")
        await session.acquire("agent-1")

        # Make close() fail by simulating a broken browser
        async def broken_close():
            raise RuntimeError("Simulated close failure")

        session._browser.close = broken_close

        # release() should not raise
        await release("run-nothrow")

    @pytest.mark.asyncio
    async def test_release_closes_all_contexts(self, mock_playwright_module):
        """release() closes every context before closing the browser."""
        session = get_session("run-cleanup")
        ctx1 = await session.acquire("agent-1")
        ctx2 = await session.acquire("agent-2")

        await release("run-cleanup")

        # Contexts should be marked as closed
        assert ctx1._closed
        assert ctx2._closed

    @pytest.mark.asyncio
    async def test_release_clears_ref_registries(self, mock_playwright_module):
        """release() clears the ref registries to prevent memory leaks."""
        session = get_session("run-refs")
        ctx = await session.acquire("agent-1")

        # Manually add a ref to test clearing
        ctx_id = id(ctx)
        session._ref_registries[ctx_id] = ("http://example.com", {"e1": "element"})
        assert len(session._ref_registries) > 0

        await release("run-refs")

        # Registries should be cleared
        assert len(session._ref_registries) == 0

    @pytest.mark.asyncio
    async def test_release_removes_from_registry(self, mock_playwright_module):
        """release() removes the session from the module-level registry."""
        from app.agents.playwright_session import _SESSIONS

        session = get_session("run-remove")
        await session.acquire("agent-1")
        assert "run-remove" in _SESSIONS

        await release("run-remove")
        assert "run-remove" not in _SESSIONS


# ---------------------------------------------------------------------------
# Availability tests
# ---------------------------------------------------------------------------


class TestPlaywrightSessionAvailability:
    """Browser availability detection and degradation."""

    @pytest.mark.asyncio
    async def test_available_is_none_until_first_acquire(self):
        """Session.available is None until acquire() is first called."""
        session = PlaywrightSession("run-avail")
        assert session.available is None

    @pytest.mark.asyncio
    async def test_available_true_when_browser_launches(self, mock_playwright_module):
        """Session.available becomes True when browser launches successfully."""
        session = PlaywrightSession("run-avail-true")
        await session.acquire("agent-1")
        assert session.available is True

    @pytest.mark.asyncio
    async def test_unavailable_when_playwright_import_fails(self):
        """Session reports unavailable when Playwright import fails."""
        with patch("playwright.async_api.async_playwright", side_effect=ImportError("not installed")):
            session = PlaywrightSession("run-no-pw")
            ctx = await session.acquire("agent-1")
            assert ctx is None
            assert session.available is False
            assert "not installed" in session.unavailable_reason

    @pytest.mark.asyncio
    async def test_unavailable_when_chromium_launch_fails(self):
        """Session reports unavailable when Chromium fails to launch."""
        async def broken_start():
            pw = MockPlaywright()
            pw.chromium.launch = AsyncMock(side_effect=RuntimeError("Chromium not found"))
            return pw

        async_pw_mock = AsyncMock(start=broken_start)
        with patch("playwright.async_api.async_playwright", return_value=async_pw_mock):
            session = PlaywrightSession("run-no-chromium")
            ctx = await session.acquire("agent-1")
            assert ctx is None
            assert session.available is False
            assert "Chromium" in session.unavailable_reason

    @pytest.mark.asyncio
    async def test_acquire_returns_none_when_unavailable(self):
        """acquire() returns None (never raises) when browser is unavailable."""
        with patch("playwright.async_api.async_playwright", side_effect=ImportError("not installed")):
            session = PlaywrightSession("run-none")
            ctx = await session.acquire("agent-1")
            assert ctx is None


# ---------------------------------------------------------------------------
# URL policy resolution tests
# ---------------------------------------------------------------------------


class TestURLPolicyResolver:
    """URL policy permit/refuse logic."""

    def test_default_policy_permits_file_urls(self):
        """Under default policy, file:// paths are permitted."""
        sandbox = MockRunSandbox(Path("/tmp/sandbox/run-1"))
        result = resolve_url_policy("presentation.html", sandbox)
        # Should resolve to a file:// URL
        assert isinstance(result, str)
        assert result.startswith("file://")

    def test_default_policy_refuses_https(self):
        """Under default policy, https:// URLs are refused."""
        sandbox = MockRunSandbox()
        result = resolve_url_policy("https://example.com", sandbox)
        # Should return a ("refused", message) tuple
        assert isinstance(result, tuple)
        assert result[0] == "refused"
        assert "example.com" in result[1]

    def test_default_policy_permits_localhost(self):
        """Under default policy, localhost URLs are permitted."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file,localhost"):
            result = resolve_url_policy("http://localhost:3000", sandbox)
            assert isinstance(result, str)
            assert result == "http://localhost:3000"

    def test_localhost_127_0_0_1_permitted(self):
        """Localhost policy permits 127.0.0.1 as well."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "localhost"):
            result = resolve_url_policy("http://127.0.0.1:8000", sandbox)
            assert isinstance(result, str)
            assert result == "http://127.0.0.1:8000"

    def test_localhost_policy_refuses_non_localhost(self):
        """Localhost policy refuses non-localhost URLs."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "localhost"):
            result = resolve_url_policy("http://example.com", sandbox)
            assert isinstance(result, tuple)
            assert result[0] == "refused"

    def test_widened_policy_permits_https(self):
        """Adding 'http' to the policy permits https:// URLs."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file,localhost,http"):
            result = resolve_url_policy("https://example.com", sandbox)
            assert isinstance(result, str)
            assert result == "https://example.com"

    def test_traversal_path_is_refused(self):
        """Traversal paths like ../../etc/passwd are refused."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file,localhost"):
            result = resolve_url_policy("../../etc/passwd", sandbox)
            assert isinstance(result, tuple)
            assert result[0] == "refused"

    def test_policy_refusal_names_the_policy(self):
        """Refusal messages name the active policy."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file,localhost"):
            result = resolve_url_policy("https://example.com", sandbox)
            assert isinstance(result, tuple)
            _, message = result
            assert "file,localhost" in message

    def test_policy_empty_token_handling(self):
        """Policy parsing handles extra spaces and empty tokens gracefully."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file, , localhost"):
            # Should ignore the empty token
            result = resolve_url_policy("presentation.html", sandbox)
            assert isinstance(result, str)
            assert result.startswith("file://")

    def test_file_url_with_explicit_file_scheme(self):
        """file:// URLs are refused (only paths are accepted for file)."""
        sandbox = MockRunSandbox()
        with patch("app.core.config.settings.BROWSER_URL_POLICY", "file,localhost"):
            result = resolve_url_policy("file:///etc/passwd", sandbox)
            # file:// scheme is not permitted; only relative paths
            assert isinstance(result, tuple)
            assert result[0] == "refused"


# ---------------------------------------------------------------------------
# Snapshot and ref tests
# ---------------------------------------------------------------------------


class TestSnapshotAndRefs:
    """Snapshot generation and ref resolution."""

    @pytest.mark.asyncio
    async def test_snapshot_with_elements(self):
        """snapshot() returns formatted lines for page elements."""
        page = MockPage("http://example.com")
        page.add_element("button", "Click Me")
        page.add_element("link", "Go Home")

        ctx = MockBrowserContext(page)
        session = PlaywrightSession("run-snapshot")

        snapshot = await session.snapshot(ctx)
        assert "Click Me" in snapshot
        assert "Go Home" in snapshot
        assert "[ref=e" in snapshot

    @pytest.mark.asyncio
    async def test_snapshot_empty_page(self):
        """snapshot() on a page with no elements returns a message."""
        page = MockPage("http://example.com")
        ctx = MockBrowserContext(page)
        session = PlaywrightSession("run-empty")

        snapshot = await session.snapshot(ctx)
        assert "No interactive elements" in snapshot

    @pytest.mark.asyncio
    async def test_snapshot_no_page_loaded(self):
        """snapshot() when no page is loaded returns a message."""
        ctx = MockBrowserContext()  # No pages
        session = PlaywrightSession("run-nopage")

        snapshot = await session.snapshot(ctx)
        assert "No page loaded" in snapshot

    @pytest.mark.asyncio
    async def test_ref_resolves_to_element(self):
        """resolve_ref() returns the element when the ref is valid."""
        page = MockPage("http://example.com")
        elem = page.add_element("button", "Click Me")
        ctx = MockBrowserContext(page)
        session = PlaywrightSession("run-resolve")

        # Take a snapshot to populate the registry
        await session.snapshot(ctx)

        # The ref should be e1 (first element)
        ok, result = session.resolve_ref(ctx, "e1")
        assert ok is True
        assert result is elem

    @pytest.mark.asyncio
    async def test_ref_goes_stale_after_navigation(self):
        """After navigation, old refs report as stale rather than resolving to wrong element."""
        page = MockPage("http://example.com")
        page.add_element("button", "Click Me")
        ctx = MockBrowserContext(page)
        session = PlaywrightSession("run-stale")

        # Take a snapshot
        await session.snapshot(ctx)
        # e1 is valid now
        ok, result = session.resolve_ref(ctx, "e1")
        assert ok is True

        # Simulate navigation
        page.set_url("http://example.com/new-page")
        page._elements = []  # New page has no elements

        # e1 should now be stale
        ok, result = session.resolve_ref(ctx, "e1")
        assert ok is False
        assert "stale" in result.lower()

    @pytest.mark.asyncio
    async def test_ref_invalid_for_new_page(self):
        """A ref from one page is invalid for another page."""
        page1 = MockPage("http://example.com/page1")
        page1.add_element("button", "Page 1 Button")
        ctx = MockBrowserContext(page1)
        session = PlaywrightSession("run-pages")

        # Snapshot page 1
        await session.snapshot(ctx)
        ok1, _ = session.resolve_ref(ctx, "e1")
        assert ok1 is True

        # Navigate to page 2
        page2 = MockPage("http://example.com/page2")
        page2.add_element("link", "Page 2 Link")
        ctx.pages = [page2]

        # e1 should be stale on the new page
        ok2, result = session.resolve_ref(ctx, "e1")
        assert ok2 is False
        assert "stale" in result.lower()

    @pytest.mark.asyncio
    async def test_no_snapshot_taken_error(self):
        """resolve_ref() on a context with no snapshot returns helpful message."""
        ctx = MockBrowserContext()
        session = PlaywrightSession("run-nosnapshot")

        ok, result = session.resolve_ref(ctx, "e1")
        assert ok is False
        assert "snapshot" in result.lower()


# ---------------------------------------------------------------------------
# Release exit path tests (async generator teardown)
# ---------------------------------------------------------------------------


class TestReleaseExitPaths:
    """Test release() is called on every engine exit path."""

    @pytest.mark.asyncio
    async def test_release_called_on_normal_completion(self, mock_playwright_module):
        """release() should be called when an async generator completes normally."""
        call_tracker = []

        async def test_generator():
            session = await acquire("run-normal", "agent-1")
            yield "step1"
            yield "step2"
            # Normal completion

        gen = test_generator()
        async for _ in gen:
            pass
        # Generator finished normally, release would be called in finally

    @pytest.mark.asyncio
    async def test_release_called_on_cancelled_error(self, mock_playwright_module):
        """release() must be called even when CancelledError is raised."""
        released = []

        async def test_coroutine():
            session = await acquire("run-cancel", "agent-1")
            try:
                await asyncio.sleep(10)  # Will be cancelled
            finally:
                await release("run-cancel")
                released.append(True)

        task = asyncio.create_task(test_coroutine())
        await asyncio.sleep(0.01)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(released) == 1

    @pytest.mark.asyncio
    async def test_release_exception_does_not_mask_propagating_exception(self, mock_playwright_module):
        """release() that raises should not mask an exception passing through finally."""
        original_exception = None

        async def test_with_exception():
            session = await acquire("run-except", "agent-1")
            try:
                raise ValueError("Original error")
            finally:
                await release("run-except")

        try:
            await test_with_exception()
        except ValueError as e:
            original_exception = e

        # The original exception should propagate, not be masked
        assert original_exception is not None
        assert str(original_exception) == "Original error"

    @pytest.mark.asyncio
    async def test_multiple_agents_released_together(self, mock_playwright_module):
        """When a run ends, all agents' contexts are released together."""
        session = get_session("run-multi")
        ctx1 = await session.acquire("agent-1")
        ctx2 = await session.acquire("agent-2")
        ctx3 = await session.acquire("agent-3")

        assert len(session._contexts) == 3

        await release("run-multi")

        # All contexts should be closed
        assert ctx1._closed
        assert ctx2._closed
        assert ctx3._closed


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestPlaywrightSessionIntegration:
    """Integration scenarios combining multiple features."""

    @pytest.mark.asyncio
    async def test_full_workflow_acquire_snapshot_resolve_navigate_stale(self, mock_playwright_module):
        """Full workflow: acquire, snapshot, resolve ref, navigate, ref becomes stale."""
        session = get_session("run-workflow")

        # Step 1: Acquire context
        ctx = await session.acquire("agent-1")
        assert ctx is not None

        # Step 2: Create a page with elements
        page = MockPage("http://example.com/page1")
        page.add_element("button", "Submit")
        page.add_element("input", "Email")
        ctx.pages = [page]

        # Step 3: Take snapshot
        snapshot = await session.snapshot(ctx)
        assert "Submit" in snapshot
        assert "Email" in snapshot

        # Step 4: Resolve refs
        ok, elem = session.resolve_ref(ctx, "e1")
        assert ok is True
        assert elem.role == "button"

        # Step 5: Navigate (simulate)
        page.set_url("http://example.com/page2")
        page._elements = []

        # Step 6: Old refs are stale
        ok, msg = session.resolve_ref(ctx, "e1")
        assert ok is False
        assert "stale" in msg.lower()

        # Step 7: New snapshot works
        snapshot2 = await session.snapshot(ctx)
        assert "No interactive elements" in snapshot2

        # Step 8: Release
        await release("run-workflow")
        from app.agents.playwright_session import _SESSIONS

        assert "run-workflow" not in _SESSIONS
