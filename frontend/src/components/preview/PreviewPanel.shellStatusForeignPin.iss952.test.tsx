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
const _tagged: RunFamily = { root_id: "root", members: [{ ...tagless.members[0], git_tag: "v1" }, { ...tagless.members[1], git_tag: "v2" }] };
beforeEach(() => { mockGetToken.mockReset().mockReturnValue("test-token"); mockGetWorkflow.mockReset(); mockGetRunSandboxRefs.mockReset().mockResolvedValue([]); });
const _NEUTRAL = "Output will appear here";
const DISTINCT = "No deliverable was saved for this version";


// ISS-952 / QA-KB-091: the SHELL (liveRunId r1 = v2) ended badly; the pinned member (root = v1)
// is a different run. The shell's status must not leak into the pinned empty version.
async function pinUnderShell(run: Record<string, unknown>, shell: Record<string, unknown>) {
  mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, ...run } as unknown));
  render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={tagless} liveRunId="r1" pinnedVersion="1" {...shell} />);
  await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
  await screen.findByRole("status");
}
async function openPreview() {
  const tab = await screen.findByRole("tab", { name: /preview/i });
  await userEvent.setup().click(tab);
}

describe("ISS-952 / QA-KB-091 - shell status must not win over a foreign empty pin", () => {
  for (const status of ["cancelled", "failed", "degraded", "diverted"] as const) {
    it("ISS-952 pinned completed+null under " + status + " shell -> own copy, Preview tab kept", async () => {
      await pinUnderShell({ status: "completed", output: null }, { reopenedRunStatus: status });
      await openPreview();
      expect(screen.getByText(DISTINCT)).toBeInTheDocument();
      expect(screen.queryByText(/This run was cancelled/)).toBeNull();
      expect(screen.queryByText(/did not complete successfully/)).toBeNull();
    });
  }
  it("ISS-952 pinned failed+null under cancelled shell -> failed copy", async () => {
    await pinUnderShell({ status: "failed", output: null }, { reopenedRunStatus: "cancelled" });
    await openPreview();
    expect(screen.getByText(/did not complete successfully/)).toBeInTheDocument();
    expect(screen.queryByText(/This run was cancelled/)).toBeNull();
  });
  it("ISS-952 CONTROL pinned completed+null under completed shell -> own copy", async () => {
    await pinUnderShell({ status: "completed", output: null }, { reopenedRunStatus: "completed" });
    expect(screen.getByText(DISTINCT)).toBeInTheDocument();
  });
  it("ISS-952 CONTROL self-pin under failed shell keeps shell failed surface (no Preview tab)", async () => {
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, status: "failed", output: null } as unknown));
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={tagless} liveRunId="root" pinnedVersion="1" reopenedRunStatus="failed" />);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    expect(screen.queryByRole("tab", { name: /preview/i })).toBeNull();
  });
});
