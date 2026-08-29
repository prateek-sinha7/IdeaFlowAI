import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";
import { renderWithProviders } from "@/test/renderWithProviders";

// ─────────────────────────────────────────────────────────────────
// ISS-199 / ISS-214 (BUG-20260828-012900-runs-id-files): WorkflowHistory's
// own detail-view Files tab (WorkflowHistory.tsx:531-560, 904-919) derives
// `isPpt` from a RAW, unnormalized `selectedRun.type` that never accounts for
// "ppt_v2" — unlike PreviewPanel.tsx:578's `renderType`, which explicitly
// folds "ppt_v2" into the "ppt" slot. For a ppt_v2 run this drops the run
// into the isGeneric branch: `pptContent` stays undefined and the generic
// deliverable is built with `filename: undefined` (WorkflowHistory.tsx:911),
// even though `selectedRun.deliverableFilename` is available.
//
// FilesTab itself is mocked here as a prop recorder (not the mock idiom used
// by genericReopen.test.tsx, which throws props away) so the test can assert
// on exactly what WorkflowHistory hands it — the defect is in WHAT gets
// passed down, not in FilesTab's own rendering.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
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
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: () => <div data-testid="appbuilder-preview" />,
}));
// Prop recorder — dumps the props WorkflowHistory hands FilesTab as JSON text
// so the test can assert on the derivation without re-implementing FilesTab.
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: (props: { workflowType: string; pptContent?: string; genericDeliverable?: { mimetype?: string; filename?: string } }) => (
    <div data-testid="files-tab">
      <span data-testid="files-tab-workflow-type">{props.workflowType}</span>
      <span data-testid="files-tab-ppt-content">{props.pptContent ?? "__UNDEFINED__"}</span>
      <span data-testid="files-tab-generic-filename">{props.genericDeliverable?.filename ?? "__UNDEFINED__"}</span>
    </div>
  ),
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

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
    title: "Kindred pitch deck",
    type: "ppt",
    status: "completed",
    input: "do a thing",
    output: "<html><title>Kindred deck</title></html>",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
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
  mockDeleteWorkflow.mockReset();
});

async function renderOpenRunAndGoToFiles(run: WorkflowRun) {
  mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
  mockGetWorkflow.mockResolvedValue(run);
  renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
  const item = await screen.findByText(run.title);
  await userEvent.click(item);
  await waitFor(() => expect(screen.getAllByText(run.title).length).toBeGreaterThan(0));
  const filesButton = screen.getByRole("button", { name: "Files" });
  await userEvent.click(filesButton);
  await screen.findByTestId("files-tab");
}

describe("WorkflowHistory — Files tab dispatch for ppt_v2 (ISS-214)", () => {
  it("ISS-214: a ppt_v2 run's Files tab still receives its deck as pptContent (not routed into the generic branch)", async () => {
    await renderOpenRunAndGoToFiles(
      makeRun({ type: "ppt_v2" as never, output: "<html><title>Kindred deck</title></html>" }),
    );

    // Today, WorkflowHistory's local `isPpt` omits "ppt_v2" (only "ppt" /
    // "ppt_revision" match), so pptContent stays undefined and the run is
    // shunted into the generic-deliverable branch instead.
    expect(screen.getByTestId("files-tab-ppt-content").textContent).toBe(
      "<html><title>Kindred deck</title></html>",
    );
  });

  it.fails("ISS-214: a ppt_v2 run's generic-deliverable fallback (if any) must not hardcode filename: undefined", async () => {
    await renderOpenRunAndGoToFiles(
      makeRun({
        type: "ppt_v2" as never,
        output: "<html><title>Kindred deck</title></html>",
        deliverableFilename: "presentation.html",
      } as Partial<WorkflowRun>),
    );

    // Since a ppt_v2 run IS a ppt for Files-tab purposes, it should never take
    // the generic-deliverable branch at all — so its filename must not stay
    // the hardcoded `undefined` WorkflowHistory.tsx:911 currently passes.
    expect(screen.getByTestId("files-tab-generic-filename").textContent).not.toBe("__UNDEFINED__");
  });
});
