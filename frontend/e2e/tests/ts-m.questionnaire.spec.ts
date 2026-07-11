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
import type { Page } from "@playwright/test";

// Phase 39 redesign: the clarify gate now renders in TWO surfaces at once — the
// inline lane clarify actions (`chat-clarify-actions`, ALL questions as chips)
// AND the right-panel QuestionnairePanel ("Quick Setup", ONE question at a time
// with a Next-driven flow + an answered counter + a final summary slide). An
// un-scoped `getByText`/`getByRole` for a question prompt or option collides
// across both surfaces (strict-mode violation), so scope each locator to its
// intended surface.

/** The inline lane clarify actions — all questions as quick-reply chips. */
function laneClarify(page: Page) {
  return page.getByTestId("chat-clarify-actions");
}

/** The right-panel QuestionnairePanel root (Quick Setup / Review & Confirm). It
 *  shows one question at a time + the answered counter + summary controls, none
 *  of which the lane surface carries. Anchored on the panel-unique "Skip all &
 *  run directly" control, walking to the nearest ancestor holding its <h2>. */
function qPanel(page: Page) {
  return page
    .getByRole("button", { name: "Skip all & run directly" })
    .locator('xpath=ancestor::div[.//h2][1]');
}

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
    // Panel subtitle is now the one-at-a-time progress label
    // "User Stories · Question 1 of 2" + the answered counter beneath it.
    await expect(dashboard.page.getByText("User Stories · Question 1 of 2")).toBeVisible();
    await expect(dashboard.page.getByText("0 of 2 answered")).toBeVisible();
    // The panel shows only the current question, so assert BOTH prompts on the
    // inline lane surface (which lists every clarify question at once).
    await expect(laneClarify(dashboard.page).getByText("Who is the audience?")).toBeVisible();
    await expect(laneClarify(dashboard.page).getByText("Tone?")).toBeVisible();
  });

  test("TS-M-03 selecting an option selects it, auto-advances, and bumps the counter", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();
    const panel = qPanel(dashboard.page);

    // q1 is shown; pick an option → it selects (inverted white text) and the
    // answered counter bumps. The redesign REPLACED the old auto-advance with a
    // one-question-at-a-time panel driven by an explicit "Next" control.
    const executives = panel.getByRole("button", { name: "Executives" });
    await executives.click();
    // Selected options render inverted (white text on the brand fill); the
    // reskin-durable signal is `text-white` (unselected options are text-gray-700).
    await expect(executives).toHaveClass(/text-white/);
    await expect(dashboard.page.getByText("1 of 2 answered")).toBeVisible();

    // Advance to q2 via the panel's Next control (heir to the old auto-advance).
    await panel.getByRole("button", { name: /^Next/ }).click();
    await expect(panel.getByRole("button", { name: "Casual" })).toBeVisible();

    // q2 is the LAST question → selecting it keeps it mounted; assert its state.
    const formal = panel.getByRole("button", { name: "Formal" });
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
    const panel = qPanel(dashboard.page);

    // Redesign copy: the hybrid free-text affordance reads "Describe your own"
    // with the placeholder "Type your specific answer…" (scoped to the panel —
    // the lane surface renders no hybrid free-text input).
    await expect(panel.getByText("Describe your own")).toBeVisible();
    const customInput = panel.getByPlaceholder("Type your specific answer…");
    await expect(customInput).toBeVisible();

    // Pick an MCQ suggestion first → it becomes selected (inverted white text).
    const optionA = panel.getByRole("button", { name: "A", exact: true });
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
    const panel = qPanel(dashboard.page);

    // Answer both questions (one at a time, advancing via Next).
    await panel.getByRole("button", { name: "Executives" }).click();
    await panel.getByRole("button", { name: /^Next/ }).click();
    await panel.getByRole("button", { name: "Casual" }).waitFor();
    await panel.getByRole("button", { name: "Formal" }).click();
    await expect(dashboard.page.getByText("2 of 2 answered")).toBeVisible();

    // With the last question answered the primary control reads "Review answers";
    // it opens the summary slide that carries the run/skip controls.
    await panel.getByRole("button", { name: /Review answers/ }).click();
    // All answered → the summary's primary run control is the labelled pipeline run.
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
    const panel = qPanel(dashboard.page);

    // Answer only q1 (leave q2 untouched), then walk to the summary slide.
    await panel.getByRole("button", { name: "Developers" }).click();
    await expect(dashboard.page.getByText("1 of 2 answered")).toBeVisible();
    await panel.getByRole("button", { name: /^Next/ }).click();
    await panel.getByRole("button", { name: /Skip & review/ }).click();

    // FLAGGED — REMOVED BEHAVIOR (Phase 39 redesign). The redesigned summary
    // slide no longer distinguishes a PARTIAL-answer state with its own
    // "Continue with N/M answered" label: it shows "Run User Stories Pipeline"
    // whenever answeredCount > 0 (see QuestionnairePanel summary primary button),
    // and "Run with defaults" only at zero. This distinct partial label is gone.
    // Left intentionally failing for reconciliation — do NOT loosen.
    await expect(dashboard.page.getByRole("button", { name: "Continue with 1/2 answered" })).toBeVisible();
  });

  test("TS-M-05c none answered → 'Run with defaults'", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();
    const panel = qPanel(dashboard.page);

    await expect(dashboard.page.getByText("0 of 2 answered")).toBeVisible();
    // Reach the summary slide WITHOUT answering (skip each question).
    await panel.getByRole("button", { name: /Skip question/ }).click();
    await panel.getByRole("button", { name: /Skip & review/ }).click();
    // Zero answered → the summary's primary control offers the defaults run.
    await expect(dashboard.page.getByRole("button", { name: "Run with defaults" })).toBeVisible();
  });

  test("TS-M-06 submit sends submit_questionnaire; questionnaire_complete dismisses the panel", async ({ dashboard, mockWs }) => {
    mockWs.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await expect(dashboard.questionnaireTitle()).toBeVisible();

    // Submit through the inline lane clarify surface (all questions at once) —
    // it fires the SAME `submit_questionnaire` resume channel as the panel. Both
    // answers select on the lane chips; "Send answers" (chat-clarify-submit) sends.
    const clarify = laneClarify(dashboard.page);
    await clarify.getByRole("button", { name: "Executives" }).click();
    await clarify.getByRole("button", { name: "Formal" }).click();
    await clarify.getByTestId("chat-clarify-submit").click();

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
