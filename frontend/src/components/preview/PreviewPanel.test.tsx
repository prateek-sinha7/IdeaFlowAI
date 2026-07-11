import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import type { GateContext } from "@/components/chat/RunChatLane";
import type { PipelineRunState, RunFamily, WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// PreviewPanel (Phase 39, RUNUI-06) — the run-header + tab-row integration specs:
// the corrected tab order (Preview · Steps · Files · Audit), the SINGLE version
// affordance (INV-3 — the old in-preview pill is retired), and the Steps review
// dot while the run is paused. Scaffold mirrors PreviewPanel.versionChip.test.tsx.
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
}));

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

vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  downloadBlob: vi.fn(),
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
const family2: RunFamily = {
  root_id: "root",
  members: [
    { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
    { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  ],
};

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunFamily.mockReset();
});

describe("PreviewPanel — Phase 39 run header + tabs", () => {
  it("tab order is Preview · Steps · Files · Audit (the Steps tab keeps the 'thinking' testid)", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent?.trim())).toEqual(["Preview", "Steps", "Files", "Audit"]);
    // The relabelled Steps tab still resolves to the stable "thinking" id.
    expect(screen.getByTestId("tab-thinking")).toHaveTextContent("Steps");
  });

  it("mounts the run header and exactly ONE version affordance (INV-3) in the settled state", () => {
    render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={family2} liveRunId="r1" />,
    );
    expect(screen.getByTestId("run-header")).toBeInTheDocument();
    // Exactly one version-menu affordance — the retired LiveVersionChip pill is gone.
    expect(screen.getAllByLabelText(/choose version/)).toHaveLength(1);
    expect(screen.getByLabelText(/Version v2, choose version/)).toBeInTheDocument();
  });

  it("shows the Steps review dot while the run is paused on a review gate", () => {
    const gate: GateContext = {
      agentId: "a1", agentName: "Planner", output: "plan", gateKey: "g1",
    };
    const pipelineState = { isRunning: true, pipeline_type: "prototype", agents: [], currentAgentIndex: 0, totalDuration: null, completedCount: 0 } as unknown as PipelineRunState;
    render(
      <PreviewPanel
        workflowType="prototype"
        pipelineState={pipelineState}
        laneGate={gate}
        runFamily={family2}
        liveRunId="r1"
      />,
    );
    expect(screen.getByTestId("run-header")).toHaveAttribute("data-run-state", "gate");
    expect(screen.getByTestId("steps-review-dot")).toBeInTheDocument();
  });

  it("does NOT show the review dot for a settled run", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" />);
    expect(screen.queryByTestId("steps-review-dot")).toBeNull();
    expect(screen.getByTestId("run-header")).toHaveAttribute("data-run-state", "complete");
  });
});
