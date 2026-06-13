/**
 * TS-I — Live agent panels (AgentProgressPanel): per-agent states, header,
 * Stop. Reference spec: proves the mock-WS pipeline event → UI mapping.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent } from "../fixtures/scenarios";

test.describe("TS-I — live agent panels", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });
  });

  test("TS-I-01/02/03 RUNNING → DONE, and ERROR badges", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    await expect(dashboard.agentCardByName("Domain Discovery Agent").first()).toBeVisible();

    mockWs.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    mockWs.agentComplete(agents[0].id);
    await expect(dashboard.doneBadge().first()).toBeVisible();

    mockWs.agentStart(agents[1].id);
    mockWs.agentError(agents[1].id, "The model rejected this request.");
    await expect(dashboard.errorBadge().first()).toBeVisible();
    await expect(dashboard.page.getByText("The model rejected this request.").first()).toBeVisible();
  });

  test("TS-I-05 header reflects progress then completion", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.agentStart(agents[0].id);
    mockWs.agentComplete(agents[0].id);
    // running header: "{completed} / {total} agents"
    await expect(dashboard.page.getByText(/\d+ \/ \d+ agents/)).toBeVisible();

    for (const a of agents.slice(1)) await runAgent(mockWs, a.id);
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    await expect(dashboard.page.getByText(/Done in \d+(\.\d)?s/)).toBeVisible();
  });

  test("TS-I-07 + TS-R Stop sends cancel and clears cards", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    await expect(dashboard.stopButton()).toBeVisible();
    await dashboard.stopButton().click();
    // The app sends a cancel_pipeline frame.
    await mockWs.waitForClientFrame("cancel_pipeline");

    // Server acks the cancel → in-flight cards clear, header flips.
    mockWs.cancelled({ duration: 8 });
    await expect(dashboard.page.getByText("Pipeline stopped")).toBeVisible();
    await expect(dashboard.runningBadge()).toHaveCount(0);
  });
});

test.describe("TS-I — extended", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });
  });

  test("TS-I-04 expand a DONE card reveals its output in a <pre>", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });

    // hasOutput requires the done agent to carry output — agent_complete itself
    // sends no text, so push a chunk first (the live chunk is NOT rendered until
    // the card is done + expanded). Use a distinctive marker to assert on.
    const marker = "Refunds discovery findings: 3 epics, 7 stories.";
    mockWs.agentStart(agents[0].id);
    mockWs.agentChunk(agents[0].id, marker);
    mockWs.agentComplete(agents[0].id);

    // The done card becomes a clickable disclosure (role=button + aria-expanded)
    // ONLY when it has output. Scope to the card that owns the marker.
    const card = dashboard.page.getByRole("button", { expanded: false }).filter({ hasText: "Domain Discovery Agent" });
    await expect(card).toBeVisible();
    // Collapsed: the output <pre> is not rendered yet.
    await expect(dashboard.page.getByText(marker)).toHaveCount(0);

    await card.click();
    await expect(dashboard.page.getByRole("button", { expanded: true })).toBeVisible();

    // Expanded: the agent's output shows inside a <pre>.
    const pre = dashboard.page.locator("pre").filter({ hasText: marker });
    await expect(pre).toBeVisible();
    await expect(pre).toContainText(marker);
  });

  test("TS-I-06 progress bar present + header count grows as agents complete", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });

    // The progress track is the h-0.5 bar; its fill is the navy (#1B2A4A) child.
    // The track is visible; the fill starts at width:0 (so it is present in the
    // DOM but zero-width → not "visible" yet), and motion animates its width as
    // agents complete. Assert presence, then growth via the header count + the
    // inline width style once it is non-zero.
    const bar = dashboard.page.locator("div.h-0\\.5.bg-gray-100");
    await expect(bar).toBeVisible();
    const fill = bar.locator("div.bg-\\[\\#1B2A4A\\]");
    await expect(fill).toBeAttached();

    // Header reflects 0 completed initially.
    await expect(dashboard.page.getByText("0 / 3 agents")).toBeVisible();

    mockWs.agentStart(agents[0].id);
    mockWs.agentComplete(agents[0].id);
    await expect(dashboard.page.getByText("1 / 3 agents")).toBeVisible();

    mockWs.agentStart(agents[1].id);
    mockWs.agentComplete(agents[1].id);
    await expect(dashboard.page.getByText("2 / 3 agents")).toBeVisible();

    // Fill width tracks completion (motion animates to width:%). After 2/3 the
    // fill carries a non-zero inline width — assert it grew past 0% (the header
    // count above is the load-bearing growth signal; this confirms the bar fill
    // follows it). The animated end state is 66.66…%.
    await expect(fill).toHaveAttribute("style", /width:\s*[1-9]/);
  });

  test("TS-I-08 completion footer shows the New Pipeline button", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });

    // RotateCcw "New Pipeline" button pinned at the footer once complete.
    await expect(dashboard.newPipelineButton()).toBeVisible();
  });

  test("TS-I-09 seed-then-transition: 3 cards appear at once and transition in place", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });

    // All three cards exist immediately (idle), before any agent_start.
    for (const a of agents) await expect(dashboard.agentCardByName(a.name).first()).toBeVisible();
    await expect(dashboard.runningBadge()).toHaveCount(0);
    await expect(dashboard.doneBadge()).toHaveCount(0);

    // Start one — it becomes RUNNING; the other two stay put (still 3 cards).
    mockWs.agentStart(agents[0].id);
    await expect(dashboard.runningBadge()).toHaveCount(1);
    for (const a of agents) await expect(dashboard.agentCardByName(a.name).first()).toBeVisible();

    // Complete it — same card flips to DONE in place; no card disappeared.
    mockWs.agentComplete(agents[0].id);
    await expect(dashboard.doneBadge()).toHaveCount(1);
    await expect(dashboard.runningBadge()).toHaveCount(0);
    for (const a of agents) await expect(dashboard.agentCardByName(a.name).first()).toBeVisible();
  });

  test("TS-I-10 a completed agent shows a wall-clock duration", async ({ dashboard, mockWs }) => {
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    mockWs.agentStart(agents[0].id);
    mockWs.agentComplete(agents[0].id);

    await expect(dashboard.doneBadge().first()).toBeVisible();
    // Duration is wall-clock — assert the FORMAT (e.g. "0s"/"1s"), never a value.
    await expect(dashboard.page.getByText(/^\d+(\.\d)?s$/).first()).toBeVisible();
  });
});
