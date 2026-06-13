import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { PreviewPanel } from "./PreviewPanel";
import type { PipelineRunState, WorkflowStatus } from "@/types/index";

// ─── Motion mock (same as the other PreviewPanel-area component tests) ────────
// Strips animation-only props so role/text queries still find rendered nodes.
const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

// Stub the heavy preview child components so the terminal+content case renders
// a cheap marker instead of dragging the markdown/PPT/prototype renderers (and
// their export/syntax-highlight dependencies) into the test environment. The
// degraded affordance + neutral empty-state live in PreviewPanel itself, so
// these stubs don't touch what we're asserting.
vi.mock("./UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => (
    <div data-testid="user-story-preview">{content}</div>
  ),
}));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div data-testid="files-tab" /> }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

// Minimal valid PipelineRunState — required fields only, plus the failure
// flags under test. Mirrors the shape useWorkflow produces.
function makePipelineState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

const AFFORDANCE_COPY = /this run did not complete successfully/i;
const NEUTRAL_COPY = /output will appear here/i;

describe("PreviewPanel — terminal-empty degraded/failed affordance (ISS-017)", () => {
  it("terminal+failed (pipelineState.failed) → shows the affordance, hides the neutral empty-state, lists failed agents", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({
          isRunning: false,
          failed: true,
          failedAgents: ["story-writer"],
        })}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // The provided failed-agent name appears in the affordance.
    expect(screen.getByText("story-writer")).toBeInTheDocument();
  });

  it("terminal+degraded (pipelineState.degraded) → shows the affordance, hides the neutral empty-state", () => {
    render(
      <PreviewPanel
        workflowType="ppt"
        isStreaming={false}
        pipelineState={makePipelineState({
          pipeline_type: "ppt",
          isRunning: false,
          degraded: true,
          degradedFailedAgents: ["ppt-validator"],
        })}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    expect(screen.getByText("ppt-validator")).toBeInTheDocument();
  });

  it("streaming+empty (isRunning, no terminal flag) → keeps the neutral empty-state, NOT the affordance", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={true}
        pipelineState={makePipelineState({ isRunning: true })}
      />,
    );

    expect(screen.getByText(NEUTRAL_COPY)).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
  });

  it("no-signal terminal+empty (completed, no failed/degraded flag) → keeps the neutral empty-state, NOT mislabeled as failed", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({ isRunning: false })}
      />,
    );

    // Server carried no failure signal — a legitimately-empty completed run
    // must NOT be flagged failed (no client empty==failed guess).
    expect(screen.getByText(NEUTRAL_COPY)).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
  });

  it("terminal+content → renders the deliverable, NOT the affordance and NOT the neutral empty-state", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        userStoryContent={"# A real deliverable"}
        pipelineState={makePipelineState({
          isRunning: false,
          // Even if a stale failure flag were present, content wins — the
          // affordance is gated on !hasContent.
          failed: true,
        })}
      />,
    );

    expect(screen.getByTestId("user-story-preview")).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });

  it("reopen+failed (reopenedRunStatus='failed', no content) → shows the affordance via the history-path server signal", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"failed" as WorkflowStatus}
        reopenedFailedAgents={["proto-builder"]}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    expect(screen.getByText("proto-builder")).toBeInTheDocument();
  });

  it("reopen+cancelled (reopenedRunStatus='cancelled', no content) → shows the affordance", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"cancelled" as WorkflowStatus}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });

  it("reopen+completed (reopenedRunStatus undefined) terminal+empty → keeps the neutral empty-state", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={undefined}
      />,
    );

    expect(screen.getByText(NEUTRAL_COPY)).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
  });
});
