/**
 * TS-I — Live agent panels: per-agent states, run header status, Stop. Reference
 * spec: proves the mock-WS pipeline event → UI mapping.
 *
 * Phase 39 run-screen redesign: the old AgentProgressPanel (uppercase
 * RUNNING/DONE/ERROR text badges, in-lane expandable output <pre>, "Done in Ns"
 * footer, "New Pipeline" button, "Pipeline stopped") is retired/unmounted. The
 * equivalents now live in TWO places:
 *   • RUN-LEVEL status  → the lane run header token (dashboard.runningBadge/
 *     doneBadge/errorBadge, testid `lane-run-status` by tone).
 *   • PER-AGENT state   → the Steps tab (L1 StepsOverviewSpine spine with a
 *     per-agent "Live" badge + segmented progress; L2 AgentDetailPanel with the
 *     agent's output / "What went wrong" failure message).
 * These tests assert those new surfaces; the mock-WS event contract is unchanged.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent } from "../fixtures/scenarios";

test.describe("TS-I — live agent panels", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });
  });

  test("TS-I-01/02/03 per-agent RUNNING → DONE → ERROR states surface in Steps", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);

    await dashboard.openSteps();
    await expect(dashboard.stepsAgentRow("Domain Discovery Agent")).toBeVisible();

    // RUNNING — agent0 carries exactly one per-agent "Live" badge.
    await expect(dashboard.stepsLiveBadge()).toHaveCount(1);

    // DONE + next RUNNING — agent0 completes, agent1 starts: the single "Live"
    // badge moves to agent1 (agent0's row is no longer live).
    mockSse.agentComplete(agents[0].id);
    mockSse.agentStart(agents[1].id);
    await expect(dashboard.stepsLiveBadge()).toHaveCount(1);

    // ERROR — agent1 errors: the overview flips to "Run failed" and the agent's
    // L2 detail surfaces the sanitized failure message.
    mockSse.agentError(agents[1].id, "The model rejected this request.");
    await expect(dashboard.page.getByText("Run failed", { exact: true })).toBeVisible();

    await dashboard.openAgentDetail("Story Writer");
    await expect(dashboard.page.getByText("The model rejected this request.").first()).toBeVisible();
  });

  test("TS-I-05 run header reflects progress then completion", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id);
    // The lane run-header meta shows "{completed}/{total} agents" while building.
    await expect(dashboard.page.getByText(/\d+\/\d+ agents/)).toBeVisible();

    for (const a of agents.slice(1)) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    // Completion → the run header status settles into the "Done" token.
    await expect(dashboard.doneBadge()).toBeVisible();
  });

  test("TS-I-07 + TS-R Stop sends cancel and clears the running state", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    await expect(dashboard.stopButton()).toBeVisible();
    await dashboard.stopButton().click();
    // The app sends a cancel_pipeline frame.
    await mockSse.waitForClientFrame("cancel_pipeline");

    // Server acks the cancel → the terminal "Cancelled by you" ack shows and the
    // run-header running token clears (replaces the old "Pipeline stopped").
    mockSse.cancelled({ duration: 8 });
    await expect(dashboard.page.getByText("Cancelled by you")).toBeVisible();
    await expect(dashboard.runningBadge()).toHaveCount(0);
  });
});

test.describe("TS-I — extended", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });
  });

  test("TS-I-04 a completed agent's output is reachable in its Steps detail", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });

    // agent_chunk accumulates onto the agent's output; agent_complete settles it.
    // Use a distinctive marker to assert on.
    const marker = "Refunds discovery findings: 3 epics, 7 stories.";
    mockSse.agentStart(agents[0].id);
    mockSse.agentChunk(agents[0].id, marker);
    mockSse.agentComplete(agents[0].id);

    // Drill into the agent's L2 detail → the "Agent output" disclosure holds the
    // streamed output (Phase 39 relocated it from the in-lane card to Steps L2).
    await dashboard.openSteps();
    await dashboard.openAgentDetail("Domain Discovery Agent");

    const outputSection = dashboard.page.getByRole("button", { name: /Agent output/i });
    await expect(outputSection).toBeVisible();
    await outputSection.click();
    await expect(dashboard.page.getByText(marker)).toBeVisible();
  });

  test("TS-I-06 progress advances as agents complete", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });

    // The lane run-header count is the load-bearing progress signal; it grows as
    // agents complete (replaces the old motion-fill h-0.5 bar in the run lane).
    await expect(dashboard.page.getByText("0/3 agents")).toBeVisible();

    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id);
    await expect(dashboard.page.getByText("1/3 agents")).toBeVisible();

    mockSse.agentStart(agents[1].id);
    mockSse.agentComplete(agents[1].id);
    await expect(dashboard.page.getByText("2/3 agents")).toBeVisible();

    // The Steps overview renders a segmented progress track (one segment/agent).
    await dashboard.openSteps();
    await expect(dashboard.stepsProgressTrack()).toBeVisible();
  });

  test("TS-I-08 a completed run settles into the Done state with a follow-up composer", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });

    // The completion affordance is now the settled "Done" status + a follow-up
    // composer (the old footer "New Pipeline" button is retired with the panel).
    await expect(dashboard.doneBadge()).toBeVisible();
    await expect(dashboard.ideaTextarea()).toBeVisible();
  });

  test("TS-I-09 seed-then-transition: agents seed idle, then exactly one runs", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    await dashboard.openSteps();

    // All three agents seeded in the spine (idle), before any agent_start; none live.
    for (const a of agents) await expect(dashboard.stepsAgentRow(a.name)).toBeVisible();
    await expect(dashboard.stepsLiveBadge()).toHaveCount(0);

    // Start one — exactly one agent goes Live; all three rows remain.
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.stepsLiveBadge()).toHaveCount(1);
    for (const a of agents) await expect(dashboard.stepsAgentRow(a.name)).toBeVisible();

    // Complete it — no agent live; all three rows remain (transitioned in place).
    mockSse.agentComplete(agents[0].id);
    await expect(dashboard.stepsLiveBadge()).toHaveCount(0);
    for (const a of agents) await expect(dashboard.stepsAgentRow(a.name)).toBeVisible();
  });

  test("TS-I-10 a completed agent shows a wall-clock duration in its Steps row", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id, { duration: 2 });

    await dashboard.openSteps();
    const row = dashboard.stepsAgentRow("Domain Discovery Agent");
    await expect(row).toBeVisible();
    // The done row's meta carries a formatted wall-clock duration (e.g. "2s").
    await expect(row).toContainText(/\d+(\.\d)?s\b/);
  });
});
