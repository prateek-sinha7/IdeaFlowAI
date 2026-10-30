/**
 * PreviewPanel — the deliverable lookup for a settled (finished) reopen (plan D8),
 * and the tab it holds while a finished run's data lands.
 *
 * The header Download is gated on the run's declared deliverable existing in the
 * workspace. For a run the page reopened as finished (`settledRun`), the declared
 * filename comes from the record the page already fetched, so PreviewPanel must
 * not refetch the run record (the heavy one was megabytes), and must not repeat
 * the lookup on every pipelineState change. A settled "completed" run with no
 * inline content (deliverable only in the workspace) must still resolve: the old
 * `reopenedRunStatus === "completed"` branch could never fire, because the page
 * never sets that status for a completed run.
 *
 * Mocked at the system boundary (@/lib/api) plus the heavy preview leaves.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";

const mockGetWorkflow = vi.fn();
const mockResolveRunDeliverable = vi.fn();
const mockGetRunSandbox = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflow: (...args: unknown[]) => mockGetWorkflow(...args),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunArtifacts: vi.fn().mockResolvedValue({ artifacts: [] }),
  getRunSandboxRefs: vi.fn().mockResolvedValue([]),
  getRunSandbox: (...args: unknown[]) => mockGetRunSandbox(...args),
  getRunSandboxFile: vi.fn().mockResolvedValue(""),
  getRunSandboxFileBlob: vi.fn(),
  getRunSandboxZip: vi.fn(),
  resolveRunDeliverable: (...args: unknown[]) => mockResolveRunDeliverable(...args),
  authedFetch: vi.fn(),
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
  deriveDeliverableFilename: () => "stories.md",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";
import type { AgentRunState, PipelineRunState, SettledReopen } from "@/types/index";

const RUN_ID = "r1";

function pipeline(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
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

function doneAgent(id: string, index: number): AgentRunState {
  return { id, name: id, role: "r", icon: "i", status: "done", output: `${id} out`, thinking: "", duration: 1, error: null, index };
}

const settled = (overrides: Partial<SettledReopen> = {}): SettledReopen => ({
  runId: RUN_ID,
  status: "completed",
  deliverableFilename: "stories.md",
  ...overrides,
});

const HIT = { path: "stories.md", size: 10, modified: 1, text: true, kind: "text", deliverable: true };

beforeEach(() => {
  mockGetWorkflow.mockReset().mockResolvedValue({ id: RUN_ID, deliverableFilename: "stories.md" });
  mockResolveRunDeliverable.mockReset().mockResolvedValue(HIT);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: RUN_ID, expired: false, truncated: false, files: [] });
});

describe("PreviewPanel settled-run deliverable lookup", () => {
  it("resolves the declared file once without refetching the run record when the settled reopen names it", async () => {
    render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories" pipelineState={pipeline()}
        liveRunId={RUN_ID} settledRun={settled()} />,
    );

    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledTimes(1));
    expect(mockResolveRunDeliverable).toHaveBeenCalledWith("test-token", RUN_ID, "stories.md", undefined);
    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });

  it("does not repeat the lookup when only pipelineState changes", async () => {
    const view = render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories" pipelineState={pipeline()}
        liveRunId={RUN_ID} settledRun={settled()} />,
    );
    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledTimes(1));

    view.rerender(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories"
        pipelineState={pipeline({ agents: [doneAgent("a1", 0)], completedCount: 1 })}
        liveRunId={RUN_ID} settledRun={settled()} />,
    );
    view.rerender(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories"
        pipelineState={pipeline({ agents: [doneAgent("a1", 0), doneAgent("a2", 1)], completedCount: 2 })}
        liveRunId={RUN_ID} settledRun={settled()} />,
    );

    // Let any re-run effect issue its request before counting.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mockResolveRunDeliverable).toHaveBeenCalledTimes(1);
    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });

  it("still resolves a settled completed run that has no inline content", async () => {
    // A workspace-only deliverable leaves the header state "idle"; the settled
    // record's "completed" status is what makes the lookup run.
    render(
      <PreviewPanel workflowType="backlog" pipelineState={pipeline({ pipeline_type: "backlog" })}
        liveRunId={RUN_ID} settledRun={settled({ deliverableFilename: "Backlog.pdf" })} />,
    );

    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledTimes(1));
    expect(mockResolveRunDeliverable).toHaveBeenCalledWith("test-token", RUN_ID, "Backlog.pdf", undefined);
    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });

  it("serves the workspace bundle for a settled run that declares no file, still without the record", async () => {
    render(
      <PreviewPanel workflowType="backlog" pipelineState={pipeline({ pipeline_type: "backlog" })}
        liveRunId={RUN_ID} settledRun={settled({ deliverableFilename: null })} />,
    );

    await waitFor(() => expect(mockGetRunSandbox).toHaveBeenCalledWith("test-token", RUN_ID, undefined));
    expect(mockGetWorkflow).not.toHaveBeenCalled();
    expect(mockResolveRunDeliverable).not.toHaveBeenCalled();
  });

  it("asks for the slim record only when neither the stream nor a settled record declares the file", async () => {
    render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories" pipelineState={pipeline()}
        liveRunId={RUN_ID} />,
    );

    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledTimes(1));
    expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", RUN_ID, false);
    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledTimes(1));
  });

  it("ignores a settled record that belongs to another run", async () => {
    render(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories" pipelineState={pipeline()}
        liveRunId={RUN_ID} settledRun={settled({ runId: "other", deliverableFilename: "other.md" })} />,
    );

    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", RUN_ID, false));
    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledWith("test-token", RUN_ID, "stories.md", undefined));
  });
});

describe("PreviewPanel tab through a finished-run reopen", () => {
  it("keeps the Preview tab selected from loading through the final agents", async () => {
    // The prop sequence page.tsx now produces for a finished run: the record in
    // flight, then content with the trace still loading, then the final agents
    // in one batch. isRunning is never true.
    const view = render(
      <PreviewPanel workflowType="user_stories" pipelineState={pipeline()} liveRunId={RUN_ID}
        isLoadingRunData isLoadingRunTrace />,
    );
    expect(screen.getByTestId("tab-preview")).toHaveAttribute("aria-selected", "true");

    view.rerender(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories" pipelineState={pipeline()}
        liveRunId={RUN_ID} settledRun={settled()} isLoadingRunData={false} isLoadingRunTrace />,
    );
    expect(screen.getByTestId("tab-preview")).toHaveAttribute("aria-selected", "true");

    view.rerender(
      <PreviewPanel workflowType="user_stories" userStoryContent="# Stories"
        pipelineState={pipeline({ agents: [doneAgent("a1", 0), doneAgent("a2", 1)], completedCount: 2 })}
        liveRunId={RUN_ID} settledRun={settled()} isLoadingRunData={false} isLoadingRunTrace={false} />,
    );

    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalled());
    expect(screen.getByTestId("tab-preview")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("user-story-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("thinking-tab")).not.toBeInTheDocument();
  });
});
