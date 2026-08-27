"""Screenshot-per-step capture.

`shot()` wraps a block of actions, runs them, and screenshots the SETTLED state
on the way out — so the image shows the result of the step rather than the
browser mid-action. On an exception it shoots anyway, suffixes the file
`-FAILED`, and re-raises: a failure is exactly when the picture is worth most.

Each shot writes a row into `steps.json` beside the images, carrying the Gherkin
line it came from, the URL, any console errors and any failed requests seen
during the block. A bare PNG makes a later reader guess what it was meant to
prove; the row tells them.

`steps.json` is rewritten after every shot rather than at the end, so a hard
crash still leaves the evidence collected up to that point.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from pathlib import Path


from framework import settings


def slugify(text: str) -> str:
    """`"Credentials entered"` -> `"credentials-entered"`."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "shot"


class Shooter:
    """Per-scenario screenshot writer. One instance per test, via the fixture."""

    def __init__(self, page, out_dir: Path, scenario_id: str, title: str, reporter=None):
        self.page = page
        self.dir = out_dir
        self.n = 0
        self.rows: list[dict] = []
        self.meta = {"scenario": scenario_id, "title": title}
        self.reporter = reporter
        self._console: list[str] = []
        self._failed: list[str] = []

        # Attached once, drained per block: a listener added inside shot() would
        # miss anything logged by a redirect the previous step kicked off.
        page.on("console", self._on_console)
        page.on("requestfailed", self._on_request_failed)

    # ── listeners ────────────────────────────────────────────────────────────

    def _on_console(self, msg) -> None:
        if msg.type == "error":
            self._console.append(msg.text)

    def _on_request_failed(self, request) -> None:
        # A cancelled navigation shows up here too; the failure text separates a
        # real network error from a request the browser abandoned on purpose.
        self._failed.append(f"{request.method} {request.url} — {request.failure}")

    # ── capture ──────────────────────────────────────────────────────────────

    def _settle(self) -> None:
        """Let the page finish painting before the shutter.

        An assertion only waits for the ONE thing it asserts on. `expect(heading)
        .to_be_visible()` is satisfied the moment that heading exists, while
        images, webfonts and the rest of the layout are still arriving — so the
        screenshot catches a half-drawn page even though the test is correct.

        Every timeout and selector used here lives in `framework/settings.py`.
        Nothing in this function hard-codes one — when shots come out
        half-painted, that file is the single place to change.

        Best-effort throughout. A screenshot must never be the reason a test
        fails, so every wait here swallows its own timeout.
        """
        try:
            # `load` covers images and stylesheets, unlike `domcontentloaded`.
            self.page.wait_for_load_state("load", timeout=settings.SETTLE_MS)
        except Exception:
            pass

        # The `load` event fires when the DOCUMENT is done, which on a
        # client-rendered app is well before the DATA is. That gap is what puts
        # skeleton cards and a "Loading workspace…" toast into an otherwise
        # correct screenshot, so wait for every busy affordance to clear.
        for selector in settings.BUSY_SELECTORS:
            try:
                self.page.locator(selector).first.wait_for(
                    state="hidden", timeout=settings.BUSY_TIMEOUT_MS
                )
            except Exception:
                # Not present at all is the common case and raises here; a
                # genuinely stuck spinner times out. Both mean "carry on and
                # shoot" — the screenshot then shows the stuck state, which is
                # the truth and is what the reader needs to see.
                pass

        try:
            # Playwright awaits a returned promise. Until fonts resolve the page
            # renders in a fallback face and reflows the instant it swaps —
            # which is most of what "blurry" and "shifted" screenshots are.
            self.page.evaluate("() => document.fonts && document.fonts.ready")
        except Exception:
            pass
        try:
            # One frame for React to commit and the browser to paint it. `fill()`
            # returns before the controlled input has re-rendered its value.
            self.page.evaluate(
                "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
            )
        except Exception:
            pass

    def _capture(self, slug: str, gherkin: str, outcome: str, ms: int, since: tuple[int, int]):
        self._settle()
        self.n += 1
        name = f"{self.n:02d}-{slugify(slug)}"
        if outcome != "passed":
            name += "-FAILED"
        filename = f"{name}.png"

        # A screenshot must never be the reason a test fails. If the page is
        # gone (crashed, navigated away mid-teardown) record that and continue —
        # the real assertion error is the one worth surfacing.
        try:
            # animations="disabled" finishes any CSS animation or transition
            # instantly and pins infinite ones to their first frame. Without it
            # a shot taken during a fade or slide catches it half-done, which
            # reads as a blurry or doubled screenshot rather than a real state.
            self.page.screenshot(path=str(self.dir / filename), animations="disabled")
            shot_error = None
        except Exception as exc:  # pragma: no cover - defensive
            shot_error = str(exc)

        c_at, f_at = since
        console = self._console[c_at:]
        failed = self._failed[f_at:]
        self.rows.append(
            {
                "n": self.n,
                "slug": slugify(slug),
                "gherkin": gherkin,
                "shot": filename,
                "url": self._safe_url(),
                "console": console,
                "failed_requests": failed,
                "outcome": outcome,
                "ms": ms,
                **({"screenshot_error": shot_error} if shot_error else {}),
            }
        )
        self._write()

        if self.reporter is not None:
            self.reporter.step_end(outcome == "passed", ms)
            # Surfaced live, not just filed in steps.json: a console error or a
            # dead request is usually the actual explanation for the failure two
            # steps later.
            for msg in console[:3]:
                self.reporter.note(f"console: {msg[:110]}")
            for req in failed[:3]:
                self.reporter.note(f"request failed: {req[:110]}")

    def _safe_url(self) -> str:
        try:
            return self.page.url
        except Exception:  # pragma: no cover - defensive
            return ""

    def _write(self) -> None:
        (self.dir / "steps.json").write_text(
            json.dumps({**self.meta, "steps": self.rows}, indent=2) + "\n"
        )

    # ── public API ───────────────────────────────────────────────────────────

    @contextmanager
    def __call__(self, slug: str, gherkin: str = ""):
        """Run a block, then screenshot what it produced.

            with shot("dashboard", "Then the dashboard loads"):
                page.click(SIGN_IN)
                expect(page).to_have_url(...)

        Put the assertion INSIDE the block: `expect()` polls until it passes, so
        it is both the wait and the check, and the screenshot lands after the
        page has settled rather than after an arbitrary sleep.
        """
        since = (len(self._console), len(self._failed))

        # Announced BEFORE the block runs. A step that takes two minutes on a
        # cold dev-server compile must be visible while it is happening — that
        # is precisely when silence looks like a hang.
        if self.reporter is not None:
            self.reporter.step_start(self.n + 1, slug, gherkin)

        started = time.monotonic()
        try:
            yield
        except BaseException:
            self._capture(slug, gherkin, "failed", int((time.monotonic() - started) * 1000), since)
            raise
        self._capture(slug, gherkin, "passed", int((time.monotonic() - started) * 1000), since)

    def now(self, slug: str, gherkin: str = "") -> None:
        """Shoot immediately, with no block around it.

        For sequences where the step boundary is a state change rather than an
        action — a run moving through queued/running/completed, or the proof
        either side of a gate click.
        """
        # Opened here too: `_capture` always closes a line, so one must be open
        # or the timing lands on the previous step's row.
        if self.reporter is not None:
            self.reporter.step_start(self.n + 1, slug, gherkin)
        self._capture(slug, gherkin, "passed", 0, (len(self._console), len(self._failed)))
