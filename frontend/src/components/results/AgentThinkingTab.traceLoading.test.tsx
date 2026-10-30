/**
 * Finished-run reopen (plan D9) — the Steps tab's loading state while the
 * reopened run's trace is still on its way.
 *
 * The page sets the run's brief (`runInput`) as soon as the record lands, which
 * makes `hasAnyData` true, so before this flag the tab dropped straight to an
 * empty overview (a brief card and no steps) until the event replay finished.
 * `isLoadingRunTrace` keeps the loading state up until the first step arrives.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { AgentThinkingTab } from "./AgentThinkingTab";
import type { AgentRunState, PipelineRunState } from "@/types/index";

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

function makePipelineState(agents: AgentRunState[] = []): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents,
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: agents.length,
  };
}

const doneAgent: AgentRunState = {
  id: "a1",
  name: "Story Writer",
  role: "writer",
  icon: "W",
  status: "done",
  output: "stories",
  thinking: "",
  duration: 1,
  error: null,
  index: 0,
};

const LOADING_COPY = /Loading this run's agent reasoning/i;

describe("AgentThinkingTab trace loading", () => {
  it("shows the loading state while the trace loads even though the brief is already known", () => {
    render(
      <AgentThinkingTab agents={[]} pipelineState={makePipelineState()} runInput="Write stories" isLoadingRunTrace />,
    );

    expect(screen.getByText(LOADING_COPY)).toBeInTheDocument();
    expect(screen.getByText(LOADING_COPY).closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
  });

  it("shows the run overview once the trace has loaded", () => {
    render(
      <AgentThinkingTab agents={[]} pipelineState={makePipelineState()} runInput="Write stories" isLoadingRunTrace={false} />,
    );

    expect(screen.queryByText(LOADING_COPY)).not.toBeInTheDocument();
    expect(screen.queryByText(/start a pipeline/i)).not.toBeInTheDocument();
  });

  it("renders the steps instead of the loading state as soon as one has arrived", () => {
    render(
      <AgentThinkingTab agents={[doneAgent]} pipelineState={makePipelineState([doneAgent])} runInput="Write stories"
        isLoadingRunTrace />,
    );

    expect(screen.queryByText(LOADING_COPY)).not.toBeInTheDocument();
    expect(screen.getAllByText("Story Writer").length).toBeGreaterThan(0);
  });

  it("keeps the fetch-in-flight loading state when the trace flag is absent", () => {
    render(<AgentThinkingTab agents={[]} pipelineState={makePipelineState()} isLoadingRunData />);

    expect(screen.getByText(LOADING_COPY)).toBeInTheDocument();
  });
});
