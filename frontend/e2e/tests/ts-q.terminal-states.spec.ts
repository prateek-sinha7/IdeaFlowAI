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

  test("TS-Q-02 model error → pipeline_failed → degraded affordance (ISS-016/017)", async ({ dashboard, mockWs }) => {
    await playFailedRun(mockWs, "user_stories");

    await expect(dashboard.errorBadge().first()).toBeVisible();
    await expect(dashboard.degradedHeading()).toBeVisible();
    await expect(dashboard.page.getByText("No deliverable was produced. The run ended in a failed or degraded state.")).toBeVisible();
    await expect(dashboard.failedAgentsLabel()).toBeVisible();
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
