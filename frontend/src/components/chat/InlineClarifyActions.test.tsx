import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ClarifyQuestion } from "../preview/QuestionnairePanel";
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

  it("'Use recommended' fills the recommended answer", () => {
    const { onSubmitAnswers } = renderClarify([Q1]);
    fireEvent.click(screen.getByText("Use recommended"));
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "List" },
    ]);
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

  it("skip marks the question skipped and omits it from the responses", () => {
    const { onSubmitAnswers } = renderClarify([Q1, Q_MULTI]);
    fireEvent.click(screen.getByText("Grid")); // answer q1
    // Skip q2 via its own skip button.
    const q2Block = screen.getByText("Which features?").closest("div")!;
    fireEvent.click(within(q2Block).getByText("Skip"));
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "Grid" },
    ]);
  });

  it("appends the global freeform as question_id 'freeform'", () => {
    const { onSubmitAnswers } = renderClarify([Q1]);
    fireEvent.click(screen.getByText("Grid"));
    fireEvent.change(screen.getByLabelText("Additional notes"), {
      target: { value: "keep it minimal" },
    });
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitAnswers).toHaveBeenCalledWith([
      { question_id: "q1", answer: "Grid" },
      { question_id: "freeform", answer: "keep it minimal" },
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
