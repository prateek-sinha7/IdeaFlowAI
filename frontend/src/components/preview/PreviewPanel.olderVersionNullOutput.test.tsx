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

async function pin(run: Record<string, unknown>) {
  mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, ...run } as unknown));
  render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={tagless} liveRunId="root" pinnedVersion="1" />);
  await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
  await screen.findByRole("status");
}

describe("ISS-154 / ISS-933 - pinned older version with null output", () => {
  it("ISS-154 pinned completed + output=null -> distinct copy, not the neutral", async () => {
    await pin({ status: "completed", output: null });
    expect(screen.getByText(DISTINCT)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL)).toBeNull();
  });
  it("ISS-154 pinned still RUNNING + output=null -> neutral stays (no false 'saved' claim)", async () => {
    await pin({ status: "running", output: null });
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
    expect(screen.queryByText(DISTINCT)).toBeNull();
  });
  // ISS-933 (INFERRED sibling): a pinned failed/cancelled/diverted/degraded run gets the
  // terminal affordance copy (DegradedRunAffordance), not the empty placeholder. The
  // ISS-154 copy for these statuses is superseded by the affordance, so only it is asserted.
  for (const [status, copy] of [
    ["failed", /did not complete successfully/],
    ["degraded", /did not complete successfully/],
    ["cancelled", /This run was cancelled/],
    ["diverted", /did not complete successfully/],
  ] as const) {
    it("ISS-933 pinned " + status + " + output=null -> terminal affordance copy, no retry, no neutral", async () => {
      await pin({ status, output: null });
      expect(screen.getByText(copy)).toBeInTheDocument();
      expect(screen.queryByText(NEUTRAL)).toBeNull();
      expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
    });
  }
  it("ISS-154 pinned completed + output='' (empty string) -> distinct copy", async () => {
    await pin({ status: "completed", output: "" });
    expect(screen.getByText(DISTINCT)).toBeInTheDocument();
  });
  it("ISS-154 CONTROL pinned completed WITH output -> deliverable renders, neither copy", async () => {
    await pin({ status: "completed", output: "<html>v1</html>" });
    expect(screen.getByTestId("proto-preview")).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL)).toBeNull();
    expect(screen.queryByText(DISTINCT)).toBeNull();
  });
  it("ISS-154 CONTROL no pin, terminal, no content -> neutral stays (degraded.test:177/259, TS-Q-05, TS-R-03)", () => {
    render(<PreviewPanel workflowType="prototype" isStreaming={false} />);
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
    expect(screen.queryByText(DISTINCT)).toBeNull();
  });
  it("ISS-154 pinned run record without a status field (partial API mock) -> neutral fallback, no crash", async () => {
    await pin({ output: null });
    expect(screen.getByText(NEUTRAL)).toBeInTheDocument();
  });
  it("ISS-154 version-menu path with git tags -> RefVersionPreview, neither copy", async () => {
    mockGetRunSandboxRefs.mockResolvedValue(["v1", "v2"]);
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve({ id, status: "completed", output: null } as unknown));
    const user = userEvent.setup();
    render(<PreviewPanel workflowType="prototype" prototypeContent="<html>latest</html>" runFamily={tagged} liveRunId="r1" />);
    await user.click(await screen.findByRole("button", { name: /v2/ }));
    await user.click(await screen.findByRole("option", { name: "v1" }));
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    expect(await screen.findAllByText(/Viewing v1 · read-only/)).not.toHaveLength(0);
    expect(screen.queryByText(NEUTRAL)).toBeNull();
    expect(screen.queryByText(DISTINCT)).toBeNull();
  });
});
