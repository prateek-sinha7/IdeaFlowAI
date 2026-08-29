import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// BUG-20260828-013500-runs-id-workspace / ISS-598.
//
// PreviewPanel.tsx:753-755 gates the Workspace tab purely on `workspaceRunId`
// truthiness — no run-status check — and `workspaceRunId` falls back to
// `pipelineState.pipelineRunId`, the SAME object `isStillRunning` reads. So a
// run that is still actively generating reaches the identical unguarded
// CodeView (SandboxTab.tsx:675-701, ISS-383) as a completed one: no read-only
// indicator, live contenteditable text. Scaffold mirrors PreviewPanel.test.tsx,
// but SandboxTab is left UN-mocked (unlike that file) because this spec
// exercises its real editor DOM.
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockGetRunSandboxZip = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: vi.fn(),
  getRunFamily: vi.fn(),
  getRunSandbox: (...args: unknown[]) => mockGetRunSandbox(...args),
  getRunSandboxFile: (...args: unknown[]) => mockGetRunSandboxFile(...args),
  getRunSandboxFileBlob: (...args: unknown[]) => mockGetRunSandboxFileBlob(...args),
  getRunSandboxZip: (...args: unknown[]) => mockGetRunSandboxZip(...args),
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
  deriveDeliverableFilename: () => "deliverable",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const RUNNING_STATE = {
  isRunning: true,
  pipelineRunId: "live-run-1",
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: 0,
  totalDuration: null,
  completedCount: 0,
} as unknown as PipelineRunState;

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetRunSandbox.mockReset();
  mockGetRunSandboxFile.mockReset();
  mockGetRunSandboxFileBlob.mockReset();
  mockGetRunSandboxZip.mockReset();
});

describe("Workspace tab on a still-running run (ISS-598)", () => {
  it("ISS-598: reaches the SAME unguarded, indicator-less CodeView while the run is still generating", async () => {
    mockGetRunSandbox.mockResolvedValue({
      run_id: "live-run-1",
      expired: false,
      truncated: false,
      files: [{ path: "PLANNER.md", size: 40, modified: 1, text: true, kind: "text", deliverable: false }],
    });
    mockGetRunSandboxFile.mockResolvedValue("# Plan\n\nSome notes so far.\n");

    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>partial</html>"
        pipelineState={RUNNING_STATE}
        isStreaming
      />,
    );

    // The run is still generating, not settled — but the Workspace tab is
    // present and reachable regardless (PreviewPanel.tsx:753-755, no status gate).
    const tab = screen.getByTestId("tab-workspace");
    expect(tab).toBeInTheDocument();
    await userEvent.click(tab);

    await waitFor(() => expect(screen.getByText("PLANNER.md")).toBeInTheDocument());
    await userEvent.click(screen.getByText("PLANNER.md"));
    // The file agent has already written is a still-open markdown draft — toggle
    // to the Code surface (ISS-383's exact call site), reached here mid-run.
    await waitFor(() => expect(screen.getByRole("button", { name: /^code$/i })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /^code$/i }));
    await waitFor(() => expect(document.querySelector(".cm-editor")).toBeTruthy());

    // Identical defect as ISS-383/ISS-597 on a completed run: a live,
    // typeable pane with no read-only/scratchpad indication anywhere,
    // reached here on a run that is STILL WRITING files.
    expect(document.querySelector(".cm-content")?.getAttribute("contenteditable")).toBe("true");
    expect(document.body.textContent).toMatch(/read.only|scratchpad|not saved|preview only|view.only/i);
  });
});
