#!/usr/bin/env python3
"""Dump the real, addressable controls on a live page.

    .venv/bin/python ../scripts/dump-controls.py /create/user-stories [role]

Reading source to find selectors is slow and gets it wrong: a control's testid
may be applied by a wrapper, a label may be composed at runtime, and a page may
render a different component than its filename suggests. This asks the running
app instead.

Signs in once through the real form — the same path suites/01_auth exercises.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2e"))

from playwright.sync_api import sync_playwright  # noqa: E402

from framework import accounts, settings  # noqa: E402
from framework.locators import auth as L  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "/dashboard"
role = sys.argv[2] if len(sys.argv) > 2 else "admin"

DUMP = """() => {
  const uniq = a => [...new Set(a)].filter(Boolean);
  const vis = el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const texts = sel => uniq([...document.querySelectorAll(sel)]
      .filter(vis)
      .map(e => (e.innerText || '').trim().replace(/\\s+/g, ' '))
      .filter(t => t && t.length < 60));
  return {
    url: location.pathname + location.search,
    testids: uniq([...document.querySelectorAll('[data-testid]')].map(e => e.dataset.testid)),
    names: uniq([...document.querySelectorAll('[name]')].map(e => e.getAttribute('name'))),
    aria: uniq([...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label'))),
    roles: uniq([...document.querySelectorAll('[role]')].map(e => e.getAttribute('role'))),
    buttons: texts('button'),
    links: texts('a'),
    headings: texts('h1,h2,h3,h4'),
    placeholders: uniq([...document.querySelectorAll('[placeholder]')].map(e => e.getAttribute('placeholder'))),
  };
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(base_url=settings.BASE_URL, viewport=settings.VIEWPORT)
    pg = ctx.new_page()
    pg.goto("/login")
    pg.fill(L.EMAIL, accounts.BY_ROLE[role])
    pg.fill(L.PASSWORD, accounts.PASSWORD)
    pg.click(L.SIGN_IN)
    pg.wait_for_url("**/dashboard", timeout=settings.LOGIN_TIMEOUT_MS)

    pg.goto(path)
    pg.wait_for_load_state("load")
    for sel in settings.BUSY_SELECTORS:
        try:
            pg.locator(sel).first.wait_for(state="hidden", timeout=settings.BUSY_TIMEOUT_MS)
        except Exception:
            pass
    pg.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")

    d = pg.evaluate(DUMP)
    for k, v in d.items():
        if isinstance(v, list):
            print(f"\n── {k} ({len(v)})")
            for item in v:
                print(f"   {item}")
        else:
            print(f"{k}: {v}")
    b.close()
