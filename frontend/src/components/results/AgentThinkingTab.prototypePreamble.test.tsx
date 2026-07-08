import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState, ClarifyRound, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Quick byv FIX-1 (updated Phase 32 plan 08 / SC-001) — the bespoke
// PrototypePipelineView + its prototype-* render-path literals are removed;
// prototype runs now render through the SAME generic Steps drill-down as every
// other workflow (INV-3 no dual impl). This test now asserts the run's
// Starting point → Clarifications preamble still renders for a prototype-id run
// via that generic path, and that the header still reads "Prototype Pipeline"
// (derived from the generic "prototype-" family prefix, NOT a gated literal).
// Real-DOM specs: (1) runInput + clarify → all three present; (2) runInput,
// no clarify → StartingPoint present, Clarifications absent (PROCEED run).
// TokenUsageSummary is stubbed (parity with the narrativeOrder idiom).
// ─────────────────────────────────────────────────────────────────

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "./AgentThinkingTab";

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Prototype phase",
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...partial,
  };
}

// A prototype-build agent that is running → isPrototypePipeline is true AND
// hasAnyData is true (status !== "idle").
const BUILD_RUNNING = makeAgent({ id: "prototype-build", name: "Build Agent", status: "running" });

const CLARIFICATIONS: ClarifyRound[] = [
  { round: 1, qa: [{ question_id: "q1", question_text: "Which auth method?", impact_level: "high", answer: "OAuth" }] },
];

function makePipelineState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [BUILD_RUNNING],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
  };
}

describe("AgentThinkingTab — prototype preamble (byv FIX-1)", () => {
  it("renders StartingPoint + Clarifications ABOVE the prototype pipeline view", () => {
    render(
      <AgentThinkingTab
        agents={[BUILD_RUNNING]}
        pipelineState={makePipelineState()}
        runInput={"Build a todo app with dark mode."}
        clarifications={CLARIFICATIONS}
      />,
    );

    // All three surfaces present: the two preamble cards + the generic header
    // (which now reads "Prototype Pipeline" off the generic family prefix).
    expect(screen.getByText("Starting point")).toBeInTheDocument();
    expect(screen.getByText("Clarifications")).toBeInTheDocument();
    expect(screen.getByText("Prototype Pipeline")).toBeInTheDocument();

    // Narrative order in the unified generic drill-down: Starting point precedes
    // Clarifications (the header leads; the two preamble cards keep their order).
    const start = screen.getByText("Starting point");
    const clar = screen.getByText("Clarifications");
    expect(start.compareDocumentPosition(clar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows StartingPoint but NO Clarifications for a clarify-less (PROCEED) prototype run", () => {
    render(
      <AgentThinkingTab
        agents={[BUILD_RUNNING]}
        pipelineState={makePipelineState()}
        runInput={"Build a todo app with dark mode."}
      />,
    );

    // StartingPoint renders from runInput alone; ClarificationsCard returns null.
    expect(screen.getByText("Starting point")).toBeInTheDocument();
    expect(screen.queryByText("Clarifications")).toBeNull();
    // The prototype view still renders below the preamble.
    expect(screen.getByText("Prototype Pipeline")).toBeInTheDocument();
  });
});
