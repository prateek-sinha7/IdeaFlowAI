/**
 * TS-L — TokenUsageSummary: the completion footer's token/cost card shown in
 * AgentProgressPanel once the run is complete (all agents done +
 * pipeline_complete). Asserts the exact number/cost formatting from
 * TokenUsageSummary.tsx (formatTokens / formatCost) and the per-agent
 * AgentTokenPill (`{X}K tokens`).
 *
 * formatTokens: ≥1e6 → `{n/1e6}M` (1dp), ≥1000 → `{n/1000}K` (1dp), else raw.
 * The summary renders only when (totalTokens || totalInputTokens) is truthy
 * AND the panel isComplete. (The "Est. cost" row and its formatCost were
 * removed in the KAN-83 restyle — see the TS-L-03 note below.)
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-L — token usage summary", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow",
    });
  });

  /** Start the canned user_stories run and run every agent to done. ISS-304: the
   *  summary totals ACCUMULATE from agent_complete (the same set the persisted
   *  token_usage is built from) — pipeline_complete's own totals are only a
   *  fallback — so each agent reports its share of the expected run totals. */
  async function runAllAgents(
    mockSse: import("../fixtures/mockSse").MockSse,
    usage: Array<{ inputTokens: number; outputTokens: number }>,
  ) {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    agents.forEach((a, i) => {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id, { ...usage[i], totalTokens: usage[i].inputTokens + usage[i].outputTokens });
    });
    return agents;
  }

  test("TS-L-01 summary card: total, input/output breakdown, cost label + value", async ({ dashboard, mockSse }) => {
    // 5000 input / 3000 output across the three agents.
    await runAllAgents(mockSse, [
      { inputTokens: 2000, outputTokens: 1000 },
      { inputTokens: 2000, outputTokens: 1000 },
      { inputTokens: 1000, outputTokens: 1000 },
    ]);
    mockSse.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      inputTokens: 5000,
      outputTokens: 3000,
      totalTokens: 8000,
      estimatedCostUsd: 0.042,
    });

    // Phase 39: the TokenUsageSummary moved out of the (retired) AgentProgressPanel
    // into the Steps tab footer (AgentThinkingTab). Open Steps to reach it.
    await expect(dashboard.previewTab()).toHaveAttribute("aria-selected", "true");
    await dashboard.openSteps();

    // Header label + total (8000 → "8.0K total")
    await expect(dashboard.page.getByText("Token Usage", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("8.0K total", { exact: true })).toBeVisible();

    // Input / output breakdown (5000 → "5.0K input", 3000 → "3.0K output")
    await expect(dashboard.page.getByText("5.0K input", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("3.0K output", { exact: true })).toBeVisible();

    // cost row removed in the KAN-83 token-summary restyle (total/input/output only)
  });

  test("TS-L-02 number format: 1.5M total", async ({ dashboard, mockSse }) => {
    await runAllAgents(mockSse, [
      { inputTokens: 500_000, outputTokens: 0 },
      { inputTokens: 500_000, outputTokens: 0 },
      { inputTokens: 0, outputTokens: 500_000 },
    ]);
    mockSse.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 1_500_000,
    });
    await expect(dashboard.previewTab()).toHaveAttribute("aria-selected", "true");
    await dashboard.openSteps();
    await expect(dashboard.page.getByText("1.5M total", { exact: true })).toBeVisible();
  });

  test("TS-L-02 number format: raw 950 total", async ({ dashboard, mockSse }) => {
    await runAllAgents(mockSse, [
      { inputTokens: 200, outputTokens: 150 },
      { inputTokens: 200, outputTokens: 100 },
      { inputTokens: 200, outputTokens: 100 },
    ]);
    mockSse.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 950,
    });
    await expect(dashboard.previewTab()).toHaveAttribute("aria-selected", "true");
    await dashboard.openSteps();
    await expect(dashboard.page.getByText("950 total", { exact: true })).toBeVisible();
  });

  // TS-L-03 (cost format: 0 → "—", sub-cent → "<$0.001", 0.042 → "~$0.042") was
  // DELETED: it asserted the summary's "Est. cost" row, which the KAN-83 restyle
  // removed — no mounted surface renders an estimated cost any more, so there is
  // nothing for a browser test to observe. The formatter itself survives only in
  // the unmounted ChatTokenWidget; its branches are owned by the unit test
  // src/components/chat/ChatTokenWidget.test.tsx ("formats cost …" cases, plus
  // "renders the pinned P26 totals and cost" for ~$0.042).

  // TS-L-04 was quarantined as a drill-in timing flake (~2/10 runs). It was not a
  // race: the L2 detail header renders its meta as ONE text node joined with " · "
  // (AgentDetailPanel.tsx:1371-1374, 1441) — "3.1K tok" when the agent has no
  // measured duration, "0s · 3.1K tok" when it does. Whether a duration is set
  // depends on the start→complete gap in the mocked stream, so the old exact
  // getByText("3.1K tok") missed whenever the duration prefix was present. The
  // locator now anchors the token count as the LAST meta bit, with or without a
  // preceding duration. (The title is unchanged: renames need a migration plan.)
  test("TS-L-04 per-agent token count: DONE agent detail shows 3.1K tok (flaky drill-in — see note above); Owner: frontend", async ({ dashboard, mockSse }) => {
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    // Complete the first agent with an explicit per-agent total.
    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id, { totalTokens: 3100 });

    // Phase 39 retired the AgentProgressPanel's per-agent "3.1K tokens" pill. The
    // per-agent token count now lives in the Steps L2 detail (AgentDetailPanel),
    // rendered as "{formatTokenCount} tok" (runStats.ts) once the agent isDone.
    // Drill in via the Steps spine and assert the new "3.1K tok" format.
    await dashboard.openSteps();
    await dashboard.openAgentDetail(agents[0].name); // "Domain Discovery Agent"
    // "3.1K tok" or "<duration> · 3.1K tok" — the whole meta node, token count last.
    await expect(dashboard.page.getByText(/^(?:\S+ · )?3\.1K tok$/)).toBeVisible();
  });
});
