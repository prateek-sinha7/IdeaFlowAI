/**
 * TS-J — Live streaming / planner / execution gate in the Steps tab
 * (AgentThinkingTab's overview spine → agent detail drill-down).
 *
 * Phase 39 plan 02 re-anchor: the Steps tab is no longer a flat list of agent
 * cards with a PipelineHeader banner and per-card LIVE/DONE/ERROR text badges.
 * It now opens on a glanceable OVERVIEW SPINE (status line + navigable agent
 * rows) and drills into a 2-column AGENT DETAIL where the live "Reasoning (live)"
 * stream with the ▌ cursor lives. This spec is re-anchored to that layout:
 *  - the empty state ("Pipeline trace") is unchanged,
 *  - the status line reads "Running" / "Run complete" / "Run failed",
 *  - the running row carries a "Live" pill; drilling in shows "Reasoning (live)",
 *  - the Deep Planner card + its execution-gate badge (PROCEED / CLARIFY_REQUIRED).
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-J — live streaming / planner / execution gate (Steps tab)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow",
    });
  });

  test("TS-J-01 Steps opens on the overview spine after pipeline_start", async ({ dashboard, mockWs }) => {
    // The redesign mounts the run screen on server pipeline_start (not
    // optimistically) with the run's data already present, so the Steps tab opens
    // on the glanceable overview SPINE (status line + navigable agent rows) rather
    // than the defensive EmptyState (which the unit test covers). Assert the spine
    // mounted: the status line + the first agent's row are visible.
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();
    await expect(dashboard.page.getByText("Running", { exact: true })).toBeVisible();
    await expect(
      dashboard.page.getByRole("button", { name: new RegExp(agents[0].name, "i") }),
    ).toBeVisible();
  });

  test("TS-J-02 Reasoning (live) stream with blinking cursor (drilled into the running agent)", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.agentStart(agents[0].id);
    mockWs.agentThinking(agents[0].id, "analyzing the brief in detail ...");
    await dashboard.thinkingTab().click();

    // Drill into the running agent's L2 detail, where the live reasoning renders.
    await dashboard.page.getByRole("button", { name: new RegExp(agents[0].name, "i") }).first().click();
    await expect(dashboard.page.getByText("Reasoning (live)")).toBeVisible();
    // The blinking cursor is a literal ▌ inside the live-reasoning <p>.
    await expect(dashboard.page.getByText("analyzing the brief in detail ...", { exact: false })).toBeVisible();
  });

  test("TS-J-03 running row is highlighted in the overview spine", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();

    // Phase 42 REMOVED the spine's "Live" text pill (it now lives ONLY in the L2
    // agent-detail header). The running row is instead marked by its violet
    // highlight + a pulsing brand dot → exactly one running spine row.
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.stepsLiveBadge()).toHaveCount(1);
    await expect(dashboard.stepsLiveBadge()).toContainText(agents[0].name);

    // Completed → no running row highlighted; the row's node flips to the done
    // check and it stays navigable.
    mockWs.agentComplete(agents[0].id);
    await expect(dashboard.stepsLiveBadge()).toHaveCount(0);
    await expect(dashboard.page.getByRole("button", { name: new RegExp(agents[0].name, "i") })).toBeVisible();
  });

  test("TS-J-04 status line: Running → Run complete", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();

    // While running → "Running".
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.page.getByText("Running", { exact: true })).toBeVisible();

    // All complete + pipeline_complete → "Run complete".
    for (const a of agents) {
      mockWs.agentStart(a.id);
      mockWs.agentComplete(a.id);
    }
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    // Phase 42-02 (§B) auto-tabs a COMPLETED run to Preview, so the Steps overview
    // status line unmounts on completion. Re-open Steps to read its settled line.
    await dashboard.thinkingTab().click();
    await expect(dashboard.page.getByText("Run complete", { exact: true })).toBeVisible();
  });

  test("TS-J-04 status line: Run failed", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();

    // One agent errors, the rest complete, then pipeline_complete (not running)
    // → the status line reads "Run failed".
    mockWs.agentStart(agents[0].id);
    mockWs.agentError(agents[0].id, "The model rejected this request.");
    for (const a of agents.slice(1)) {
      mockWs.agentStart(a.id);
      mockWs.agentComplete(a.id);
    }
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "" });
    // Phase 42-03 (§D) auto-tabs a terminal-FAILED run to Audit, so the Steps
    // overview status line unmounts. Re-open Steps to read its settled line.
    await dashboard.thinkingTab().click();
    await expect(dashboard.page.getByText("Run failed", { exact: true })).toBeVisible();
  });

  test("TS-J-05 Deep-Planner card is NOT surfaced on the Steps overview (PROCEED)", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    // pipeline_start first so the run is "active" and the run screen mounts.
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();
    mockWs.plannerStart();
    mockWs.plannerComplete("Build a refunds backlog", "PROCEED");

    // Phase 39 plan 02 (human ruling): the Deep-Planner card was DROPPED from the
    // Steps overview to match the mock's clean spine. The run still renders — the
    // agent spine shows — but no planner card / gate badge is surfaced here.
    await expect(dashboard.page.getByRole("button", { name: new RegExp(agents[0].name, "i") })).toBeVisible();
    await expect(dashboard.page.getByText("Deep Planner")).toHaveCount(0);
  });

  test("TS-J-05 Deep-Planner card is NOT surfaced on the Steps overview (CLARIFY)", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await dashboard.thinkingTab().click();
    mockWs.plannerStart();
    mockWs.plannerComplete("Build a refunds backlog", "CLARIFY_REQUIRED");

    await expect(dashboard.page.getByRole("button", { name: new RegExp(agents[0].name, "i") })).toBeVisible();
    await expect(dashboard.page.getByText("Deep Planner")).toHaveCount(0);
  });

  test("TS-J-06 generic overview renders the prototype pipeline (SC-001, no name gate)", async ({ dashboard, mockWs }) => {
    // AGENTS.od_prototype carries the prototype-specify/-plan/-build/-validate
    // ids; the bespoke PrototypePipelineView was retired (Phase 32 / SC-001), so
    // prototype runs now render through the SAME generic overview spine.
    const agents = AGENTS.od_prototype;
    mockWs.start(agents, { pipelineType: "od_prototype" });
    mockWs.agentStart(agents[0].id); // prototype-specify (Spec Writer) running
    await dashboard.thinkingTab().click();

    // The generic spine shows the Spec Writer row (navigable → opens its detail).
    await expect(dashboard.page.getByRole("button", { name: /Spec Writer/i }).first()).toBeVisible();
  });
});
