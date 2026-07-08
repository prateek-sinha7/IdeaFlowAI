/**
 * ChatTokenWidget — compact lane token-usage widget (Phase 31, CHATUI-03).
 *
 * Proves:
 *   1. renders the pinned P26 totals (total tokens + cost) from run state;
 *   2. the cached segment shows ONLY when cacheReadTokens > 0 (with the %);
 *   3. renders nothing when there is no token data yet.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatTokenWidget } from "./ChatTokenWidget";
import type { PipelineRunState } from "@/types/index";

function state(partial: Partial<PipelineRunState>): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "generic",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    ...partial,
  };
}

describe("ChatTokenWidget", () => {
  it("renders the pinned P26 totals and cost", () => {
    render(
      <ChatTokenWidget
        pipelineState={state({
          totalTokens: 12_500,
          totalInputTokens: 10_000,
          totalOutputTokens: 2_500,
          estimatedCostUsd: 0.042,
        })}
      />,
    );
    expect(screen.getByTestId("chat-token-widget")).toBeInTheDocument();
    expect(screen.getByText("12.5K tokens")).toBeInTheDocument();
    expect(screen.getByText("~$0.042")).toBeInTheDocument();
  });

  it("shows the cached segment only when cacheReadTokens > 0", () => {
    const { rerender } = render(
      <ChatTokenWidget
        pipelineState={state({ totalTokens: 5_000, totalInputTokens: 5_000 })}
      />,
    );
    expect(screen.queryByText(/cached/)).not.toBeInTheDocument();

    rerender(
      <ChatTokenWidget
        pipelineState={state({
          totalTokens: 5_000,
          totalInputTokens: 4_000,
          cacheReadTokens: 2_000,
        })}
      />,
    );
    // 2000 / 4000 = 50%
    expect(screen.getByText(/2\.0K cached \(50%\)/)).toBeInTheDocument();
  });

  it("renders nothing when there is no token data", () => {
    const { container } = render(<ChatTokenWidget pipelineState={state({})} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("hides the composed-context sub-display when the stream omits it (graceful degrade)", () => {
    render(
      <ChatTokenWidget
        pipelineState={state({ totalTokens: 5_000, totalInputTokens: 5_000 })}
      />,
    );
    expect(screen.queryByTestId("chat-context-usage")).not.toBeInTheDocument();
  });

  it("surfaces composed-context usage % and flags high usage (D-08 display-only)", () => {
    render(
      <ChatTokenWidget
        pipelineState={{
          ...state({ totalTokens: 5_000, totalInputTokens: 5_000 }),
          // Composed-context telemetry (Phase-34 stream fields).
          composedContextTokens: 90_000,
          contextBudgetTokens: 100_000,
        }}
      />,
    );
    const ctx = screen.getByTestId("chat-context-usage");
    expect(ctx).toHaveTextContent("90% context");
    expect(ctx).toHaveAttribute("data-context-high", "true");
  });

  it("does not flag composed-context usage below the compact threshold", () => {
    render(
      <ChatTokenWidget
        pipelineState={{
          ...state({ totalTokens: 5_000, totalInputTokens: 5_000 }),
          composedContextTokens: 40_000,
          contextBudgetTokens: 100_000,
        }}
      />,
    );
    const ctx = screen.getByTestId("chat-context-usage");
    expect(ctx).toHaveTextContent("40% context");
    expect(ctx).toHaveAttribute("data-context-high", "false");
  });
});
