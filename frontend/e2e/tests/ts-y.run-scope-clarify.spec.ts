/**
 * TS-Y — run-scoped clarify reset (BUG-005).
 *
 * The run screen's clarify LANE state is derived from `activePipelineRunId`:
 * `laneClarifyOpen = questionnaireQuestions.length > 0 && !!activePipelineRunId`
 * (DashboardLayout.tsx:1308) → `runLaneState === "clarify"` → the lane renders the
 * `lane-clarify-status` "Paused — N questions for you" card + a "Clarifying" run
 * status pill (RunChatLane.tsx:1058 / LaneRunHeader.tsx:100).
 *
 * `activePipelineRunId` (page.tsx) is a SINGLE page-level state fed by the SSE
 * provider's non-run-scoped fan-out — every frame from every attached run reaches
 * the one subscriber. The `pipeline_start` branch (page.tsx WR-03) reset
 * `activePipelineRunId`/`questionnaireData`/the seen-set UNCONDITIONALLY, so a
 * CONCURRENT foreign run entering its build phase nulled the VIEWED run's
 * `activePipelineRunId` → the lane fell through clarify→building ("Running 0/0
 * BUILDING", no clarify card) (BUG-005, live-QA under concurrent load).
 *
 * Fix: run-scope the reset with a synced `trackedRunIdRef` — a foreign
 * `pipeline_start` (pipeline_run_id ≠ the tracked/viewed run) no longer resets
 * this tab's clarify. The just-launched / same-run `pipeline_start` STILL resets
 * (launch→build flow unregressed).
 *
 * NB: the lane clarify card (`lane-clarify-status`) is the correct observable, NOT
 * the Steps `chat-clarify-actions` card — the latter is gated purely on
 * `questionnaireQuestions.length` (DashboardLayout.tsx:585-589 never clears it on a
 * null questionnaireData), so it does not track the `activePipelineRunId` collapse
 * this bug is about.
 *
 * Setup mirrors TS-M (clarify) + TS-live-state (concurrent frames): home → a
 * user_stories run → `questionnaireReady([...6])`.
 */
import { test, expect } from "../fixtures/test";

/** Six well-formed clarify questions (the live BUG-005 questionnaire had 6). */
const SIX_QUESTIONS = [
  { id: "q1", text: "Who is the primary audience?", options: ["Executives", "Developers"], answerType: "single" },
  { id: "q2", text: "What tone should it take?", options: ["Formal", "Casual"] },
  { id: "q3", text: "Which platform is the priority?", options: ["Web", "Mobile"] },
  { id: "q4", text: "What is the core success metric?", options: ["Retention", "Revenue"] },
  { id: "q5", text: "How opinionated should defaults be?", options: ["Prescriptive", "Flexible"] },
  { id: "q6", text: "What is the delivery timeline?", options: ["Weeks", "Months"] },
];

test.describe("TS-Y — run-scoped clarify reset (BUG-005)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-Y-01 a FOREIGN run's pipeline_start does NOT wipe the viewed run's clarify lane", async ({ dashboard, mockSse }) => {
    // Drive the VIEWED run (run-e2e-1) to its clarify gate — the lane shows the
    // clarify status card + a "Clarifying" pill.
    mockSse.questionnaireReady(SIX_QUESTIONS);
    const clarifyCard = dashboard.page.getByTestId("lane-clarify-status");
    const runStatus = dashboard.page.getByTestId("lane-run-status");
    await expect(clarifyCard).toBeVisible();
    await expect(runStatus).toHaveText(/Clarifying/);

    // Open the Steps panel (right column) — the lane (left column) stays mounted so
    // its clarify card remains observable. The Steps spine gives us an ORDERED
    // barrier: the foreign agents seed there once the foreign frame is applied.
    await dashboard.thinkingTab().click();

    // A CONCURRENT foreign run enters its build phase. Its pipeline_start carries a
    // DIFFERENT pipeline_run_id + its own agents; the non-run-scoped fan-out still
    // forwards it to the single reducer (so its agents seed — the frame IS
    // processed), but the run-scoped guard must NOT let it reset THIS tab's clarify.
    mockSse.emit("pipeline_start", {
      pipeline_run_id: "run-e2e-foreign",
      agents: [
        { id: "foreign-a", name: "Foreign Agent One", role: "worker", order: 0 },
        { id: "foreign-b", name: "Foreign Agent Two", role: "worker", order: 1 },
        { id: "foreign-c", name: "Foreign Agent Three", role: "worker", order: 2 },
      ],
    });

    // Ordered barrier: the foreign frame is applied ONCE its agents seed the spine.
    // Same-stream frames are delivered in order, so the reset block (page.tsx:462)
    // has already run for the foreign pipeline_start by the time this resolves.
    await expect(dashboard.stepsAgentRow("Foreign Agent One")).toBeVisible();

    // Fail-before: the unconditional reset nulled activePipelineRunId → the lane
    // fell through clarify→building (no clarify card, "Building" pill). Pass-after:
    // the clarify lane SURVIVES the foreign frame.
    await expect(clarifyCard).toBeVisible();
    await expect(runStatus).toHaveText(/Clarifying/);
  });

  test("TS-Y-02 the SAME (viewed) run's pipeline_start STILL clears its clarify lane", async ({ dashboard, mockSse }) => {
    // Positive control — the guard must NOT over-block: the viewed run's OWN
    // pipeline_start (matching pipeline_run_id) still resets its clarify lane.
    mockSse.questionnaireReady(SIX_QUESTIONS);
    const clarifyCard = dashboard.page.getByTestId("lane-clarify-status");
    await expect(clarifyCard).toBeVisible();
    await dashboard.thinkingTab().click();

    // A matching pipeline_start (same run id as the launched/viewed run).
    mockSse.emit("pipeline_start", {
      pipeline_run_id: mockSse.currentRunId,
      agents: [
        { id: "own-a", name: "Own Agent One", role: "worker", order: 0 },
        { id: "own-b", name: "Own Agent Two", role: "worker", order: 1 },
      ],
    });

    // Ordered barrier: the same-run frame is applied once its agents seed the spine.
    await expect(dashboard.stepsAgentRow("Own Agent One")).toBeVisible();

    // Same-run reset preserved: the clarify lane clears when the build begins.
    await expect(clarifyCard).toHaveCount(0);
  });
});
