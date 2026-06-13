/**
 * TS-L — TokenUsageSummary: the completion footer's token/cost card shown in
 * AgentProgressPanel once the run is complete (all agents done +
 * pipeline_complete). Asserts the exact number/cost formatting from
 * TokenUsageSummary.tsx (formatTokens / formatCost) and the per-agent
 * AgentTokenPill (`{X}K tokens`).
 *
 * formatTokens: ≥1e6 → `{n/1e6}M` (1dp), ≥1000 → `{n/1000}K` (1dp), else raw.
 * formatCost:   0 → `—` (em dash), <0.001 → `<$0.001`, else `~$X.XXX` (3dp).
 * The summary renders only when (totalTokens || totalInputTokens) is truthy
 * AND the panel isComplete. The cost label model name comes from model_id
 * (mockWs.complete sends the Haiku 4.5 id → `Est. cost (Haiku 4.5)`).
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent } from "../fixtures/scenarios";

test.describe("TS-L — token usage summary", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({
      workflow: "Generate product requirements",
      idea: "Generate epics for a refunds workflow",
    });
  });

  /** Innermost flex row whose text starts with "Est. cost" — label + value. */
  const costRow = (dashboard: { page: import("@playwright/test").Page }) =>
    dashboard.page.locator("div").filter({ hasText: /^Est\. cost/ }).last();

  /** Start the canned user_stories run and run every agent to done. */
  async function runAllAgents(mockWs: import("../fixtures/mockWs").MockWs) {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);
    return agents;
  }

  test("TS-L-01 summary card: total, input/output breakdown, cost label + value", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      inputTokens: 5000,
      outputTokens: 3000,
      totalTokens: 8000,
      estimatedCostUsd: 0.042,
    });

    // Header label + total (8000 → "8.0K total")
    await expect(dashboard.page.getByText("Token Usage", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("8.0K total", { exact: true })).toBeVisible();

    // Input / output breakdown (5000 → "5.0K input", 3000 → "3.0K output")
    await expect(dashboard.page.getByText("5.0K input", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("3.0K output", { exact: true })).toBeVisible();

    // Cost row: model short-name from model_id + cost value
    await expect(dashboard.page.getByText("Est. cost (Haiku 4.5)", { exact: true })).toBeVisible();
    await expect(costRow(dashboard)).toContainText("~$0.042");
  });

  test("TS-L-02 number format: 1.5M total", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 1_500_000,
    });
    await expect(dashboard.page.getByText("1.5M total", { exact: true })).toBeVisible();
  });

  test("TS-L-02 number format: raw 950 total", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 950,
    });
    await expect(dashboard.page.getByText("950 total", { exact: true })).toBeVisible();
  });

  test("TS-L-03 cost format: zero → em dash", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 8000, // keep card visible; only the cost is under test
      estimatedCostUsd: 0,
    });
    await expect(dashboard.page.getByText("Est. cost (Haiku 4.5)", { exact: true })).toBeVisible();
    await expect(costRow(dashboard)).toContainText("—");
  });

  test("TS-L-03 cost format: sub-cent → <$0.001", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 8000,
      estimatedCostUsd: 0.0005,
    });
    await expect(costRow(dashboard)).toContainText("<$0.001");
  });

  test("TS-L-03 cost format: 0.042 → ~$0.042", async ({ dashboard, mockWs }) => {
    await runAllAgents(mockWs);
    mockWs.complete({
      pipelineType: "user_stories",
      finalOutput: "# Product Backlog\n",
      totalTokens: 8000,
      estimatedCostUsd: 0.042,
    });
    await expect(costRow(dashboard)).toContainText("~$0.042");
  });

  test("TS-L-04 per-agent token pill: DONE card shows 3.1K tokens", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    // Complete the first agent with an explicit per-agent total → AgentTokenPill.
    mockWs.agentStart(agents[0].id);
    mockWs.agentComplete(agents[0].id, { totalTokens: 3100 });

    await expect(dashboard.doneBadge().first()).toBeVisible();
    await expect(dashboard.page.getByText("3.1K tokens", { exact: true })).toBeVisible();
  });
});
