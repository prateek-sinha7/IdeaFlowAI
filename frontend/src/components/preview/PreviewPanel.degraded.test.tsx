import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { PreviewPanel } from "./PreviewPanel";
import type { AgentRunState, PipelineRunState, WorkflowStatus } from "@/types/index";

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

// ISS-024 — a minimal {id,name} agent for the live id→name resolution cases.
function makeAgent(id: string, name: string): AgentRunState {
  return {
    id,
    name,
    role: "",
    icon: "",
    status: "error",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
  };
}

const AFFORDANCE_COPY = /this run did not complete successfully/i;
const NEUTRAL_COPY = /output will appear here/i;

describe("PreviewPanel — terminal-empty degraded/failed affordance (ISS-017)", () => {
  it("terminal+failed (pipelineState.failed) → shows the affordance, hides the neutral empty-state, lists the failed agent's NAME (ISS-024)", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({
          isRunning: false,
          failed: true,
          failedAgents: ["story-writer"],
          // ISS-024: pipelineState.agents carries the id→name source on the live
          // path — the affordance must surface the NAME, not the raw id.
          agents: [makeAgent("story-writer", "Story Writer")],
        })}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // ISS-024: the human NAME appears, not the raw id.
    expect(screen.getByText("Story Writer")).toBeInTheDocument();
    expect(screen.queryByText("story-writer")).not.toBeInTheDocument();
  });

  it("terminal+degraded (pipelineState.degraded) → shows the affordance, hides the neutral empty-state, lists the failed agent's NAME (ISS-024)", () => {
    render(
      <PreviewPanel
        workflowType="ppt"
        isStreaming={false}
        pipelineState={makePipelineState({
          pipeline_type: "ppt",
          isRunning: false,
          degraded: true,
          degradedFailedAgents: ["ppt-validator"],
          agents: [makeAgent("ppt-validator", "Slide Validator")],
        })}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // ISS-024: human NAME, not the id.
    expect(screen.getByText("Slide Validator")).toBeInTheDocument();
    expect(screen.queryByText("ppt-validator")).not.toBeInTheDocument();
  });

  it("ISS-024: a failed-agent id absent from pipelineState.agents falls back to the raw id (never blank)", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({
          isRunning: false,
          failed: true,
          failedAgents: ["story-writer", "unknown-agent"],
          // Only one agent is named; the other id has no name source.
          agents: [makeAgent("story-writer", "Story Writer")],
        })}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    // Resolved name for the known id…
    expect(screen.getByText("Story Writer")).toBeInTheDocument();
    // …and a fallback to the raw id for the unknown one (not blank).
    expect(screen.getByText("unknown-agent")).toBeInTheDocument();
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

  it("reopen+failed (reopenedRunStatus='failed', no content) → shows the affordance + the reopened agent's NAME via reopenedAgentNameById (ISS-024)", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"failed" as WorkflowStatus}
        reopenedFailedAgents={["proto-builder"]}
        // ISS-024: the live pipelineState can't name a reopened run's agents — the
        // dashboard threads the id→name map built from the run detail's
        // agentOutputs. The affordance must surface the NAME.
        reopenedAgentNameById={{ "proto-builder": "Build Agent" }}
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // ISS-024: the human NAME appears, not the raw id.
    expect(screen.getByText("Build Agent")).toBeInTheDocument();
    expect(screen.queryByText("proto-builder")).not.toBeInTheDocument();
  });

  it("ISS-024: reopen+failed with NO name map falls back to the raw id (older runs, never blank)", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"failed" as WorkflowStatus}
        reopenedFailedAgents={["proto-builder"]}
        // No reopenedAgentNameById (e.g. an older run with no agentOutputs) — the
        // raw id must still render rather than a blank list item.
      />,
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.getByText("proto-builder")).toBeInTheDocument();
  });

  it("reopen+cancelled (reopenedRunStatus='cancelled', no content) → shows the cancelled-specific copy, NOT the failed/degraded copy", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"cancelled" as WorkflowStatus}
      />,
    );

    // IN-03: a deliberate user cancel must NOT be labelled "failed or degraded".
    expect(screen.getByText(/this run was cancelled/i)).toBeInTheDocument();
    expect(screen.queryByText(/failed or degraded/i)).not.toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });

  it("reopen+degraded (reopenedRunStatus='degraded', no content) → shows the affordance with the wired failed-agent list (WR-01 + IN-01)", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"degraded" as WorkflowStatus}
        reopenedFailedAgents={["domain-analyst", "story-estimator"]}
      />,
    );

    // WR-01: a degraded run reopened from history with no partial deliverable
    // surfaces the failure affordance, not the neutral empty-state.
    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // IN-01: the real reopened failed-agent ids appear (not an empty list).
    expect(screen.getByText("domain-analyst")).toBeInTheDocument();
    expect(screen.getByText("story-estimator")).toBeInTheDocument();
    // A degraded reopen is NOT a cancel — keeps the failed/degraded copy.
    expect(screen.queryByText(/this run was cancelled/i)).not.toBeInTheDocument();
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
