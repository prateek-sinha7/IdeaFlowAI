/**
 * TS-M — mid-run clarify gate (Phase 42 re-anchor: the INLINE Steps clarify).
 *
 * The planner can pause a run with CLARIFY_REQUIRED, emitting
 * `questionnaire_ready`. page.tsx maps that into `questionnaireData` +
 * `activePipelineRunId`. Answers submit back as a `submit_questionnaire` frame to
 * resume the paused run.
 *
 * Phase 42-06 DELETED the full-screen right-panel `QuestionnairePanel` "Quick
 * Setup" wizard (one-question-at-a-time flow, answered counter, auto-advance,
 * hybrid free-text, per-question Skip / "Use recommended" / "Rec." badge / "Skip
 * all", and the "Run {label} Pipeline" / "Run with defaults" summary controls).
 * Clarify is now a single INLINE surface in the Steps spine (`InlineClarifyActions`
 * inside the "Clarifications" card, testid `chat-clarify-actions`): every question
 * as quick-reply chips (`chat-clarify-chip`) + ONE submit "Submit [N answers] &
 * proceed" (`chat-clarify-submit`). The lane composer during clarify is now a
 * plain phase-hint input, so `chat-clarify-actions` renders in exactly ONE place.
 * The `submit_questionnaire` resume channel is UNCHANGED.
 *
 * Setup: home → "Generate product requirements" (→ user_stories) → Run, then
 * `pauseAtClarify` drives planner_start → planner_complete(CLARIFY_REQUIRED) →
 * questionnaire_ready (the engine's order) and opens the Steps tab.
 */
import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import type { DashboardPage } from "../fixtures/dashboard";
import type { MockSse } from "../fixtures/mockSse";

/** The inline Steps clarify root — the sole clarify surface post-Phase-42. */
function laneClarify(page: Page) {
  return page.getByTestId("chat-clarify-actions");
}

type ClarifyQuestionSeed = Parameters<MockSse["questionnaireReady"]>[0][number];

/**
 * Pause the launched run at clarify in the order the engine emits it
 * (engine.py: planner_start → planner_complete(CLARIFY_REQUIRED) →
 * questionnaire_ready, all BEFORE pipeline_start). planner_start is what flips
 * the run live and mounts the execution view, so the clarify surface is
 * reachable; then open the Steps tab and return the inline clarify root.
 */
async function pauseAtClarify(dashboard: DashboardPage, mockSse: MockSse, questions: ClarifyQuestionSeed[]) {
  mockSse.plannerStart();
  mockSse.plannerComplete("Refunds backlog", "CLARIFY_REQUIRED");
  mockSse.questionnaireReady(questions);
  await dashboard.openSteps();
  const clarify = laneClarify(dashboard.page);
  await expect(clarify).toBeVisible();
  return clarify;
}

test.describe("TS-M — clarify gate (inline Steps clarify)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-M-02 renders the clarify questions as chips + a single submit", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, [
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);

    // The inline surface lists EVERY clarify question at once (not one-at-a-time).
    await expect(clarify.getByText("Who is the audience?")).toBeVisible();
    await expect(clarify.getByText("Tone?")).toBeVisible();
    // A single submit — the "Quick Setup" wizard's one-at-a-time flow is retired
    // (Phase 42-06). With nothing answered yet the label carries no count.
    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveCount(1);
    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveText(/^\s*Submit answers & proceed\s*$/);
  });

  test("TS-M-03 selecting a chip marks it selected (inverted brand fill)", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, [
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);

    // Phase 42-06 REPLACED the wizard's auto-advance + answered counter with a flat
    // chip list. Selecting a chip marks it selected — the reskin-durable signal is
    // the inverted `text-white` on the brand fill (unselected chips are ink-700).
    const executives = clarify.getByRole("button", { name: "Executives" });
    await executives.click();
    await expect(executives).toHaveClass(/text-white/);

    // A second question's chip selects independently (both questions are present).
    const formal = clarify.getByRole("button", { name: "Formal" });
    await formal.click();
    await expect(formal).toHaveClass(/text-white/);
  });

  // TS-M-04 / TS-M-05a-c were re-anchored from the deleted "Quick Setup" wizard onto
  // the inline clarify (InlineClarifyActions). The inline surface DOES carry the
  // behaviours they guarded: a `hybrid` question renders a free-text override
  // (`chat-clarify-text`) that shares the chips' answer slot, the submit label
  // counts the answered questions, and "Skip the rest" (`chat-clarify-skip-all`)
  // resumes with whatever is answered — nothing at all being the run-with-defaults
  // case. Each case drives the real submit_questionnaire up-channel, and pauses
  // the run through `pauseAtClarify` (the engine's real planner → clarify order).
  const TWO_QUESTIONS: ClarifyQuestionSeed[] = [
    { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
    { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
  ];

  test("TS-M-04 hybrid question exposes a free-text input that clears the MCQ selection", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, [
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "hybrid" },
    ]);

    // A hybrid question offers its MCQ suggestions as chips AND a free-text field.
    const executives = clarify.getByRole("button", { name: "Executives" });
    const freeText = clarify.getByRole("textbox", { name: "Who is the audience?" });
    await expect(freeText).toBeVisible();

    await executives.click();
    await expect(executives).toHaveAttribute("aria-pressed", "true");

    // Typing an override REPLACES the chip selection (one shared answer slot).
    await freeText.fill("Board members");
    await expect(executives).toHaveAttribute("aria-pressed", "false");

    await clarify.getByTestId("chat-clarify-submit").click();
    const frame = await mockSse.waitForClientFrame("submit_questionnaire");
    expect(frame.responses).toEqual([{ question_id: "q1", answer: "Board members" }]);
  });

  test("TS-M-05a all answered → the submit counts every answer and no skip control remains", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, TWO_QUESTIONS);

    await clarify.getByRole("button", { name: "Executives" }).click();
    await clarify.getByRole("button", { name: "Formal" }).click();

    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveText(/Submit 2 answers & proceed/);
    // Nothing is left to skip once every question is answered.
    await expect(clarify.getByTestId("chat-clarify-skip-all")).toHaveCount(0);
  });

  test("TS-M-05b some answered → partial count label; submit sends only the answered question", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, TWO_QUESTIONS);

    await clarify.getByRole("button", { name: "Executives" }).click();

    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveText(/Submit 1 answer & proceed/);
    await expect(clarify.getByTestId("chat-clarify-skip-all")).toBeVisible();

    await clarify.getByTestId("chat-clarify-submit").click();
    const frame = await mockSse.waitForClientFrame("submit_questionnaire");
    // The unanswered question is omitted, not sent as an empty answer.
    expect(frame.responses).toEqual([{ question_id: "q1", answer: "Executives" }]);
  });

  test("TS-M-05c none answered → 'Skip the rest' resumes with defaults (empty responses)", async ({ dashboard, mockSse }) => {
    const clarify = await pauseAtClarify(dashboard, mockSse, TWO_QUESTIONS);

    // With nothing answered the submit carries no count.
    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveText(/^\s*Submit answers & proceed\s*$/);

    await clarify.getByTestId("chat-clarify-skip-all").click();
    const frame = await mockSse.waitForClientFrame("submit_questionnaire");
    expect(frame.pipeline_run_id).toBe(mockSse.currentRunId);
    expect(frame.responses).toEqual([]);
  });

  test("TS-M-06 submit sends submit_questionnaire; questionnaire_complete dismisses the clarify", async ({ dashboard, mockSse }) => {
    // Submit through the inline Steps clarify (all questions at once) — it fires the
    // SAME `submit_questionnaire` resume channel the deleted QuestionnairePanel used.
    const clarify = await pauseAtClarify(dashboard, mockSse, TWO_QUESTIONS);
    await clarify.getByRole("button", { name: "Executives" }).click();
    await clarify.getByRole("button", { name: "Formal" }).click();
    await clarify.getByTestId("chat-clarify-submit").click();

    // Outbound frame: { type:"submit_questionnaire", pipeline_run_id, responses }.
    const frame = await mockSse.waitForClientFrame("submit_questionnaire");
    expect(frame.pipeline_run_id).toBe(mockSse.currentRunId);
    const responses = frame.responses as Array<{ question_id: string; answer: string }>;
    expect(responses).toEqual(
      expect.arrayContaining([
        { question_id: "q1", answer: "Executives" },
        { question_id: "q2", answer: "Formal" },
      ]),
    );

    // Resolving the gate clears the inline clarify.
    mockSse.questionnaireComplete();
    await expect(clarify).toHaveCount(0);
  });
});
