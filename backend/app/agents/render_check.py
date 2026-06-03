"""app/agents/render_check.py — headless render validation for HTML prototypes.

Loads a single-file prototype in headless Chromium and reports whether it actually
works: JS console errors, uncaught exceptions, and — for the SPA prototype family —
that each sidebar nav link switches to a real, active page section. Consumed by the
per-task sub-agent validation loop (Phase 4): a task isn't "done" until its page
renders and navigates without errors.

Playwright + Chromium are bundled in the backend image (see Dockerfile). The import
is lazy so this module loads anywhere; if the browser is unavailable the caller
treats the check as *skipped* (available=False), never as a hard failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("app.agents.render_check")


@dataclass
class NavResult:
    href: str
    activated: str | None  # data-page id that became active, or None
    ok: bool


@dataclass
class RenderResult:
    ok: bool
    available: bool = True  # False when Playwright/Chromium isn't installed
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    nav_results: list[NavResult] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        if not self.available:
            return f"render skipped ({self.note})"
        bits: list[str] = []
        if self.console_errors:
            bits.append(f"{len(self.console_errors)} console error(s)")
        if self.page_errors:
            bits.append(f"{len(self.page_errors)} uncaught exception(s)")
        broken = [n for n in self.nav_results if not n.ok]
        if broken:
            bits.append(f"{len(broken)}/{len(self.nav_results)} nav link(s) dead")
        return "OK" if not bits else "; ".join(bits)


async def render_check(
    html_path: str | Path,
    *,
    check_nav: bool = True,
    timeout_ms: int = 15000,
) -> RenderResult:
    """Render an HTML file headless and return a structured health report."""
    path = Path(html_path)
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001 — unavailable browser is a skip, not an error
        logger.warning("render_check: Playwright unavailable (%s) — skipping render", exc)
        return RenderResult(ok=True, available=False, note=f"Playwright unavailable: {exc}")

    if not path.is_file():
        return RenderResult(ok=False, note=f"file not found: {path}")

    console_errors: list[str] = []
    page_errors: list[str] = []
    nav_results: list[NavResult] = []

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001 — browser binary absent → skip, not fail
            logger.warning("render_check: Chromium launch failed (%s) — skipping", exc)
            return RenderResult(ok=True, available=False, note=f"Chromium unavailable: {exc}")
        try:
            page = await browser.new_page()
            page.on(
                "console",
                lambda m: console_errors.append(m.text) if m.type == "error" else None,
            )
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            await page.goto(path.as_uri(), wait_until="networkidle", timeout=timeout_ms)
            if check_nav:
                nav_results = await _check_nav(page)
        except Exception as exc:  # noqa: BLE001
            page_errors.append(f"render harness error: {exc}")
        finally:
            await browser.close()

    ok = not console_errors and not page_errors and all(n.ok for n in nav_results)
    return RenderResult(
        ok=ok,
        console_errors=console_errors,
        page_errors=page_errors,
        nav_results=nav_results,
    )


async def _check_nav(page) -> list[NavResult]:
    """Click each sidebar nav link and assert a page section becomes active.

    Heuristic for the SPA template family: nav links are ``.nav-item[href^='#']``;
    the visible page is ``[data-page].is-active`` / ``.section.is-active``. We record
    which data-page id actually activated, so the validator can detect route↔section
    mismatches (exactly the class of bug that motivated per-task validation).
    """
    results: list[NavResult] = []
    try:
        hrefs = await page.eval_on_selector_all(
            ".nav-item[href]", "els => els.map(e => e.getAttribute('href'))"
        )
    except Exception:
        return results
    for href in hrefs or []:
        if not href or not href.startswith("#"):
            continue
        try:
            await page.click(f'.nav-item[href="{href}"]', timeout=2000)
            activated = await page.eval_on_selector(
                "[data-page].is-active, .section.is-active",
                "el => el.getAttribute('data-page')",
            )
        except Exception:
            activated = None
        results.append(NavResult(href=href, activated=activated, ok=bool(activated)))
    return results
