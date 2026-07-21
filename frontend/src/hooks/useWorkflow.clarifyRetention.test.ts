/**
 * Workstream C1 (POR §6.5) — clarify round retention. The answered Q&A must
 * survive the questionnaire panel unmount (retained in run-scoped state) and
 * must reset at the start of a fresh run (the startPipeline boundary).
 */
import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWorkflow } from "./useWorkflow";
import type { ClarifyRound } from "@/types/index";

const r1: ClarifyRound = {
  round: 1,
  qa: [{ question_id: "q1", question_text: "Which theme?", impact_level: "high", answer: "dark" }],
};
const r2: ClarifyRound = {
  round: 2,
  qa: [{ question_id: "q2", question_text: "Which font?", impact_level: "low", answer: "serif" }],
};

describe("useWorkflow — retainClarifyRound", () => {
  it("appends rounds that survive, then resets to empty on a fresh run", () => {
    const { result } = renderHook(() => useWorkflow());

    act(() => {
      void result.current.startPipeline("prototype", "build it");
    });
    expect(result.current.pipelineState.clarifications).toEqual([]);

    act(() => result.current.retainClarifyRound(r1));
    act(() => result.current.retainClarifyRound(r2));
    expect(result.current.pipelineState.clarifications).toEqual([r1, r2]);

    // A second fresh run resets the retained rounds (per-run boundary).
    act(() => {
      void result.current.startPipeline("prototype", "build it again");
    });
    expect(result.current.pipelineState.clarifications).toEqual([]);
  });
});
