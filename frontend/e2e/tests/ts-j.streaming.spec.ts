/**
 * TS-J — Live streaming / planner / execution gate in the PreviewPanel
 * "Thinking" tab (AgentThinkingTab + its prototype variant PrototypePipelineView).
 *
 * The Thinking tab is the rich trace surface: per-card LIVE/DONE/ERROR badges,
 * the live "Reasoning (live)" stream with the ▌ cursor, the pipeline status
 * banner, the Deep Planner card + execution-gate badge, and the Spec-Kit
 * pipeline view for prototype runs.
 *
 * Scoping note: the LEFT AgentProgressPanel and the RIGHT Thinking tab both
 * receive the same pipelineState, so the plain "DONE"/"ERROR" badge text is
 * present in BOTH panels (count 2 when one agent is in that state). Strings
 * that are UNIQUE to the Thinking tab — "LIVE", "Pipeline Running",
 * "Pipeline Complete", "Completed with errors", "Pipeline Trace",
 * "Reasoning (live)", "Deep Planner", "Spec Kit Pipeline", "▌",
 * "✓ PROCEED", "⚡ CLARIFY" — are asserted directly (verified absent from
 * AgentProgressPanel / WaveTreePanel).
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-J — live streaming / planner / execution gate (Thinking tab)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow",
    });
  });

  test("TS-J-01 empty trace before any agent event", async ({ dashboard }) => {
    // On the Thinking tab BEFORE pipeline_start: no agents, no plannerStatus →
    // AgentThinkingTab renders EmptyState (hasAnyData is false).
    await dashboard.thinkingTab().click();
    await expect(dashboard.page.getByText("Pipeline Trace")).toBeVisible();
    await expect(
      dashboard.page.getByText(
        "Start a pipeline to see real-time agent reasoning, tool calls, and context flow.",
      ),
    ).toBeVisible();
  });

  test("TS-J-02 Reasoning (live) stream with blinking cursor", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();

    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.agentStart(agents[0].id);
    mockWs.agentThinking(agents[0].id, "analyzing the brief in detail ...");

    // Live reasoning block only renders for a running agent with thinkingText.
    await expect(dashboard.page.getByText("Reasoning (live)")).toBeVisible();
    // The blinking cursor is a literal ▌ inside the live-reasoning <p>.
    await expect(dashboard.page.getByText("▌")).toBeVisible();
    // The thinking text (last 300 chars) is shown alongside the cursor. The
    // cursor-bearing node is unique to the Thinking-tab live-reasoning <p> (the
    // left AgentProgressPanel also echoes the thinking text, but without ▌).
    await expect(
      dashboard.page.getByText("analyzing the brief in detail ... ▌"),
    ).toBeVisible();
  });

  test("TS-J-03 per-card LIVE / DONE / ERROR badges in the trace", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();
    mockWs.start(agents, { pipelineType: "user_stories" });

    // Running → LIVE (this badge is unique to the Thinking tab; the left panel
    // shows "RUNNING" instead).
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.page.getByText("LIVE", { exact: true })).toBeVisible();

    // Completed → DONE. "DONE" appears in BOTH panels (left + Thinking), so a
    // single completed agent yields exactly 2 — proving the Thinking-tab card
    // rendered it too.
    mockWs.agentComplete(agents[0].id);
    await expect(dashboard.page.getByText("DONE", { exact: true })).toHaveCount(2);

    // Errored → ERROR (likewise present in both panels → count 2).
    mockWs.agentStart(agents[1].id);
    mockWs.agentError(agents[1].id, "The model rejected this request.");
    await expect(dashboard.page.getByText("ERROR", { exact: true })).toHaveCount(2);
  });

  test("TS-J-04 pipeline status banner: Running → Complete", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();
    mockWs.start(agents, { pipelineType: "user_stories" });

    // While running → "Pipeline Running".
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.page.getByText("Pipeline Running")).toBeVisible();

    // All complete + pipeline_complete → "Pipeline Complete".
    for (const a of agents) {
      mockWs.agentStart(a.id);
      mockWs.agentComplete(a.id);
    }
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    // exact:true → the banner "Pipeline Complete", not the lowercase footer
    // "Pipeline complete" line that AgentThinkingTab also renders when done.
    await expect(dashboard.page.getByText("Pipeline Complete", { exact: true })).toBeVisible();
  });

  test("TS-J-04 pipeline status banner: Completed with errors", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();
    mockWs.start(agents, { pipelineType: "user_stories" });

    // One agent errors, the rest complete, then pipeline_complete (not running)
    // → banner reads "Completed with errors".
    mockWs.agentStart(agents[0].id);
    mockWs.agentError(agents[0].id, "The model rejected this request.");
    for (const a of agents.slice(1)) {
      mockWs.agentStart(a.id);
      mockWs.agentComplete(a.id);
    }
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "" });
    await expect(dashboard.page.getByText("Completed with errors")).toBeVisible();
  });

  test("TS-J-05 execution gate badge: PROCEED", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();
    // pipeline_start first so the run is "active" — keeps PreviewPanel mounted
    // (otherwise the running-planner PlanningOverlay would replace it).
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.plannerStart();
    mockWs.plannerComplete("Build a refunds backlog", "PROCEED");

    // Deep Planner card + the PROCEED gate badge in the header banner.
    await expect(dashboard.page.getByText("Deep Planner")).toBeVisible();
    await expect(dashboard.page.getByText("✓ PROCEED")).toBeVisible();
  });

  test("TS-J-05 execution gate badge: CLARIFY", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    await dashboard.thinkingTab().click();
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.plannerStart();
    mockWs.plannerComplete("Build a refunds backlog", "CLARIFY_REQUIRED");

    await expect(dashboard.page.getByText("Deep Planner")).toBeVisible();
    await expect(dashboard.page.getByText("⚡ CLARIFY")).toBeVisible();
  });

  test("TS-J-06 Spec-Kit live view (prototype pipeline)", async ({ dashboard, mockWs }) => {
    // AGENTS.od_prototype carries the prototype-specify/-plan/-build/-validate
    // ids, which makes AgentThinkingTab swap to the PrototypePipelineView.
    const agents = AGENTS.od_prototype;
    await dashboard.thinkingTab().click();
    mockWs.start(agents, { pipelineType: "od_prototype" });
    mockWs.agentStart(agents[0].id); // prototype-specify running

    await expect(dashboard.page.getByText("Spec Kit Pipeline")).toBeVisible();
    await expect(dashboard.page.getByText("Spec Writer — Specification")).toBeVisible();
  });
});
