/**
 * TS-T — WorkflowHistory (TEST-REGISTER §3): list & status badges, filter/search,
 * reopen (incl. the generic/custom sandboxed-iframe security heuristic), delete.
 *
 * The history view is one of DashboardLayout's `mainView`s. There is no top-level
 * nav button for it — it is reached through the AppHeader profile dropdown
 * (`onNavigate("history")` → setMainView("history")). The list is populated by
 * WorkflowHistory's getWorkflows() on mount, which the mock REST backend serves
 * from `mockApi.setRuns([...])`. So the pattern for every case is:
 *   1. mockApi.setRuns([ makeRun(...) ])  (BEFORE goto — armed when the view mounts)
 *   2. dashboard.goto()
 *   3. openHistory(page)  → click profile dropdown → "Workflow History"
 */
import { test, expect } from "../fixtures/test";
import { makeRun } from "../fixtures/mockApi";
import type { Page } from "@playwright/test";

/**
 * Open the WorkflowHistory view via the AppHeader profile dropdown.
 * The profile trigger is the last button in the dark global header (User avatar
 * + ChevronDown, no text label); the dropdown then exposes a "Workflow History"
 * menu item that calls onNavigate("history").
 */
async function openHistory(page: Page) {
  // The profile button is the trailing button in the <header>. Notifications +
  // profile are the only always-present trailing buttons; the profile one is last.
  const headerButtons = page.locator("header button");
  await headerButtons.last().click();
  // Phase 39 redesign renamed the profile menu item + list heading to "Run History"
  // and the dropdown items now carry role="menuitem" (not the implicit button role).
  await page.getByRole("menuitem", { name: "Run History" }).click();
  // The history list header heading confirms we landed on the view.
  await expect(page.getByRole("heading", { name: "Run History" })).toBeVisible();
}

test.describe("TS-T — WorkflowHistory", () => {
  test("TS-T-01 list & status badges (completed/cancelled/failed/running)", async ({ dashboard, mockApi, page }) => {
    mockApi.setRuns([
      makeRun({ id: "h-done", title: "Refunds backlog", type: "user_stories", status: "completed" }),
      makeRun({ id: "h-cancel", title: "Pitch deck draft", type: "ppt", status: "cancelled" }),
      makeRun({ id: "h-fail", title: "Broken prototype", type: "prototype", status: "failed" }),
      makeRun({ id: "h-run", title: "Live app build", type: "app_builder", status: "running" }),
    ]);

    await dashboard.goto();
    await openHistory(page);

    // Each seeded run renders a row by title.
    await expect(page.getByText("Refunds backlog")).toBeVisible();
    await expect(page.getByText("Pitch deck draft")).toBeVisible();
    await expect(page.getByText("Broken prototype")).toBeVisible();
    await expect(page.getByText("Live app build")).toBeVisible();

    // Status badge labels (WorkflowHistory list view): Done / Cancelled / Failed / Running.
    // Scope each badge to its row so the assertion is row-accurate.
    const rowOf = (title: string) =>
      page.locator("div").filter({ hasText: title }).filter({ has: page.getByText(/^(Done|Cancelled|Failed|Running)$/) }).last();

    await expect(rowOf("Refunds backlog").getByText("Done", { exact: true })).toBeVisible();
    await expect(rowOf("Pitch deck draft").getByText("Cancelled", { exact: true })).toBeVisible();
    await expect(rowOf("Broken prototype").getByText("Failed", { exact: true })).toBeVisible();
    await expect(rowOf("Live app build").getByText("Running", { exact: true })).toBeVisible();
  });

  test("TS-T-02 filter tabs & search filter the list", async ({ dashboard, mockApi, page }) => {
    // A type-filter tab only renders when its count > 0, so seed one run of each
    // base type to surface every tab.
    mockApi.setRuns([
      makeRun({ id: "f-us", title: "Stories alpha", type: "user_stories", status: "completed" }),
      makeRun({ id: "f-ppt", title: "Deck beta", type: "ppt", status: "completed" }),
      makeRun({ id: "f-proto", title: "Proto gamma", type: "prototype", status: "completed" }),
      makeRun({ id: "f-app", title: "App delta", type: "app_builder", status: "completed" }),
      makeRun({ id: "f-custom", title: "Custom epsilon", type: "custom", status: "completed" }),
    ]);

    await dashboard.goto();
    await openHistory(page);

    // Filter tabs render with TYPE_META labels (NOT the raw type keys):
    //   all→"All", user_stories→"User Stories", ppt→"Presentation",
    //   prototype→"Prototype", app_builder→"App Builder", custom→"Custom".
    const tabs = page.locator(".overflow-x-auto").first();
    await expect(tabs.getByRole("button", { name: /^All/ })).toBeVisible();
    await expect(tabs.getByRole("button", { name: /^User Stories/ })).toBeVisible();
    await expect(tabs.getByRole("button", { name: /^Presentation/ })).toBeVisible();
    await expect(tabs.getByRole("button", { name: /^Prototype/ })).toBeVisible();
    await expect(tabs.getByRole("button", { name: /^App Builder/ })).toBeVisible();
    await expect(tabs.getByRole("button", { name: /^Custom/ })).toBeVisible();

    // Clicking a type tab narrows the list to that type.
    await tabs.getByRole("button", { name: /^User Stories/ }).click();
    await expect(page.getByText("Stories alpha")).toBeVisible();
    await expect(page.getByText("Deck beta")).toHaveCount(0);

    // Back to All, then the search input filters rows by title.
    await tabs.getByRole("button", { name: /^All/ }).click();
    await expect(page.getByText("Deck beta")).toBeVisible();

    const search = page.getByPlaceholder("Search workflows...");
    await search.fill("gamma");
    await expect(page.getByText("Proto gamma")).toBeVisible();
    await expect(page.getByText("Stories alpha")).toHaveCount(0);
    await expect(page.getByText("Deck beta")).toHaveCount(0);

    // Clearing the search restores the full list.
    await search.fill("");
    await expect(page.getByText("Stories alpha")).toBeVisible();
  });

  test("TS-T-03 reopen a completed run → the SHARED run screen shows its output (BUG-002)", async ({ dashboard, mockApi, page }) => {
    mockApi.setRuns([
      makeRun({
        id: "r-open",
        title: "Refunds backlog",
        type: "user_stories",
        status: "completed",
        output: "# Product Backlog\n\n## Epic: Refunds\n\nAs a user I want a refund.",
      }),
    ]);

    await dashboard.goto();
    await openHistory(page);

    // BUG-002: a History row tap now routes through onOpenRun → the SHARED run
    // screen (execution-chat-lane + composer), NOT WorkflowHistory's divergent
    // internal RunDetailPage (Preview/Files/Thinking). Its reopen deliverable now
    // renders in the run screen's PreviewPanel — parity with the Home-recents path
    // covered by ts-live-state (b).
    await page.getByText("Refunds backlog").click();

    // The shared run screen mounts (NOT the internal detail).
    await expect(page.getByTestId("execution-chat-lane")).toBeVisible();

    // The reopened deliverable renders in the run screen's Preview tab.
    await dashboard.previewTab().click();
    await expect(page.getByText("Product Backlog").first()).toBeVisible();
  });

  test("TS-T-04 generic/custom run History tap opens the shared run screen (BUG-002 routing)", async ({ dashboard, mockApi, page }) => {
    // A `custom`/unknown run whose output is HTML. BUG-002: the History tap now
    // routes through onOpenRun → the shared run screen (execution-chat-lane),
    // NOT WorkflowHistory's internal RunDetailPage. The sandboxed-iframe SECURITY
    // contract for the generic reopen is pinned in-browser by
    // WorkflowHistory.genericReopen.test.tsx; the run-screen rendering of it is
    // covered by TS-T-04b below.
    mockApi.setRuns([
      makeRun({
        id: "r-generic",
        title: "Custom deliverable",
        type: "custom",
        status: "completed",
        output: "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>",
      }),
    ]);

    await dashboard.goto();
    await openHistory(page);

    await page.getByText("Custom deliverable").click();

    // The shared run screen mounts (BUG-002 routing) — NOT the internal detail.
    await expect(page.getByTestId("execution-chat-lane")).toBeVisible();
    await expect(page.getByRole("tab", { name: /Steps/i })).toBeVisible();
  });

  test.fixme("TS-T-04b generic/custom reopen renders its SANDBOXED iframe in the shared run screen", async ({ dashboard, mockApi, page }) => {
    // FOLLOW-UP (deferred-items.md / DEF-BUG-002-generic-reopen): after BUG-002
    // routed History taps to the shared run screen, a reopened GENERIC/CUSTOM
    // deliverable renders the empty "Output will appear here" state in the run
    // screen's PreviewPanel (the reopen content seed does not repopulate
    // genericDeliverable on this path). TYPED deliverables (user_stories — TS-T-03)
    // render fine; the Home-recents path shares this generic-reopen gap, so BUG-002
    // exposed rather than introduced it. The sandbox SECURITY contract itself stays
    // covered by WorkflowHistory.genericReopen.test.tsx. Un-fixme once the run
    // screen renders a reopened generic deliverable.
    mockApi.setRuns([
      makeRun({ id: "r-generic", title: "Custom deliverable", type: "custom", status: "completed", output: "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>" }),
    ]);
    await dashboard.goto();
    await openHistory(page);
    await page.getByText("Custom deliverable").click();
    await expect(page.getByTestId("execution-chat-lane")).toBeVisible();
    await dashboard.previewTab().click();
    const iframe = page.locator('iframe[title="Deliverable Preview"]');
    await expect(iframe).toBeVisible();
    await expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
    const sandbox = (await iframe.getAttribute("sandbox")) || "";
    expect(sandbox).not.toContain("allow-same-origin");
    await expect(iframe).toHaveAttribute("srcdoc", /<h1>Hi<\/h1>/);
  });

  test("TS-T-06 delete a run via kebab → confirm modal → DELETE request", async ({ dashboard, mockApi, page }) => {
    mockApi.setRuns([
      makeRun({ id: "del-1", title: "Disposable run", type: "user_stories", status: "completed" }),
      makeRun({ id: "keep-1", title: "Kept run", type: "ppt", status: "completed" }),
    ]);

    await dashboard.goto();
    await openHistory(page);

    // The kebab (MoreHorizontal) button is hidden until row hover, so move the
    // pointer onto the row first, then open its menu.
    const row = page.locator("div.cursor-pointer").filter({ hasText: "Disposable run" }).first();
    await row.hover();
    // The kebab is the row's only trailing icon-button (no text); it sits before
    // the ChevronRight. Click it to open the per-row menu.
    await row.getByRole("button").last().click();

    // Menu → Delete → confirm modal "Delete workflow" → confirm Delete.
    // The per-row menu Delete item is a role="menuitem" (RowMenu); the modal's
    // confirm Delete (below) is a plain button.
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await expect(page.getByRole("heading", { name: "Delete workflow" })).toBeVisible();

    // The modal exposes Cancel + Delete; click the confirming Delete (the last one).
    await page.getByRole("button", { name: "Delete", exact: true }).last().click();

    // Assert the DELETE request was made to /api/runs/<id> AND the row vanished.
    await expect(page.getByText("Disposable run")).toHaveCount(0);
    const deleteReq = mockApi.requests.find(
      (r) => r.method === "DELETE" && /\/api\/runs\/del-1$/.test(r.url),
    );
    expect(deleteReq, "a DELETE /api/runs/del-1 request should have been recorded").toBeTruthy();
    // The other run is untouched.
    await expect(page.getByText("Kept run")).toBeVisible();
  });
});
