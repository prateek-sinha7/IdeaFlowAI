/**
 * ISS-391 — WorkflowHistory's `reopenTerminalFailure` triad omits "diverted",
 * so a selected diverted run with no output falls through to the generic
 * "No preview available" placeholder instead of being suppressed (as the
 * failed/cancelled/degraded siblings already are, per the comment at
 * WorkflowHistory.tsx:588-591 — the summary column is assumed to already
 * explain the failure, so the deliverable pane renders `null`).
 *
 * Scaffold cloned from WorkflowHistory.genericReopen.test.tsx (render + open
 * pattern) and WorkflowHistory.divertLinks.test.tsx (diverted-run makeRun
 * shape / mocks).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";
import { renderWithProviders } from "@/test/renderWithProviders";

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: () => Promise.resolve(),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  getRunSummary: () => Promise.reject(new Error("no summary in this suite")),
}));
vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("@/components/preview/UserStoryPreview", () => ({ UserStoryPreview: () => <div /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("@/components/preview/AppBuilderPreview", () => ({ AppBuilderPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div />,
  deriveDeliverableFilename: () => "deliverable",
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn(() => null) }),
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
    id: "run-1",
    title: "Ex A4 Human Divert",
    type: "prototype",
    status: "diverted",
    input: "brief",
    output: null,
    createdAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
    duration: 100,
    agentCount: 3,
    parentRunId: null,
    rootRunId: "run-1",
    ...overrides,
  } as WorkflowRun;
}

beforeEach(() => {
  cleanup();
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
});

describe("WorkflowHistory — ISS-391 diverted selection deliverable pane", () => {
  it("a selected diverted run with no output suppresses the deliverable pane (like failed/cancelled/degraded), not the generic 'No preview available'", async () => {
    const run = makeRun();
    mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
    mockGetWorkflow.mockResolvedValue(run);
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);

    const item = await screen.findByText(run.title);
    await userEvent.click(item);
    await waitFor(() => expect(screen.getAllByText(run.title).length).toBeGreaterThan(0));

    // Correct behaviour: a diverted run with no deliverable is already
    // explained by the summary column, so the right-column pane must NOT
    // show the generic empty-state placeholder.
    expect(screen.queryByText("No preview available")).not.toBeInTheDocument();
  });
});
