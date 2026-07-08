/**
 * TS-M — QuestionnairePanel / clarify gate.
 *
 * The Deep_Planner_Agent can pause a run with CLARIFY_REQUIRED, emitting
 * `questionnaire_ready`. page.tsx maps that into `questionnaireData` + sets
 * `activePipelineRunId` (from the event's pipeline_run_id); DashboardLayout then
 * mounts QuestionnairePanel in the right-hand area. Answers submit back as a
 * `submit_questionnaire` frame to resume the paused run.
 *
 * Setup: home → "Generate product requirements" (→ user_stories) → Run, then
 * drive `mockWs.questionnaireReady([...])`. user_stories ⇒ pipeline label
 * "User Stories" (PIPELINE_LABELS in QuestionnairePanel.tsx).
 */
import { test, expect } from "../fixtures/test";

test.describe("TS-M — questionnaire / clarify gate", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-M-02 renders Quick Setup with subtitle + answered counter", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);

    await expect(dashboard.questionnaireTitle()).toBeVisible();
    // Subtitle: "User Stories · 2 questions to personalise your output"
    await expect(dashboard.page.getByText(/2 questions/)).toBeVisible();
    await expect(dashboard.page.getByText("0 of 2 answered")).toBeVisible();
    // Both question prompts render.
    await expect(dashboard.page.getByText("Who is the audience?")).toBeVisible();
    await expect(dashboard.page.getByText("Tone?")).toBeVisible();
  });

  test("TS-M-03 selecting an option selects it, auto-advances, and bumps the counter", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    // q1 is expanded by default; pick an option.
    await dashboard.page.getByRole("button", { name: "Executives" }).click();

    // Counter advances (deterministic, survives the q1 collapse).
    await expect(dashboard.page.getByText("1 of 2 answered")).toBeVisible();
    // Auto-advance (~300ms) expands q2 → its options become visible. Poll via
    // toBeVisible rather than a hard sleep.
    await expect(dashboard.page.getByRole("button", { name: "Casual" })).toBeVisible();

    // q2 is the LAST question → selecting it does NOT auto-advance, so the
    // selected option stays mounted and we can assert its selected state.
    // Selected options render inverted (white text on the brand fill); the
    // reskin-durable signal is `text-white` (unselected options are text-gray-700),
    // which survives the navy-hex→brand-token migration that a hex class does not.
    const formal = dashboard.page.getByRole("button", { name: "Formal" });
    await formal.click();
    await expect(formal).toHaveClass(/text-white/);
    await expect(dashboard.page.getByText("2 of 2 answered")).toBeVisible();
  });

  test("TS-M-04 hybrid question exposes a free-text input that clears the MCQ selection", async ({ dashboard, mockWs }) => {
    // Single hybrid question so it stays expanded (no auto-advance) and its
    // free-text input is autofocused.
    mockWs.questionnaireReady([
      { id: "q3", text: "Topic?", answerType: "hybrid", options: ["A", "B"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    // The "Describe your own topic" affordance + its exact placeholder.
    await expect(dashboard.page.getByText("Describe your own topic")).toBeVisible();
    const customInput = dashboard.page.getByPlaceholder(
      "e.g. Q3 sales results, climate change impact, AI in healthcare…",
    );
    await expect(customInput).toBeVisible();

    // Pick an MCQ suggestion first → it becomes selected (inverted white text).
    const optionA = dashboard.page.getByRole("button", { name: "A", exact: true });
    await optionA.click();
    await expect(optionA).toHaveClass(/text-white/);

    // Typing a custom topic clears the MCQ selection for this question.
    await customInput.fill("Climate change");
    await expect(optionA).not.toHaveClass(/text-white/);
    // Effective answer is now the custom text → still counts as answered.
    await expect(dashboard.page.getByText("1 of 1 answered")).toBeVisible();
  });

  test("TS-M-05a all answered → primary 'Run User Stories Pipeline' + skip control", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    await dashboard.page.getByRole("button", { name: "Executives" }).click();
    await expect(dashboard.page.getByRole("button", { name: "Casual" })).toBeVisible();
    await dashboard.page.getByRole("button", { name: "Formal" }).click();
    await expect(dashboard.page.getByText("2 of 2 answered")).toBeVisible();

    await expect(dashboard.page.getByRole("button", { name: "Run User Stories Pipeline" })).toBeVisible();
    // Secondary skip control is always present.
    await expect(dashboard.page.getByRole("button", { name: "Skip all & run directly" })).toBeVisible();
  });

  test("TS-M-05b some answered → 'Continue with 1/2 answered'", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    // Answer only q1 (leave q2 untouched).
    await dashboard.page.getByRole("button", { name: "Developers" }).click();
    await expect(dashboard.page.getByText("1 of 2 answered")).toBeVisible();

    await expect(dashboard.page.getByRole("button", { name: "Continue with 1/2 answered" })).toBeVisible();
  });

  test("TS-M-05c none answered → 'Run with defaults'", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    await expect(dashboard.page.getByText("0 of 2 answered")).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: "Run with defaults" })).toBeVisible();
  });

  test("TS-M-06 submit sends submit_questionnaire; questionnaire_complete dismisses the panel", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    // Answer both so the primary button is the "all answered" label.
    await dashboard.page.getByRole("button", { name: "Executives" }).click();
    await expect(dashboard.page.getByRole("button", { name: "Casual" })).toBeVisible();
    await dashboard.page.getByRole("button", { name: "Formal" }).click();
    await expect(dashboard.page.getByText("2 of 2 answered")).toBeVisible();

    await dashboard.page.getByRole("button", { name: "Run User Stories Pipeline" }).click();

    // Outbound frame: { type:"submit_questionnaire", pipeline_run_id, responses }.
    const frame = await mockWs.waitForClientFrame("submit_questionnaire");
    expect(frame.pipeline_run_id).toBe(mockWs.currentRunId);
    const responses = frame.responses as Array<{ question_id: string; answer: string }>;
    expect(responses).toEqual(
      expect.arrayContaining([
        { question_id: "q1", answer: "Executives" },
        { question_id: "q2", answer: "Formal" },
      ]),
    );

    // Resolving the gate clears the panel.
    mockWs.questionnaireComplete();
    await expect(dashboard.questionnaireTitle()).toHaveCount(0);
  });
});
