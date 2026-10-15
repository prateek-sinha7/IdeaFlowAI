/**
 * TS-V2 — Sandbox Git Versioning V2: version browse, restore, and chain launch
 * (Task 11.9, Requirements 9, 20, 21).
 *
 * These tests cover the UI-observable slice of the chain versioning feature.
 * Backend-persistence and reconnect-only behaviors are covered in
 * backend/tests/unit/test_chain_projection.py and
 * backend/tests/integration/api/test_duplicate_context_guard_api.py.
 *
 * Cases:
 *  TS-V2-01  Version browse: a completed run with a git_tag shows the tag in the
 *            VersionTimeline chip row (if visible), and in the SandboxTab ref picker.
 *  TS-V2-04  Chain launch: RunEngineNotice renders for chain_context_unavailable event.
 *  TS-V2-05  Degraded run: the Badge shows "Degraded", not "Done".
 *  TS-V2-06  Degraded finalization: RunEngineNotice renders for run_finalization_failed.
 *
 * TS-V2-02/03/07/08 were deleted from this file; see the note at the end of the
 * describe for the owner that covers each.
 *
 * Fixture contract: `mocked` project — no real backend needed.
 */
import { test, expect } from "../fixtures/test";
import { makeRun } from "../fixtures/mockApi";
import { AGENTS, runAgent } from "../fixtures/scenarios";
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

    await expect(page.getByText("User story backlog v1").first()).toBeVisible();
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

    await expect(page.getByText("Degraded run output").first()).toBeVisible();
    // Title kept (renames need a migration plan). History now labels a degraded
    // run "Failed" (RevisionFamilyView THE RULE: an agent failed → the run failed,
    // no softer word) — and still never "Done" or "Queued".
    await expect(page.getByText("Failed", { exact: true })).toBeVisible();
    expect(await page.getByText("Degraded", { exact: true }).count()).toBe(0);
    expect(await page.getByText("Done", { exact: true }).count()).toBe(0);
  });

  // TS-V2-04 / TS-V2-06 — the engine-fact notices, end to end over the mocked SSE
  // stream: the frame reaches the useWorkflow reducer and RunChatLane mounts the
  // RunEngineNotice (role=status) in the live run's transcript. The copy for every
  // reason code is owned by src/components/__tests__/RunEngineNotice.test.tsx.
  test("TS-V2-04 chain_context_unavailable on the stream renders the chain-unavailable notice", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Chain from the refunds backlog" });
    mockSse.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    mockSse.emit("chain_context_unavailable", { run_id: mockSse.currentRunId, reason: "source_non_chainable" });

    const notice = page.getByTestId("run-engine-notice-chain_unavailable");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute("role", "status");
    await expect(notice).toContainText(/source run cannot be used as context/i);
    // The bounded reason code is support detail, never the user-facing headline.
    await expect(notice.getByText("source_non_chainable")).toHaveCount(0);
  });

  test("TS-V2-06 run_finalization_failed before the terminal renders the finalization notice", async ({
    dashboard,
    mockSse,
    page,
  }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    // engine.py finalize: a degraded finalization queues run_finalization_failed
    // BEFORE the terminal frame.
    mockSse.emit("run_finalization_failed", { run_id: mockSse.currentRunId, reason: "db_write_failure" });

    const notice = page.getByTestId("run-engine-notice-finalization_failed");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveAttribute("role", "status");
    await expect(notice).toContainText(/run finalization encountered an issue/i);

    // The notice survives the terminal frame that follows it.
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n", status: "degraded" });
    await expect(dashboard.stopButton()).toHaveCount(0);
    await expect(notice).toBeVisible();
  });

  // Deleted from the mocked project (were empty test.fixme bodies):
  //   TS-V2-02 / TS-V2-03 restore gating — inapplicable: there is no Restore
  //     control any more (its cited owner "SandboxTab.restore.test.tsx" does not
  //     exist). The absence is pinned by src/components/preview/
  //     VersionSwitch.integration.test.tsx "VersionSwitch: no restore control".
  //   TS-V2-07 version browse by git tag — owned by src/components/preview/
  //     PreviewPanel.sandboxRef.test.tsx "Task U1 — version menu ref-view".
  //   TS-V2-08 non-chainable source shown as unavailable — owned by
  //     src/components/history/WorkflowHistory.test.tsx "WorkflowHistory —
  //     non-success chain sources" (payload_chainable=false / true cases).
});
