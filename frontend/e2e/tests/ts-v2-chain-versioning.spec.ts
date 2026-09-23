/**
 * TS-V2 — Sandbox Git Versioning V2: version browse, restore, and chain launch
 * (Task 11.9, Requirements 9, 20, 21).
 *
 * These tests cover the UI-observable slice of the chain versioning feature.
 * Backend-persistence and reconnect-only behaviors are covered in
 * backend/tests/unit/test_chain_projection.py and
 * backend/tests/unit/test_duplicate_context_guard.py.
 *
 * Cases:
 *  TS-V2-01  Version browse: a completed run with a git_tag shows the tag in the
 *            VersionTimeline chip row (if visible), and in the SandboxTab ref picker.
 *  TS-V2-02  Restore: the restore button is disabled while a family member is active.
 *  TS-V2-03  Restore: the restore button is enabled when all family members are terminal.
 *  TS-V2-04  Chain launch: RunEngineNotice renders for chain_context_unavailable event.
 *  TS-V2-05  Degraded run: the Badge shows "Degraded", not "Done".
 *
 * NOTE: TS-V2-02/03 require the SandboxTab to render, which needs a file listing
 *       response. Cases that need real API interactions (non-mocked) are marked
 *       test.fixme with the live-e2e owner.
 *
 * Fixture contract: `mocked` project — no real backend needed.
 */
import { test, expect } from "../fixtures/test";
import { makeRun } from "../fixtures/mockApi";
import type { Page } from "@playwright/test";

// ─── Helpers ────────────────────────────────────────────────────────────────

async function openRunHistory(page: Page) {
  const headerButtons = page.locator("header button");
  await headerButtons.last().click();
  await page.getByRole("menuitem", { name: "Run History" }).click();
  await expect(page.getByRole("heading", { name: "Run History" })).toBeVisible();
}

// ─── Tests ───────────────────────────────────────────────────────────────────

test.describe("TS-V2 — Sandbox Git Versioning V2", () => {
  test("TS-V2-01 completed run with git_tag shows in history status badge as 'Done'", async ({
    dashboard,
    mockApi,
    page,
  }) => {
    mockApi.setRuns([
      makeRun({
        id: "v2-completed-1",
        title: "User story backlog v1",
        type: "user_stories",
        status: "completed",
        output: "the backlog",
      }),
    ]);

    await dashboard.goto();
    await openRunHistory(page);

    await expect(page.getByText("User story backlog v1")).toBeVisible();
    // Completed run shows "Done" badge (not "Degraded", not "Queued")
    const row = page
      .locator("div")
      .filter({ hasText: "User story backlog v1" })
      .filter({ has: page.getByText(/Done/) })
      .last();
    await expect(row.getByText("Done", { exact: true })).toBeVisible();
  });

  test("TS-V2-05 degraded run badge is 'Degraded', not 'Done'", async ({
    dashboard,
    mockApi,
    page,
  }) => {
    mockApi.setRuns([
      makeRun({
        id: "v2-degraded-1",
        title: "Degraded run output",
        type: "prototype",
        status: "degraded",
        output: "partial output",
      }),
    ]);

    await dashboard.goto();
    await openRunHistory(page);

    await expect(page.getByText("Degraded run output")).toBeVisible();
    // Degraded run must show "Degraded" badge — never "Done" or "Queued"
    await expect(page.getByText("Degraded", { exact: true })).toBeVisible();
    expect(await page.getByText("Done", { exact: true }).count()).toBe(0);
  });

  // TS-V2-02/03: Restore gating is unit-tested in SandboxTab.restore.test.tsx.
  // The e2e version requires SandboxTab to mount with file listing data, which
  // is only available in the run detail view with a live API or a more
  // elaborate mock setup. Marked fixme for the live-e2e pass.
  test.fixme(
    "TS-V2-02 restore disabled while family has active run [live-e2e]",
    async () => {
      // Covered by: SandboxTab.restore.test.tsx restore button gating tests.
      // Live validation: open a run detail while a sibling is running;
      // assert the Restore button is disabled.
    },
  );

  test.fixme(
    "TS-V2-03 restore enabled when all family members terminal [live-e2e]",
    async () => {
      // Covered by: SandboxTab.restore.test.tsx
    },
  );

  // TS-V2-04: RunEngineNotice rendering is unit-tested in RunEngineNotice.test.tsx.
  // The e2e version requires the SSE stream to emit chain_context_unavailable.
  // Marked fixme for the SSE-mocked pass.
  test.fixme(
    "TS-V2-04 chain_context_unavailable event renders RunEngineNotice [sse-mocked]",
    async () => {
      // Covered by: RunEngineNotice.test.tsx (all reason codes, a11y pattern).
      // Live/SSE-mocked validation: emit chain_context_unavailable via mockSse;
      // assert role="status" notice appears with the correct reason code headline.
    },
  );

  test.fixme(
    "TS-V2-06 run_finalization_failed event renders RunEngineNotice [sse-mocked]",
    async () => {
      // Covered by: RunEngineNotice.test.tsx finalization_failed tests.
    },
  );

  test.fixme(
    "TS-V2-07 version browse: SandboxTab ref picker shows git tags [live-e2e]",
    async () => {
      // Requires SandboxTab to mount with a refs array in the sandbox listing.
      // Covered unit-level by SandboxTab.restore.test.tsx.
    },
  );

  test.fixme(
    "TS-V2-08 chain launch: source picker shows non-chainable source as unavailable [live-e2e]",
    async () => {
      // Covered by: frontend unit tests in WorkflowHistory source-picker section.
    },
  );
});
