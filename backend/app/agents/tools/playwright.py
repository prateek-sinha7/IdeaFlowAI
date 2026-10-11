"""app/agents/tools/playwright.py — the nine ``playwright_*`` tools (spec 018 / T4).

An agent granted ``tools: [playwright]`` in its ``AGENT.md`` opens HTML files in
a headless browser, reads the page structure, interacts with elements by stable
reference, captures screenshots, and inspects console output — all within a single
step, with every path resolved inside the run sandbox and every screenshot written
where the run's workspace browser shows it.

Sandbox binding: the factory binds these per run (``_resolve_custom_tool_keys``),
so the sandbox ``ContextVar`` is set at bind time and every path goes through
``RunSandbox.path_for``, which is traversal-proof (``is_relative_to(root)``).

Every tool returns ACTIONABLE TEXT and never raises. An unavailable browser, a
navigation timeout, a stale ref, and a policy refusal are all things the agent
can act on; an exception is not (spec 018, FR-017).

Same contract as ``pptx_tools.py``: plain sync ``@tool`` functions. Playwright's
async API objects (browser/context/page) are bound to whichever event loop
created them, so the sync calls below run their Playwright coroutines on one
dedicated background loop (``_bridge_loop`` / ``_run``) instead of via
``asyncio.run()`` — a fresh loop per call would strand every earlier
``new_page()``/``new_context()`` the moment that call returned, breaking the
persistent-session-across-calls guarantee (FR-007, FR-010).
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Reserved prefix for browser output (screenshots, etc.). Written to the run
# sandbox, visible in the workspace, excluded from the deliverable.
_BROWSER_DIR = ".browser"

# ContextVars for per-task isolation: concurrent wave workers in one process
# share the same agent_id ("custom-agent:pb-build"), so module globals get
# overwritten by whichever worker bound last. ContextVar values propagate
# within each asyncio task (each worker runs in its own task), so each worker
# gets its own context key → its own BrowserContext (spec 018 / FR-010).
_SANDBOX_VAR: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "playwright_sandbox", default=None
)
_AGENT_KEY_VAR: contextvars.ContextVar[str] = contextvars.ContextVar(
    "playwright_agent_key", default="unknown"
)


def bind_sandbox(
    sandbox: Any, agent_id: str = "unknown", worker_key: str | None = None
) -> None:
    """Point the tools at this run's sandbox. Called by the factory, not the model.

    Args:
        sandbox: The RunSandbox for this run.
        agent_id: The ID of the agent using these tools (for browser context isolation).
        worker_key: Optional per-worker key (e.g., thread_id for a fan-out worker).
            When provided, used instead of agent_id as the context key to ensure
            concurrent workers with the same agent_id each get their own BrowserContext.
            When None, falls back to agent_id (backward compatible, keys by agent alone).
    """
    _SANDBOX_VAR.set(sandbox)
    _AGENT_KEY_VAR.set(worker_key or agent_id)


def _run(coro: Any) -> Any:
    """Run a Playwright coroutine on the shared bridge loop and block for its result.

    The bridge loop itself lives in ``app.agents.playwright_session`` — shared with
    every other module that touches a session, since Playwright's async objects are
    bound to whichever loop created them (two independent loops would fault the
    moment two agents in one run shared a session).
    """
    from app.agents.playwright_session import run_sync

    return run_sync(coro)


def _get_session(run_id: str) -> Any:
    """Lazily get or create the PlaywrightSession for this run."""
    from app.agents.playwright_session import get_session

    return get_session(run_id)


def _get_run_id() -> str | None:
    """Extract the run_id from the current context (injected by the runner)."""
    from app.agents.playwright_session import run_id_from_sandbox

    return run_id_from_sandbox(_SANDBOX_VAR.get())


@tool
def playwright_navigate(url: str) -> str:
    """Open a URL or workspace file in the browser.

    Accepts either an absolute http(s) URL (only localhost by default) or a
    workspace file path (resolved through your sandbox). The browser session
    persists across calls, so navigate once and interact across several calls.

    Returns an actionable message: the page loaded, a timeout, a policy refusal,
    or browser unavailable.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    # Resolve and validate the URL against the policy before any browser call
    from app.agents.playwright_session import resolve_url_policy

    policy_result = resolve_url_policy(url, _SANDBOX_VAR.get())
    if isinstance(policy_result, tuple) and policy_result[0] == "refused":
        return policy_result[1]
    resolved_url = policy_result

    # Acquire a context for this agent (lazily launches browser if needed).
    # The agent_id was bound by the factory at runner-composition time.
    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        try:
            page = _run(context.new_page())
        except Exception as exc:  # noqa: BLE001
            return f"failed to create page: {exc}"

        try:
            _run(page.goto(resolved_url, wait_until="load", timeout=30000))
        except Exception as exc:  # noqa: BLE001
            return f"navigation timeout or failed: {exc}"

        return f"opened {url}"
    except Exception as exc:  # noqa: BLE001
        return f"navigation failed: {exc}"


@tool
def playwright_snapshot() -> str:
    """Read back the page structure: interactive elements with stable references.

    Returns a compact text listing showing role, accessible name, and a ref token
    for each element. Use the ref tokens with playwright_click, playwright_type,
    and other interaction tools.

    Empty if the page has no interactive elements. Returns an actionable message
    if the browser is unavailable or no page is loaded.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        snapshot = _run(session.snapshot(context))
        return snapshot
    except Exception as exc:  # noqa: BLE001
        return f"snapshot failed: {exc}"


@tool
def playwright_click(ref: str) -> str:
    """Click an element by its reference token from a snapshot.

    The ref must come from a recent snapshot (playwright_snapshot). If the page
    has navigated since the ref was generated, it will report stale — take a
    fresh snapshot and try again.

    Returns an actionable message: clicked, ref stale, ref not found, or an error.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        ok, element_or_msg = session.resolve_ref(context, ref)
        if not ok:
            return str(element_or_msg)

        element = element_or_msg
        try:
            _run(element.click())
        except Exception as exc:  # noqa: BLE001
            return f"click failed: {exc}"

        return f"clicked {ref}"
    except Exception as exc:  # noqa: BLE001
        return f"click error: {exc}"


@tool
def playwright_type(ref: str, text: str) -> str:
    """Type text into an element by its reference token from a snapshot.

    The ref must come from a recent snapshot (playwright_snapshot). If the page
    has navigated, take a fresh snapshot first.

    Returns an actionable message: typed, ref stale, or an error.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        ok, element_or_msg = session.resolve_ref(context, ref)
        if not ok:
            return str(element_or_msg)

        element = element_or_msg
        try:
            _run(element.type(text))
        except Exception as exc:  # noqa: BLE001
            return f"type failed: {exc}"

        return f"typed {len(text)} character(s) into {ref}"
    except Exception as exc:  # noqa: BLE001
        return f"type error: {exc}"


@tool
def playwright_take_screenshot(
    filename: str = "screenshot.png", ref: str | None = None
) -> str:
    """Capture a screenshot of the page or a single element.

    Writes to the run workspace under ``.browser/`` so it appears in the run's
    file browser but not in the deliverable. The tool returns the relative path
    it wrote so you can cite it in your output.

    If ``ref`` is provided (a ref from a recent snapshot), captures only that
    element. Otherwise captures the full page.

    Returns the relative path written, or an actionable error message.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — cannot write screenshots."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    # Ensure the filename is safe (no path traversal).
    # Requirement 24 AC 3: use per-run browser_dir from RunSandbox so every
    # revision's screenshots land in .browser/{run_id}/ rather than the flat
    # .browser/ root shared by all revisions in the family.
    try:
        # Validate the filename is a safe relative name only (no separators that
        # would escape the per-run dir).  We construct the full path via the
        # per-run property and then verify it stays under the sandbox root.
        _sb = _SANDBOX_VAR.get()
        safe_path = _sb.browser_dir / filename
        # Traversal check: the resolved path must still live inside the sandbox.
        safe_path.resolve().relative_to(_sb.root.resolve())
    except (ValueError, OSError):
        return "filename escapes sandbox — choose a different name."

    # Ensure the directory exists
    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"failed to create screenshot directory: {exc}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        page = context.pages[0]

        if ref:
            # Capture a specific element
            ok, element_or_msg = session.resolve_ref(context, ref)
            if not ok:
                return str(element_or_msg)

            element = element_or_msg
            try:
                _run(element.screenshot(path=str(safe_path)))
            except Exception as exc:  # noqa: BLE001
                return f"element screenshot failed: {exc}"
        else:
            # Capture the full page
            try:
                _run(page.screenshot(path=str(safe_path)))
            except Exception as exc:  # noqa: BLE001
                return f"page screenshot failed: {exc}"

        # Return the relative path from the sandbox root
        try:
            rel_path = safe_path.relative_to(_SANDBOX_VAR.get().root)
            return str(rel_path)
        except ValueError:
            return str(safe_path)
    except Exception as exc:  # noqa: BLE001
        return f"screenshot error: {exc}"


@tool
def playwright_console_messages() -> str:
    """Read console output collected from the page so far.

    Returns all logged console messages (info, warn, error) as a text block, one
    message per line prefixed with its level. Returns an actionable message if no
    console output is available or the page has not loaded.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        # Return all accumulated console messages for this context.
        # The session attaches listeners when pages are created, so this
        # returns all messages captured during navigation and page load.
        return session.get_console_messages(context)
    except Exception as exc:  # noqa: BLE001
        return f"console messages error: {exc}"


@tool
def playwright_wait_for(text: str = "", duration_ms: int = 0) -> str:
    """Wait for text to appear on the page, or for a duration.

    If ``text`` is provided, waits up to 10 seconds for it to appear; if ``text``
    is empty and ``duration_ms`` > 0, waits for that many milliseconds.

    Returns an actionable message: text found, timed out, or an error.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        page = context.pages[0]

        if text:
            # Wait for text to appear
            try:
                _run(
                    page.wait_for_function(
                        f"() => document.body.innerText.includes('{text.replace(chr(39), chr(92) + chr(39))}')",
                        timeout=10000,
                    )
                )
                return f"found text: {text}"
            except Exception:  # noqa: BLE001
                return f"text not found within 10 seconds: {text}"
        elif duration_ms > 0:
            # Wait for a duration
            try:
                _run(asyncio.sleep(duration_ms / 1000.0))
                return f"waited {duration_ms} ms"
            except Exception as exc:  # noqa: BLE001
                return f"wait error: {exc}"
        else:
            return "specify either text to wait for or duration_ms > 0."
    except Exception as exc:  # noqa: BLE001
        return f"wait_for error: {exc}"


@tool
def playwright_evaluate(script: str) -> str:
    """Run arbitrary JavaScript in the page and return the result.

    The script is evaluated in the page's global context, so you can read DOM
    state, compute values, or poke app state (e.g., ``return document.title``
    or ``return window.myGlobal``).

    Bounded by the same URL policy as navigation — under the default policy the
    only reachable pages are files the run itself wrote.

    Returns the script result as a string, or an actionable error.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    session = _get_session(run_id)
    if session.available is False:
        return f"browser unavailable — {session.unavailable_reason}"

    try:
        context = _run(session.acquire(_AGENT_KEY_VAR.get()))
        if context is None:
            return f"browser unavailable — {session.unavailable_reason}"

        if not context.pages:
            return "no page loaded — navigate first."

        page = context.pages[0]

        try:
            result = _run(page.evaluate(script))
            return str(result)
        except Exception as exc:  # noqa: BLE001
            return f"evaluate error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"evaluate failed: {exc}"


@tool
def playwright_close() -> str:
    """Release the browser early.

    Closes every context and the browser itself. Idempotent and never raises —
    safe to call even if the browser is already closed.

    Useful when you are done with the browser and want to free its ~150 MB
    footprint before the run ends. The engine also releases it automatically
    on every run exit path.

    Returns a confirmation message.
    """
    if _SANDBOX_VAR.get() is None:
        return "no run sandbox is bound — playwright tools are unavailable in this context."

    run_id = _get_run_id()
    if not run_id:
        return "cannot extract run_id from context — playwright unavailable."

    try:
        from app.agents.playwright_session import release

        _run(release(run_id))
        return "browser closed."
    except Exception as exc:  # noqa: BLE001
        return f"close error: {exc}"
