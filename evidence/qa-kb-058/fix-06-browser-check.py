"""Ad-hoc fixer check for ISS-917 / ISS-982 (not a committed test).

Never clicks Continue (that launches a run).
"""
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:3000"
EVID = sys.argv[1]
BACK = '[aria-label="Back to dashboard"]'
BRIEF = 'textarea[name="brief"]'
class Results(list):
    def append(self, line):
        print(line, flush=True)
        super().append(line)


results = Results()


def dialog(page):
    return page.get_by_role("dialog").filter(has_text="Leave without saving?")


def settle(page):
    page.goto("/dashboard")
    page.goto("/create/prototype")
    page.wait_for_selector(BRIEF)
    # let the library, override/plan fetch and both registries land (FIX-103 apple auto-select)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    ctx = browser.new_context(base_url=BASE)
    page = ctx.new_page()
    page.on("dialog", lambda d: (results.append(f"NATIVE DIALOG: {d.message}"), d.dismiss()))
    page.goto("/login")
    page.fill('input[type="email"]', "admin@velocity.ai")
    page.fill('input[type="password"]', "Velocity!Dev2026")
    page.click('button:has-text("Sign in")')
    expect(page).to_have_url(re.compile(r"/dashboard"), timeout=30000)

    # A: untouched wizard, every async seed landed -> Back leaves, no dialog
    settle(page)
    page.click(BACK)
    page.wait_for_timeout(1500)
    a_ok = "/dashboard" in page.url and dialog(page).count() == 0
    page.screenshot(path=f"{EVID}/fix-01-untouched-back-leaves.png")
    results.append(f"A untouched Back -> {page.url} dialog={dialog(page).count()} {'PASS' if a_ok else 'FAIL'}")

    # B: typed brief -> Back shows dialog; Stay keeps text; Back + Leave anyway leaves
    settle(page)
    page.fill(BRIEF, "ISS-917 fixer check")
    page.click(BACK)
    page.wait_for_timeout(800)
    shown = dialog(page).count() > 0 and "/create/prototype" in page.url
    page.screenshot(path=f"{EVID}/fix-02-typed-back-dialog.png")
    results.append(f"B step1 after Back: url={page.url} dialog={dialog(page).count()}")
    dialog(page).get_by_role("button", name="Stay").click(timeout=5000)
    page.wait_for_timeout(500)
    stayed = dialog(page).count() == 0 and "/create/prototype" in page.url and page.input_value(BRIEF) == "ISS-917 fixer check"
    page.click(BACK)
    page.wait_for_timeout(500)
    dialog(page).get_by_role("button", name="Leave anyway").click()
    page.wait_for_timeout(1500)
    left = "/dashboard" in page.url
    page.screenshot(path=f"{EVID}/fix-03-leave-anyway-left.png")
    results.append(f"B typed: dialog={shown} stay-keeps-text={stayed} leave-anyway-left={left} ({page.url}) {'PASS' if shown and stayed and left else 'FAIL'}")

    # C: design-system pick only (no typing) -> Back prompts
    settle(page)
    page.click('[data-testid="tab-design-system"]')
    page.wait_for_timeout(1000)
    pick = page.locator('[data-testid="ds-band-select"][aria-pressed="false"]').first
    pick.dispatch_event("click")  # the toggle is opacity-0 until hover
    page.wait_for_timeout(500)
    page.click(BACK)
    page.wait_for_timeout(800)
    c_ok = dialog(page).count() > 0 and "/create/prototype" in page.url
    page.screenshot(path=f"{EVID}/fix-04-ds-pick-back-dialog.png")
    results.append(f"C design-system pick, nothing typed: dialog={dialog(page).count()} {'PASS' if c_ok else 'FAIL'}")
    dialog(page).get_by_role("button", name="Stay").click()

    # D: ISS-982 Advanced > Open in full canvas with a typed brief -> dialog, then Leave anyway -> canvas
    settle(page)
    page.fill(BRIEF, "ISS-982 fixer check")
    adv = page.locator('button:has-text("Advanced")')
    expect(adv).to_be_enabled(timeout=20000)
    adv.click()
    page.get_by_role("button", name="Open in full canvas").click()
    page.wait_for_timeout(800)
    d_shown = dialog(page).count() > 0 and "/create/prototype" in page.url
    page.screenshot(path=f"{EVID}/fix-05-canvas-exit-dialog.png")
    dialog(page).get_by_role("button", name="Leave anyway").click()
    page.wait_for_timeout(2500)
    d_left = "/workflows/prototype/canvas" in page.url
    results.append(f"D canvas exit: dialog={d_shown} leave-anyway-> {page.url} {'PASS' if d_shown and d_left else 'FAIL'}")

    # E: untouched wizard -> Open in full canvas goes straight through
    settle(page)
    adv = page.locator('button:has-text("Advanced")')
    expect(adv).to_be_enabled(timeout=20000)
    adv.click()
    page.get_by_role("button", name="Open in full canvas").click()
    page.wait_for_timeout(2500)
    e_ok = "/workflows/prototype/canvas" in page.url and dialog(page).count() == 0
    results.append(f"E untouched canvas exit -> {page.url} {'PASS' if e_ok else 'FAIL'}")

    browser.close()

print("DONE")
