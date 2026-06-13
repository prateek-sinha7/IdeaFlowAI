/**
 * TS-H — run_pipeline outbound contract + execution transition.
 *
 * Proves the trigger half of the workflow loop: what the app SENDS when the
 * user clicks Run, and that the execution surface swaps in optimistically
 * (before any server event). The inbound→UI mapping is covered by TS-I/TS-Q;
 * here we pin the OUTBOUND frame shape (byte-identical legacy payload) and the
 * synchronous view transition in DashboardLayout.handleRunPipeline.
 *
 * Frame fields are TOP-LEVEL on the parsed outbound object: the app sends
 * JSON.stringify({ type, pipeline_type, message, agent_ids, ... }) and MockWs
 * parses it raw — so assert f.pipeline_type / f.agent_ids / f.message directly.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-H — trigger contract", () => {
  test("TS-H-01 run_pipeline payload (minimal) is the byte-identical legacy shape", async ({ dashboard, mockWs }) => {
    // runWith selects "Generate product requirements" (→ user_stories), types the
    // brief, clicks Run, and waits for the outbound run_pipeline frame. No
    // skills / hooks / model-overrides / review-gates are touched anywhere, so
    // the payload must carry ONLY the legacy keys.
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Build a refunds backlog",
    });

    const f = await mockWs.waitForClientFrame("run_pipeline");

    expect(f.type).toBe("run_pipeline");
    expect(f.pipeline_type).toBe("user_stories");
    // IdeaInputPage sends ideaInput.trim() — assert the exact trimmed brief.
    expect(f.message).toBe("Build a refunds backlog");
    // Default user_stories line-up seeds agents from the library → non-empty.
    expect(Array.isArray(f.agent_ids)).toBe(true);
    expect((f.agent_ids as string[]).length).toBeGreaterThan(0);

    // The legacy contract: with nothing opted into, NONE of the additive
    // capability keys are present on the wire (INV-3 — byte-identical payload).
    expect(f).not.toHaveProperty("attached_skills");
    expect(f).not.toHaveProperty("attached_hooks");
    expect(f).not.toHaveProperty("model_overrides");
    expect(f).not.toHaveProperty("gate_agent_ids");

    // The frame must carry EXACTLY the four legacy keys and nothing else.
    expect(Object.keys(f).sort()).toEqual(["agent_ids", "message", "pipeline_type", "type"]);
  });

  test("TS-H-02 clicking Run swaps to the execution view immediately (pre-event)", async ({ dashboard, mockWs }) => {
    await dashboard.goto();

    // On the input page the brief textarea is present.
    await dashboard.selectWorkflow("Generate product requirements");
    await dashboard.fillIdea("Build a refunds backlog");
    await expect(dashboard.ideaTextarea()).toBeVisible();

    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    // The transition is OPTIMISTIC: handleRunPipeline sets mainView="execution"
    // synchronously, before onStartPipeline sends the frame and long before any
    // server event. So immediately after the run_pipeline frame lands, the
    // IdeaInputPage textarea is gone and the agent-panel header is mounted —
    // with NO pipeline_start/agent_* sent yet.
    await mockWs.waitForClientFrame("run_pipeline");
    await expect(dashboard.page.locator("textarea")).toHaveCount(0);
    // The left agent panel renders its header even before pipeline_start
    // (isRunning is already true → "0 / 0 agents"). This is the pre-event marker.
    await expect(dashboard.page.getByText(/\d+ \/ \d+ agents/)).toBeVisible();

    // Now drive the server: pipeline_start seeds the real cards into the same
    // mounted panel, confirming the execution surface is live.
    mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    await expect(dashboard.agentCardByName("Domain Discovery Agent").first()).toBeVisible();
    await expect(dashboard.page.locator("textarea")).toHaveCount(0);
  });

  test("TS-H-04 pipeline_start seeds exactly the sent cards; currentAgentIndex starts at 0", async ({ dashboard, mockWs }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Build a refunds backlog",
    });

    const agents = AGENTS.user_stories; // exactly 3
    expect(agents).toHaveLength(3);
    mockWs.start(agents, { pipelineType: "user_stories" });

    // Exactly those 3 agent names render as cards.
    for (const a of agents) {
      await expect(dashboard.agentCardByName(a.name).first()).toBeVisible();
    }

    // currentAgentIndex starts at 0 → the FIRST agent can transition to RUNNING.
    // (agent_start only flips a card it can find at its seeded index; the seed
    // sets currentAgentIndex:0, so the head-of-line agent driving RUNNING proves
    // the index contract.)
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();
  });

  // TS-H-05 — the wizard path (prototype/ppt) sends od_prototype / od_ppt with a
  // template_id. From home those workflows router.push to
  // /workflow/{prototype,ppt}/templates (they do NOT open IdeaInputPage), so the
  // payload only fires after the template/design-system wizard completes — which
  // is out of scope for this mocked, WS-only spec. Tracked under TS-V (live).
  // Standalone fixme so it skips ONLY this case (a bare test.fixme in the
  // describe body would skip the whole group).
  test("TS-H-05 wizard path (prototype/ppt) sends od_prototype/od_ppt + template_id", async () => {
    test.fixme(true, "wizard path covered by TS-V live");
  });
});
