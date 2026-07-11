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

/**
 * Stub GET /api/runs/{id}/summary (SHELL-03 RunDetailPage data spine). The shared
 * mockApi (frontend/e2e/fixtures/mockApi.ts — outside the nine files this wave may
 * edit) has no route for it, so its catch-all returns {} and RunDetailPage throws
 * on the missing `agents`/`token_usage` fields → ErrorBoundary blanks the reopen
 * detail. Registered per-test so it wins (LIFO) over the fixture's "**\/api\/**".
 * Returns a minimal, crash-free RunSummary keyed to the requested run id.
 */
async function stubRunSummary(page: Page) {
  await page.route("**/api/runs/*/summary", async (route) => {
    const parts = new URL(route.request().url()).pathname.split("/");
    const id = parts[parts.length - 2] || "run";
    await route.fulfill({
      json: {
        id,
        title: "",
        type: "custom",
        status: "completed",
        input: "",
        duration: null,
        agent_count: 0,
        token_usage: {},
        error: null,
        agents: [],
        root_id: id,
        members: [],
      },
    });
  });
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

  test("TS-T-03 reopen a completed run → detail view shows its output", async ({ dashboard, mockApi, page }) => {
    mockApi.setRuns([
      makeRun({
        id: "r-open",
        title: "Refunds backlog",
        type: "user_stories",
        status: "completed",
        output: "# Product Backlog\n\n## Epic: Refunds\n\nAs a user I want a refund.",
      }),
    ]);
    // Phase 39 (SHELL-03): the reopen detail's left summary column is now the
    // RunDetailPage, fed by GET /api/runs/{id}/summary — an endpoint the shared
    // mockApi (outside these nine files) does not serve, so its catch-all returns
    // {} and RunDetailPage throws on summary.agents.map → ErrorBoundary, which
    // blanks the whole detail (incl. the right-column tabs this test asserts).
    // Stub the summary endpoint here with a minimal valid RunSummary so the detail
    // renders. This override wins over the fixture's "**/api/**" route (LIFO).
    await stubRunSummary(page);

    await dashboard.goto();
    await openHistory(page);

    // Click the row → detail view opens. The detail surface carries the
    // Preview / Files / Thinking tabs and renders the run output (UserStoryPreview).
    await page.getByText("Refunds backlog").click();

    await expect(page.getByRole("button", { name: "Preview" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Files" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Thinking" })).toBeVisible();

    // The reopened preview renders the persisted backlog content.
    await expect(page.getByText("Product Backlog").first()).toBeVisible();
  });

  test("TS-T-04 generic/custom reopen renders a SANDBOXED iframe (allow-scripts, no same-origin)", async ({ dashboard, mockApi, page }) => {
    // A `custom`/unknown run whose output is HTML routes through the generic
    // fallback: deriveDeliverableMimetype → text/html → the SAME sandboxed iframe
    // as the live deliverable path (allow-scripts only, NEVER allow-same-origin).
    // Mirrors WorkflowHistory.genericReopen.test.tsx in-browser.
    mockApi.setRuns([
      makeRun({
        id: "r-generic",
        title: "Custom deliverable",
        type: "custom",
        status: "completed",
        output: "<!DOCTYPE html><html><body><h1>Hi</h1></body></html>",
      }),
    ]);
    // See TS-T-03: stub the SHELL-03 RunDetailPage summary endpoint so the reopen
    // detail renders instead of crashing into the ErrorBoundary.
    await stubRunSummary(page);

    await dashboard.goto();
    await openHistory(page);

    await page.getByText("Custom deliverable").click();

    const iframe = page.locator('iframe[title="Deliverable Preview"]');
    await expect(iframe).toBeVisible();
    // BLOCKING security contract: exactly allow-scripts, explicitly NOT same-origin.
    await expect(iframe).toHaveAttribute("sandbox", "allow-scripts");
    const sandbox = (await iframe.getAttribute("sandbox")) || "";
    expect(sandbox).not.toContain("allow-same-origin");
    // The HTML deliverable is delivered via srcdoc (the heading is inside it).
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
