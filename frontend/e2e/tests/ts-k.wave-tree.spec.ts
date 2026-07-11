/**
 * TS-K — Wave / Subagent tree (WaveTreePanel): empty state, wave groups,
 * worker leaves. Reference spec: proves wave event mapping.
 *
 * Phase 39 plan 02 re-anchor: the wave/subagent fan-out is no longer a separate
 * panel — it is ONE integrated "Construction · waves & subagents" block inside the
 * Steps tab's L2 Build-Agent detail, with the build TASKS NESTED under their waves
 * (the former standalone WaveTreePanel "Wave / Subagent tree" is retired here —
 * INV-12, single representation). This spec drives the od_prototype pipeline (which
 * has a real Build Agent), opens the Steps tab, drills into the Build Agent, and
 * asserts the nested wave→task block there.
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

  test("TS-K-02 empty construction block inside the Build Agent detail before any wave", async ({ dashboard }) => {
    // The construction section renders for the Build Agent even with no waves yet.
    await expect(dashboard.page.getByTestId("construction-block")).toBeVisible();
    await expect(dashboard.waveHeading()).toBeVisible();
    await expect(dashboard.waveEmpty()).toBeVisible();
  });

  test("TS-K-03/04/05 wave group + nested task rows + status transitions", async ({ dashboard, mockWs }) => {
    // A wave over three tasks; two concurrent subagents => the wave ran in parallel.
    mockWs.waveStarted(0, "fanout", ["t1", "t2", "t3"]);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 0);
    mockWs.subagentSpawned(0, "fanout", "ui-proto-researcher", 1);

    // The wave header (1-based) with its parallel kind, and the three tasks nested
    // under it as navigable rows (the mock's model — tasks under waves, not workers).
    await expect(dashboard.waveGroup(0)).toBeVisible();
    await expect(dashboard.page.getByText("parallel").first()).toBeVisible();
    await expect(dashboard.page.getByTestId("construction-task-row")).toHaveCount(3);

    mockWs.subagentResult(0, "fanout", "ui-proto-researcher", 0);
    mockWs.subagentResult(0, "fanout", "ui-proto-researcher", 1);
    mockWs.waveCompleted(0, "fanout");
    // Once a wave exists the empty affordance is gone and the wave reads completed.
    await expect(dashboard.waveEmpty()).toHaveCount(0);
    await expect(dashboard.page.getByText("completed").first()).toBeVisible();
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
