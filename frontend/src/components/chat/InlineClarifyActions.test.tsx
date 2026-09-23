import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ClarifyQuestion } from "@/types/index";
import { InlineClarifyActions } from "./InlineClarifyActions";

// ─── InlineClarifyActions — in-lane mirror of the Steps QuestionnairePanel ────
// Presentational + callback-driven. Chips + option picker submit via the SAME
// submit_questionnaire answer channel — one backend command either way. Emits
// the canonical [{ question_id, answer }] shape, multi joined by ", ", freeform
// as question_id "freeform". Keyed on generic question ids (SC-001).

const Q1: ClarifyQuestion = {
  id: "q1",
  question: "Which layout?",
  options: ["Grid", "List"],
  answerType: "single_choice",
  recommendedAnswer: "List",
};

const Q_MULTI: ClarifyQuestion = {
  id: "q2",
  question: "Which features?",
  options: ["Auth", "Search", "Export"],
  answerType: "multi_select",
};

function renderClarify(questions: ClarifyQuestion[]) {
  const onSubmitAnswers = vi.fn();
  const utils = render(
    <InlineClarifyActions questions={questions} onSubmitAnswers={onSubmitAnswers} />,
  );
  return { onSubmitAnswers, ...utils };
}

// ── Accept all recommended ────────────────────────────────────────────────────
// One gap per question means a real corpus asks fifty of them at once. Clicking
// "Use recommended" fifty times to agree with nearly all of them is the whole
// cost of asking, so the footer answers every recommended question in one go.

const Q3: ClarifyQuestion = {
  id: "q3",
  question: "Which billing plan?",
  options: ["Monthly", "Quarterly"],
  answerType: "single_choice",
  recommendedAnswer: "Quarterly",
};

const Q_NO_REC: ClarifyQuestion = {
  id: "q4",
  question: "What should the error copy say?",
  options: ["Inline", "Toast"],
  answerType: "single_choice",
};

describe("InlineClarifyActions — accept all recommended", () => {
  it("submits every recommendation in one click", () => {
    const { onSubmitAnswers } = renderClarify([Q1, Q3]);
    fireEvent.click(screen.getByTestId("chat-clarify-accept-all-recommended"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "List" },
      { question_id: "q3", answer: "Quarterly" },
    ]);
  });

  it("counts only the questions that carry a recommendation", () => {
    renderClarify([Q1, Q3, Q_NO_REC]);
    expect(screen.getByTestId("chat-clarify-accept-all-recommended")).toHaveTextContent(
      "Accept all 2 recommended & continue",
    );
  });

  it("leaves a question with no recommendation unanswered rather than guessing", () => {
    const { onSubmitAnswers } = renderClarify([Q1, Q_NO_REC]);
    fireEvent.click(screen.getByTestId("chat-clarify-accept-all-recommended"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([{ question_id: "q1", answer: "List" }]);
  });

  it("keeps an answer the user already chose over the recommendation for that one", () => {
    // The user disagreed with q1 on purpose; accepting the rest must not undo it.
    const { onSubmitAnswers } = renderClarify([Q1, Q_NO_REC]);
    fireEvent.click(screen.getByText("Toast"));
    fireEvent.click(screen.getByTestId("chat-clarify-accept-all-recommended"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "List" },
      { question_id: "q4", answer: "Toast" },
    ]);
  });

  it("splits a multi-select recommendation into its chips", () => {
    const multiRec: ClarifyQuestion = { ...Q_MULTI, recommendedAnswer: "Auth, Export" };
    const { onSubmitAnswers } = renderClarify([multiRec]);
    fireEvent.click(screen.getByTestId("chat-clarify-accept-all-recommended"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q2", answer: "Auth, Export" },
    ]);
  });

  it("is absent when nothing carries a recommendation", () => {
    renderClarify([Q_MULTI, Q_NO_REC]);
    expect(screen.queryByTestId("chat-clarify-accept-all-recommended")).toBeNull();
  });

  it("submits once — the run is already resuming on the second click", () => {
    const { onSubmitAnswers } = renderClarify([Q1]);
    const btn = screen.getByTestId("chat-clarify-accept-all-recommended");
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(onSubmitAnswers).toHaveBeenCalledTimes(1);
  });
});

describe("InlineClarifyActions", () => {
  it("renders nothing when there are no questions", () => {
    const { container } = render(
      <InlineClarifyActions questions={[]} onSubmitAnswers={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("selecting a chip + submit fires onSubmitAnswers with the right response", () => {
    const { onSubmitAnswers } = renderClarify([Q1]);
    fireEvent.click(screen.getByText("Grid"));
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledTimes(1);
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "Grid" },
    ]);
  });

  it("submit copy reads 'Submit answers & proceed'", () => {
    renderClarify([Q1]);
    expect(screen.getByTestId("chat-clarify-submit")).toHaveTextContent(
      "Submit answers & proceed",
    );
  });

  it("shows the 'Use recommended' hint for a question with a recommendedAnswer, before any selection", () => {
    renderClarify([Q1, Q_MULTI]);
    // Q1 has a recommendedAnswer and nothing selected yet → the hint + button show.
    expect(screen.getByText("Use recommended")).toBeInTheDocument();
    // Neither a per-question "Skip" nor a "Rec." badge nor a freeform notes
    // field exist in this component at all (only the multi-question "Select
    // all that apply" hint and the batch "Proceed with auto recommendation"
    // affordance do).
    expect(screen.queryByText("Skip", { exact: true })).toBeNull();
    expect(screen.queryByText("Rec.")).toBeNull();
    expect(screen.queryByLabelText("Additional notes")).toBeNull();
  });

  it("clicking 'Use recommended' selects the recommended chip and shows the confirmation", () => {
    renderClarify([Q1]);
    fireEvent.click(screen.getByText("Use recommended"));
    expect(screen.getByText("✓ Using recommended answer")).toBeInTheDocument();
    expect(screen.queryByText("Use recommended")).toBeNull();
  });

  it("multi-select accumulates selected options into one joined answer", () => {
    const { onSubmitAnswers } = renderClarify([Q_MULTI]);
    fireEvent.click(screen.getByText("Auth"));
    fireEvent.click(screen.getByText("Export"));
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q2", answer: "Auth, Export" },
    ]);
  });

  it("unanswered questions are simply omitted from the responses", () => {
    const { onSubmitAnswers } = renderClarify([Q1, Q_MULTI]);
    fireEvent.click(screen.getByText("Grid")); // answer q1 only
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "Grid" },
    ]);
  });

  it("latches after one submit to prevent a double-send", () => {
    const { onSubmitAnswers } = renderClarify([Q1]);
    fireEvent.click(screen.getByText("Grid"));
    const submit = screen.getByTestId("chat-clarify-submit");
    fireEvent.click(submit);
    fireEvent.click(submit);
    expect(onSubmitAnswers).toHaveBeenCalledTimes(1);
  });

  it("omits the Cancel-Workflow affordance when onCancelWorkflow is not provided", () => {
    renderClarify([Q1]);
    expect(screen.queryByTestId("chat-clarify-cancel-workflow")).toBeNull();
  });

  it("Cancel-Workflow re-home (§A2): renders the affordance and fires onCancelWorkflow", () => {
    const onCancelWorkflow = vi.fn();
    render(
      <InlineClarifyActions
        questions={[Q1]}
        onSubmitAnswers={vi.fn()}
        onCancelWorkflow={onCancelWorkflow}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-clarify-cancel-workflow"));
    expect(onCancelWorkflow).toHaveBeenCalledTimes(1);
  });

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/InlineClarifyActions.tsx"),
      "utf8",
    );
    expect(
      /prototype-analyze|prototype-specify|"prototype"|od_ppt|app_builder/.test(
        src,
      ),
    ).toBe(false);
  });
});
