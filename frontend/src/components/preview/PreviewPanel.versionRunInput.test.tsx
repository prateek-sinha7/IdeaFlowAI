import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-057 / ISS-753 + ISS-754 — the Steps "Starting point" card (and the Files
// tab's prompt.md row, which shares the prop) must follow the version dropdown,
// exactly as the agent list already does.
//
// VersionView carries every other per-version value (agents / pipelineState /
// agentOutputs / content / genericDeliverable) but used to carry no runInput, so
// the two consumers read the raw prop — page.tsx's submittedBrief, set only on
// opening a run or switching live run, never by the dropdown. FIX-603 added
// VersionView.runInput + effRunInput.
//
// SHAPE is the point of the first assertion: runInput is the PARSED, first-line,
// trimmed brief (what submittedBrief already is, FIX-130), never run.input raw.
// The fixture's input deliberately has a second line; if the raw string ever
// starts flowing through here instead, that line shows up and this fails.
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
// Both consumers are stubbed to echo the one prop under test.
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: ({ runInput }: { runInput?: string }) => <div data-testid="files-tab">{runInput}</div>,
  downloadBlob: vi.fn(),
  deriveDeliverableFilename: () => "prototype.html",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: ({ runInput }: { runInput?: string }) => <div data-testid="thinking-tab">{runInput}</div> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const SETTLED_STATE = {
  isRunning: false, pipelineRunId: "member-uuid-v2", pipeline_type: "prototype",
  agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0,
  deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

const V1_ID = "member-uuid-v1";
const V2_ID = "member-uuid-v2";
const family = {
  root_id: V1_ID,
  members: [
    { id: V1_ID, type: "prototype", title: "v1 run", status: "completed", revision_index: 1, parent_run_id: null, created_at: "2026-09-01T00:00:00Z", completed_at: "2026-09-01T01:00:00Z", git_tag: "v1" },
    { id: V2_ID, type: "prototype_revision", title: "v2 run", status: "completed", revision_index: 2, parent_run_id: V1_ID, created_at: "2026-09-02T00:00:00Z", completed_at: "2026-09-02T01:00:00Z", git_tag: "v2" },
  ],
};

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: "run-1", expired: false, truncated: false, files: [] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html></html>");
  mockResolveRunDeliverable.mockReset().mockResolvedValue(null);
  mockGetWorkflow.mockReset().mockImplementation((_t: string, id: string) =>
    id === V1_ID
      ? Promise.resolve({
          id: V1_ID, title: "v1 run", type: "prototype", status: "completed",
          // RAW input, with the markers a real revision-family root carries.
          input: "Subsea Fibre Splice Operations\nsecond line that must not show",
          output: "<html>v1</html>", agentOutputs: [], parentRunId: null, rootRunId: V1_ID,
        })
      : Promise.resolve(null));
});

describe("QA-PS-057 probe — Starting point follows the pin", () => {
  it("pinning v1 renders v1's OWN brief, parsed+first-line, not the live runInput prop", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v2 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_ID}
        runFamily={family}
        runInput="LIVE BRIEF FROM submittedBrief"
        initialTab="preview"
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("button", { name: /^v2\b/ }));
    await userEvent.click(screen.getByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_ID));

    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await waitFor(() =>
      expect(screen.getByTestId("thinking-tab").textContent).toBe("Subsea Fibre Splice Operations"),
    );

    expect(screen.getByTestId("thinking-tab").textContent).not.toContain("second line");
  });
});

describe("QA-PS-057 probe — control", () => {
  it("with NO pin the live runInput prop is still what Steps renders", async () => {
    render(
      <PreviewPanel
        workflowType="prototype"
        prototypeContent="<html>v2 live</html>"
        pipelineState={SETTLED_STATE}
        liveRunId={V2_ID}
        runFamily={family}
        runInput="LIVE BRIEF FROM submittedBrief"
        initialTab="preview"
      />,
    );
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await waitFor(() =>
      expect(screen.getByTestId("thinking-tab").textContent).toBe("LIVE BRIEF FROM submittedBrief"),
    );
  });
});
