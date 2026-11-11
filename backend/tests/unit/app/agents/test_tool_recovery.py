"""Unit tests for ``app/agents/tool_recovery.py`` — failed tool calls become recoverable.

Run 725474ee: the Playwright tools return failure TEXT (ADR-0036), so the framework
treated every failure as a normal result. Nothing retried it and nothing told the model it
had failed; the tester carried on after ``navigate('prototype.html?r=3')`` failed with
``ERR_FILE_NOT_FOUND``. These tests pin the three behaviours of the middleware: recognise
the failure, retry only what an identical repeat can fix, and name the change that does.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

import app.agents.tool_recovery as tr
import app.agents.tools.playwright as playwright_tools
from agents.execution_engine.budget import BudgetExceeded
from app.agents.tool_recovery import ToolFailureRecoveryMiddleware, classify_text


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(tr, "_RETRY_BACKOFF_SECONDS", 0.0)


def _request(name: str, args: dict | None = None, call_id: str = "c1"):
    return SimpleNamespace(tool_call={"name": name, "args": args or {}, "id": call_id})


def _msg(name: str, content, *, status: str = "success") -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id="c1", status=status)


class _Handler:
    """An async handler that plays back ``outcomes`` in order (the last one repeats)."""

    def __init__(self, *outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    async def __call__(self, request):
        outcome = self._outcomes[min(self.calls, len(self._outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _content(message) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


# ── classification: the real failure strings from run 725474ee ─────────────────


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "navigation timeout or failed: Page.goto: net::ERR_FILE_NOT_FOUND at "
            "file:///C:/run/prototype.html?r=3",
            "argument",
        ),
        (
            "evaluate error: Page.evaluate: SyntaxError: Illegal return statement\n    at eval",
            "script",
        ),
        ("evaluate error: Page.evaluate: TypeError: x is null", "script"),
        ("no page loaded — navigate first.", "state"),
        ("Reference e12 is stale — take a fresh snapshot after navigation.", "state"),
        ("click failed: ElementHandle.click: Timeout 30000ms exceeded.", "state"),
        ("browser unavailable — chromium is not installed", "environment"),
        (
            "refused: /etc/passwd is not permitted by BROWSER_URL_POLICY=file,localhost",
            "policy",
        ),
        (
            "navigation timeout or failed: Page.goto: Timeout 30000ms exceeded.",
            "timeout",
        ),
        (
            "navigation timeout or failed: Page.goto: net::ERR_CONNECTION_RESET",
            "transient",
        ),
        ("text not found within 10 seconds: Ready", "state"),
        ("page screenshot failed: boom", "argument"),
    ],
)
def test_classify_text_names_the_cause_when_a_browser_tool_fails(text, kind):
    assert classify_text("playwright_navigate", text).kind == kind


def test_classify_text_does_not_call_every_navigation_failure_a_timeout():
    """'navigation timeout or failed:' prefixes ALL navigation failures."""
    failure = classify_text(
        "playwright_navigate",
        "navigation timeout or failed: Page.goto: net::ERR_NAME_NOT_RESOLVED at http://x",
    )
    assert failure.kind != "timeout"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Error: String not found in file: 'abc'", "argument"),
        ("Error: String 'x' appears 3 times in file. Use replace_all=True", "argument"),
        (
            "Cannot write to /a.md because it already exists. Read and then make an edit",
            "state",
        ),
        ("Error: File '/build/x.md' not found", "argument"),
        ("Error: permission denied for write on /.logs/x", "policy"),
        (
            "Error invoking tool 'edit_file' with kwargs {} with error: field required",
            "argument",
        ),
    ],
)
def test_classify_text_names_the_cause_when_a_filesystem_tool_fails(text, kind):
    assert classify_text("edit_file", text).kind == kind


def test_every_failure_return_is_recognised():
    """Drift guard: a new ``return f"..."`` failure in the tools must be in _FAILURE_PATTERNS."""
    source = inspect.getsource(playwright_tools)
    success_heads = (
        "opened ",
        "clicked ",
        "typed ",
        "waited ",
        "found text",
        "browser closed",
    )
    heads = {m.group(2) for m in re.finditer(r'return (f?)"([^"{]+)', source)}
    # a real message has words; this drops the ``return f"..."`` placeholder in the docs
    failures = {
        h
        for h in heads
        if re.search(r"[A-Za-z]{3}", h) and not h.startswith(success_heads)
    }
    assert (
        len(failures) >= 10
    ), "the scan found too few return strings: the regex drifted"
    unrecognised = sorted(
        h for h in failures if not playwright_tools.is_failure(h + "x")
    )
    assert (
        unrecognised == []
    ), f"failure messages missing from _FAILURE_PATTERNS: {unrecognised}"


def test_is_failure_ignores_page_data_that_merely_contains_a_failure_word():
    assert not playwright_tools.is_failure("the button said: click error, try again")
    assert not playwright_tools.is_failure('{"ok": true, "screens": 9}')


# ── middleware: results that are not failures pass through untouched ───────────


@pytest.mark.asyncio
async def test_awrap_returns_the_same_message_when_the_call_succeeds():
    ok = _msg("playwright_navigate", "opened prototype.html")

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_navigate"), _Handler(ok)
    )

    assert result is ok


@pytest.mark.asyncio
async def test_awrap_returns_a_command_unchanged():
    command = Command(update={"files": {}})

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("write_todos"), _Handler(command)
    )

    assert result is command


# ── middleware: recognise the failure and tell the model what to change ────────


@pytest.mark.asyncio
async def test_awrap_appends_advice_when_a_browser_tool_returns_failure_text():
    failed = _msg(
        "playwright_navigate",
        "navigation timeout or failed: Page.goto: net::ERR_FILE_NOT_FOUND at file:///x/p.html?r=3",
    )

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_navigate", {"url": "prototype.html?r=3"}), _Handler(failed)
    )

    text = _content(result)
    assert text.startswith("navigation timeout or failed")  # the original error is kept
    assert "[tool recovery] playwright_navigate failed (argument)" in text
    assert "ls or glob" in text and "query string" in text
    assert result.status == "error"


@pytest.mark.asyncio
async def test_awrap_appends_advice_when_a_filesystem_tool_reports_status_error():
    failed = _msg("edit_file", "Error: String not found in file: 'abc'", status="error")

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("edit_file", {"old_string": "abc"}), _Handler(failed)
    )

    assert "[tool recovery] edit_file failed (argument)" in _content(result)
    assert "read_file" in _content(result)


@pytest.mark.asyncio
async def test_awrap_converts_a_raised_exception_into_an_error_message():
    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("custom_tool"), _Handler(ValueError("bad thing"))
    )

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.tool_call_id == "c1"
    assert "ValueError: bad thing" in _content(result)
    assert "[tool recovery] custom_tool failed (exception)" in _content(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [GraphInterrupt(), BudgetExceeded("tokens", "over the cap")],
    ids=["langgraph-interrupt", "budget-exceeded"],
)
async def test_awrap_lets_control_flow_exceptions_through(exc):
    with pytest.raises(type(exc)):
        await ToolFailureRecoveryMiddleware().awrap_tool_call(
            _request("custom_tool"), _Handler(exc)
        )


# ── middleware: retry only what an identical repeat can fix ────────────────────


@pytest.mark.asyncio
async def test_awrap_retries_a_transient_failure_on_an_idempotent_tool_and_returns_the_success():
    dropped = _msg(
        "playwright_navigate",
        "navigation timeout or failed: Page.goto: net::ERR_CONNECTION_RESET",
    )
    opened = _msg("playwright_navigate", "opened prototype.html")
    handler = _Handler(dropped, opened)

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_navigate", {"url": "prototype.html"}), handler
    )

    assert result is opened
    assert handler.calls == 2


@pytest.mark.asyncio
async def test_awrap_gives_up_after_the_retry_budget_and_says_how_many_were_tried():
    dropped = _msg(
        "playwright_snapshot",
        "snapshot failed: Target page, context or browser has been closed",
    )
    handler = _Handler(dropped)

    result = await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_snapshot"), handler
    )

    assert handler.calls == 1 + tr._MAX_AUTO_RETRIES
    assert f"retried {tr._MAX_AUTO_RETRIES} time(s)" in _content(result)


@pytest.mark.asyncio
async def test_awrap_does_not_retry_a_transient_failure_on_a_tool_with_side_effects():
    """A repeated evaluate could run its script twice."""
    dropped = _msg(
        "playwright_evaluate",
        "evaluate error: Page.evaluate: Execution context was destroyed",
    )
    handler = _Handler(dropped)

    await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_evaluate", {"script": "1"}), handler
    )

    assert handler.calls == 1


@pytest.mark.asyncio
async def test_awrap_does_not_retry_a_deterministic_failure():
    missing = _msg(
        "playwright_navigate",
        "navigation timeout or failed: Page.goto: net::ERR_FILE_NOT_FOUND",
    )
    handler = _Handler(missing)

    await ToolFailureRecoveryMiddleware().awrap_tool_call(
        _request("playwright_navigate", {"url": "x.html"}), handler
    )

    assert handler.calls == 1


# ── middleware: the note escalates so the model cannot loop on a failing call ──


@pytest.mark.asyncio
async def test_awrap_escalates_the_note_when_the_same_call_keeps_failing():
    failed = _msg(
        "playwright_evaluate",
        "evaluate error: Page.evaluate: SyntaxError: Illegal return statement",
    )
    middleware = ToolFailureRecoveryMiddleware()
    request = _request("playwright_evaluate", {"script": "return 1"})

    first = await middleware.awrap_tool_call(request, _Handler(failed))
    second = await middleware.awrap_tool_call(request, _Handler(failed))
    third = await middleware.awrap_tool_call(request, _Handler(failed))

    assert "failed 2 times" not in _content(first)
    assert "failed 2 times" in _content(second)
    assert "Stop retrying" not in _content(second)
    assert "failed 3 times" in _content(third)
    assert "Stop retrying" in _content(third)


@pytest.mark.asyncio
async def test_awrap_does_not_escalate_when_the_arguments_change_between_failures():
    failed = _msg(
        "playwright_evaluate",
        "evaluate error: Page.evaluate: SyntaxError: Illegal return statement",
    )
    middleware = ToolFailureRecoveryMiddleware()

    await middleware.awrap_tool_call(
        _request("playwright_evaluate", {"script": "return 1"}), _Handler(failed)
    )
    changed = await middleware.awrap_tool_call(
        _request("playwright_evaluate", {"script": "(() => 1)()"}), _Handler(failed)
    )

    assert "failed 2 times" not in _content(changed)


@pytest.mark.asyncio
async def test_awrap_resets_the_count_when_the_same_call_later_succeeds():
    failed = _msg("playwright_snapshot", "no page loaded — navigate first.")
    fine = _msg("playwright_snapshot", "a 'New order' [ref=e1]")
    middleware = ToolFailureRecoveryMiddleware()
    request = _request("playwright_snapshot")

    await middleware.awrap_tool_call(request, _Handler(failed))
    await middleware.awrap_tool_call(request, _Handler(fine))
    again = await middleware.awrap_tool_call(request, _Handler(failed))

    assert "failed 2 times" not in _content(again)


@pytest.mark.asyncio
async def test_awrap_warns_that_a_tool_is_unavailable_after_a_streak_of_failures():
    middleware = ToolFailureRecoveryMiddleware()
    result = None
    for attempt in range(tr._STREAK_AT):
        result = await middleware.awrap_tool_call(
            _request("playwright_evaluate", {"script": f"s{attempt}"}),
            _Handler(
                _msg(
                    "playwright_evaluate", "evaluate error: Page.evaluate: TypeError: x"
                )
            ),
        )

    assert "Treat it as unavailable" in _content(result)


# ── the sync path (sync tool graphs) behaves the same ──────────────────────────


def test_wrap_retries_then_returns_the_success_on_the_sync_path():
    dropped = _msg(
        "playwright_navigate",
        "navigation timeout or failed: Page.goto: net::ERR_CONNECTION_RESET",
    )
    opened = _msg("playwright_navigate", "opened prototype.html")
    outcomes = iter([dropped, opened])

    result = ToolFailureRecoveryMiddleware().wrap_tool_call(
        _request("playwright_navigate"), lambda _request: next(outcomes)
    )

    assert result is opened


def test_wrap_annotates_a_failure_on_the_sync_path():
    failed = _msg("playwright_snapshot", "no page loaded — navigate first.")

    result = ToolFailureRecoveryMiddleware().wrap_tool_call(
        _request("playwright_snapshot"), lambda _request: failed
    )

    assert "[tool recovery] playwright_snapshot failed (state)" in _content(result)
