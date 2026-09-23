/**
 * ISS-752 — QA-PS-014 sibling: the Steps tab's `EmptyState` ("Start a
 * pipeline to see real-time agent reasoning...") renders during the same
 * reopened-run fetch gap as ISS-739/ISS-740, because `hasAnyData`
 * (`AgentThinkingTab.tsx`) is false for the whole fetch window (empty
 * `agents`, no `runInput` yet) and nothing gates ahead of it with a loading
 * signal. For an already-completed run whose trace is simply still loading,
 * telling the user to "start a pipeline" is actively misleading, and no
 * spinner/skeleton exists anywhere in this branch.
 *
 * See `.knowledge/cards/20260922-1409-ISS-752.md`.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { AgentThinkingTab } from "./AgentThinkingTab";
import type { PipelineRunState } from "@/types/index";

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

function makePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

const START_PIPELINE_COPY = /start a pipeline/i;

// AgentThinkingTab has no fetch-in-flight prop today — this cast lets the
// test express the intended future signal without a compile error, mirroring
// the card's proposed threading of the same flag ISS-739 introduces. Until
// the fixer wires it in, the extra prop is silently ignored and the
// component behaves exactly as it does today, which is precisely the defect
// this test pins.
const LoadingAwareAgentThinkingTab = AgentThinkingTab as unknown as React.FC<
  React.ComponentProps<typeof AgentThinkingTab> & { isLoadingRunData?: boolean }
>;

describe("ISS-752 — Steps tab must not show 'Start a pipeline' while an already-run reopen is still fetching", () => {
  it(
    "ISS-752 — while the reopen fetch is in flight (no agents/runInput yet), the 'Start a pipeline' EmptyState must not be shown",
    () => {
      render(
        <LoadingAwareAgentThinkingTab
          agents={[]}
          pipelineState={makePipelineState()}
          isLoadingRunData={true}
        />,
      );
      // BUG (ISS-752): isLoadingRunData is not read anywhere yet, so hasAnyData
      // is false and EmptyState's "start a pipeline" copy renders regardless —
      // indistinguishable from a run that genuinely never executed.
      expect(screen.queryByText(START_PIPELINE_COPY)).not.toBeInTheDocument();
    },
  );
});
