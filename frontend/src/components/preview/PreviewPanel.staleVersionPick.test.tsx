import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState } from "@/types/index";

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

// ISS-758 / ISS-938 / ISS-939 (QA-KB-037) — a version pick must never apply a response that
// a newer selection (or a URL pin change) has superseded, and the Steps tab must not keep the
// previous version's data under a chip that already names the new one.

const SETTLED_STATE = {
  isRunning: false, pipelineRunId: "m3", pipeline_type: "prototype",
  agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0,
  deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

const mk = (id: string, n: number, parent: string | null) => ({
  id, type: n === 1 ? "prototype" : "prototype_revision", title: `v${n} run`, status: "completed",
  revision_index: n, parent_run_id: parent, created_at: `2026-09-0${n}T00:00:00Z`,
  completed_at: `2026-09-0${n}T01:00:00Z`, git_tag: `v${n}`,
});
const family = { root_id: "m1", members: [mk("m1", 1, null), mk("m2", 2, "m1"), mk("m3", 3, "m2")] };

const runFor = (id: string) => ({
  id, title: `${id} run`, type: "prototype", status: "completed", input: `brief-${id}`,
  output: `<html>${id}</html>`, agentOutputs: [], parentRunId: null, rootRunId: "m1",
});

let pending: Record<string, ((v: unknown) => void)[]>;
const settle = async (id: string) => { await act(async () => { (pending[id] ?? []).forEach((r) => r(runFor(id))); }); };

beforeEach(() => {
  pending = {};
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2", "v3"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: "m3", expired: false, truncated: false, files: [] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html></html>");
  mockResolveRunDeliverable.mockReset().mockResolvedValue(null);
  mockGetWorkflow.mockReset().mockImplementation(
    (_t: string, id: string) => new Promise((resolve) => { (pending[id] ??= []).push(resolve); }),
  );
});

function renderPanel(pinnedVersion?: string) {
  const ui = (pv?: string) => (
    <PreviewPanel
      workflowType="prototype"
      prototypeContent="<html>m3 live</html>"
      pipelineState={SETTLED_STATE}
      liveRunId="m3"
      runFamily={family}
      runInput="brief-m3"
      initialTab="preview"
      pinnedVersion={pv}
    />
  );
  const r = render(ui(pinnedVersion));
  return { ...r, rerenderPin: (pv?: string) => r.rerender(ui(pv)) };
}

async function pick(tag: string) {
  await userEvent.click(document.querySelector<HTMLElement>("button[aria-haspopup=listbox]")!);
  await userEvent.click(screen.getByRole("option", { name: tag }));
}

const banner = () => screen.queryByText(/Viewing v\d+ \(read-only\)/)?.textContent ?? "";

describe("ISS-758 — out-of-order version picks", () => {
  it("ISS-758: an older pick whose response lands last must not overwrite the newer pick", async () => {
    renderPanel();
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v1");
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "m1"));
    await pick("v2");
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "m2"));

    await settle("m2");
    await waitFor(() => expect(banner()).toMatch(/Viewing v2/));
    await settle("m1");

    expect(banner()).toMatch(/Viewing v2/);
    expect(banner()).not.toMatch(/Viewing v1/);
  });
});

describe("ISS-938 — URL pin change during a pending pick", () => {
  it("ISS-938: browser Back to a different pin supersedes the pending pick", async () => {
    const { rerenderPin } = renderPanel();
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "m2"));
    rerenderPin("2"); // the pick's own URL write round-tripping
    rerenderPin("1"); // browser Back
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "m1"));
    await settle("m1");
    await waitFor(() => expect(banner()).toMatch(/Viewing v1/));
    await settle("m2"); // the abandoned pick lands last

    expect(banner()).toMatch(/Viewing v1/);
    expect(banner()).not.toMatch(/Viewing v2/);
  });
});

describe("ISS-939 — pending window", () => {
  it.fails("ISS-939: while a pick is loading, Steps does not show the previous version's data", async () => {
    renderPanel();
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await pick("v2");
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "m2"));
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));

    // Chip already says v2 while getWorkflow(m2) is still pending: Steps must not show live m3 data.
    expect(screen.getByTestId("thinking-tab").textContent).not.toBe("brief-m3");
  });
});
