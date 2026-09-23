import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-054 / QA-PS-056 — every frontend surface that reads a run's workspace
// bytes must carry the SELECTED ref, so a pinned older version never shows
// the live/HEAD tree's bytes under that version's name.
//
// The backend contract (already correct, not under test here): omitting `ref`
// means "the live working tree"; `ref=vN` means that version's own bytes.
// Every family member shares ONE sandbox, so a UI surface that forgets to
// pass its selected ref silently falls back to HEAD instead of erroring —
// that is exactly why these bugs went unnoticed.
//
// NOTE: at the time these tests were written the fix for both cards had
// already landed in this working tree (PreviewPanel.tsx's handleHeaderDownload
// now passes `sandboxSelectedRef ?? undefined` to getRunSandboxFileBlob/
// getRunSandboxZip — see its "QA-PS-054 / ISS-706" comment — and the
// pinnedVersion effect now also calls setSandboxSelectedRef — see its
// "QA-PS-056" comment). These are therefore GREEN regression tests, not
// xfail: each was confirmed to fail for the right reason against a
// deliberately-reverted 3-argument call before the fix comments were found,
// and now pins the fixed behaviour so it cannot regress silently.
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn();
const mockGetRunSandboxRefs = vi.fn();
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockGetRunSandboxZip = vi.fn();
const mockResolveRunDeliverable = vi.fn();

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

vi.mock("./UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content?: string }) => (
    <div data-testid="user-story-preview">{content}</div>
  ),
}));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
// FilesTab itself is out of scope here (it is the "Files" tab, not the header
// Download button or the "Workspace" tab) — stubbed like the sibling suite.
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

// No declared deliverable — routes handleHeaderDownload into the ISS-313
// whole-workspace-archive branch (getRunSandboxZip), the fallback QA-PS-054
// also covers.
const NO_DECLARED_STATE = {
  isRunning: false,
  pipelineRunId: "run-1",
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
} as unknown as PipelineRunState;

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset().mockResolvedValue({});
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({
    run_id: "run-1",
    expired: false,
    truncated: false,
    files: [{ path: "prototype.html", size: 34_000, modified: 0, text: true, deliverable: true }],
  });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html></html>");
  mockGetRunSandboxFileBlob.mockReset().mockResolvedValue(new Blob(["<html></html>"], { type: "text/html" }));
  mockGetRunSandboxZip.mockReset().mockResolvedValue(new Blob(["zip"], { type: "application/zip" }));
  mockResolveRunDeliverable.mockReset().mockResolvedValue({
    path: "prototype.html",
    size: 10,
    modified: 1,
    text: true,
    kind: "text",
    deliverable: true,
  });
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

async function selectVersionV1() {
  const chip = screen.getByRole("button", { name: /^v1\b/ });
  await userEvent.click(chip);
  await userEvent.click(screen.getByRole("option", { name: "v1" }));
}

describe("GREEN control — the harness can observe the selected ref", () => {
  it("selecting v1 makes the Preview tab's deliverable fetch carry ref=v1", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId="run-1"
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));
    await selectVersionV1();
    await waitFor(() =>
      expect(mockGetRunSandboxFile).toHaveBeenCalledWith("test-token", "run-1", "prototype.html", "v1"),
    );
  });
});

describe("QA-PS-054 — the header Download button carries the selected ref", () => {
  it("with v1 pinned, the header Download fetches v1's own bytes, not HEAD's", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId="run-1"
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));
    await selectVersionV1();

    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    await userEvent.click(btn);

    // The download reads the PINNED version's bytes (4th arg "v1"). If this
    // regressed to a 3-argument call, the button would silently hand back
    // HEAD's bytes under the "Viewing v1 (read-only)" banner.
    await waitFor(() =>
      expect(mockGetRunSandboxFileBlob).toHaveBeenCalledWith("test-token", "run-1", "prototype.html", "v1"),
    );
  });

  it("with v1 pinned and no declared file, the header Download zip carries ref=v1", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live</html>"
        pipelineState={NO_DECLARED_STATE}
        liveRunId="run-1"
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalledWith("test-token", "run-1"));
    await selectVersionV1();

    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    await userEvent.click(btn);

    // The whole-workspace zip fallback (ISS-313, no declared file) also reads
    // v1's own tree — the same contract SandboxTab.tsx's own zip download
    // (SandboxTab.tsx:1119) already followed.
    await waitFor(() =>
      expect(mockGetRunSandboxZip).toHaveBeenCalledWith("test-token", "run-1", "v1"),
    );
  });
});

describe("QA-PS-056 — a direct URL pin to an older version sets the Workspace tab's ref", () => {
  it("visiting /versions/1 directly (no VersionMenu click) lists the Workspace tab at ref=v1, not HEAD", async () => {
    const V1_MEMBER_ID = "member-uuid-v1";
    const V2_MEMBER_ID = "member-uuid-v2";
    const runFamily = {
      root_id: V1_MEMBER_ID,
      members: [
        {
          id: V1_MEMBER_ID, type: "prototype", title: "v1 run", status: "completed",
          revision_index: 1, parent_run_id: null,
          created_at: "2026-09-01T00:00:00Z", completed_at: "2026-09-01T01:00:00Z",
          git_tag: "v1",
        },
        {
          id: V2_MEMBER_ID, type: "prototype", title: "v2 run", status: "completed",
          revision_index: 2, parent_run_id: V1_MEMBER_ID,
          created_at: "2026-09-02T00:00:00Z", completed_at: "2026-09-02T01:00:00Z",
          git_tag: "v2",
        },
      ],
    };
    mockGetWorkflow.mockImplementation((_token: string, runId: string) => {
      if (runId === V1_MEMBER_ID) {
        return Promise.resolve({
          id: V1_MEMBER_ID,
          type: "prototype",
          output: "<html>v1 content</html>",
          agentOutputs: [],
          tokenUsage: null,
          status: "completed",
        });
      }
      return Promise.resolve({});
    });

    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>live content</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_MEMBER_ID}
        runFamily={runFamily}
        // The URL-deep-link pin (ISS-230's /versions/{v}), NOT a VersionMenu
        // click — mirrors loading v1's own page directly.
        pinnedVersion="1"
      />,
    );

    // The pin resolved to the v1 member (proves the deep-link path fired).
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_MEMBER_ID));

    await userEvent.click(screen.getByTestId("tab-workspace"));

    // The Workspace tab lists v1's OWN tree. If this regressed (the
    // pinnedVersion effect setting viewingVersion but not sandboxSelectedRef),
    // SandboxTab's selectedRef would stay null and it would list the shared
    // sandbox's live/HEAD tree (v2's bytes) under v1's run id instead.
    await waitFor(() =>
      expect(mockGetRunSandbox).toHaveBeenCalledWith("test-token", V1_MEMBER_ID, "v1"),
    );
  });
});
