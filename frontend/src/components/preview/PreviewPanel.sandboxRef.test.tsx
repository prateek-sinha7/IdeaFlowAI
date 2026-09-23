import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// Task U1 — the RunHeader VersionMenu is the ONE version selector for the whole
// run. Picking a tag makes the run view read-only at that ref: the Workspace
// tab (SandboxTab, real/un-mocked here) lists/reads with `ref=<tag>`, and the
// Preview tab fetches + renders the deliverable AT that ref, under a read-only
// banner — with no restore control anywhere. Scaffold mirrors
// PreviewPanel.workspaceDuringRun.test.tsx (SandboxTab left real so its own
// ref-aware fetches are actually exercised).
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetRunSandboxRefs = vi.fn();
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockGetRunSandboxZip = vi.fn();
const mockResolveRunDeliverable = vi.fn();
const mockGetWorkflow = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (...args: unknown[]) => mockGetWorkflow(...args),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunSandboxRefs: (...args: unknown[]) => mockGetRunSandboxRefs(...args),
  getRunSandbox: (...args: unknown[]) => mockGetRunSandbox(...args),
  getRunSandboxFile: (...args: unknown[]) => mockGetRunSandboxFile(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => mockGetRunSandboxFileBlob(...args),
  getRunSandboxZip: (...args: unknown[]) => mockGetRunSandboxZip(...args),
  resolveRunDeliverable: (...args: unknown[]) => mockResolveRunDeliverable(...args),
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

// T7 — renders its `content` prop (rather than a static stub) so a test can
// assert on the actual rendered text, not just that the component mounted.
vi.mock("./UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content?: string }) => (
    <div data-testid="user-story-preview">{content}</div>
  ),
}));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  downloadBlob: vi.fn(),
  deriveDeliverableFilename: () => "prototype.html",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const SETTLED_STATE = {
  isRunning: false,
  pipelineRunId: "run-1",
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

// T7 — a reopened/history run's own deliverable_filename never streamed into
// THIS browser session's pipelineState (the same reopen gap ISS-017/ISS-609's
// reopenedRunStatus/reopenedAgentNameById props exist to cover elsewhere for
// other surfaces) — deliverableFilename is absent here on purpose.
const REOPENED_STATE = {
  isRunning: false,
  pipelineRunId: "run-1",
  pipeline_type: "user_stories",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
} as unknown as PipelineRunState;

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({
    run_id: "run-1",
    expired: false,
    truncated: false,
    files: [{ path: "notes.md", size: 20, modified: 1, text: true, kind: "text", deliverable: true }],
  });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("some file content");
  mockGetRunSandboxFileBlob.mockReset();
  mockGetRunSandboxZip.mockReset();
  mockResolveRunDeliverable.mockReset().mockResolvedValue({
    path: "prototype.html",
    size: 10,
    modified: 1,
    text: true,
    kind: "text",
    deliverable: true,
  });
});

describe("Task U1 — version menu ref-view (Preview + Workspace tabs)", () => {
  it("selecting v1 fetches the deliverable at ref=v1, shows a read-only banner, and has no restore control", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId="run-1"
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));

    // Open the RunHeader VersionMenu and pick v1.
    const chip = screen.getByRole("button", { name: /^v1\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));

    // The deliverable fetch for the Preview tab carries ref=v1 (task U1 item 4).
    await waitFor(() =>
      expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "prototype.html", "v1"),
    );

    // A read-only banner renders …
    const banner = screen.getByRole("status");
    expect(within(banner).getByText(/Viewing v1/)).toBeInTheDocument();
    expect(within(banner).getByText(/read-only/i)).toBeInTheDocument();
    // … and no restore control exists anywhere on screen.
    expect(screen.queryByText(/restore/i)).toBeNull();
  });

  it("the Workspace tab's file list and file read carry ref=v1 while v1 is selected", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId="run-1"
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));

    const chip = screen.getByRole("button", { name: /^v1\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));

    // Switch to the Workspace tab.
    await userEvent.click(screen.getByTestId("tab-workspace"));

    // The file LIST carries ref=v1.
    await waitFor(() =>
      expect(mockGetRunSandbox).toHaveBeenCalledWith("test-token", "run-1", "v1"),
    );

    // Opening a file — the file READ carries ref=v1 too.
    await waitFor(() => expect(screen.getByText("notes.md")).toBeInTheDocument());
    await userEvent.click(screen.getByText("notes.md"));
    await waitFor(() =>
      expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "notes.md", "v1"),
    );

    // Same read-only signal on the Workspace tab; still no restore control.
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.queryByText(/restore/i)).toBeNull();
  });

  it("Latest (live) drops the ref and returns to the live deliverable/tree", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId="run-1"
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));

    const chip = screen.getByRole("button", { name: /^v1\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));
    await waitFor(() =>
      expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "prototype.html", "v1"),
    );
    const banner = screen.getByRole("status");
    expect(within(banner).getByText(/Viewing v1/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    expect(screen.queryByRole("status")).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// T7 — a family with two real, differently-content'd tags (v1/v2) reopened
// without a live-streamed pipelineState (SETTLED_STATE above always carried
// deliverableFilename directly — the one shape that never hit the bug). This
// reproduces the reported defect: banner switches correctly, but the body was
// stuck on "Loading v2…" forever because `declared` fell straight to null,
// which routed the effect into the ISS-313 bundle branch and never populated
// `deliverableFile` — so the ref-scoped `getRunSandboxFile` fetch, gated on
// `deliverableFile`, never fired at all (confirmed failing pre-fix below).
// ─────────────────────────────────────────────────────────────────────────────
describe("T7 — ref-scoped preview loads when pipelineState never carried the deliverable name (reopened run)", () => {
  it("selecting v1 reads the deliverable AT ref=v1 and renders that version's content; Latest renders the live content again", async () => {
    mockGetWorkflow.mockResolvedValue({ deliverableFilename: "user_stories.md" });
    mockResolveRunDeliverable.mockResolvedValue({
      path: "user_stories.md",
      size: 10,
      modified: 1,
      text: true,
      kind: "text",
      deliverable: true,
    });
    mockGetRunSandboxFile.mockImplementation(
      (_token: string, _runId: string, _path: string, ref?: string) =>
        Promise.resolve(ref === "v1" ? "# Content for v1" : "# Content for v2"),
    );

    render(
      <PreviewPanel
        workflowType="user_stories"
        userStoryContent="# Live content"
        pipelineState={REOPENED_STATE}
        liveRunId="run-1"
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));
    expect(await screen.findByText("# Live content")).toBeInTheDocument();

    const chip = screen.getByRole("button", { name: /^v1\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));

    // pipelineState carried no declared name — the effect must fall back to
    // the run's own persisted deliverable_filename before it can resolve one.
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "run-1"));

    // The ref-scoped read actually fires, carrying ref=v1 — this is the
    // request the pre-fix code never issued at all.
    await waitFor(() =>
      expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "user_stories.md", "v1"),
    );

    // v1's OWN content renders — not a stuck "Loading v1…" and not the live content.
    expect(await screen.findByText("# Content for v1")).toBeInTheDocument();
    expect(screen.queryByText(/Loading v1/)).toBeNull();
    expect(screen.queryByText("# Live content")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    expect(await screen.findByText("# Live content")).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// B22 regression guard — version menu pins the Steps tab (and all pipeline
// data) to the selected version's run, not just the Workspace files.
//
// Root cause (BUG-124): handleVersionMenuSelect only called setSandboxSelectedRef
// and never routed through handleSelectVersion, so viewingVersion was never set
// and the Steps/agents/outputs always showed the live run.
//
// This test confirms:
// 1. When a tag is selected via the VersionMenu and runFamily carries a member
//    with that git_tag, getWorkflow is called with that MEMBER'S run UUID —
//    proving handleSelectVersion was reached (it is the only caller of getWorkflow
//    via the version-pin path) and will set viewingVersion.
// 2. The sandbox ref survives the activeRunId-change reset — getRunSandboxFile is
//    still called with ref=v1, confirming intendedSandboxRef preserved the tag
//    through the reset effect.
// ─────────────────────────────────────────────────────────────────────────────
describe("B22 regression guard — version menu calls handleSelectVersion with the member UUID", () => {
  it("selecting v1 calls getWorkflow with the v1 member UUID and keeps ref=v1 for file reads", async () => {
    const V1_MEMBER_ID = "member-uuid-v1";
    const V2_MEMBER_ID = "member-uuid-v2";

    // runFamily with two members, each carrying their git_tag.
    const runFamily = {
      root_id: V1_MEMBER_ID,
      members: [
        {
          id: V1_MEMBER_ID,
          type: "prototype",
          title: "v1 run",
          status: "completed",
          revision_index: 1,
          parent_run_id: null,
          created_at: "2026-09-01T00:00:00Z",
          completed_at: "2026-09-01T01:00:00Z",
          git_tag: "v1",
        },
        {
          id: V2_MEMBER_ID,
          type: "prototype",
          title: "v2 run",
          status: "completed",
          revision_index: 2,
          parent_run_id: V1_MEMBER_ID,
          created_at: "2026-09-02T00:00:00Z",
          completed_at: "2026-09-02T01:00:00Z",
          git_tag: "v2",
        },
      ],
    };

    // getWorkflow returns a minimal run record for the v1 member.
    mockGetWorkflow.mockImplementation((_token: string, runId: string) => {
      if (runId === V1_MEMBER_ID) {
        return Promise.resolve({
          id: V1_MEMBER_ID,
          output: "<html>v1 content</html>",
          agentOutputs: [],
          tokenUsage: null,
          status: "completed",
        });
      }
      return Promise.resolve(null);
    });

    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live content</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_MEMBER_ID}
        runFamily={runFamily}
      />,
    );

    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", V2_MEMBER_ID));

    // Open the RunHeader VersionMenu and pick v1.
    const chip = screen.getByRole("button", { name: /^v2\b/ });
    await userEvent.click(chip);
    await userEvent.click(screen.getByRole("option", { name: "v1" }));

    // --- B22 regression check 1: handleSelectVersion was invoked --------
    // getWorkflow must be called with the V1 MEMBER UUID, not the tag string "v1".
    // Pre-fix: handleVersionMenuSelect only called setSandboxSelectedRef("v1") and
    // never called handleSelectVersion, so getWorkflow was never invoked at all.
    await waitFor(
      () => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_MEMBER_ID),
      { timeout: 2000 },
    );

    // --- B22 regression check 2: sandboxSelectedRef survived the reset ---
    // intendedSandboxRef must have carried the tag through the activeRunId-change
    // reset effect. Evidence: the deliverable file fetch carries ref=v1.
    await waitFor(
      () =>
        expect(mockGetRunSandboxFile).toHaveBeenCalledWith(
          "test-token", V2_MEMBER_ID, "prototype.html", "v1",
        ),
      { timeout: 2000 },
    );

    // A read-only banner renders and no restore control is shown.
    // There may be two role="status" elements (version chip + banner strip) — find the banner strip.
    const banners = screen.getAllByRole("status");
    const banner = banners.find((el) => el.textContent?.includes("read-only")) ?? banners[0];
    expect(banner.textContent).toMatch(/Viewing v1/);
    expect(screen.queryByText(/restore/i)).toBeNull();
  });
});
