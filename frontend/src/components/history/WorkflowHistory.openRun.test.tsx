/**
 * BUG-002 — a top-nav Run History row tap must open the SHARED run screen
 * (execution-chat-lane + composer) via `onOpenRun`, NOT WorkflowHistory's own
 * divergent internal `RunDetailPage` (one-shot getRunSummary, no SSE, no chat
 * lane → stale QUEUED / "No agent data" / "No preview").
 *
 * The Home-recents path already routes via onOpenRun; the History mount passed no
 * such prop, so `handleSelectRun` fell to `setSelectedRun(run)` → RunDetailPage.
 * These tests pin that a provided `onOpenRun` routes the tap through it (and the
 * internal detail is NOT mounted), the KAN-96 active-run guard still wins, and the
 * legacy `setSelectedRun` fallback survives when `onOpenRun` is absent.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: () => Promise.resolve(),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  getRunSummary: () => Promise.reject(new Error("no summary in this suite")),
}));
// RunDetailPage is the internal-detail marker — its presence proves the tap fell
// through to setSelectedRun (the BUG-002 degraded path) instead of onOpenRun.
vi.mock("./RunDetailPage", () => ({
  RunDetailPage: () => <div data-testid="run-detail-page" />,
}));
vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content }: { content: string }) => <div data-testid="ppt-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: () => <div data-testid="prototype-preview" />,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: () => <div data-testid="markdown-preview" />,
}));
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: () => <div data-testid="appbuilder-preview" />,
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    if (!content) return fallback || "deliverable.md";
    // Stub implementation: return a sensible default based on workflow type
    if (workflowType.includes("user_stories")) return fallback || "user-stories.md";
    if (workflowType.includes("ppt")) return fallback || "presentation.html";
    if (workflowType.includes("prototype")) return fallback || "prototype.html";
    return fallback || "deliverable.md";
  },
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
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
import { WorkflowHistory } from "./WorkflowHistory";
function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-1",
    title: "Shift-scheduling app for cafes",
    type: "user_stories",
    status: "completed",
    input: "A shift-scheduling app for cafes",
    output: "# Stories\n\nSome content...",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: "run-1",
    ...overrides,
  };
}
beforeEach(() => {
  cleanup();
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
});
describe("WorkflowHistory — onOpenRun routing (BUG-002)", () => {
  it("a row tap (id !== activeRunId) calls onOpenRun(run) and does NOT mount the internal RunDetailPage", async () => {
    const run = makeRun();
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    const onOpenRun = vi.fn();
    renderWithProviders(
      <WorkflowHistory
        onBack={vi.fn()}
        onOpenRun={onOpenRun}
        activeRunId="a-different-live-run"
        onViewRunningPipeline={vi.fn()}
      />,
    );
    await userEvent.click(await screen.findByText(run.title));
    await waitFor(() => expect(onOpenRun).toHaveBeenCalledTimes(1));
    expect(onOpenRun).toHaveBeenCalledWith(expect.objectContaining({ id: run.id }));
    // The degraded internal detail is NOT mounted — the shared run screen owns it.
    expect(screen.queryByTestId("run-detail-page")).not.toBeInTheDocument();
  });
  it("KAN-96 — a row whose id === activeRunId still routes via onViewRunningPipeline (not onOpenRun)", async () => {
    const run = makeRun();
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    const onOpenRun = vi.fn();
    const onViewRunningPipeline = vi.fn();
    renderWithProviders(
      <WorkflowHistory
        onBack={vi.fn()}
        onOpenRun={onOpenRun}
        activeRunId={run.id}
        onViewRunningPipeline={onViewRunningPipeline}
      />,
    );
    await userEvent.click(await screen.findByText(run.title));
    await waitFor(() => expect(onViewRunningPipeline).toHaveBeenCalledTimes(1));
    expect(onOpenRun).not.toHaveBeenCalled();
    expect(screen.queryByTestId("run-detail-page")).not.toBeInTheDocument();
  });
  it("legacy fallback — with NO onOpenRun, a tap opens the internal RunDetailPage (unchanged)", async () => {
    const run = makeRun();
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await userEvent.click(await screen.findByText(run.title));
    await waitFor(() => expect(screen.getByTestId("run-detail-page")).toBeInTheDocument());
  });
});
