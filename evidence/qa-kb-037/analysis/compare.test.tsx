// SCRATCH comparison for QA-KB-037 / ISS-758 (scratchpad only, NOT in the repo).
// Runs every scenario against (1) the unmodified PreviewPanel and (2) a scratchpad COPY with the
// "agreed minimal fix" (selectGen ref) applied, and writes the observed states to results.json.
import { describe, expect, it, vi, beforeEach, afterAll } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { writeFileSync } from "node:fs";
import type { PipelineRunState } from "@/types/index";

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

const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover", "whileTap", "whileFocus",
  "whileInView", "viewport", "layout", "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy({}, {
    get: (_t, prop: string) => ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
      React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))), children),
  }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content?: string }) => <div data-testid="user-story-preview">{content}</div>,
}));
vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("@/components/preview/AppBuilderPreview", () => ({ AppBuilderPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div />, downloadBlob: vi.fn(), deriveDeliverableFilename: () => "user_stories.md",
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({
  AgentThinkingTab: ({ agents }: { agents?: { id: string }[] }) => (
    <div data-testid="thinking-tab">{(agents ?? []).map((a) => a.id).join(",")}</div>
  ),
}));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div /> }));

import { PreviewPanel as Current } from "@/components/preview/PreviewPanel";
import { PreviewPanel as Fixed } from "./PreviewPanelFixed";
import { PreviewPanel as FixedX } from "./PreviewPanelFixedX";

const STATE = {
  isRunning: false, pipelineRunId: "member-v3", pipeline_type: "user_stories", agents: [],
  currentAgentIndex: -1, totalDuration: null, completedCount: 0,
} as unknown as PipelineRunState;

const member = (n: number, parent: string | null) => ({
  id: `member-v${n}`, type: "user_stories", title: `v${n} run`, status: "completed", revision_index: n,
  parent_run_id: parent, created_at: `2026-09-0${n}T00:00:00Z`, completed_at: `2026-09-0${n}T01:00:00Z`, git_tag: `v${n}`,
});
const FAMILY = { root_id: "member-v1", members: [member(1, null), member(2, "member-v1"), member(3, "member-v2")] };
const runRec = (n: number, agentIds: string[] = []) => ({
  id: `member-v${n}`, output: `v${n} content`, type: "user_stories", status: "completed", input: "", tokenUsage: null,
  agentOutputs: agentIds.map((id) => ({ agent_id: id, name: id, output: "x", thinking: "" })),
});

type Def = { promise: Promise<unknown>; resolve: (v: unknown) => void; reject: (e: unknown) => void };
const deferred = (): Def => {
  let resolve!: (v: unknown) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<unknown>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

const results: Record<string, unknown>[] = [];
afterAll(() => { writeFileSync(__dirname + "/results.json", JSON.stringify(results, null, 1)); });

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2", "v3"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({
    run_id: "x", expired: false, truncated: false,
    files: [{ path: "user_stories.md", size: 20, modified: 1, text: true, kind: "text", deliverable: true }],
  });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("file content");
  mockGetRunSandboxFileBlob.mockReset();
  mockGetRunSandboxZip.mockReset();
  mockResolveRunDeliverable.mockReset().mockResolvedValue({
    path: "user_stories.md", size: 10, modified: 1, text: true, kind: "text", deliverable: true,
  });
});

const chip = () => screen.getAllByRole("button").find((b) => b.getAttribute("aria-haspopup") === "listbox")!;
async function pick(tag: string) {
  await userEvent.click(chip());
  await userEvent.click(screen.getByRole("option", { name: tag }));
}
const banner = () =>
  screen.queryAllByRole("status").find((el) => el.textContent?.includes("(read-only)"))?.textContent?.replace("Back to latest →", "") ?? "(no banner)";
const shown = () => screen.queryByTestId("user-story-preview")?.textContent ?? "(no preview)";
const snap = () => ({ chip: chip().textContent, banner: banner(), shown: shown() });

const baseProps = {
  workflowType: "user_stories" as const,
  userStoryContent: "live (v3) content",
  pipelineState: STATE,
  liveRunId: "member-v3",
  runFamily: FAMILY,
};

describe.each([
  ["CURRENT (unmodified)", Current],
  ["AGREED FIX (scratch copy)", Fixed],
  ["AGREED FIX + URL-PIN BUMPS (scratch copy)", FixedX],
])("%s", (impl, Panel) => {
  const record = (scenario: string, data: Record<string, unknown>) => results.push({ impl, scenario, ...data });

  it("A. older pick lands after a newer pick: newer selection must win", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : id === "member-v1" ? Promise.resolve(runRec(1)) : Promise.resolve(runRec(3)));
    render(<Panel {...baseProps} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await pick("v1");
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    const before = snap();
    await act(async () => { slowV2.resolve(runRec(2)); });
    const after = snap();
    record("A out-of-order pick", { before, after });
    expect(after.banner).toMatch(/Viewing v1/);
    expect(after.chip).toMatch(/v1/);
  });

  it("B. pick vN then return to latest: late response must not re-pin vN", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : Promise.resolve(runRec(3)));
    render(<Panel {...baseProps} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await pick("v3");
    const before = snap();
    await act(async () => { slowV2.resolve(runRec(2)); });
    const after = snap();
    record("B live-return", { before, after });
    expect(after.banner).toBe("(no banner)");
  });

  it("C. older pick that FAILS late must not wipe the newer pick", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : id === "member-v1" ? Promise.resolve(runRec(1)) : Promise.resolve(runRec(3)));
    vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<Panel {...baseProps} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await pick("v1");
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    await act(async () => { slowV2.reject(new Error("network")); });
    const after = snap();
    record("C late failure", { after });
    expect(after.banner).toMatch(/Viewing v1/);
  });

  it("D. control: a single pick still lands (normal switching unchanged)", async () => {
    mockGetWorkflow.mockImplementation((_t: string, id: string) => Promise.resolve(runRec(Number(id.slice(-1)))));
    render(<Panel {...baseProps} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await waitFor(() => expect(banner()).toMatch(/Viewing v2/));
    await pick("v1");
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    await pick("v3");
    await waitFor(() => expect(banner()).toBe("(no banner)"));
    record("D sequential picks", { after: snap() });
  });

  it("S2. pending window (Steps tab): previous version's agents stay under the new selection", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : Promise.resolve(runRec(3)));
    render(<Panel {...baseProps}
      agents={[{ id: "live-v3-agent", name: "Live", role: "", icon: "", status: "done", output: "o", thinking: "", duration: null, error: null, index: 0 } as never]} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await userEvent.click(screen.getByTestId("tab-thinking"));
    await pick("v2");
    const pending = { ...snap(), steps: screen.getByTestId("thinking-tab").textContent };
    await act(async () => { slowV2.resolve(runRec(2, ["v2-agent"])); });
    const resolved = { ...snap(), steps: screen.getByTestId("thinking-tab").textContent };
    record("S2 pending window", { pending, resolved });
    expect(pending.steps).not.toBe("live-v3-agent");
  });

  it("S1. URL-driven pin change (Back) while a pick is in flight", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : id === "member-v1" ? Promise.resolve(runRec(1)) : Promise.resolve(runRec(3)));
    const props = { ...baseProps, onTabSelect: vi.fn() };
    const { rerender } = render(<Panel {...props} pinnedVersion="1" />);   // deep link /versions/1
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    await pick("v2");                                                        // pick v2 (pending)
    rerender(<Panel {...props} pinnedVersion="2" />);                        // URL write round-trips into the prop
    rerender(<Panel {...props} pinnedVersion="1" />);                        // browser Back -> /versions/1
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    const before = snap();
    await act(async () => { slowV2.resolve(runRec(2)); });                   // the abandoned pick lands
    const after = snap();
    record("S1 Back while pending", { urlPin: "1", before, after });
    expect(after.banner).toMatch(/Viewing v1/);
  });
  it("S1b. Back to an UNPINNED url while a pick is in flight", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : id === "member-v1" ? Promise.resolve(runRec(1)) : Promise.resolve(runRec(3)));
    const props = { ...baseProps, onTabSelect: vi.fn() };
    const { rerender } = render(<Panel {...props} />);                       // base /runs/{id}, no pin
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");                                                        // pending
    rerender(<Panel {...props} pinnedVersion="2" />);                        // URL -> /versions/2
    rerender(<Panel {...props} />);                                          // Back -> base URL, no pin
    const before = snap();
    await act(async () => { slowV2.resolve(runRec(2)); });
    const after = snap();
    record("S1b Back to unpinned while pending", { before, after });
    expect(after.banner).toBe("(no banner)");
  });

  it("E. normal flow with the URL round-trip: pick v2, URL prop follows, response lands -> v2 shown", async () => {
    const slowV2 = deferred();
    mockGetWorkflow.mockImplementation((_t: string, id: string) =>
      id === "member-v2" ? slowV2.promise : Promise.resolve(runRec(3)));
    const props = { ...baseProps, onTabSelect: vi.fn() };
    const { rerender } = render(<Panel {...props} />);
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    rerender(<Panel {...props} pinnedVersion="2" />);
    await act(async () => { slowV2.resolve(runRec(2)); });
    await waitFor(() => expect(banner()).toMatch(/Viewing v2/));
    record("E normal pick with URL round-trip", { after: snap() });
  });
});
