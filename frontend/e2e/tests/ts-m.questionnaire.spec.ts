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
 * as quick-reply chips (`chat-clarify-chip`) + ONE submit "Submit answers & start
 * the build" (`chat-clarify-submit`). The lane composer during clarify is now a
 * plain phase-hint input, so `chat-clarify-actions` renders in exactly ONE place.
 * The `submit_questionnaire` resume channel is UNCHANGED.
 *
 * Setup: home → "Generate product requirements" (→ user_stories) → Run, drive
 * `mockSse.questionnaireReady([...])`, then open the Steps tab.
 */
import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";

/** The inline Steps clarify root — the sole clarify surface post-Phase-42. */
function laneClarify(page: Page) {
  return page.getByTestId("chat-clarify-actions");
}

test.describe("TS-M — clarify gate (inline Steps clarify)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
  });

  test("TS-M-02 renders the clarify questions as chips + a single submit", async ({ dashboard, mockSse }) => {
    mockSse.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await dashboard.thinkingTab().click();

    const clarify = laneClarify(dashboard.page);
    await expect(clarify).toBeVisible();
    // The inline surface lists EVERY clarify question at once (not one-at-a-time).
    await expect(clarify.getByText("Who is the audience?")).toBeVisible();
    await expect(clarify.getByText("Tone?")).toBeVisible();
    // A single submit — the "Quick Setup" wizard's counter / one-at-a-time flow is
    // retired (Phase 42-06); the submit label reads "Submit answers & start the build".
    await expect(clarify.getByTestId("chat-clarify-submit")).toHaveText(/Submit answers & start the build/);
  });

  test("TS-M-03 selecting a chip marks it selected (inverted brand fill)", async ({ dashboard, mockSse }) => {
    mockSse.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await dashboard.thinkingTab().click();
    const clarify = laneClarify(dashboard.page);
    await expect(clarify).toBeVisible();

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

  test.fixme("TS-M-04 hybrid question exposes a free-text input that clears the MCQ selection", async () => {
    // The "Quick Setup" wizard's hybrid free-text affordance ("Describe your own" /
    // "Type your specific answer…") was intentionally REMOVED with the panel (Phase
    // 42-06, CONTEXT §G / §8 decision 3). The inline clarify (InlineClarifyActions)
    // is chips-only — a hybrid question renders its MCQ suggestions as chips with no
    // free-text override. This flow has no inline equivalent; re-home it if the
    // inline clarify grows a free-text affordance. Replacement surface:
    // components/chat/InlineClarifyActions.tsx (chat-clarify-actions).
  });

  test.fixme("TS-M-05a all answered → primary 'Run User Stories Pipeline' + skip control", async () => {
    // The wizard's summary slide (a per-answer-count primary control "Run {label}
    // Pipeline" + "Skip all & run directly") was DELETED with the panel (Phase
    // 42-06). The inline clarify has a single, answer-count-agnostic submit
    // ("Submit answers & start the build", asserted by TS-M-02 / TS-M-06). No inline
    // equivalent for the labelled summary controls. Replacement surface:
    // components/chat/InlineClarifyActions.tsx (chat-clarify-submit).
  });

  test.fixme("TS-M-05b some answered → primary 'Run User Stories Pipeline' (partial label)", async () => {
    // As TS-M-05a: the wizard summary's partial-answer "Run {label} Pipeline" control
    // is retired. The inline clarify submits any (incl. partial) selection through the
    // one "Submit answers & start the build" control. Replacement surface:
    // components/chat/InlineClarifyActions.tsx (chat-clarify-submit).
  });

  test.fixme("TS-M-05c none answered → 'Run with defaults'", async () => {
    // The wizard's zero-answered "Run with defaults" summary control is retired with
    // the panel (Phase 42-06). The inline clarify offers only "Submit answers & start
    // the build"; submitting with no chips selected sends an empty responses array
    // (the resume-with-defaults behavior) through the SAME submit_questionnaire
    // channel. No distinct "Run with defaults" affordance survives. Replacement
    // surface: components/chat/InlineClarifyActions.tsx (chat-clarify-submit).
  });

  test("TS-M-06 submit sends submit_questionnaire; questionnaire_complete dismisses the clarify", async ({ dashboard, mockSse }) => {
    mockSse.questionnaireReady([
      { id: "q1", text: "Who is the audience?", options: ["Executives", "Developers"], answerType: "single" },
      { id: "q2", text: "Tone?", options: ["Formal", "Casual"] },
    ]);
    await dashboard.thinkingTab().click();

    // Submit through the inline Steps clarify (all questions at once) — it fires the
    // SAME `submit_questionnaire` resume channel the deleted QuestionnairePanel used.
    const clarify = laneClarify(dashboard.page);
    await expect(clarify).toBeVisible();
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
