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

// ── L3 construction task detail + failed-overview state ──
const BUILD_AGENT: AgentRunState = makeAgent({
  id: "prototype-build", name: "Build Agent", status: "done", totalTokens: 88_000,
  toolCalls: [{ tool: "write_file", args: { path: "index.html" }, result: "ok", timestamp: "t" }],
});

function makeBuildPipeline(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "od_prototype",
    agents: [BUILD_AGENT],
    currentAgentIndex: 0,
    totalDuration: 300,
    completedCount: 1,
    protoCompletedTaskCount: 3,
    protoCompletedTasks: [
      { number: 1, title: "Scaffold shared layout", summary: "Built the shared nav + footer." },
      { number: 2, title: "Home page", summary: "Composed the landing hero." },
      { number: 3, title: "Compare page", summary: "Rendered the comparison grid." },
    ],
  };
}

describe("AgentThinkingTab — L3 task detail", () => {
  it("drills overview -> construction agent -> task detail and back", () => {
    render(<AgentThinkingTab agents={[BUILD_AGENT]} pipelineState={makeBuildPipeline()} />);

    // L1 -> L2 (construction agent detail with the construction block)
    fireEvent.click(screen.getByRole("button", { name: /Build Agent/i }));
    expect(screen.getByTestId("construction-block")).toBeInTheDocument();

    // L2 -> L3 (open a task row → single-task detail)
    fireEvent.click(screen.getByRole("button", { name: /Task 2 · Home page/i }));
    expect(screen.getByRole("button", { name: /Build Agent \/ task detail/i })).toBeInTheDocument();
    expect(screen.getByText("Task 2 · Home page")).toBeInTheDocument();
    expect(screen.getByText("Composed the landing hero.")).toBeInTheDocument();

    // L3 -> L2 back
    fireEvent.click(screen.getByRole("button", { name: /Build Agent \/ task detail/i }));
    expect(screen.getByTestId("construction-block")).toBeInTheDocument();
  });
});

describe("AgentThinkingTab — failed overview", () => {
  it("shows the Pipeline-halted banner + Not-run rows from live pipeline state", () => {
    const failedAgents: AgentRunState[] = [
      makeAgent({ id: "spec", name: "Spec Writer", status: "done", duration: 40 }),
      makeAgent({ id: "build", name: "Build Agent", status: "error", error: "Blocked by the security gate", duration: null }),
      makeAgent({ id: "validate", name: "Validator", status: "idle", duration: null }),
      makeAgent({ id: "polish", name: "Polisher", status: "idle", duration: null }),
    ];
    const ps: PipelineRunState = {
      isRunning: false, pipeline_type: "od_prototype", agents: failedAgents,
      currentAgentIndex: 1, totalDuration: 401, completedCount: 1, failed: true,
    };
    render(<AgentThinkingTab agents={failedAgents} pipelineState={ps} />);

    expect(screen.getByText("Run failed")).toBeInTheDocument();
    // Live count (2 idle agents) — never the mock's fixed text.
    expect(screen.getByText(/Pipeline halted — 2 agents did not run/i)).toBeInTheDocument();
    expect(screen.getByText(/resume from Build Agent/i)).toBeInTheDocument();
    expect(screen.getAllByText("Not run").length).toBe(2);
  });
});
