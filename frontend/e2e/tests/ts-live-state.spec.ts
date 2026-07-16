/**
 * TS-LIVE-STATE — bind the run-screen LIVE state to the VIEWED run (DEF-44-12-4,
 * subsumes DEF-44-12-2 + DEF-44-12-1's missing e2e).
 *
 * The run screen was built assuming "the run you launched == the run you're
 * viewing" — true only for the in-session launch→watch flow. Opening a DIFFERENT
 * run from the Home "Jump back in" recents fires page.tsx's
 * `handleSelectWorkflowRun` (onOpenRun → onSelectWorkflowRun → the execution
 * view), which set `contentSourceRunId` (Preview/Files) but never seeded the two
 * live consumers — the pipeline reducer (Steps trace) and the useRunChat
 * transcript. So a history-opened running run showed the empty "Start a pipeline…"
 * placeholder, and a Concierge reply (persisted durable-only, never queued → the
 * live SSE tail never carries it) never rendered.
 *
 * The fix seeds both from the durable `GET /api/runs/{id}/events` rows and
 * re-fetches after a send. These cases prove:
 *   (a) LIVE-open  → the still-running run's Steps trace renders (Half A).
 *   (b) TERMINAL-open → deliverable + prior chat + a Concierge reply that
 *       renders as its OWN turn (Half B = DEF-44-12-2; the POST closes the
 *       missing DEF-44-12-1 e2e).
 *   (c) launch→watch still renders the launched run's live trace (primary-flow
 *       regression guard).
 *
 * Fully offline — no backend, no Bedrock. Uses the durable (non-stream) events
 * stub, distinct from the mockSse `/events/stream` down-channel.
 */
import { test, expect, type StubRunEventRow } from "../fixtures/test";
import { makeRun } from "../fixtures/mockApi";
import { AGENTS, SAMPLE_BACKLOG } from "../fixtures/scenarios";

/** Build a durable run_events row; `payload_json` carries the frame's own
 *  event_id/seq (the page router + useRunChat dedup on them). */
function evRow(seq: number, type: string, payload: Record<string, unknown>): StubRunEventRow {
  const event_id = `srv-${seq}`;
  return { seq, event_id, type, payload_json: { ...payload, event_id, seq } };
}

test.describe("TS-LIVE-STATE — run-screen live state bound to the viewed run", () => {
  test("(a) LIVE-open: opening a still-running run from recents renders its Steps trace", async ({
    dashboard,
    mockApi,
    page,
  }) => {
    const agents = AGENTS.user_stories;
    // A non-terminal run in history/recents.
    mockApi.setRuns([
      makeRun({ id: "run-live", title: "Live refunds run", type: "user_stories", status: "running", input: "Generate refund epics" }),
    ]);
    // Its durable trace: pipeline_start (builds agents[]) + agent lifecycle.
    await dashboard.stubRunEvents("run-live", [
      evRow(1, "pipeline_start", {
        pipeline_run_id: "run-live",
        pipeline_type: "user_stories",
        agents: agents.map((a, i) => ({ id: a.id, name: a.name, role: a.role, icon: "🤖", order: i })),
      }),
      evRow(2, "agent_start", { agent_id: agents[0].id }),
      evRow(3, "agent_complete", { agent_id: agents[0].id, total_tokens: 100 }),
      evRow(4, "agent_start", { agent_id: agents[1].id }),
    ]);

    await dashboard.goto();
    await dashboard.openRecent("Live refunds run");

    // The Steps trace renders the seeded agent rows — NOT the empty placeholder.
    await dashboard.thinkingTab().click();
    await expect(dashboard.stepsAgentRow(agents[0].name)).toBeVisible();
    await expect(dashboard.stepsAgentRow(agents[1].name)).toBeVisible();
    await expect(page.getByText("Start a pipeline to see")).toHaveCount(0);
  });

  test("(b) TERMINAL-open: deliverable + prior chat + a Concierge reply renders its own turn", async ({
    dashboard,
    mockApi,
    mockSse,
    page,
  }) => {
    mockApi.setRuns([
      makeRun({
        id: "run-term",
        title: "Refunds backlog",
        type: "user_stories",
        status: "completed",
        input: "Generate refund epics",
        output: SAMPLE_BACKLOG,
      }),
    ]);
    // The durable rows: a prior user turn + a prior narrator reply. The array is
    // MUTATED below (a Concierge reply pushed post-open) so it lands only on the
    // re-fetch-after-send — modelling the durable-only Concierge persist.
    const events: StubRunEventRow[] = [
      evRow(1, "chat_message", { message_id: "prior-q", text: "prior question", run_id: "run-term" }),
      evRow(2, "chat_reply", { message_id: "prior-a", text: "prior answer", run_id: "run-term" }),
    ];
    await dashboard.stubRunEvents("run-term", events);

    await dashboard.goto();
    await dashboard.openRecent("Refunds backlog");

    // Deliverable renders in Preview.
    await dashboard.previewTab().click();
    await expect(page.getByText("Product Backlog").first()).toBeVisible();

    // Prior chat turns render in the transcript (Piece 3 seed).
    const transcript = page.getByTestId("chat-transcript");
    await expect(transcript).toContainText("prior question");
    await expect(transcript).toContainText("prior answer");

    // Send a Concierge turn. The reply is delivered DURABLY: push it onto the
    // stubbed rows (seq 3, distinct event_id "chat-reply:{id}") so the
    // re-fetch-after-send (after=2) pulls it.
    events.push(
      evRow(3, "chat_reply", {
        event_id: "chat-reply:concierge",
        message_id: "concierge-q",
        text: "Concierge: 3 of 5 stories complete.",
        run_id: "run-term",
      }),
    );

    const composer = page.getByLabel("Chat message input");
    await expect(composer).toBeVisible();
    await composer.fill("How many stories are done?");
    await page.getByTestId("chat-send").click();

    // The send POSTs to /api/runs/{id}/messages (DEF-44-12-1 e2e).
    const sent = await mockSse.waitForCommand(
      (c) => c.type === "user_message" && c.run_id === "run-term",
    );
    expect(String(sent.text)).toBe("How many stories are done?");

    // The question bubble is PRESERVED and the reply renders as its OWN turn
    // (DEF-44-12-2 de-collision).
    await expect(transcript).toContainText("How many stories are done?");
    await expect(transcript).toContainText("Concierge: 3 of 5 stories complete.");
  });

  test("(c) launch→watch regression: the launched run's live trace renders unchanged", async ({
    dashboard,
    mockSse,
  }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    // The launched run's live trace renders in Steps (guard: the seed logic never
    // fires on the launch path — handleSelectWorkflowRun is not called).
    await dashboard.thinkingTab().click();
    await expect(dashboard.stepsAgentRow(agents[0].name)).toBeVisible();

    for (const a of agents) {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id);
    }
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });
    await expect(dashboard.doneBadge()).toBeVisible();
  });
});
