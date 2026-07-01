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
import re
from dataclasses import dataclass, field
from pathlib import Path

# The first-path-segment page-id extraction is the SINGLE shared helper with
# static_check (a route's first segment is what the SPA router matches against a
# ``data-page`` id — deeper segments are ``:params``). Importing it here keeps
# ONE definition (no second copy) so both validators agree on the target id.
from app.agents.static_check import _href_target_id

logger = logging.getLogger("app.agents.render_check")


# --------------------------------------------------------------------------- #
# Pure, offline-testable nav/coverage helpers (no browser, no I/O).
# --------------------------------------------------------------------------- #

# Click-handler nav discovery: an ``onclick`` that drives the hash router by
# assigning ``location.hash = '#/…'`` OR calling ``navigateTo('#/…')``. The route
# string is captured so the check can exercise a representative of each target.
_HASH_ASSIGN_RE = re.compile(r"location\.hash\s*=\s*['\"]([^'\"]+)['\"]")
_NAVIGATE_TO_RE = re.compile(r"navigateTo\(\s*['\"]([^'\"]+)['\"]")


def _first_path_segment(route: str) -> str:
    """First path segment of a route (the candidate page id) — shared with static_check.

    Normalizes a handler-extracted route (``#/inventory/4521`` -> ``inventory``,
    ``inventory-list`` -> ``inventory-list``) then delegates to static_check's
    ``_href_target_id`` so BOTH validators resolve the SAME target id.
    """
    r = (route or "").strip()
    if not r:
        return ""
    if not r.startswith("#"):
        r = "#" + r if r.startswith("/") else "#/" + r
    return _href_target_id(r)


def _extract_handler_routes(onclick_body: str) -> list[str]:
    """Return the hash routes an ``onclick`` body navigates to (``location.hash`` / navigateTo).

    Only fragment routes (``#/…``) are returned — a non-hash target is not a SPA
    nav we can exercise. Pure regex over the handler string (offline-testable).
    """
    routes: list[str] = []
    for rx in (_HASH_ASSIGN_RE, _NAVIGATE_TO_RE):
        for m in rx.finditer(onclick_body or ""):
            route = m.group(1).strip()
            if route.startswith("#"):
                routes.append(route)
    return routes


def _nav_ok(activated: str | None, expected: str | None) -> bool:
    """A nav is OK iff the activated data-page equals the EXPECTED first-path-segment.

    ``activated == expected`` (wrong-section activation → False; nothing activated →
    False). Pure + offline-testable — the wrong-section-activation regression guard.
    """
    return activated is not None and activated == expected


def _coverage_finding(section_count: int, exercised: int) -> str | None:
    """P0 coverage message when a multi-section SPA exercised ZERO nav targets, else None.

    A prototype with ``>= 2`` ``[data-page]`` sections but ``0`` discoverable/
    exercised navigation is a fail-open blind spot (the old ``nav_results=0`` silent
    OK). A single-section (or no-section) page never trips this. Pure + offline.
    """
    if section_count >= 2 and exercised == 0:
        return (
            f"no navigable elements exercised: {section_count} <section data-page> "
            f"present but 0 navigation targets were discovered/exercised — the SPA's "
            f"pages are unreachable (nav coverage = 0)"
        )
    return None


@dataclass
class NavResult:
    href: str
    activated: str | None  # data-page id that became active, or None
    ok: bool
    expected: str | None = None  # the first-path-segment page id we expected to activate


@dataclass
class RenderResult:
    ok: bool
    available: bool = True  # False when Playwright/Chromium isn't installed
    console_errors: list[str] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)
    nav_results: list[NavResult] = field(default_factory=list)
    coverage_errors: list[str] = field(default_factory=list)
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
        if self.coverage_errors:
            bits.append(f"{len(self.coverage_errors)} nav-coverage finding(s)")
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
    coverage_errors: list[str] = []

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
                # Nav COVERAGE: a multi-section SPA that exercised ZERO nav targets
                # is the fail-open blind spot (the old ``nav_results=0`` silent OK).
                try:
                    section_count = await page.eval_on_selector_all(
                        "[data-page]", "els => els.length"
                    )
                except Exception:  # noqa: BLE001 — a query failure ⇒ no coverage finding
                    section_count = 0
                finding = _coverage_finding(int(section_count or 0), len(nav_results))
                if finding:
                    coverage_errors.append(finding)
        except Exception as exc:  # noqa: BLE001
            page_errors.append(f"render harness error: {exc}")
        finally:
            await browser.close()

    ok = (
        not console_errors
        and not page_errors
        and all(n.ok for n in nav_results)
        and not coverage_errors
    )
    return RenderResult(
        ok=ok,
        console_errors=console_errors,
        page_errors=page_errors,
        nav_results=nav_results,
        coverage_errors=coverage_errors,
    )


async def _check_nav(page) -> list[NavResult]:
    """Exercise each discoverable nav target and assert the EXPECTED page activates.

    Nav discovery is broadened beyond the old ``.nav-item[href]`` heuristic (which
    silently found ZERO on a hash-router SPA that navigates via ``onclick`` handlers
    and parameterized routes — the coverage blind spot this hardening closes):

      * generic anchor routes ``a[href^='#']``;
      * click-handler nav — any element whose ``onclick`` assigns ``location.hash``
        or calls ``navigateTo('#/…')`` (route extracted by regex from the handler).

    Candidates are DEDUPED by their first-path-segment target (so ``#/certificate/1``
    and ``#/certificate/2`` collapse to one representative ``certificate``), and one
    representative of each target is exercised. The visible page is
    ``[data-page].is-active`` / ``.section.is-active``. Each ``NavResult`` records the
    EXPECTED first-path-segment id and ``ok = activated == expected`` — so a
    wrong-section activation (and a dead/parameterized route with NO matching section)
    is caught, not just a hard "nothing activated".
    """
    results: list[NavResult] = []

    # (route, from_anchor) candidates.
    candidates: list[tuple[str, bool]] = []

    # (1) generic anchor routes.
    try:
        hrefs = await page.eval_on_selector_all(
            "a[href^='#']", "els => els.map(e => e.getAttribute('href'))"
        )
    except Exception:  # noqa: BLE001 — a query failure just means no anchor nav
        hrefs = []
    for href in hrefs or []:
        if href and href.startswith("#"):
            candidates.append((href, True))

    # (2) click-handler nav (onclick location.hash / navigateTo).
    try:
        onclicks = await page.eval_on_selector_all(
            "[onclick]", "els => els.map(e => e.getAttribute('onclick'))"
        )
    except Exception:  # noqa: BLE001 — a query failure just means no handler nav
        onclicks = []
    for body in onclicks or []:
        for route in _extract_handler_routes(body or ""):
            candidates.append((route, False))

    # Dedupe by first-path-segment target (one representative per target).
    seen_targets: set[str] = set()
    reps: list[tuple[str, bool]] = []
    for route, from_anchor in candidates:
        target = _first_path_segment(route)
        if not target or target in seen_targets:
            continue
        seen_targets.add(target)
        reps.append((route, from_anchor))

    for route, from_anchor in reps:
        expected = _first_path_segment(route)
        activated = await _exercise_route(page, route, from_anchor)
        results.append(
            NavResult(
                href=route,
                activated=activated,
                ok=_nav_ok(activated, expected),
                expected=expected,
            )
        )
    return results


async def _exercise_route(page, route: str, from_anchor: bool) -> str | None:
    """Exercise ONE nav route and return the activated ``data-page`` id (or None).

    Anchors are clicked (the legacy behavior); a handler route drives the hash router
    by assigning ``location.hash``. Either way the router's ``hashchange`` handler
    runs, then the active section id is read back.
    """
    try:
        if from_anchor:
            try:
                await page.click(f'a[href="{route}"]', timeout=2000)
            except Exception:  # noqa: BLE001 — fall back to driving the hash directly
                await page.evaluate("(h) => { window.location.hash = h; }", route)
        else:
            await page.evaluate("(h) => { window.location.hash = h; }", route)
        # Let the router's hashchange handler run before reading the active section.
        await page.wait_for_timeout(50)
        return await page.eval_on_selector(
            "[data-page].is-active, .section.is-active",
            "el => el.getAttribute('data-page')",
        )
    except Exception:  # noqa: BLE001 — nothing activated (dead route / no section)
        return None
