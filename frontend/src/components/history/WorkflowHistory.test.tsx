import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Mocks. These are hoisted by vitest before module imports.
// ─────────────────────────────────────────────────────────────────

// Stable mock fns we can drive per-test.
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
}));

// Replace heavy preview components with placeholders. The chain panel
// lives in the left sidebar of the detail view, not inside any of these,
// so their real implementations are irrelevant for this test.
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

// Same motion mock used in AgentProgressPanel.test.tsx — preserves the
// underlying HTML tag so role-based queries still find buttons.
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

// Imported AFTER the mocks so the component picks up the mocked deps.
import { WorkflowHistory } from "./WorkflowHistory";

// ─────────────────────────────────────────────────────────────────
// Test fixtures
// ─────────────────────────────────────────────────────────────────

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-1",
    title: "Test deck",
    type: "ppt",
    status: "completed",
    input: "Pitch our new AI feature",
    output: "# Slide deck\n\nSome content...",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    ...overrides,
  };
}

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
});

type ChainHandler = (run: WorkflowRun, type: import("@/types/index").WorkflowType) => void;

async function renderAndOpenRun(run: WorkflowRun, onChainPipeline?: ChainHandler) {
  mockGetWorkflows.mockResolvedValue([run]);
  // The detail-load short-circuits when run.output is set, but mock
  // getWorkflow anyway so any code path that does fetch the full run
  // resolves correctly.
  mockGetWorkflow.mockResolvedValue(run);

  render(<WorkflowHistory onBack={vi.fn()} onChainPipeline={onChainPipeline} />);

  // Wait for the list to render the run, then click it to open detail.
  const item = await screen.findByText(run.title);
  await userEvent.click(item);
  // The detail view shows the run title again in a larger heading.
  await waitFor(() => expect(screen.getAllByText(run.title).length).toBeGreaterThan(0));
}

// ─────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────

describe("WorkflowHistory — Suggested next steps", () => {
  it("hides the chain panel when onChainPipeline is not provided", async () => {
    await renderAndOpenRun(makeRun({ type: "ppt" }), undefined);
    expect(screen.queryByText(/suggested next steps/i)).not.toBeInTheDocument();
  });

  it("hides the chain panel when the run failed", async () => {
    await renderAndOpenRun(
      makeRun({ status: "failed", error: "Bedrock timeout" }),
      vi.fn(),
    );
    expect(screen.queryByText(/suggested next steps/i)).not.toBeInTheDocument();
  });

  it("shows the chain panel with sibling targets for a completed base run", async () => {
    await renderAndOpenRun(makeRun({ type: "ppt" }), vi.fn());

    expect(await screen.findByText(/suggested next steps/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /user stories/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prototype/i })).toBeInTheDocument();
    // Just-completed base must not be offered back to itself.
    expect(screen.queryByRole("button", { name: /^presentation/i })).not.toBeInTheDocument();
  });

  it("normalises a `_revision` run the same as its base (refine -> chain)", async () => {
    // The regression test for the refine-bug as it surfaces in history:
    // a stored `ppt_revision` run must not re-offer chaining back to PPT.
    await renderAndOpenRun(makeRun({ type: "ppt_revision" }), vi.fn());

    expect(await screen.findByText(/suggested next steps/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^presentation/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /user stories/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prototype/i })).toBeInTheDocument();
  });

  it("calls onChainPipeline with the historical run and the chosen target", async () => {
    const onChainPipeline = vi.fn();
    const run = makeRun({ type: "user_stories" });
    await renderAndOpenRun(run, onChainPipeline);

    await userEvent.click(screen.getByRole("button", { name: /prototype/i }));

    expect(onChainPipeline).toHaveBeenCalledTimes(1);
    // Critical: the run object passed back is the historical one — the
    // parent uses its `input`/`output` for context, not the dashboard's
    // stale state.
    expect(onChainPipeline).toHaveBeenCalledWith(
      expect.objectContaining({ id: run.id, type: run.type, output: run.output }),
      "prototype",
    );
  });
});
