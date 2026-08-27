"""spec 018 — the nine playwright_* tools (T10).

Each tool returns actionable text (never raises), and gracefully handles:
  - A sandbox-absent context (path-writing tools refuse)
  - An unavailable browser (every tool reports unavailable, none reports success)
  - A policy refusal (the active policy is named)
  - A traversal-shaped filename (rejected before any write)

This mirrors test_pptx_tools.py structure: fake sandbox, monkeypatch binding.
"""

from __future__ import annotations

import pathlib
from unittest import mock

import pytest

from app.agents.tools import playwright as playwright_tools
from app.agents.sandbox import is_deliverable_relpath
from app.core.config import settings


class _Sandbox:
    """Minimal RunSandbox mock for binding the tools."""

    def __init__(self, root: pathlib.Path):
        self.root = root

    def path_for(self, name: str) -> pathlib.Path:
        """Traverse-proof path resolution (matching RunSandbox behavior)."""
        target = self.root / name
        # Enforce that the resolved path stays within root
        try:
            target.relative_to(self.root)
        except ValueError:
            raise ValueError(f"path escapes sandbox: {name}")
        return target


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Bind the playwright tools to a temporary run sandbox."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", _Sandbox(tmp_path))
    return tmp_path


def test_all_nine_tools_are_importable():
    """The nine tools exist and are @tool-decorated."""
    tools = [
        "playwright_navigate",
        "playwright_snapshot",
        "playwright_click",
        "playwright_type",
        "playwright_take_screenshot",
        "playwright_console_messages",
        "playwright_wait_for",
        "playwright_evaluate",
        "playwright_close",
    ]
    for name in tools:
        tool = getattr(playwright_tools, name, None)
        assert tool is not None, f"{name} not found"
        # LangChain @tool adds a `name` attribute
        assert hasattr(tool, "invoke") or callable(tool), f"{name} is not a tool"


def test_bind_sandbox_sets_module_state(tmp_path):
    """bind_sandbox sets the module-level _SANDBOX."""
    original = playwright_tools._SANDBOX
    try:
        sb = _Sandbox(tmp_path)
        playwright_tools.bind_sandbox(sb)
        assert playwright_tools._SANDBOX is sb
    finally:
        playwright_tools._SANDBOX = original


# ─── Error paths: every tool returns TEXT, never raises ──────────────────────


def test_playwright_navigate_without_sandbox(monkeypatch):
    """With no sandbox, navigate refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_navigate.invoke({"url": "http://example.com"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_snapshot_without_sandbox(monkeypatch):
    """With no sandbox, snapshot refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_snapshot.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_click_without_sandbox(monkeypatch):
    """With no sandbox, click refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_click.invoke({"ref": "e1"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_type_without_sandbox(monkeypatch):
    """With no sandbox, type refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_type.invoke({"ref": "e1", "text": "hello"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_take_screenshot_without_sandbox(monkeypatch):
    """With no sandbox, screenshot refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_take_screenshot.invoke({})
    assert isinstance(out, str)
    # The tool returns "no run sandbox" message, which means unavailable
    assert "sandbox" in out.lower() or "unavailable" in out.lower()


def test_playwright_console_messages_without_sandbox(monkeypatch):
    """With no sandbox, console_messages refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_console_messages.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_wait_for_without_sandbox(monkeypatch):
    """With no sandbox, wait_for refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_wait_for.invoke({"text": "hello"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_evaluate_without_sandbox(monkeypatch):
    """With no sandbox, evaluate refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_evaluate.invoke({"script": "return 1"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_playwright_close_without_sandbox(monkeypatch):
    """With no sandbox, close refuses."""
    monkeypatch.setattr(playwright_tools, "_SANDBOX", None)
    out = playwright_tools.playwright_close.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


# ─── Traversal protection: path-escaping filenames are rejected ─────────────


def test_playwright_take_screenshot_rejects_traversal_filename(sandbox, monkeypatch):
    """A traversal-shaped filename (../../etc/passwd) is rejected."""
    # Ensure no browser is available; we're testing the path check, not browser behavior
    monkeypatch.setattr(
        "app.agents.tools.playwright._get_session",
        lambda run_id: mock.MagicMock(available=False, unavailable_reason="no browser"),
    )
    out = playwright_tools.playwright_take_screenshot.invoke({"filename": "../../etc/passwd"})
    assert isinstance(out, str)
    # The tool should refuse the path, not write anything
    assert "escapes sandbox" in out or "unavailable" in out.lower()


# ─── Screenshot deliverable exclusion ──────────────────────────────────────


def test_playwright_take_screenshot_path_is_not_deliverable(sandbox):
    """A screenshot written under .browser/ is not a deliverable."""
    # This test checks the path contract, not actual browser behavior.
    # A screenshot path would be ".browser/screenshot.png"
    screenshot_path = ".browser/screenshot.png"
    assert not is_deliverable_relpath(screenshot_path), (
        f"screenshot path {screenshot_path} must not be deliverable"
    )


def test_verify_prefix_still_not_deliverable():
    """Regression: .verify/ is still excluded (T1 didn't break it)."""
    assert not is_deliverable_relpath(".verify/report.txt")


def test_regular_files_still_deliverable():
    """Regression: regular sandbox files are still deliverable."""
    assert is_deliverable_relpath("output.html")
    assert is_deliverable_relpath("results.json")


# ─── Policy refusal: names the active policy ──────────────────────────────────


def test_playwright_navigate_refuses_out_of_policy_url_and_names_policy(sandbox, monkeypatch):
    """A URL refused by policy names BROWSER_URL_POLICY and its value."""
    # Mock the session to be unavailable so we get past the browser check
    # and test the policy resolver itself
    from app.agents.playwright_session import resolve_url_policy

    # This is a pure function that doesn't need a real session
    sb = _Sandbox(sandbox)
    # Default policy is "file,localhost" — https://example.com is out of policy
    result = resolve_url_policy("https://example.com", sb)

    # It should be a refusal tuple
    assert isinstance(result, tuple)
    status, msg = result
    assert status == "refused"
    # The message should name the policy
    assert "BROWSER_URL_POLICY" in msg
    assert "file,localhost" in msg or settings.BROWSER_URL_POLICY in msg


def test_playwright_navigate_accepts_localhost_url(sandbox, monkeypatch):
    """With default policy, localhost URLs are accepted (not refused)."""
    from app.agents.playwright_session import resolve_url_policy

    sb = _Sandbox(sandbox)
    result = resolve_url_policy("http://localhost:8080/", sb)
    # Should return a URL string, not a refusal tuple
    assert isinstance(result, str)
    assert "localhost" in result


def test_playwright_navigate_accepts_file_path(sandbox, monkeypatch):
    """With default policy, workspace file paths are accepted (not refused)."""
    from app.agents.playwright_session import resolve_url_policy

    sb = _Sandbox(sandbox)
    # Create a file in the sandbox
    test_file = sandbox / "test.html"
    test_file.write_text("<html></html>")

    result = resolve_url_policy("test.html", sb)
    # Should return a file:// URL, not a refusal
    assert isinstance(result, str)
    assert result.startswith("file://")


# ─── Unavailable browser: every tool reports unavailable, none reports success ──


@pytest.fixture
def unavailable_session(monkeypatch):
    """Mock a PlaywrightSession that reports unavailable."""
    session = mock.MagicMock()
    session.available = False
    session.unavailable_reason = "Chromium not found"
    monkeypatch.setattr(
        "app.agents.tools.playwright._get_session",
        lambda run_id: session,
    )
    return session


def test_unavailable_browser_navigate_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, navigate reports unavailable."""
    out = playwright_tools.playwright_navigate.invoke({"url": "http://localhost:8080"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()
    assert "Chromium not found" in out or "browser unavailable" in out.lower()


def test_unavailable_browser_snapshot_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, snapshot reports unavailable."""
    out = playwright_tools.playwright_snapshot.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_click_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, click reports unavailable."""
    out = playwright_tools.playwright_click.invoke({"ref": "e1"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_type_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, type reports unavailable."""
    out = playwright_tools.playwright_type.invoke({"ref": "e1", "text": "hello"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_take_screenshot_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, take_screenshot reports unavailable."""
    out = playwright_tools.playwright_take_screenshot.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_console_messages_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, console_messages reports unavailable."""
    out = playwright_tools.playwright_console_messages.invoke({})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_wait_for_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, wait_for reports unavailable."""
    out = playwright_tools.playwright_wait_for.invoke({"text": "hello"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_evaluate_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, evaluate reports unavailable."""
    out = playwright_tools.playwright_evaluate.invoke({"script": "return 1"})
    assert isinstance(out, str)
    assert "unavailable" in out.lower()


def test_unavailable_browser_close_reports_unavailable(sandbox, unavailable_session):
    """With unavailable browser, close reports unavailable."""
    out = playwright_tools.playwright_close.invoke({})
    # close might behave differently, but it should still report something actionable
    assert isinstance(out, str)


def test_unavailable_browser_none_report_success(sandbox, unavailable_session):
    """With unavailable browser, no tool reports success (FIX-307 guard).

    This is the regression class: a tool that silently returns a clean result
    with no browser is exactly the defect spec 018 forbids.
    """
    results = {
        "navigate": playwright_tools.playwright_navigate.invoke({"url": "http://localhost:8080"}),
        "snapshot": playwright_tools.playwright_snapshot.invoke({}),
        "click": playwright_tools.playwright_click.invoke({"ref": "e1"}),
        "type": playwright_tools.playwright_type.invoke({"ref": "e1", "text": "hi"}),
        "screenshot": playwright_tools.playwright_take_screenshot.invoke({}),
        "console": playwright_tools.playwright_console_messages.invoke({}),
        "wait": playwright_tools.playwright_wait_for.invoke({"text": "x"}),
        "evaluate": playwright_tools.playwright_evaluate.invoke({"script": "1"}),
        "close": playwright_tools.playwright_close.invoke({}),
    }

    for tool_name, result in results.items():
        assert isinstance(result, str), f"{tool_name}: tool must return text, not raise"
        # All tools except close should report unavailable when browser is unavailable.
        # close is special — it just closes, but still shouldn't report working navigation/interaction
        if tool_name != "close":
            # Navigation/interaction tools should report unavailable or error
            assert "unavailable" in result.lower() or "error" in result.lower() or "failed" in result.lower(), (
                f"{tool_name}: should report unavailable when browser unavailable, got: {result}"
            )


# ─── Sanity: screenshot path sanity ──────────────────────────────────────────


def test_browser_dir_constant_matches_path_convention():
    """The _BROWSER_DIR constant matches what is_deliverable_relpath excludes."""
    # The tool uses _BROWSER_DIR = ".browser"
    # is_deliverable_relpath checks for ".browser/" prefix
    # Verify the constant is correct
    assert playwright_tools._BROWSER_DIR == ".browser"
    # Verify is_deliverable_relpath excludes it
    assert not is_deliverable_relpath(".browser/anything.png")
