import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflow: vi.fn(),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunArtifacts: vi.fn().mockResolvedValue([]),
  getRunSandboxRefs: vi.fn().mockResolvedValue([]),
  getRunSandbox: (...a: unknown[]) => mockGetRunSandbox(...a),
  getRunSandboxFile: (...a: unknown[]) => mockGetRunSandboxFile(...a),
  getRunSandboxFileBlob: vi.fn(),
  getRunSandboxZip: vi.fn(),
  resolveRunDeliverable: vi.fn().mockResolvedValue(null),
}));
const STRIPPED = new Set(["initial", "animate", "exit", "transition", "layout", "layoutId", "variants", "custom"]);
vi.mock("motion/react", () => ({
  motion: new Proxy({}, { get: (_t, prop: string) => ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))), children) }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div />, downloadBlob: vi.fn(), deriveDeliverableFilename: () => "prototype.html" }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div /> }));

import { PreviewPanel } from "./PreviewPanel";

const file = (path: string) => ({ path, size: 10, modified: 0, text: true });
const running = (completed: number, agentIndex = 0) => ({
  isRunning: true,
  pipeline_type: "goal",
  agents: [{ id: "custom-agent:build", name: "Build", role: "", icon: "", status: "running", output: "", thinking: "", duration: null }],
  currentAgentIndex: agentIndex,
  totalDuration: null,
  completedCount: 0,
  protoCompletedTaskCount: completed,
  protoTotalTasks: 11,
});

async function openPreview() {
  await userEvent.setup().click(await screen.findByRole("tab", { name: /preview/i }));
}

beforeEach(() => {
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: "r1", expired: false, truncated: false, files: [file("example.html"), file("prototype.html")] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html><body>draft</body></html>");
});

describe("live draft preview while a run builds", () => {
  it("shows the workspace's main output file with a work-in-progress banner", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    render(<PreviewPanel workflowType={"goal" as any} liveRunId="r1" isStreaming pipelineState={running(6) as any} />);
    await openPreview();
    const draft = await screen.findByTestId("live-draft");
    expect(draft).toHaveTextContent("Work in progress");
    expect(draft).toHaveTextContent("Build · 6/11 tasks done");
    expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "r1", "prototype.html");
    expect(screen.queryByText(/Building your deliverable/)).toBeNull();
  });

  it("re-reads the file when a task completes and on Refresh", async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { rerender } = render(<PreviewPanel workflowType={"goal" as any} liveRunId="r1" isStreaming pipelineState={running(6) as any} />);
    await openPreview();
    await screen.findByTestId("live-draft");
    expect(mockGetRunSandboxFile).toHaveBeenCalledTimes(1);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rerender(<PreviewPanel workflowType={"goal" as any} liveRunId="r1" isStreaming pipelineState={running(7) as any} />);
    await waitFor(() => expect(mockGetRunSandboxFile).toHaveBeenCalledTimes(2));
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(mockGetRunSandboxFile).toHaveBeenCalledTimes(3));
  });

  it("keeps the placeholder until a main output file exists", async () => {
    mockGetRunSandbox.mockResolvedValue({ run_id: "r1", expired: false, truncated: false, files: [file("spec.md")] });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    render(<PreviewPanel workflowType={"goal" as any} liveRunId="r1" isStreaming pipelineState={running(0) as any} />);
    await openPreview();
    await waitFor(() => expect(mockGetRunSandbox).toHaveBeenCalled());
    expect(screen.getByText(/Building your deliverable/)).toBeInTheDocument();
    expect(mockGetRunSandboxFile).not.toHaveBeenCalled();
  });
});
