"""Unit tests for :mod:`app.agents.render_check` browser-failure classification.

Pins the skip-vs-failure contract stated in the module docstring: "if the browser is
unavailable the caller treats the check as *skipped* (available=False), never as a
hard failure".

A browser/connection death mid-check used to be appended to ``page_errors``, which is
the PROTOTYPE-CONTENT signal (``summary()`` renders it as "uncaught exception(s)").
That misclassification manufactured a CRITICAL ``html_render`` issue and blocked the
validation gate for a prototype that was never actually rendered — and, because it
depends on whether the machine's browser happened to die, it made the
characterization event stream non-deterministic across machines (INV-3).

Playwright is faked entirely, so no browser, subprocess, or socket is ever used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import app.agents.render_check as rc

# The verbatim Playwright message that contaminated
# golden/prototype_revision.events.json with a false ``gate_blocked`` event.
_BROWSER_CLOSED_MSG = (
    "Browser.new_page: Target page, context or browser has been closed"
)


class _FakeBrowser:
    """Browser whose ``new_page`` fails with a caller-supplied exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.closed = False

    async def new_page(self):
        raise self._exc

    async def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    """``async_playwright()`` stand-in that launches a failing browser."""

    def __init__(self, exc: Exception) -> None:
        self.browser = _FakeBrowser(exc)
        outer = self

        class _Chromium:
            async def launch(self, **_kwargs):
                return outer.browser

        self.chromium = _Chromium()

    async def __aenter__(self) -> _FakePlaywright:
        return self

    async def __aexit__(self, *_exc_info) -> bool:
        return False


@pytest.fixture
def prototype_html(tmp_path: Path) -> Path:
    """A minimal, VALID single-file prototype — it cannot legitimately throw."""
    path = tmp_path / "prototype.html"
    path.write_text(
        "<!doctype html><html><body>revised</body></html>", encoding="utf-8"
    )
    return path


@pytest.fixture
def fake_playwright(monkeypatch: pytest.MonkeyPatch):
    """Patch ``playwright.async_api.async_playwright`` to raise ``exc`` at ``new_page``."""
    import playwright.async_api as playwright_async_api

    def _install(exc: Exception) -> _FakePlaywright:
        fake = _FakePlaywright(exc)
        monkeypatch.setattr(
            playwright_async_api, "async_playwright", lambda: fake, raising=True
        )
        return fake

    return _install


@pytest.mark.parametrize(
    "message",
    [
        _BROWSER_CLOSED_MSG,
        "Target closed",
        "Browser has been closed",
        "Connection closed while reading from the driver",
    ],
)
@pytest.mark.asyncio
async def test_render_check_returns_skip_when_browser_closed_mid_check(
    prototype_html: Path, fake_playwright, message: str
) -> None:
    """A browser/connection death degrades to a SKIP, never to a page error."""
    fake_playwright(Exception(message))

    result = await rc.render_check(prototype_html)

    assert result.available is False, "browser death must be reported as unavailable"
    assert result.ok is True, "a skip must not be a hard failure"
    assert result.page_errors == [], (
        "an infrastructure death must NOT surface as an uncaught page exception — "
        "that is what produced the false CRITICAL html_render issue"
    )
    assert "browser unavailable" in result.note
    assert result.summary().startswith("render skipped")


@pytest.mark.asyncio
async def test_render_check_closes_browser_when_browser_closed_mid_check(
    prototype_html: Path, fake_playwright
) -> None:
    """The early skip-return still runs the ``finally`` cleanup (no leaked browser)."""
    fake = fake_playwright(Exception(_BROWSER_CLOSED_MSG))

    await rc.render_check(prototype_html)

    assert fake.browser.closed is True


@pytest.mark.parametrize(
    "message",
    [
        "TypeError: cannot read properties of undefined",
        "strict mode violation: locator resolved to 2 elements",
        "net::ERR_FILE_NOT_FOUND",
    ],
)
@pytest.mark.asyncio
async def test_render_check_reports_failure_when_harness_error_is_not_lifecycle(
    prototype_html: Path, fake_playwright, message: str
) -> None:
    """Kill-test: a non-lifecycle harness error must STILL fail (detection intact)."""
    fake_playwright(Exception(message))

    result = await rc.render_check(prototype_html)

    assert result.available is True, "a real error must not be downgraded to a skip"
    assert result.ok is False
    assert len(result.page_errors) == 1
    assert f"render harness error: {message}" == result.page_errors[0]


@pytest.mark.parametrize(
    "message",
    [
        _BROWSER_CLOSED_MSG,
        "TARGET PAGE, CONTEXT OR BROWSER HAS BEEN CLOSED",
        "Browser has disconnected",
    ],
)
def test_is_browser_lifecycle_error_returns_true_when_message_marks_infrastructure(
    message: str,
) -> None:
    """Message matching is case-insensitive and tolerates Playwright's API prefix."""
    assert rc._is_browser_lifecycle_error(Exception(message)) is True


def test_is_browser_lifecycle_error_returns_true_when_exception_type_is_target_closed() -> (
    None
):
    """Playwright's ``TargetClosedError`` is infrastructure regardless of its message."""

    class TargetClosedError(Exception):
        pass

    assert rc._is_browser_lifecycle_error(TargetClosedError("anything")) is True


@pytest.mark.parametrize(
    "message",
    [
        "TypeError: x is undefined",
        "Timeout 15000ms exceeded",
        "net::ERR_FILE_NOT_FOUND",
        "",
    ],
)
def test_is_browser_lifecycle_error_returns_false_when_error_is_not_infrastructure(
    message: str,
) -> None:
    """Content/timeout/unknown errors are NOT reclassified as browser deaths."""
    assert rc._is_browser_lifecycle_error(Exception(message)) is False
