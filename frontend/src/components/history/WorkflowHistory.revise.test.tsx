import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Revision Families (B1): the EMIT side of the history-revision linkage
// fix — a history-launched revision must forward selectedRun.id as the 3rd
// arg (sourceRunId) so the backend links the parent. Previously history
// revisions sent nothing → orphan runs. Scaffold mirrors WorkflowHistory.test.tsx.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  // B2: WorkflowHistory now fetches the revision family on detail-open. This
  // suite doesn't assert the version timeline, so return an empty family
  // (VersionTimeline renders null for <2 members) — this only prevents the
  // undefined-mock-export throw that would otherwise crash render.
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  // Detail summary column (RunDetailPage) is mounted but not asserted here — a
  // benign rejection lands RunDetailPage in its graceful error state.
  getRunSummary: () => Promise.reject(new Error("no summary in this suite")),
}));

vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content }: { content: string }) => <div data-testid="ppt-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: ({ content }: { content: string }) => <div data-testid="prototype-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
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

import { WorkflowHistory } from "./WorkflowHistory";

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "hist-7",
    title: "Interactive prototype",
    type: "prototype",
    status: "completed",
    input: "build a landing page",
    output: "<!doctype html><html><body>hello</body></html>",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: "hist-7",
    ...overrides,
  };
}

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
});

describe("WorkflowHistory revision linkage (B1)", () => {
  it("forwards selectedRun.id as the 3rd arg to onRevisePrototype", async () => {
    const run = makeRun();
    mockGetWorkflows.mockResolvedValue([run]);
    mockGetWorkflow.mockResolvedValue(run);
    const onRevisePrototype = vi.fn();

    render(<WorkflowHistory onBack={vi.fn()} onRevisePrototype={onRevisePrototype} />);

    // Open the run detail.
    const item = await screen.findByText(run.title);
    await userEvent.click(item);
    await waitFor(() => expect(screen.getAllByText(run.title).length).toBeGreaterThan(0));

    // Open the revise affordance ("Revise Prototype"), type an instruction, send.
    const reviseButton = await screen.findByText("Revise Prototype");
    await userEvent.click(reviseButton);

    const textarea = await screen.findByPlaceholderText("Describe what you'd like to change...");
    // fireEvent.change sets the controlled value in one shot — robust against the
    // detail view's per-keystroke re-render churn.
    fireEvent.change(textarea, { target: { value: "make the header blue" } });

    const sendButton = screen.getByRole("button", { name: /Send/i });
    await userEvent.click(sendButton);

    expect(onRevisePrototype).toHaveBeenCalledTimes(1);
    expect(onRevisePrototype).toHaveBeenCalledWith(
      "make the header blue",
      run.output,
      "hist-7",
    );
  });
});
