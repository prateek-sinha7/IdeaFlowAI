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

// ─────────────────────────────────────────────────────────────────────────────
// PreviewChrome (Phase 39, RUNUI-06/07) — the browser-chrome frame wrapping the
// REUSED deliverable renderer (ND-G), the real-filename URL bar + the live
// "Renders as" switch (ND-D), the streaming build affordance (progress bar +
// building URL, no image-slot per ND-F), and the preserved failed degraded card.
// ─────────────────────────────────────────────────────────────────────────────
describe("PreviewPanel — Phase 39 Preview browser chrome", () => {
  const settledState = {
    isRunning: false,
    pipeline_type: "prototype",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    deliverableFilename: "apple-reference-prototype.html",
  } as unknown as PipelineRunState;

  it("frames a PLAIN (non-self-chromed) deliverable in the browser chrome with the REAL live filename (ND-D/ND-G)", () => {
    // user_stories is NOT self-chromed → it keeps our PreviewChrome browser frame.
    render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# stories" pipelineState={settledState} />,
    );
    const chrome = screen.getByTestId("preview-chrome");
    expect(chrome).toBeInTheDocument();
    // The URL bar shows the real live filename — never the mock's fixed index.html.
    expect(screen.getByTestId("preview-url")).toHaveTextContent("apple-reference-prototype.html");
    // ND-G — the REUSED renderer is slotted INSIDE the chrome, unchanged.
    expect(chrome).toContainElement(screen.getByTestId("user-story-preview"));
  });

  it("renders a SELF-CHROMED type (prototype) in its OWN frame — no browser chrome — keeping the Renders-as switch (ND-J)", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" pipelineState={settledState} />);
    // ND-J (Option B): prototype brings its own frame → our PreviewChrome is absent.
    expect(screen.queryByTestId("preview-chrome")).toBeNull();
    // …but the "Renders as" switch still sits above the renderer.
    expect(screen.getByTestId("renders-as-switch")).toBeInTheDocument();
    expect(screen.getByTestId("proto-preview")).toBeInTheDocument();
  });

  it("renders a SELF-CHROMED type (app_builder IDE) in its OWN frame — no browser chrome (ND-J)", () => {
    render(
      <PreviewPanel
        workflowType="app_builder"
        userStoryContent={"```filename: a.ts\nconst a = 1;\n```"}
        pipelineState={settledState}
      />,
    );
    expect(screen.queryByTestId("preview-chrome")).toBeNull();
    expect(screen.getByTestId("appbuilder-preview")).toBeInTheDocument();
  });

  it("offers a 'Renders as' switch with ONLY the deliverable's live typed renderers (ND-D — not the mock's fixed 5-way)", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" />);
    expect(screen.getByTestId("renders-as-switch")).toBeInTheDocument();
    const pills = screen.getAllByTestId("renderer-pill").map((p) => p.textContent?.trim());
    // Auto + the one typed renderer genuinely available for a prototype deliverable.
    expect(pills).toEqual(["Auto", "Prototype"]);
    // The mock's hardcoded 5-way labels never appear.
    expect(screen.queryByText("Deck")).toBeNull();
    expect(screen.queryByText("App code")).toBeNull();
    expect(screen.queryByText("Doc")).toBeNull();
  });

  it("shows the streaming build chrome — a 'building …' URL + top progress bar, no settled switch row (ND-F: no image-slot)", () => {
    const streamingState = { ...settledState, isRunning: true } as unknown as PipelineRunState;
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>partial…</html>"
        pipelineState={streamingState}
        isStreaming
      />,
    );
    const chrome = screen.getByTestId("preview-chrome");
    expect(chrome).toHaveAttribute("data-streaming", "true");
    expect(screen.getByTestId("preview-url")).toHaveTextContent("building apple-reference-prototype.html");
    expect(screen.getByTestId("preview-progress")).toBeInTheDocument();
    // Streaming omits the settled "Renders as" switch row.
    expect(screen.queryByTestId("renders-as-switch")).toBeNull();
  });

  it("keeps the degraded affordance UNWRAPPED (no chrome) for a terminal-failed, empty run", () => {
    const failedState = {
      isRunning: false,
      failed: true,
      pipeline_type: "prototype",
      agents: [],
      currentAgentIndex: 0,
      totalDuration: null,
      completedCount: 0,
      failedAgents: ["prototype-build"],
    } as unknown as PipelineRunState;
    render(<PreviewPanel workflowType="prototype" pipelineState={failedState} />);
    // The failed mock shows the degraded card, NOT a chromed preview.
    expect(screen.queryByTestId("preview-chrome")).toBeNull();
    expect(screen.getByText(/did not complete successfully/i)).toBeInTheDocument();
  });
});
