/**
 * TS-K — Wave / Subagent tree (WaveTreePanel): empty state, wave groups,
 * worker leaves, fold-above-the-fold. Reference spec: proves wave event mapping.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-K — wave / subagent tree", () => {
  // Any running pipeline mounts the execution surface (and the wave panel);
  // user_stories seeds default agents so Run is enabled without the composer.
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Build a habit tracker" });
    mockWsStart(dashboard);
  });

  test("TS-K-02 empty state before any wave", async ({ dashboard }) => {
    await expect(dashboard.waveHeading()).toBeVisible();
    await expect(dashboard.waveEmpty()).toBeVisible();
  });

  test("TS-K-03/04/05 wave groups + worker leaves + status transitions", async ({ dashboard, mockWs }) => {
    mockWs.waveStarted(0, "fanout", ["t1", "t2", "t3"]);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 0);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 1);

    await expect(dashboard.waveGroup(0)).toBeVisible();
    await expect(dashboard.page.getByText("ui-proto-researcher").first()).toBeVisible();
    // Two parallel workers of the same agent render as two distinct leaves.
    await expect(dashboard.page.getByText("ui-proto-researcher")).toHaveCount(2);

    mockWs.subagentResult(0, "fanout", "ui-proto-researcher", 0);
    mockWs.subagentResult(0, "fanout", "ui-proto-researcher", 1);
    mockWs.waveCompleted(0, "fanout");
    await expect(dashboard.waveEmpty()).toHaveCount(0);
  });

  test("TS-K-01 wave heading sits above the fold at 1440×950", async ({ dashboard, mockWs }) => {
    await dashboard.page.setViewportSize({ width: 1440, height: 950 });
    mockWs.waveStarted(0, "fanout", ["t1"]);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 0);

    const heading = dashboard.waveHeading();
    await expect(heading).toBeVisible();
    const box = await heading.boundingBox();
    expect(box).not.toBeNull();
    // Heading bottom must be within the 950px viewport (the ISS-019 fold fix).
    expect((box!.y + box!.height)).toBeLessThanOrEqual(950);
  });
});

// Helper: start a pipeline so the execution surface (and wave panel) mounts.
function mockWsStart(dashboard: import("../fixtures/dashboard").DashboardPage) {
  dashboard.ws.start(AGENTS.user_stories, { pipelineType: "user_stories" });
}
