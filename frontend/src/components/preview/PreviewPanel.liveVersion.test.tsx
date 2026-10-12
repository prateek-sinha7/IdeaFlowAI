import { describe, expect, it, vi, beforeEach } from "vitest";
import type { MockedFunction } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

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

vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
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
import type { PipelineRunState } from "@/types/index";

// A version still running has no saved agent outputs, so pinning it (a DB
// snapshot) showed an empty Steps page — while opening it directly works,
// because that attaches its live stream. Picking it must open it live.

const SETTLED_STATE = {
  isRunning: false, pipelineRunId: "v1", pipeline_type: "prototype", agents: [],
  currentAgentIndex: -1, totalDuration: null, completedCount: 0, deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

const V1_ID = "member-uuid-v1";
const V2_ID = "member-uuid-v2";
const member = (id: string, idx: number, status: string, tag?: string) => ({
  id, type: idx === 1 ? "prototype_v2" : "prototype_revision", title: `v${idx}`, status, revision_index: idx,
  parent_run_id: idx === 1 ? null : V1_ID, created_at: "2026-09-28T00:00:00Z", completed_at: null, ...(tag ? { git_tag: tag } : {}),
});

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset().mockResolvedValue({ id: V2_ID, output: "", agentOutputs: [], tokenUsage: null, status: "completed" });
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: V1_ID, expired: false, truncated: false, files: [] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html></html>");
  mockResolveRunDeliverable.mockReset().mockResolvedValue({ path: "prototype.html", size: 10, modified: 1, text: true, kind: "text", deliverable: true });
});

async function pickLatest(family: unknown, onOpenLiveRun: MockedFunction<(runId: string, tab: string) => void>) {
  render(
    <PreviewPanel workflowType="prototype" prototypeContent="<html>v1</html>" pipelineState={SETTLED_STATE}
      liveRunId={V1_ID} runFamily={family as never} onOpenLiveRun={onOpenLiveRun} />,
  );
  await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: /^v1\b/ }));
  await userEvent.click(screen.getByRole("option", { name: /Latest/ }));
}

describe("Version menu — a still-running version opens live", () => {
  it("on v1, picking the running v2 opens it live instead of an empty saved snapshot", async () => {
    const onOpenLiveRun = vi.fn();
    await pickLatest({ root_id: V1_ID, members: [member(V1_ID, 1, "completed", "v1"), member(V2_ID, 2, "generating")] }, onOpenLiveRun);
    expect(onOpenLiveRun).toHaveBeenCalledWith(V2_ID, expect.any(String));
    expect(mockGetWorkflow).not.toHaveBeenCalledWith("test-token", V2_ID);
  });

  it("a finished v2 is still pinned from its saved snapshot", async () => {
    const onOpenLiveRun = vi.fn();
    await pickLatest({ root_id: V1_ID, members: [member(V1_ID, 1, "completed", "v1"), member(V2_ID, 2, "completed", "v2")] }, onOpenLiveRun);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V2_ID));
    expect(onOpenLiveRun).not.toHaveBeenCalled();
  });
});
