"""app/agents/playwright_session.py — the per-run browser lifecycle owner (spec 018 / T3a).

``render_check.py`` is a MACRO: launch, do everything, tear down, all scoped
inside one ``async with`` block wrapping ``async_playwright()``. That shape is
correct there because the whole job finishes before the block exits.

It is WRONG here. This session must stay alive across several tool calls inside
one step (navigate, then click, then screenshot) — long after any single call
returns. [FIX-307](../../../.knowledge/cards/20260826-0124-FIX-307.md) is exactly
what happens when browser work drifts outside that scope: the browser tears
down, every subsequent ``new_page()``/``new_context()`` raises "Target page,
context or browser has been closed", and that exception got swallowed into a
findings list — the render validator reported CLEAN on every run for weeks. So
this module NEVER scopes the Playwright handle to a context-manager block. It
holds the handle explicitly
(``await async_playwright().start()``) and releases it explicitly (``await
pw.stop()``), and every failure path sets state instead of raising, so an
unavailable browser is reported as unavailable (FR-018) rather than as a session
that silently does nothing.

Import is lazy (inside ``_launch``, never at module scope) so this module loads
fine on a machine with no ``playwright`` installed — mirrors the same pattern in
``render_check.py``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # never imported at runtime — see the module docstring
    from playwright.async_api import Browser, BrowserContext, Playwright

logger = logging.getLogger("app.agents.playwright_session")

# How long a session sits idle (no acquire() call) before it releases itself.
# Defence in depth behind the engine's run-teardown `finally` (T7) and the
# `playwright_close` tool (T4) — this is the reclaim path for a run that is
# still executing but has simply stopped touching the browser.
_DEFAULT_IDLE_TIMEOUT_S = 300.0


class PlaywrightSession:
    """Owns ONE browser for one run; hands out ONE ``BrowserContext`` per agent.

    Contexts (not separate browsers) isolate agents from each other's cookies
    and storage. A browser per agent would multiply Chromium's ~150 MB footprint
    by the fan-out width; a context is cheap.

    Created lazily — nothing launches until :meth:`acquire` is called for the
    first time, so an agent granted the ``playwright`` tool set but never
    calling a tool costs nothing.
    """

    def __init__(self, run_id: str, idle_timeout_s: float = _DEFAULT_IDLE_TIMEOUT_S) -> None:
        self.run_id = run_id
        self._idle_timeout_s = idle_timeout_s
        # The started (not `async with`-scoped) Playwright handle. See module docstring.
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        # Serializes launch + context creation so two concurrent acquire() calls
        # for the same run cannot each launch their own browser.
        self._lock = asyncio.Lock()
        # None = not yet attempted. True/False set on the first launch attempt.
        self._available: bool | None = None
        self._unavailable_reason = ""
        self._idle_handle: asyncio.TimerHandle | None = None
        # Per-context ref registry: maps context id to (page_url, ref_map).
        # ref_map is {ref_token → element}. Invalidated on navigation.
        self._ref_registries: dict[int, tuple[str, dict[str, Any]]] = {}
        self._ref_counter = 0
        # Per-context console message collection: maps context id to list of messages.
        # Persists across tool calls so playwright_console_messages can return them.
        self._console_messages: dict[int, list[str]] = {}

    @property
    def available(self) -> bool | None:
        """None until the first acquire(); then whether the browser launched."""
        return self._available

    @property
    def unavailable_reason(self) -> str:
        """Why the browser is unavailable, once ``available`` is False."""
        return self._unavailable_reason

    async def acquire(self, agent_id: str) -> Any | None:
        """Return this agent's ``BrowserContext``, launching the browser lazily.

        Returns ``None`` when the browser is unavailable (Playwright not
        installed, Chromium won't launch) — never raises. Callers should check
        ``.available`` / ``.unavailable_reason`` to explain that to the agent.
        """
        async with self._lock:
            if self._available is False:
                return None
            if self._browser is None and not await self._launch():
                return None
            self._rearm_idle_timer()
            if agent_id not in self._contexts:
                try:
                    context = await self._browser.new_context()
                except Exception as exc:  # noqa: BLE001 — report, never raise (FR-018)
                    self._mark_unavailable(f"browser context creation failed: {exc}")
                    return None
                self._contexts[agent_id] = context
                # Initialize console message list for this context
                ctx_id = id(context)
                self._console_messages[ctx_id] = []
                # Attach console listener to capture messages going forward. Best-effort
                # and isolated from context creation above: a listener-attachment failure
                # is a lost instrumentation feature, not a reason to report the whole
                # browser unavailable (which would fail every other agent's acquire()).
                try:
                    self._attach_console_listener(context)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "PlaywrightSession[%s]: console listener attach failed: %s",
                        self.run_id, exc,
                    )
            return self._contexts[agent_id]

    async def snapshot(self, context: Any) -> str:
        """Return a compact text snapshot of interactive/landmark page elements.

        Each element line: ``{role} "{accessible_name}" [ref=e{n}]``

        Generates stable ref tokens and stores a mapping so interaction tools
        can resolve a ref back to the element. The mapping is invalidated on
        navigation — a ref from a previous page will report as stale rather than
        silently acting on a new element in that position.

        Returns the snapshot text (possibly empty if the page has no interactive
        elements).
        """
        try:
            page = context.pages[0] if context.pages else None
            if not page:
                return "No page loaded."
        except Exception as exc:  # noqa: BLE001 — report, never raise
            return f"Failed to get page: {exc}"

        # Check if the page URL has changed; if so, clear the old ref map.
        ctx_id = id(context)
        try:
            current_url = page.url
        except Exception as exc:  # noqa: BLE001
            current_url = ""

        # Get the existing registration for this context
        if ctx_id in self._ref_registries:
            old_url, old_refs = self._ref_registries[ctx_id]
            if old_url != current_url:
                # Page has navigated; invalidate old refs
                self._ref_registries[ctx_id] = (current_url, {})
        else:
            # First snapshot for this context
            self._ref_registries[ctx_id] = (current_url, {})

        _, ref_map = self._ref_registries[ctx_id]

        # Query interactive and landmark elements.
        # This selector covers buttons, links, form inputs, and ARIA landmarks.
        selector = (
            "button, a[href], input, textarea, select, "
            "[role='button'], [role='link'], [role='menuitem'], "
            "[role='tab'], [role='navigation'], [role='main'], "
            "[role='region'], [role='search'], [role='complementary']"
        )

        try:
            elements = await context.pages[0].query_selector_all(selector)
        except Exception as exc:  # noqa: BLE001
            return f"Failed to query elements: {exc}"

        snapshot_lines = []
        for element in elements:
            try:
                # Get the element's role and accessible name
                role, name = await self._get_element_info(element)
                if not role or not name:
                    # Skip elements without role or name
                    continue

                # Generate a stable ref token
                self._ref_counter += 1
                ref_token = f"e{self._ref_counter}"

                # Store in the registry
                ref_map[ref_token] = element

                # Format the snapshot line
                snapshot_lines.append(f'{role} "{name}" [ref={ref_token}]')
            except Exception as exc:  # noqa: BLE001 — best-effort element processing
                logger.warning("Failed to process element: %s", exc)
                continue

        return "\n".join(snapshot_lines) if snapshot_lines else "No interactive elements found."

    async def _get_element_info(self, element: Any) -> tuple[str, str]:
        """Extract role and accessible name from an element.

        Returns (role, name) tuple. Both are strings; may be empty.
        """
        try:
            # Try to get the element's role via getAttribute or the role property
            role = await element.evaluate("el => el.getAttribute('role') || el.tagName.toLowerCase()")
            if not role:
                role = ""
        except Exception:  # noqa: BLE001
            role = ""

        try:
            # Get the accessible name: aria-label, aria-labelledby text, or text content
            name = await element.evaluate(
                """el => {
                    // aria-label takes precedence
                    let label = el.getAttribute('aria-label');
                    if (label) return label.trim();

                    // Check for aria-labelledby
                    let labelledBy = el.getAttribute('aria-labelledby');
                    if (labelledBy) {
                        let ids = labelledBy.split(/\\s+/);
                        let texts = [];
                        for (let id of ids) {
                            let ref = document.getElementById(id);
                            if (ref) texts.push(ref.textContent);
                        }
                        if (texts.length > 0) return texts.join(' ').trim();
                    }

                    // Fall back to text content (trim and truncate)
                    let text = el.textContent || '';
                    text = text.trim();
                    if (text.length > 50) text = text.substring(0, 47) + '...';
                    return text;
                }"""
            )
            if not name:
                name = ""
        except Exception:  # noqa: BLE001
            name = ""

        return (role, name)

    def get_console_messages(self, context: Any) -> str:
        """Return accumulated console messages for this context as a string.

        Returns a formatted list of all console messages captured since the
        context was created or the page was navigated. Returns a message
        indicating no console output if none were captured.
        """
        ctx_id = id(context)
        messages = self._console_messages.get(ctx_id, [])
        if not messages:
            return "no console messages logged."
        return "\n".join(messages)

    def _attach_console_listener(self, context: Any) -> None:
        """Attach a listener to capture console messages from all pages in this context."""
        # We need to handle both current pages and future pages (via new_page() calls)
        def _on_page(page: Any) -> None:
            """Attach console listener to a new page."""
            def _on_console(msg: Any) -> None:
                ctx_id = id(context)
                if ctx_id not in self._console_messages:
                    self._console_messages[ctx_id] = []
                try:
                    msg_type = msg.type.upper() if hasattr(msg, "type") else "LOG"
                    msg_text = msg.text if hasattr(msg, "text") else str(msg)
                    self._console_messages[ctx_id].append(f"{msg_type}: {msg_text}")
                except Exception:  # noqa: BLE001 — best-effort logging
                    pass

            page.on("console", _on_console)

        # Attach listener to existing pages
        try:
            for page in context.pages:
                _on_page(page)
        except Exception:  # noqa: BLE001 — best-effort setup
            pass

        # Attach listener for future pages created via new_page()
        context.on("page", _on_page)

    def resolve_ref(self, context: Any, ref_token: str) -> tuple[bool, Any | str]:
        """Resolve a ref token to an element, or report if the ref is stale.

        Returns:
            (ok, element_or_message) where ok=True means the element exists,
            ok=False means the ref is stale or invalid.
        """
        ctx_id = id(context)
        if ctx_id not in self._ref_registries:
            return (False, "No snapshot taken for this page — take a fresh snapshot first.")

        old_url, ref_map = self._ref_registries[ctx_id]

        # Check if the page has navigated since the ref was created
        try:
            if context.pages:
                current_url = context.pages[0].url
                if current_url != old_url:
                    # Page has navigated; all refs are now stale
                    self._ref_registries[ctx_id] = (current_url, {})
                    # Clear console messages on navigation
                    self._console_messages[ctx_id] = []
                    return (False, f"Reference {ref_token} is stale — take a fresh snapshot after navigation.")
        except Exception:  # noqa: BLE001 — best-effort check, fall through to check ref_map
            pass

        if ref_token not in ref_map:
            return (False, f"Reference {ref_token} is stale or invalid — take a fresh snapshot.")

        element = ref_map[ref_token]
        return (True, element)

    def _invalidate_refs(self, context: Any) -> None:
        """Invalidate all refs for a context after navigation."""
        ctx_id = id(context)
        if ctx_id in self._ref_registries:
            url, _ = self._ref_registries[ctx_id]
            # Keep the URL but clear the ref map
            self._ref_registries[ctx_id] = (url, {})

    async def _launch(self) -> bool:
        """Start Playwright and launch Chromium. Sets ``available``; never raises."""
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:  # noqa: BLE001 — not installed → unavailable, not a crash
            self._mark_unavailable(f"Playwright unavailable: {exc}")
            return False
        try:
            # Held explicitly rather than scoped to a context-manager block —
            # see the module docstring / FIX-307. This handle outlives this method.
            self._playwright = await async_playwright().start()
        except Exception as exc:  # noqa: BLE001
            self._mark_unavailable(f"Playwright failed to start: {exc}")
            return False
        try:
            # --no-sandbox disables CHROMIUM's OWN process sandbox (required to
            # launch inside this container, matching render_check.py:207). It is
            # unrelated to RunSandbox's filesystem isolation — the two mechanisms
            # just happen to share the word "sandbox".
            self._browser = await self._playwright.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001 — binary missing/broken → unavailable
            self._mark_unavailable(f"Chromium unavailable: {exc}")
            await self._playwright.stop()
            self._playwright = None
            return False
        self._available = True
        return True

    def _mark_unavailable(self, reason: str) -> None:
        self._available = False
        self._unavailable_reason = reason
        logger.warning("PlaywrightSession[%s]: %s", self.run_id, reason)

    def _rearm_idle_timer(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(self._idle_timeout_s, self._on_idle_timeout)

    def _on_idle_timeout(self) -> None:
        async def _release_if_still_current() -> None:
            # Guard against releasing a NEW session that has since replaced this
            # one in the registry under the same run id.
            if _SESSIONS.get(self.run_id) is self:
                await release(self.run_id)

        asyncio.create_task(_release_if_still_current())

    async def close(self) -> None:
        """Tear down every context, the browser, and the Playwright handle.

        Idempotent and never raises — called from :func:`release`, which is
        itself called from a ``finally`` that must not be able to mask the
        exception passing through it.
        """
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None
        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception as exc:  # noqa: BLE001 — best-effort teardown
                logger.warning("PlaywrightSession[%s]: context close failed: %s", self.run_id, exc)
        self._contexts.clear()
        self._ref_registries.clear()
        self._console_messages.clear()
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("PlaywrightSession[%s]: browser close failed: %s", self.run_id, exc)
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("PlaywrightSession[%s]: playwright stop failed: %s", self.run_id, exc)
            self._playwright = None


# One background loop for every Playwright coroutine in this process, shared
# across every tool module that touches a session. Playwright's async objects
# are bound to whichever loop created them — a second independent bridge loop
# calling into a session another module already launched would raise "Future
# attached to a different loop" the moment their calls interleaved (e.g.
# ppt-deck-qa-v2 and ppt-code-generator sharing one run's session).
_BRIDGE_LOOP: asyncio.AbstractEventLoop | None = None
_BRIDGE_LOCK = threading.Lock()


def _bridge_loop() -> asyncio.AbstractEventLoop:
    global _BRIDGE_LOOP
    with _BRIDGE_LOCK:
        if _BRIDGE_LOOP is None:
            _BRIDGE_LOOP = asyncio.new_event_loop()
            threading.Thread(target=_BRIDGE_LOOP.run_forever, daemon=True).start()
        return _BRIDGE_LOOP


def run_sync(coro: Any) -> Any:
    """Run a Playwright coroutine on the shared bridge loop and block for its result."""
    return asyncio.run_coroutine_threadsafe(coro, _bridge_loop()).result()


def run_id_from_sandbox(sandbox: Any) -> str | None:
    """Best-effort run_id extraction from a bound RunSandbox's root path."""
    if sandbox is None:
        return None
    try:
        parts = Path(sandbox.root).parts
        if len(parts) >= 2:
            return parts[-1]
    except Exception:  # noqa: BLE001 — best-effort extraction
        pass
    return None


# Module-level registry keyed by run id — the seam the tools (T4) and the engine
# (T7) both reach through so they operate on the SAME session for a run.
_SESSIONS: dict[str, PlaywrightSession] = {}


def get_session(run_id: str) -> PlaywrightSession:
    """Return this run's session, creating an (unlaunched) one if none exists.

    Creating the Python object costs nothing — no browser launches until
    :meth:`PlaywrightSession.acquire` is called.
    """
    session = _SESSIONS.get(run_id)
    if session is None:
        session = PlaywrightSession(run_id)
        _SESSIONS[run_id] = session
    return session


async def acquire(run_id: str, agent_id: str) -> Any | None:
    """Convenience wrapper: ``get_session(run_id).acquire(agent_id)``."""
    return await get_session(run_id).acquire(agent_id)


async def release(run_id: str) -> None:
    """Release the session for ``run_id``, if one exists.

    Idempotent, a no-op for a run that never had a session, and NEVER raises —
    this is called from a ``finally`` inside a long-lived async generator, and a
    release that throws there would mask the exception passing through it.
    """
    session = _SESSIONS.pop(run_id, None)
    if session is None:
        return
    try:
        await session.close()
    except Exception as exc:  # noqa: BLE001 — release must never raise
        logger.warning("PlaywrightSession[%s]: release failed: %s", run_id, exc)


def resolve_url_policy(url: str, sandbox: Any) -> str | tuple[str, str]:
    """Resolve a requested URL against the browser URL policy.

    Takes a requested URL (or path) and a RunSandbox, reads settings.BROWSER_URL_POLICY,
    and returns EITHER a resolved URL to open OR a (status, refusal_string) tuple
    explaining why the URL is not permitted.

    Policy tokens, parsed from the comma-separated setting:
      - "file": resolve the path through RunSandbox.path_for and return a file:// URI.
        A path that escapes the sandbox is refused.
      - "localhost": permit http://localhost:<port> and http://127.0.0.1:<port> only.
      - "http": permit any http(s) URL. NOT in the default policy.
      - Anything not permitted: refused with a message naming the active policy.

    The refusal happens BEFORE any network or filesystem access, and names the policy
    in its text so the agent can act on it.

    Args:
        url: The requested URL or file path (string).
        sandbox: A RunSandbox instance for path resolution.

    Returns:
        A string URL if allowed, or a ("refused", message) tuple if not permitted.
    """
    from app.core.config import settings
    from urllib.parse import urlparse

    policy_str = settings.BROWSER_URL_POLICY
    policy_tokens = {t.strip() for t in policy_str.split(",") if t.strip()}

    # Try to parse as a URL first
    parsed = urlparse(url)
    scheme_lower = parsed.scheme.lower()

    # A bare path (no scheme at all) and an already-formed "file://" URI name the SAME
    # thing — a local file — and both belong to the "file" token, resolved through the
    # sandbox. They must NOT fall into the http(s)-only branch below: "file" has a
    # scheme (truthy), so treating "has a scheme" as "is a network URL" silently refused
    # every agent-constructed file:// URI even though "file" was in the policy.
    if scheme_lower in ("", "file"):
        # For a "file://" URI, resolve against its path component (the part after the
        # scheme); for a bare path, the url itself.
        path_str = parsed.path if scheme_lower == "file" else url

        if "file" not in policy_tokens:
            return (
                "refused",
                f"refused: {url} is not permitted by BROWSER_URL_POLICY={policy_str}",
            )

        # Try to resolve the path through the sandbox
        try:
            abs_path = sandbox.path_for(path_str)
        except ValueError:
            # Path escapes the sandbox
            return (
                "refused",
                f"refused: {url} is not permitted by BROWSER_URL_POLICY={policy_str}",
            )

        # Convert to file:// URL
        return abs_path.as_uri()

    # Anything else with a scheme is a network URL: check against the policy.
    # All URL-based checks require http/https scheme.
    if scheme_lower not in ("http", "https"):
        return (
            "refused",
            f"refused: {url} is not permitted by BROWSER_URL_POLICY={policy_str}",
        )

    # Check for "http" token (permits any http/https)
    if "http" in policy_tokens:
        return url

    # Check for "localhost" token
    if "localhost" in policy_tokens:
        hostname = parsed.hostname or ""
        if hostname in ("localhost", "127.0.0.1"):
            return url
        return (
            "refused",
            f"refused: {url} is not permitted by BROWSER_URL_POLICY={policy_str}",
        )

    # No matching token: refuse
    return (
        "refused",
        f"refused: {url} is not permitted by BROWSER_URL_POLICY={policy_str}",
    )
