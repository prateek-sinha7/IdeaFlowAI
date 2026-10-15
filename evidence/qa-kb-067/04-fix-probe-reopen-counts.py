"""QA-KB-067 probe: count the reopen requests per run-open surface.

Read-only against the running app (no run is launched). Usage:
  tests/integration/e2e/.venv/bin/python probe_reopen_counts.py <evidence-dir> <label>
"""
import json
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

OUT, LABEL = sys.argv[1], sys.argv[2]
EMAIL, PW = "admin@velocity.ai", "Velocity!Dev2026"


def counts(reqs, rid):
    return {
        "GET /api/runs/{id}": sum(1 for u in reqs if re.search(rf"/api/runs/{rid}(\?|$)", u)),
        "events?after=0": sum(1 for u in reqs if f"/api/runs/{rid}/events" in u and "after=0" in u),
        "/family": sum(1 for u in reqs if f"/api/runs/{rid}/family" in u),
    }


def runs_page(page, token, offset):
    return page.evaluate(
        """async ([t, off]) => {
            const r = await fetch(`http://localhost:8000/api/runs?limit=50&offset=${off}`,
                                  { headers: { Authorization: `Bearer ${t}` } });
            const j = await r.json();
            return Array.isArray(j) ? j : (j.runs ?? j.items ?? []);
        }""",
        [token, offset],
    )


def seed_notification(page, run, title):
    note = [{
        "id": f"probe-{run['id']}", "workflowRunId": run["id"],
        "workflowType": run.get("type") or "custom", "title": title,
        "status": "completed", "createdAt": datetime.now(timezone.utc).isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(), "read": False,
    }]
    page.evaluate("n => localStorage.setItem('flowin.notifications.v3', JSON.stringify(n))", note)


def open_from_bell(page, title):
    page.locator('button[aria-label="Notifications"]').click()
    page.locator(f'[role="dialog"][aria-label="Notifications"] [role="button"][aria-label="{title}"]').click()


results = {}
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(base_url="http://localhost:3000", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    reqs: list[str] = []
    page.on("request", lambda r: reqs.append(r.url))

    page.goto("/login")
    page.fill('input[type="email"]', EMAIL)
    page.fill('input[type="password"]', PW)
    page.click('button:has-text("Sign in")')
    page.wait_for_url(re.compile(r"/dashboard"), timeout=60000)
    token = page.evaluate("localStorage.getItem('auth_token')")

    recent = runs_page(page, token, 0)
    older = runs_page(page, token, 50)
    done = lambda rs: [r for r in rs if r.get("status") == "completed"]
    cached = done(recent)[0]
    uncached = next((r for r in done(older) if r["id"] not in {x["id"] for x in recent}), None)

    # 1. History row (ISS-840, T7) — the test's own path.
    page.goto("/dashboard"); page.wait_for_timeout(500)
    page.goto("/runs")
    page.locator('div[role="button"][aria-label^="Open "]').first.wait_for()
    labels = page.locator('div[role="button"][aria-label^="Open "]').evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))")
    idx = next(i for i, l in enumerate(labels) if l.rsplit(",", 1)[-1].strip().lower() == "completed")
    page.wait_for_timeout(1500); reqs.clear()
    page.locator('div[role="button"][aria-label^="Open "]').nth(idx).click()
    page.wait_for_url(lambda u: "/runs/" in u); page.wait_for_timeout(4000)
    rid = re.search(r"/runs/([^/?#]+)", page.url).group(1)
    results["history_row"] = {"run": rid, "url": page.url, **counts(reqs, rid),
                              "empty_state_visible": page.get_by_text("Output will appear here").is_visible()}
    page.screenshot(path=f"{OUT}/{LABEL}-1-history-row.png")

    # 2. Bell, run in the recents window (ISS-1076, T11 via the cached branch).
    seed_notification(page, cached, "QA-KB-067 probe cached")
    page.goto("/dashboard"); page.wait_for_timeout(2500); reqs.clear()
    open_from_bell(page, "QA-KB-067 probe cached")
    page.wait_for_url(lambda u: f"/runs/{cached['id']}" in u); page.wait_for_timeout(4000)
    results["bell_cached"] = {"run": cached["id"], "url": page.url, **counts(reqs, cached["id"]),
                              "empty_state_visible": page.get_by_text("Output will appear here").is_visible()}
    page.screenshot(path=f"{OUT}/{LABEL}-2-bell-cached.png")

    # 3. Bell, run outside the recents window (ISS-1076, the dropped fetch-then-open).
    if uncached:
        seed_notification(page, uncached, "QA-KB-067 probe uncached")
        page.goto("/dashboard"); page.wait_for_timeout(2500); reqs.clear()
        open_from_bell(page, "QA-KB-067 probe uncached")
        page.wait_for_url(lambda u: f"/runs/{uncached['id']}" in u); page.wait_for_timeout(4000)
        results["bell_uncached"] = {"run": uncached["id"], "url": page.url, **counts(reqs, uncached["id"]),
                                    "empty_state_visible": page.get_by_text("Output will appear here").is_visible()}
        page.screenshot(path=f"{OUT}/{LABEL}-3-bell-uncached.png")

    # 4. Bell for the run already on screen at the URL it pushes (no remount).
    seed_notification(page, cached, "QA-KB-067 probe same")
    page.goto(f"/runs/{cached['id']}/stream"); page.wait_for_timeout(5000); reqs.clear()
    open_from_bell(page, "QA-KB-067 probe same")
    page.wait_for_timeout(4000)
    results["bell_same_url"] = {"run": cached["id"], "url": page.url, **counts(reqs, cached["id"]),
                                "empty_state_visible": page.get_by_text("Output will appear here").is_visible()}
    page.screenshot(path=f"{OUT}/{LABEL}-4-bell-same-url.png")

    browser.close()

print(json.dumps(results, indent=2))
