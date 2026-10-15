import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { RunFamily } from "@/types";

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<unknown>>();
const mockGetRunSandboxRefs = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunSandboxRefs: (...a: unknown[]) => mockGetRunSandboxRefs(...a),
  getRunSandbox: vi.fn().mockResolvedValue({ run_id: "x", expired: false, truncated: false, files: [] }),
  getRunSandboxFile: vi.fn().mockResolvedValue(""),
  getRunSandboxFileBlob: vi.fn(),
  getRunSandboxZip: vi.fn(),
  resolveRunDeliverable: vi.fn().mockResolvedValue(null),
}));
const STRIPPED_MOTION_PROPS = new Set(["initial","animate","exit","transition","whileHover","whileTap","whileFocus","whileInView","viewport","layout","layoutId","drag","dragConstraints","variants","custom"]);
vi.mock("motion/react", () => ({
  motion: new Proxy({}, { get: (_t, prop: string) => ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k))), children) }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div data-testid="files-tab" />, downloadBlob: vi.fn(), deriveDeliverableFilename: () => "prototype.html" }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const t0 = new Date("2026-08-13T10:00:00Z").toISOString();
const t1 = new Date("2026-08-13T11:00:00Z").toISOString();
const tagless: RunFamily = {
  root_id: "root",
  members: [
    { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
    { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
  ],
};
const tagged: RunFamily = { root_id: "root", members: [{ ...tagless.members[0], git_tag: "v1" }, { ...tagless.members[1], git_tag: "v2" }] };
beforeEach(() => { mockGetToken.mockReset().mockReturnValue("test-token"); mockGetWorkflow.mockReset(); mockGetRunSandboxRefs.mockReset().mockResolvedValue([]); });
const NEUTRAL = "Output will appear here";
const DISTINCT = "No deliverable was saved for this version";
const BUILDING = /Building your deliverable/;

// ISS-1031 / ISS-1032 (QA-KB-091 siblings of ISS-952, FIX-748): the SHELL (liveRunId r1 = v2)
// and the pinned member (root = v1) are DIFFERENT runs, so the shell's failed or streaming
// state must not describe the pin.
async function pinUnderShell(run: Record<string, unknown>, shell: Record<string, unknown>) {
  mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, ...run } as unknown));
  render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={tagless} liveRunId="r1" pinnedVersion="1" {...shell} />);
  await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
  await screen.findByText("Viewing v1 (read-only)");
}
async function openPreview() {
  await userEvent.setup().click(await screen.findByRole("tab", { name: /preview/i }));
}
function expectSettledHeader() {
  expect(screen.queryByText(/Run failed/)).toBeNull();
  expect(screen.getByLabelText("Share this run")).toBeInTheDocument();
  expect(screen.getByLabelText("Download the deliverable")).toBeInTheDocument();
}

describe("ISS-1031 - the header describes the pinned version, not a failed shell", () => {
  for (const status of ["failed", "degraded"] as const) {
    it("ISS-1031 pinned completed WITH content under " + status + " shell -> settled header with Share and Download", async () => {
      await pinUnderShell({ status: "completed", output: "<html>v1</html>" }, { reopenedRunStatus: status });
      expectSettledHeader();
    });
  }
  it("ISS-1031 Version-menu pick of completed v1 under a failed shell -> settled header with Share and Download", async () => {
    mockGetRunSandboxRefs.mockResolvedValue(["v1", "v2"]);
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, status: "completed", output: "<html>v1</html>" } as unknown));
    const user = userEvent.setup();
    render(<PreviewPanel workflowType="prototype" runFamily={tagged} liveRunId="r1" reopenedRunStatus="failed" />);
    await user.click(await screen.findByRole("button", { name: /v2/ }));
    await user.click(await screen.findByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    await screen.findByText("Viewing v1 (read-only)");
    expectSettledHeader();
  });
  it("ISS-1031 CONTROL unpinned failed shell WITH content keeps Run failed, no Share or Download", () => {
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>partial</html>" runFamily={tagless} liveRunId="r1" reopenedRunStatus="failed" />);
    expect(screen.getByText(/Run failed/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Share this run")).toBeNull();
    expect(screen.queryByLabelText("Download the deliverable")).toBeNull();
  });
});

describe("ISS-1032 - a streaming shell does not answer for a settled foreign pin", () => {
  it("ISS-1032 pinned failed+null under a streaming shell -> the pin's failed copy, not Building", async () => {
    await pinUnderShell({ status: "failed", output: null }, { isStreaming: true });
    await openPreview();
    expect(screen.getByText(/did not complete successfully/)).toBeInTheDocument();
    expect(screen.queryByText(BUILDING)).toBeNull();
  });
  it("ISS-1032 pinned completed+null under a streaming shell -> the pin's saved-nothing copy, not Building", async () => {
    await pinUnderShell({ status: "completed", output: null }, { isStreaming: true });
    await openPreview();
    expect(screen.getByText(DISTINCT)).toBeInTheDocument();
    expect(screen.queryByText(BUILDING)).toBeNull();
  });
  it("ISS-1032 pinned RUNNING+null under a streaming shell -> neutral copy (TERMINAL_RUN_STATUSES guard)", async () => {
    await pinUnderShell({ status: "running", output: null }, { isStreaming: true });
    await openPreview();
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
    expect(screen.queryByText(BUILDING)).toBeNull();
  });
  it("ISS-1032 CONTROL pinned WITH content under a streaming shell -> the pin's deliverable", async () => {
    await pinUnderShell({ status: "completed", output: "<html>v1</html>" }, { isStreaming: true });
    await openPreview();
    expect(screen.getByTestId("proto-preview")).toBeInTheDocument();
  });
  it("ISS-1032 CONTROL unpinned streaming shell with no content keeps Building your deliverable", async () => {
    render(<PreviewPanel workflowType="prototype" runFamily={tagless} liveRunId="r1" isStreaming />);
    await openPreview();
    expect(screen.getByText(BUILDING)).toBeInTheDocument();
  });
});
