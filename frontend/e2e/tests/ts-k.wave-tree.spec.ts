/**
 * TS-K — Wave / Subagent tree: the wave fan-out of a step, drawn inside the
 * Steps tab's L2 detail for that step.
 *
 * Re-anchored to the current model: a wave fan-out is the "Waves & tasks" block
 * (AgentDetailPanel WaveWorkersBlock), fed by the step's STAMPED worker events —
 * agent_start / agent_complete carrying the parent's agent_id plus `task_id`
 * (useWorkflow folds them into `agents[].waveWorkers`) — grouped per wave from the
 * wave lifecycle (wave_started / wave_completed). The older "Construction · waves
 * & subagents" block now draws ONLY task_loop progress and is withdrawn when it has
 * nothing to draw (AgentThinkingTab hasTaskLoopProgress), so a step with no fan-out
 * yet shows neither panel (no empty duplicate).
 *
 * The prototype pipeline seeds a Build Agent (prototype-build) — the wave host.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

const BUILD = "prototype-build";

test.describe("TS-K — wave / subagent tree", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    // Any launchable row gets us onto the run screen; the pipeline agents (incl.
    // the Build Agent) are driven by sse.start below (the mocked stream is the
    // source of truth for the rendered pipeline, independent of the launched row).
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Build an Apple-style reference prototype" });
    dashboard.sse.start(AGENTS.prototype, { pipelineType: "prototype", runId: "run-e2e-1" });
    // Make the Build Agent navigable (a running row → opens L2), then drill in.
    dashboard.sse.agentStart(BUILD);
    await dashboard.thinkingTab().click();
    await dashboard.page.getByRole("button", { name: /Build Agent/i }).first().click();
  });

  // Title kept (renames need a migration plan); re-anchored: the "empty
  // construction block" is now the ABSENCE of any empty fan-out panel.
  test("TS-K-02 empty construction block inside the Build Agent detail before any wave", async ({ dashboard }) => {
    // Drilled in (the L2 detail is up) …
    await expect(dashboard.page.getByRole("button", { name: "Steps / Build Agent" })).toBeVisible();
    // … but with nothing fanned out yet there is nothing to draw: no empty panel.
    await expect(dashboard.waveBlock()).toHaveCount(0);
    await expect(dashboard.page.getByTestId("construction-block")).toHaveCount(0);
  });

  test("TS-K-03/04/05 wave group + nested task rows + status transitions", async ({ dashboard, mockSse }) => {
    // One wave over three tasks, each run by its own worker.
    mockSse.waveStarted(0, BUILD, ["t1", "t2", "t3"]);
    ["t1", "t2", "t3"].forEach((t, i) => mockSse.waveWorkerStart(BUILD, t, 0, i));

    // The wave section (0-based index on the wire) holds the three worker rows.
    const wave = dashboard.waveGroup(0);
    await expect(wave).toBeVisible();
    await expect(wave.getByTestId("wave-worker-row")).toHaveCount(3);
    await expect(wave.getByTestId("wave-section-progress")).toHaveText("0 / 3 done");
    await expect(dashboard.waveBlock().getByTestId("wave-workers-progress")).toHaveText("0 / 1 wave");

    ["t1", "t2", "t3"].forEach((t, i) => mockSse.waveWorkerComplete(BUILD, t, 0, i));
    mockSse.waveCompleted(0, BUILD);
    // Every worker settled and the wave reads completed.
    await expect(wave.getByTestId("wave-section-progress")).toHaveText("3 / 3 done");
    await expect(wave.getByText("completed", { exact: true })).toBeVisible();
    await expect(dashboard.waveBlock().getByTestId("wave-workers-progress")).toHaveText("1 / 1 wave");
  });

  test("TS-K-01 wave heading is visible once drilled into the Build Agent", async ({ dashboard, mockSse }) => {
    mockSse.waveStarted(0, BUILD, ["t1"]);
    mockSse.waveWorkerStart(BUILD, "t1", 0, 0);

    const heading = dashboard.waveHeading();
    await expect(heading).toBeVisible();
    const box = await heading.boundingBox();
    expect(box).not.toBeNull();
  });
});
