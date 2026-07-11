/**
 * TS-K — Wave / Subagent tree (WaveTreePanel): empty state, wave groups,
 * worker leaves. Reference spec: proves wave event mapping.
 *
 * Phase 39 plan 02 re-anchor: the WaveTreePanel is no longer a flat panel on the
 * execution surface — it lives inside the Steps tab's L2 agent detail, under the
 * construction (Build) agent's "Construction · waves & subagents" section. This
 * spec now drives the od_prototype pipeline (which has a real Build Agent), opens
 * the Steps tab, drills into the Build Agent, and asserts the wave tree there.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-K — wave / subagent tree", () => {
  // od_prototype seeds a Build Agent (id prototype-build → the construction host).
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    // Any launchable row gets us onto the run screen; the pipeline agents (incl.
    // the Build Agent) are driven by ws.start below (the mocked WS is the source
    // of truth for the rendered pipeline, independent of the launched row).
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Build an Apple-style reference prototype" });
    dashboard.ws.start(AGENTS.od_prototype, { pipelineType: "od_prototype", runId: "run-e2e-1" });
    // Make the Build Agent navigable (a running row → opens L2), then drill in.
    dashboard.ws.agentStart("prototype-build");
    await dashboard.thinkingTab().click();
    await dashboard.page.getByRole("button", { name: /Build Agent/i }).first().click();
  });

  test("TS-K-02 empty wave tree inside the Build Agent detail before any wave", async ({ dashboard }) => {
    // The construction section renders for the Build Agent even with no waves yet.
    await expect(dashboard.page.getByTestId("construction-block")).toBeVisible();
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

  test("TS-K-01 wave heading is visible once drilled into the Build Agent", async ({ dashboard, mockWs }) => {
    mockWs.waveStarted(0, "fanout", ["t1"]);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 0);

    const heading = dashboard.waveHeading();
    await expect(heading).toBeVisible();
    const box = await heading.boundingBox();
    expect(box).not.toBeNull();
  });
});
