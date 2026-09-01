import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockDownloadBlob = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
  getRunSandbox: (token: string, id: string) => mockGetRunSandbox(token, id),
  getRunSandboxFileBlob: (token: string, id: string, path: string) =>
    mockGetRunSandboxFileBlob(token, id, path),
  // ISS-251: resolveRunDeliverable is now called by PreviewPanel instead of
  // re-implementing the sibling-preference rule inline. Route through the same
  // mockGetRunSandbox the old inline code used, so all existing download tests
  // work unchanged — their sandbox stubs already encode the expected results.
  resolveRunDeliverable: async (token: string, runId: string, declared?: string | null) => {
    if (!declared) return null;
    const listing = await mockGetRunSandbox(token, runId);
    const dot = declared.lastIndexOf(".");
    const stem = dot > 0 ? declared.slice(0, dot) : declared;
    const ext = dot > 0 ? declared.slice(dot + 1).toLowerCase() : "";
    const candidates = [...new Set(
      ext === "html" ? [`${stem}.pptx`, declared]
      : ext === "pptx" ? [declared, `${stem}.html`]
      : [declared],
    )];
    return candidates
      .map((c: string) => (listing.files as Array<{ path: string }>).find((f) => f.path === c))
      .find(Boolean) ?? null;
  },
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
  downloadBlob: (...a: unknown[]) => mockDownloadBlob(...a),
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    // Simplified stub that dispatches on workflow type like the real function
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      if (!content) return fallback || "user-stories.md";
      const match = content.match(/^#\s+(.+)/m);
      if (match) return match[1].toLowerCase() + ".md";
      return fallback || "user-stories.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      if (!content) return fallback || "presentation.html";
      if (content.match(/<title>/i) || content.match(/<h1[^>]*>/i)) return "presentation.html";
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      if (!content) return fallback || "prototype.html";
      if (content.match(/<title>/i)) return "prototype.html";
      return fallback || "prototype.html";
    }
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") return "project.zip";
    return fallback || "deliverable";
  },
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

  it("shows Workspace as soon as a run id is known, not after the detail fetch", () => {
    // The tab is dropped while `workspaceRunId` is null. On a history reopen the
    // id used to be published only after `getWorkflow` resolved, so Workspace
    // appeared ~2s behind the other four and read as a broken tab.
    render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" liveRunId="r1" />,
    );
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent?.trim());
    expect(tabs).toEqual(["Preview", "Steps", "Files", "Workspace", "Audit"]);
  });

  it("drops Workspace only when there is no run id at all", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" />);
    expect(screen.queryByTestId("tab-workspace")).toBeNull();
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
    // Use realistic data: workflow type matches deliverable (user_stories → .md file).
    render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# stories" pipelineState={{ ...settledState, deliverableFilename: "stories.md" }} />,
    );
    const chrome = screen.getByTestId("preview-chrome");
    expect(chrome).toBeInTheDocument();
    // The URL bar shows the real live filename — derived from the content (# stories → stories.md).
    expect(screen.getByTestId("preview-url")).toHaveTextContent("stories.md");
    // ND-G — the REUSED renderer is slotted INSIDE the chrome, unchanged.
    expect(chrome).toContainElement(screen.getByTestId("user-story-preview"));
  });

  it("renders a SELF-CHROMED type (prototype) in its OWN frame — no browser chrome — keeping the Renders-as switch (ND-V)", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" pipelineState={settledState} />);
    // ND-V (Option B): prototype brings its own frame → our PreviewChrome is absent.
    expect(screen.queryByTestId("preview-chrome")).toBeNull();
    // …but the "Renders as" switch still sits above the renderer.
    expect(screen.getByTestId("renders-as-switch")).toBeInTheDocument();
    expect(screen.getByTestId("proto-preview")).toBeInTheDocument();
  });

  it("renders a SELF-CHROMED type (app_builder IDE) in its OWN frame — no browser chrome (ND-V)", () => {
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

  it("a ppt_v2 deliverable renders through the Slides renderer, with no generic mimetype pills", () => {
    // spec 017 — ppt_v2 is the SAME HTML deck as ppt (it only ALSO emits a .pptx),
    // so it normalizes to renderType "ppt" and belongs in the pptContent slot.
    // It used to be routed into the GENERIC deliverable channel by page.tsx (whose
    // dispatch listed only "ppt"/"ppt_revision"), which left Auto and Slides empty
    // and made the accidental HTML/Markdown/Bundle pills the only thing that worked.
    render(<PreviewPanel workflowType={"ppt_v2" as never} pptContent="<html>deck</html>" />);
    expect(screen.getByTestId("ppt-preview")).toBeInTheDocument();
    const pills = screen.getAllByTestId("renderer-pill").map((p) => p.textContent?.trim());
    expect(pills).toEqual(["Auto", "Slides"]);
  });

  // ── Header Download — the workflow's DECLARED file, from the workspace ──────
  // Every workflow.yaml names what it delivers (prototype → prototype.html), the
  // engine emits that literal on pipeline_complete, and this button serves THAT
  // FILE. It used to rebuild one from on-screen content and name it from a
  // <title>, so the declaration lost to a guess and the bytes came from what the
  // panel held rather than from what the run wrote.
  const dlProps = {
    workflowType: "prototype" as const,
    prototypeContent: "<html><head><title>Bespoke Facebook · Sprint 8</title></head></html>",
    liveRunId: "run-1",
    pipelineState: { ...settledState, deliverableFilename: "prototype.html" },
  };

  it("Download is DISABLED until the declared file exists in the workspace", async () => {
    mockGetRunSandbox.mockResolvedValue({
      run_id: "run-1", expired: false, truncated: false,
      files: [{ path: "spec.md", size: 10, modified: 0, text: true }],
    });
    render(<PreviewPanel {...dlProps} />);
    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(mockGetRunSandbox).toHaveBeenCalled());
    expect(btn).toBeDisabled();
  });

  it("Download serves the declared workspace file, not a name derived from content", async () => {
    mockGetRunSandbox.mockResolvedValue({
      run_id: "run-1", expired: false, truncated: false,
      files: [
        { path: "spec.md", size: 10, modified: 0, text: true },
        { path: "prototype.html", size: 34_000, modified: 0, text: true },
      ],
    });
    mockGetRunSandboxFileBlob.mockResolvedValue(new Blob(["<html></html>"], { type: "text/html" }));
    mockDownloadBlob.mockClear();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

    render(<PreviewPanel {...dlProps} />);
    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);

    // The run's OWN bytes, read from the workspace — not the on-screen content.
    await waitFor(() =>
      expect(mockGetRunSandboxFileBlob).toHaveBeenCalledWith("test-token", "run-1", "prototype.html"),
    );
    // …saved under the DECLARED name, not "bespoke-facebook-sprint-8.html"
    // derived from the deck's <title>.
    await waitFor(() =>
      expect(mockDownloadBlob).toHaveBeenCalledWith("blob:mock", "prototype.html", "text/html"),
    );
    vi.restoreAllMocks();
  });

  it("prefers the editable .pptx over the declared .html when the run wrote both", async () => {
    // ppt_v2 declares presentation.html (that declaration also drives Preview's
    // mimetype and its render-step-failed fallback, so it stays as it is), but
    // the file you send is the PowerPoint. Keyed on the EXTENSION, not the
    // workflow name.
    mockGetRunSandbox.mockResolvedValue({
      run_id: "run-1", expired: false, truncated: false,
      files: [
        { path: "presentation.html", size: 30_000, modified: 0, text: true },
        { path: "presentation.pptx", size: 90_000, modified: 0, text: false },
      ],
    });
    mockGetRunSandboxFileBlob.mockResolvedValue(new Blob(["x"], { type: "application/vnd.ms-powerpoint" }));
    render(
      <PreviewPanel
        workflowType={"ppt_v2" as never}
        pptContent="<html><title>Deck</title></html>"
        liveRunId="run-1"
        pipelineState={{ ...settledState, deliverableFilename: "presentation.html" }}
      />,
    );
    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);
    await waitFor(() =>
      expect(mockGetRunSandboxFileBlob).toHaveBeenCalledWith("test-token", "run-1", "presentation.pptx"),
    );
  });

  it("falls back to the deck when the declared .pptx was never written (plain ppt)", async () => {
    // `ppt` declares presentation.pptx while nothing in it emits PptxGenJS, so
    // that file is never on disk and the button used to be dead. Same-stem
    // fallback gives you the deck the run actually produced.
    mockGetRunSandbox.mockResolvedValue({
      run_id: "run-1", expired: false, truncated: false,
      files: [{ path: "presentation.html", size: 30_000, modified: 0, text: true }],
    });
    render(
      <PreviewPanel
        workflowType="ppt"
        pptContent="<html><title>Deck</title></html>"
        liveRunId="run-1"
        pipelineState={{ ...settledState, deliverableFilename: "presentation.pptx" }}
      />,
    );
    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    fireEvent.click(btn);
    await waitFor(() =>
      expect(mockGetRunSandboxFileBlob).toHaveBeenCalledWith("test-token", "run-1", "presentation.html"),
    );
  });

  it("considers NO sibling for a non-deck deliverable", async () => {
    // Scoped by the declared EXTENSION, not the workflow name: only a .html or
    // .pptx declaration asks a deck question. A .md deliverable resolves to
    // itself and nothing else, so a stray same-stem file can never be served in
    // its place.
    mockGetRunSandbox.mockResolvedValue({
      run_id: "run-1", expired: false, truncated: false,
      files: [
        { path: "user_stories.pptx", size: 1, modified: 0, text: false },
        { path: "user_stories.html", size: 1, modified: 0, text: true },
      ],
    });
    render(
      <PreviewPanel
        workflowType="user_stories"
        userStoryContent="# stories"
        liveRunId="run-1"
        pipelineState={{ ...settledState, deliverableFilename: "user_stories.md" }}
      />,
    );
    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(mockGetRunSandbox).toHaveBeenCalled());
    // The declared .md is absent, and neither sibling is a candidate.
    expect(btn).toBeDisabled();
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
    // Phase 42-02 (§B): a live/building run now auto-lands on the Steps tab, so
    // select Preview to assert its streaming build chrome (still hosted there).
    fireEvent.click(screen.getByTestId("tab-preview"));
    const chrome = screen.getByTestId("preview-chrome");
    expect(chrome).toHaveAttribute("data-streaming", "true");
    expect(screen.getByTestId("preview-url")).toHaveTextContent("building apple-reference-prototype.html");
    expect(screen.getByTestId("preview-progress")).toBeInTheDocument();
    // Streaming omits the settled "Renders as" switch row.
    expect(screen.queryByTestId("renders-as-switch")).toBeNull();
  });

  it("Group D: a terminal-failed empty run drops the Preview tab, defaults to Audit, and retires the amber DegradedRunAffordance on the run screen", () => {
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
    // The Failed mock has NO Preview surface — the tab set is [Steps, Audit, Files].
    expect(screen.queryByTestId("tab-preview")).toBeNull();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent?.trim())).toEqual(["Steps", "Files", "Audit"]);
    // It defaults to Audit (Hexaware Run - Failed tab:'audit').
    expect(screen.getByTestId("tab-audit")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("audit-tab")).toBeInTheDocument();
    // The amber DegradedRunAffordance is retired on the run screen (red lives in
    // the lane/Steps/header per §4 KEEP); no chromed preview either.
    expect(screen.queryByText(/did not complete successfully/i)).toBeNull();
    expect(screen.queryByTestId("preview-chrome")).toBeNull();
    // The RunHeader still reads the red failed state (§4 KEEP — unchanged).
    expect(screen.getByTestId("run-header")).toHaveAttribute("data-run-state", "terminal");
  });

  it("Group D: a NON-failed settled run keeps all four tabs and defaults to Preview", () => {
    const settled = {
      isRunning: false,
      pipeline_type: "prototype",
      agents: [],
      currentAgentIndex: 0,
      totalDuration: null,
      completedCount: 0,
    } as unknown as PipelineRunState;
    render(
      <PreviewPanel workflowType="prototype" prototypeContent="<html>ok</html>" pipelineState={settled} />,
    );
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent?.trim())).toEqual(["Preview", "Steps", "Files", "Audit"]);
    expect(screen.getByTestId("tab-preview")).toHaveAttribute("aria-selected", "true");
  });
});
