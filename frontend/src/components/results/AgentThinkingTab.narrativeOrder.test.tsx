import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ClarifyRound, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 / UI-SPEC §0) — the Thinking-tab narrative order:
// Starting point → Planner → Clarifications → Agents. Asserted via real DOM
// order (compareDocumentPosition) + the card-header a11y contract.
// TokenUsageSummary is stubbed so the test stays focused on ordering.
// ─────────────────────────────────────────────────────────────────

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "./AgentThinkingTab";

const CLARIFICATIONS: ClarifyRound[] = [
  { round: 1, qa: [{ question_id: "q1", question_text: "Auth?", impact_level: "high", answer: "OAuth" }] },
];

function makePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "prototype",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: 1.2,
    completedCount: 0,
    plannerStatus: "complete",
    plannerSummary: "Build a todo app with dark mode",
  };
}

describe("AgentThinkingTab — narrative order + a11y", () => {
  it("renders StartingPoint → Clarifications in DOM order (Deep-Planner card retired)", () => {
    render(
      <AgentThinkingTab
        agents={[]}
        pipelineState={makePipelineState()}
        runInput={"Build a todo app with dark mode."}
        clarifications={CLARIFICATIONS}
      />,
    );

    const startingPoint = screen.getByText("Starting point");
    const clarifications = screen.getByText("Clarifications");

    // Phase 39 plan 02 (human ruling): the Deep-Planner card is removed from the
    // Steps overview. Starting point still precedes Clarifications.
    expect(screen.queryByText("Deep Planner")).toBeNull();
    expect(startingPoint.compareDocumentPosition(clarifications) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("exposes both card headers as aria-expanded buttons", () => {
    render(
      <AgentThinkingTab
        agents={[]}
        pipelineState={makePipelineState()}
        runInput={"Build a todo app with dark mode."}
        clarifications={CLARIFICATIONS}
      />,
    );

    const startHeader = screen.getByRole("button", { name: /starting point/i });
    const clarHeader = screen.getByRole("button", { name: /clarifications/i });
    expect(startHeader).toHaveAttribute("aria-expanded");
    expect(clarHeader).toHaveAttribute("aria-expanded");
  });
});
