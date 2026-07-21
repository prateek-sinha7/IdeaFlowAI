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
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

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

// Phase 42-03 (§D / Group D): the amber DegradedRunAffordance is RETIRED on the
// run screen for a terminal-FAILED / DEGRADED run — those runs now drop the
// Preview tab entirely (tabs become [Steps, Files, Audit]) and default to Audit
// (Hexaware Run - Failed tab:'audit'). The affordance component stays exported for
// RunDetailPage.tsx (history reopen, §8 decision 4 OUT OF SCOPE), and a CANCELLED
// reopen still keeps its Preview affordance (below). The red failed treatment now
// lives in the lane / Steps / header (§4 KEEP), not this amber card.
function expectFailedTabSet() {
  // No Preview surface; the tab set is [Steps, Files, Audit].
  expect(screen.queryByTestId("tab-preview")).toBeNull();
  const tabs = screen.getAllByRole("tab");
  expect(tabs.map((t) => t.textContent?.trim())).toEqual(["Steps", "Files", "Audit"]);
  // Defaults to Audit.
  expect(screen.getByTestId("tab-audit")).toHaveAttribute("aria-selected", "true");
  // The amber affordance is gone; the neutral empty-state never shows (no Preview).
  expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
  expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
}

describe("PreviewPanel — terminal-failed run drops Preview + defaults Audit (Group D)", () => {
  it("terminal+failed (pipelineState.failed) → drops the Preview tab, defaults to Audit, retires the amber affordance", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({
          isRunning: false,
          failed: true,
          failedAgents: ["story-writer"],
          agents: [makeAgent("story-writer", "Story Writer")],
        })}
      />,
    );
    expectFailedTabSet();
  });

  it("terminal+degraded (pipelineState.degraded) → drops the Preview tab, defaults to Audit, retires the amber affordance", () => {
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
    expectFailedTabSet();
  });

  it("terminal+failed with multiple failed agents → still drops the Preview tab + defaults to Audit (no amber affordance)", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        pipelineState={makePipelineState({
          isRunning: false,
          failed: true,
          failedAgents: ["story-writer", "unknown-agent"],
          agents: [makeAgent("story-writer", "Story Writer")],
        })}
      />,
    );
    expectFailedTabSet();
    // The retired affordance means its raw-id / name list no longer renders here.
    expect(screen.queryByText("unknown-agent")).not.toBeInTheDocument();
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

  it("reopen+failed (reopenedRunStatus='failed', no content) → drops the Preview tab, defaults to Audit, retires the amber affordance", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"failed" as WorkflowStatus}
        reopenedFailedAgents={["proto-builder"]}
        reopenedAgentNameById={{ "proto-builder": "Build Agent" }}
      />,
    );
    expectFailedTabSet();
  });

  it("reopen+failed with NO name map → still drops the Preview tab + defaults to Audit (no amber affordance)", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"failed" as WorkflowStatus}
        reopenedFailedAgents={["proto-builder"]}
      />,
    );
    expectFailedTabSet();
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

  it("reopen+degraded (reopenedRunStatus='degraded', no content) → drops the Preview tab, defaults to Audit, retires the amber affordance (WR-01)", () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        isStreaming={false}
        reopenedRunStatus={"degraded" as WorkflowStatus}
        reopenedFailedAgents={["domain-analyst", "story-estimator"]}
      />,
    );
    // WR-01: a degraded reopen with no partial deliverable is a terminal failure —
    // it now drops Preview and lands on Audit (no neutral empty-state, no amber card).
    expectFailedTabSet();
    // A degraded reopen is NOT a cancel — the cancelled copy never appears.
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
