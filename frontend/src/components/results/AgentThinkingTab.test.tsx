import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { AgentRunState, ContextSource, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06/08) — the Steps tab's three-level navigation:
// L1 overview spine → L2 agent detail with the sticky "Context received" panel.
// Asserts overview→detail→back navigation and that the Context panel is built
// from the agent's LIVE contextSources (ND-D — never the mock's hardcoded values).
// TokenUsageSummary is stubbed (parity with the sibling narrativeOrder idiom).
// ─────────────────────────────────────────────────────────────────

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "./AgentThinkingTab";

const CTX: ContextSource[] = [
  { type: "artifact", artifact_type: "requirements.md", artifact_size_chars: 12_400 },
  { type: "summary", agent_name: "Domain Analyst", summary_length: 3_100, full_output_length: 15_500 },
];

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Phase",
    icon: "🤖",
    status: "done",
    output: "Final output text.",
    thinking: "",
    duration: 84,
    error: null,
    index: 0,
    ...partial,
  };
}

const AGENTS: AgentRunState[] = [
  makeAgent({ id: "spec-writer", name: "Spec Writer", status: "done", totalTokens: 30_100, contextSources: CTX, thinkingText: "Analysed the brief and drafted the spec." }),
  makeAgent({ id: "backlog-builder", name: "Backlog Builder", status: "done", totalTokens: 20_500 }),
];

function makePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: AGENTS,
    currentAgentIndex: 1,
    totalDuration: 131,
    completedCount: 2,
  };
}

describe("AgentThinkingTab — Steps three-level navigation", () => {
  it("opens on the overview spine (status line + navigable agent rows)", () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);

    // Status line + both agent rows in the overview spine.
    expect(screen.getByText("Run complete")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Spec Writer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Backlog Builder/i })).toBeInTheDocument();

    // Overview does NOT show the L2 breadcrumb yet.
    expect(screen.queryByText(/^Steps$/)).toBeNull();
  });

  it("drills into the 2-column agent detail with a Context-received panel from live contextSources", () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);

    fireEvent.click(screen.getByRole("button", { name: /Spec Writer/i }));

    // Breadcrumb "Steps / Spec Writer" is present in L2.
    const breadcrumb = screen.getByRole("button", { name: /Steps \/ Spec Writer/i });
    expect(breadcrumb).toBeInTheDocument();

    // The sticky Context-received panel renders from the LIVE contextSources —
    // the source names, and the count — never the mock's hardcoded literal.
    expect(screen.getByText("Context received")).toBeInTheDocument();
    expect(screen.getByText("2 sources fed in")).toBeInTheDocument();
    expect(screen.getByText("requirements.md")).toBeInTheDocument();
    expect(screen.getByText("Domain Analyst")).toBeInTheDocument();
    expect(screen.queryByText("spec.md 36.4 KB")).toBeNull();
  });

  it("navigates back from the agent detail to the overview", () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);

    fireEvent.click(screen.getByRole("button", { name: /Spec Writer/i }));
    const breadcrumb = screen.getByRole("button", { name: /Steps \/ Spec Writer/i });
    fireEvent.click(breadcrumb);

    // Back on the overview: the status line + both spine rows are visible again.
    expect(screen.getByText("Run complete")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Backlog Builder/i })).toBeInTheDocument();
  });

  it("renders the sticky Context panel source metadata (size + compression) from live values", () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    fireEvent.click(screen.getByRole("button", { name: /Spec Writer/i }));

    // requirements.md 12.4k artifact; Domain Analyst summary 3.1k with -80% compression.
    expect(screen.getByText(/12\.4k/)).toBeInTheDocument();
    expect(screen.getByText(/-80%/)).toBeInTheDocument();
  });
});
