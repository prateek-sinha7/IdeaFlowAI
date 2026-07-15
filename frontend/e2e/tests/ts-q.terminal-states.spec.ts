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

  test("TS-Q-01 success renders the deliverable, no failure chrome", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);
    mockWs.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

    await expect(dashboard.page.getByText("Product Backlog").first()).toBeVisible();
    await expect(dashboard.degradedHeading()).toHaveCount(0);
  });

  test("TS-Q-02 model error → pipeline_failed → new failed chrome (Audit-default + red lane card)", async ({ dashboard, mockWs }) => {
    await playFailedRun(mockWs, "user_stories");

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

  test("TS-Q-05 clean empty completion shows neutral state, NOT the affordance", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);
    // Completes with no content and NO failure signal.
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "" });

    await expect(dashboard.previewEmpty()).toBeVisible();
    await expect(dashboard.degradedHeading()).toHaveCount(0);
  });
});
