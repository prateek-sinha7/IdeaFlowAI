/**
 * TS-R — Cancel (Stop a live run). Proves the Stop → cancel_pipeline outbound
 * frame and the pipeline_cancelled inbound teardown: in-flight cards clear to
 * idle, already-DONE agents are preserved, the header flips to "Pipeline
 * stopped", and a live cancel shows NEUTRAL preview chrome (no failed/degraded
 * affordance — a deliberate Stop sets no failure flag; see useWorkflow's
 * pipeline_cancelled handler + PreviewPanel's server-keyed failure signal).
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent } from "../fixtures/scenarios";

test.describe("TS-R — cancel", () => {
  test.beforeEach(async ({ dashboard, mockWs }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });
    mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    // An agent is in flight when the user hits Stop.
    mockWs.agentStart(AGENTS.user_stories[0].id);
  });

  test("TS-R-01 Stop sends a cancel_pipeline frame", async ({ dashboard, mockWs }) => {
    await expect(dashboard.runningBadge().first()).toBeVisible();
    await expect(dashboard.stopButton()).toBeVisible();

    await dashboard.stopButton().click();
    // The only outbound effect of Stop is the cancel_pipeline frame; reset is
    // driven by the inbound pipeline_cancelled event, not the click.
    await mockWs.waitForClientFrame("cancel_pipeline");
  });

  test("TS-R-02 cancelled clears in-flight cards but preserves DONE agents", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    // Finish one agent (stays DONE), leave another in flight (clears to idle).
    await runAgent(mockWs, agents[0].id);
    await expect(dashboard.doneBadge()).toHaveCount(1);
    mockWs.agentStart(agents[1].id);
    await expect(dashboard.runningBadge()).toHaveCount(1);

    await dashboard.stopButton().click();
    await mockWs.waitForClientFrame("cancel_pipeline");

    mockWs.cancelled({ duration: 8 });

    // Header flips to the stopped state.
    await expect(dashboard.page.getByText("Pipeline stopped")).toBeVisible();
    // In-flight agent reset to idle → no RUNNING badges remain.
    await expect(dashboard.runningBadge()).toHaveCount(0);
    // The already-completed agent is untouched.
    await expect(dashboard.doneBadge()).toHaveCount(1);
  });

  test("TS-R-03 a live cancel shows neutral preview chrome, not failure chrome", async ({ dashboard, mockWs }) => {
    await dashboard.stopButton().click();
    await mockWs.waitForClientFrame("cancel_pipeline");

    mockWs.cancelled({ duration: 8 });
    await expect(dashboard.page.getByText("Pipeline stopped")).toBeVisible();

    // Live cancel sets NO failed/degraded flag (agents reset to idle), so the
    // preview keeps its neutral empty state (no deliverable was produced) — the
    // degraded/failed affordance must NOT appear (that copy is reserved for a
    // history-reopen of a failed/cancelled run).
    await expect(dashboard.previewEmpty()).toBeVisible();
    await expect(dashboard.degradedHeading()).toHaveCount(0);
    await expect(dashboard.cancelledHeading()).toHaveCount(0);
  });

  test("TS-R-04 cancel-during-revision writes no poisoned parent", async () => {
    // Backend-gated persistence concern (Phase 14): a cancel that lands during a
    // revision run must not write a poisoned/partial parent record. There is no
    // FE-observable surface for this in mocked mode (it is a DB/state-machine
    // invariant), so it cannot be exercised here.
    test.fixme(true, "revision-cancel persistence is backend-gated (Phase 14)");
  });
});
