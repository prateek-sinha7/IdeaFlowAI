/**
 * TS-Q — Terminal states & degraded affordance (server-signal-gated).
 * Reference spec: proves success / failed-degraded / clean-empty branching.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, playFailedRun, SAMPLE_BACKLOG } from "../fixtures/scenarios";

test.describe("TS-Q — terminal states", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-Q-01 success renders the deliverable, no failure chrome", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

    await expect(dashboard.page.getByText("Product Backlog").first()).toBeVisible();
    await expect(dashboard.degradedHeading()).toHaveCount(0);
  });

  test("TS-Q-02 model error → pipeline_failed → new failed chrome (Audit-default + red lane card)", async ({ dashboard, mockSse }) => {
    await playFailedRun(mockSse, "user_stories");

    // Run-level failed token (lane-run-status, failed tone).
    await expect(dashboard.errorBadge().first()).toBeVisible();

    // Phase 42-03 (§D): the amber DegradedRunAffordance is RETIRED on the run
    // screen — a terminal-failed run now DROPS the Preview tab and auto-defaults
    // to Audit. So the retired affordance heading must NOT appear here (it lives
    // only on the history/reopen RunDetailPage now).
    await expect(dashboard.degradedHeading()).toHaveCount(0);
    await expect(dashboard.page.getByRole("tab", { name: /Audit/i })).toHaveAttribute("aria-selected", "true");
    await expect(dashboard.previewTab()).toHaveCount(0);

    // The new failed chrome lives in the left lane: the RunChatLane terminal
    // failure card ("What went wrong" + "• Failed agents: …").
    await expect(dashboard.page.getByText("What went wrong")).toBeVisible();
    await expect(dashboard.failedAgentsLabel().first()).toBeVisible();
    // The neutral empty state must NOT show on a failed run.
    await expect(dashboard.previewEmpty()).toHaveCount(0);
  });

  test("TS-Q-05 clean empty completion shows neutral state, NOT the affordance", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    // Completes with no content and NO failure signal.
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "" });

    // Phase 42-02 (§B) auto-tabs a live/building run to Steps; a clean EMPTY
    // completion is terminal-idle (no deliverable, no failure) so it fires no
    // further auto-tab and leaves the panel on Steps. The neutral Preview
    // empty-state lives on the (still-present) Preview tab — open it (as TS-R-03
    // does for the analogous terminal-non-failed cancel).
    await dashboard.previewTab().click();
    await expect(dashboard.previewEmpty()).toBeVisible();
    await expect(dashboard.degradedHeading()).toHaveCount(0);
  });
});
