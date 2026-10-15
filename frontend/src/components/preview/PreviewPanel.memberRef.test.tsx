import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { PipelineRunState, RunFamily } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-KB-053 (ISS-665, ISS-972, ISS-973, ISS-975) — every member of a revision
// family shares ONE sandbox, and its live tree is the NEWEST member's. A surface
// that presents one member's deliverable must read that member's own tag, or it
// names, sizes and serves the newest member's file under the older one's label.
//
// The REAL FilesTab is mounted (the sibling suites stub it), so the row's
// resolve call and its Download are both observable. The resolver is mocked
// with the real one's contract: the ref it resolved at rides on the hit.
// ─────────────────────────────────────────────────────────────────────────────

const V1 = "member-v1";
const V2 = "member-v2";
const V3 = "member-v3";

const mockResolve = vi.fn();
const mockBlob = vi.fn();
const mockGetWorkflow = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflow: (...args: unknown[]) => mockGetWorkflow(...args),
  getRunFamily: vi.fn(),
  postShareRun: vi.fn(),
  deleteShareRun: vi.fn(),
  getRunSandboxRefs: () => Promise.resolve(["v1", "v2", "v3"]),
  getRunSandbox: vi.fn(),
  getRunSandboxFile: () => Promise.resolve("<html></html>"),
  getRunSandboxFileBlob: (...args: unknown[]) => mockBlob(...args),
  getRunSandboxZip: vi.fn(),
  resolveRunDeliverable: (...args: unknown[]) => mockResolve(...args),
}));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
// One component per tag, cached: a fresh function per access would be a new
// component type on every PreviewPanel render, remounting the real FilesTab (and
// dropping its expanded "From v{n-1}" section) whenever the panel re-renders.
vi.mock("motion/react", () => {
  const byTag = new Map<string, unknown>();
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, prop: string) => {
          if (!byTag.has(prop)) {
            byTag.set(prop, ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
              const cleaned = Object.fromEntries(
                Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
              );
              return React.createElement(prop, cleaned, children);
            });
          }
          return byTag.get(prop);
        },
      },
    ),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock("./UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories: vi.fn() }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));

import { PreviewPanel } from "./PreviewPanel";

const SETTLED_STATE = {
  isRunning: false,
  pipelineRunId: V2,
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  deliverableFilename: "prototype.html",
} as unknown as PipelineRunState;

function family(v2Tag?: string): RunFamily {
  const member = (id: string, idx: number, parent: string | null, tag?: string) => ({
    id, type: "prototype_revision", title: `v${idx}`, status: "completed", revision_index: idx,
    parent_run_id: parent, created_at: "2026-10-01T00:00:00Z", completed_at: "2026-10-01T01:00:00Z",
    ...(tag ? { git_tag: tag } : {}),
  });
  return { root_id: V1, members: [member(V1, 1, null, "v1"), member(V2, 2, V1, v2Tag), member(V3, 3, V2, "v3")] };
}

function renderMember(liveRunId: string, runFamily: RunFamily = family("v2")) {
  return render(
    <PreviewPanel
      workflowType="prototype"
      prototypeContent="<html><head><title>Member Proto</title></head></html>"
      pipelineState={SETTLED_STATE}
      liveRunId={liveRunId}
      runFamily={runFamily}
      deepLinkTarget={{ tab: "files", nonce: 1 }}
    />,
  );
}

// FilesTab resolves its own row with no declared name; the header passes one.
const filesRowCalls = () => mockResolve.mock.calls.filter((c) => c[2] === undefined);

beforeEach(() => {
  mockGetWorkflow.mockReset().mockImplementation((_t: string, id: string) =>
    Promise.resolve(id === V1
      ? { id: V1, type: "prototype", output: "<html><title>Base Proto</title></html>", deliverableFilename: "prototype.html" }
      : {}),
  );
  mockResolve.mockReset().mockImplementation((_t: string, _id: string, _declared?: string, ref?: string) =>
    Promise.resolve({
      path: "prototype.html", size: 86_812, modified: 0, text: true, kind: "text", deliverable: true,
      ...(ref ? { ref } : {}),
    }),
  );
  mockBlob.mockReset().mockResolvedValue(new Blob(["<html></html>"], { type: "text/html" }));
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
});

describe("QA-KB-053 — an older member's own page reads its own tag", () => {
  it("ISS-665/ISS-973: the Files row of an older member resolves at its tag and Download reads those bytes", async () => {
    renderMember(V2);

    await waitFor(() => expect(filesRowCalls().length).toBeGreaterThan(0));
    expect(filesRowCalls().every((c) => c[1] === V2 && c[3] === "v2")).toBe(true);
    await userEvent.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() =>
      expect(mockBlob).toHaveBeenCalledWith("test-token", V2, "prototype.html", "v2"),
    );
  });

  it("GREEN control: the newest member's Files row reads the live tree", async () => {
    renderMember(V3);

    await waitFor(() => expect(filesRowCalls().length).toBeGreaterThan(0));
    expect(filesRowCalls().every((c) => c[3] === undefined)).toBe(true);
  });

  it("ISS-665: an older member with no tag keeps its derived row; the live tree is never read for it", async () => {
    renderMember(V2, family(undefined));

    // The header has resolved (so FilesTab's own effect has had its turn too).
    await waitFor(() => expect(mockResolve.mock.calls.some((c) => c[2] === "prototype.html")).toBe(true));
    await new Promise((r) => setTimeout(r, 30));

    expect(filesRowCalls()).toEqual([]);
    expect(screen.getByText("member-proto.html")).toBeInTheDocument();
  });

  it("ISS-972: \"From v1\" resolves the parent's file at the parent's own tag", async () => {
    renderMember(V2);

    await userEvent.click(await screen.findByLabelText("From version 1"));

    await waitFor(() =>
      expect(mockResolve).toHaveBeenCalledWith("test-token", V1, "prototype.html", "v1"),
    );
  });

  it("ISS-973: the header Download of an older member reads its own tag", async () => {
    renderMember(V2);

    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    await userEvent.click(btn);

    await waitFor(() =>
      expect(mockBlob).toHaveBeenCalledWith("test-token", V2, "prototype.html", "v2"),
    );
  });

  it("ISS-975: a header Download that fails tells the user instead of rejecting silently", async () => {
    mockBlob.mockReset().mockRejectedValue(new Error("404: could not download prototype.html"));
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    renderMember(V2);

    const btn = screen.getByLabelText("Download the deliverable");
    await waitFor(() => expect(btn).not.toBeDisabled());
    await userEvent.click(btn);

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
  });
});
