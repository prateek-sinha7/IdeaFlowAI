import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";
import type { RunSummary } from "@/lib/api";
// ─────────────────────────────────────────────────────────────────
// Mocks. These are hoisted by vitest before module imports.
// ─────────────────────────────────────────────────────────────────
// Stable mock fns we can drive per-test.
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
// SHELL-03: the terminal-run detail now mounts RunDetailPage (fed by getRunSummary)
// for the summary column — KPI / per-agent breakdown / version timeline / failure
// banner. Controllable so a test can drive the RunDetailPage-rendered failure banner.
const mockGetRunSummary = vi.fn<(token: string, id: string) => Promise<RunSummary>>();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
  getRunSummary: (token: string, id: string) => mockGetRunSummary(token, id),
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
vi.mock("@/components/results/FilesTab", () => {
  // Mirror slugify helper from the real FilesTab.tsx
  function slugify(raw: string, maxWords = 8): string {
    const clean = raw.replace(/[^a-zA-Z0-9\s]/g, "").trim();
    const words = clean.split(/\s+/).filter(Boolean).slice(0, maxWords);
    return words.join("-").toLowerCase();
  }

  return {
    FilesTab: () => <div data-testid="files-tab" />,
    deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
      // User Stories
      if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
        if (content) {
          const h = content.match(/^#\s+(.+)/m);
          const stem = h ? slugify(h[1]) : "user-stories";
          return `${stem || "user-stories"}.md`;
        }
        return fallback || "user-stories.md";
      }
      // Custom
      if (workflowType === "custom") {
        if (content) {
          const h = content.match(/^#\s+(.+)/m);
          const stem = h ? slugify(h[1]) : "custom-output";
          return `${stem || "custom-output"}.md`;
        }
        return fallback || "custom-output.md";
      }
      // PPT
      if (workflowType === "ppt" || workflowType === "ppt_revision") {
        const ext = "html";
        if (content) {
          const t = content.match(/<title>([^<]+)<\/title>/i);
          const h1 = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
          let stem = "presentation";
          if (t && t[1] !== "Presentation") stem = slugify(t[1]) || "presentation";
          else if (h1) stem = slugify(h1[1]) || "presentation";
          return `${stem}.${ext}`;
        }
        return fallback || `presentation.${ext}`;
      }
      // Prototype
      if (workflowType === "prototype" || workflowType === "prototype_revision") {
        if (content) {
          const t = content.match(/<title>(.+?)<\/title>/i);
          const stem = t ? slugify(t[1]) : "prototype";
          return `${stem || "prototype"}.html`;
        }
        return fallback || "prototype.html";
      }
      // App Builder
      if (workflowType === "app_builder" || workflowType === "app_builder_revision") {
        return "project.zip";
      }
      // Generic fallback
      return fallback || "deliverable";
    },
  };
});;
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
        }
    }
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
    parentRunId: null,
    rootRunId: "run-1",
    ...overrides,
  };
}
beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset().mockResolvedValue({ runs: [], total: 0 });
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
  // Default: no summary needed → RunDetailPage lands in its graceful error state
  // (the right-column deliverable + footer are what most of these tests assert).
  mockGetRunSummary.mockReset().mockRejectedValue(new Error("no summary in this test"));
});
// Build a RunSummary the RunDetailPage summary column renders from — used by the
// terminal-failure tests (the failure banner now lives in RunDetailPage).
function summaryFor(run: WorkflowRun, agents: { agent_id: string; name: string }[] = []): RunSummary {
  return {
    id: run.id,
    title: run.title,
    type: run.type,
    status: run.status,
    duration: run.duration ?? null,
    agent_count: agents.length,
    token_usage: { total_tokens: 0 },
    error: run.error ?? null,
    agents: agents.map((a) => ({ agent_id: a.agent_id, name: a.name, role: "Agent", icon: "", duration: null, total_tokens: 0 })),
    root_id: run.rootRunId,
    members: [
      { id: run.id, type: run.type, title: run.title, status: run.status, revision_index: 1, parent_run_id: null, created_at: run.createdAt, completed_at: run.completedAt ?? null },
    ],
  };
}
type ChainHandler = (run: WorkflowRun, type: import("@/types/index").WorkflowType) => void;
async function renderAndOpenRun(run: WorkflowRun, onChainPipeline?: ChainHandler) {
  mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
  // The detail-load short-circuits when run.output is set, but mock
  // getWorkflow anyway so any code path that does fetch the full run
  // resolves correctly.
  mockGetWorkflow.mockResolvedValue(run);
  // Set up getRunSummary for non-failed runs so the chain panel can render
  if (run.status !== "failed" && run.status !== "cancelled") {
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
  }
  // Initialize Redux store with workflow chain data so useWorkflowChaining works
  const preloadedState = {
    global: {
      workflows: [
        {
          id: "user_stories",
          name: "User Stories",
          display_name: "User Stories",
          description: "Create user stories",
          step_count: 2,
          steps: [],
          user_launchable: true,
          chained_from: [
            { id: "ppt", beta: false, text: "PPT" },
            { id: "prototype", beta: false, text: "Prototype" },
            { id: "custom", beta: false, text: "Custom" },
          ],
        },
        {
          id: "ppt",
          name: "Presentation",
          display_name: "Presentation",
          description: "Create presentation",
          step_count: 2,
          steps: [],
          user_launchable: true,
          chained_from: [
            { id: "user_stories", beta: false, text: "User Stories" },
            { id: "prototype", beta: false, text: "Prototype" },
            { id: "custom", beta: false, text: "Custom" },
          ],
        },
        {
          id: "prototype",
          name: "Prototype",
          display_name: "Prototype",
          description: "Create prototype",
          step_count: 2,
          steps: [],
          user_launchable: true,
          chained_from: [
            { id: "user_stories", beta: false, text: "User Stories" },
            { id: "ppt", beta: false, text: "PPT" },
            { id: "custom", beta: false, text: "Custom" },
          ],
        },
        {
          id: "custom",
          name: "Custom",
          display_name: "Custom",
          description: "Create custom",
          step_count: 0,
          steps: [],
          user_launchable: true,
          chained_from: [
            { id: "user_stories", beta: false, text: "User Stories" },
            { id: "ppt", beta: false, text: "PPT" },
            { id: "prototype", beta: false, text: "Prototype" },
          ],
        },
      ],
      workflowsStatus: "succeeded" as const,
      workflowsError: null,
      recentRuns: [],
      recentRunsStatus: "idle" as const,
      recentRunsError: null,
    },
  };
  renderWithProviders(<WorkflowHistory onBack={vi.fn()} onChainPipeline={onChainPipeline} />, { preloadedState });
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
// ─────────────────────────────────────────────────────────────────
// SHELL-03 — terminal-failure affordance on reopen (promoted onto RunDetailPage).
//
// The in-panel DegradedRunAffordance was RETIRED from WorkflowHistory (no dual
// implementation). The failure banner + failed-agent name resolution now render
// in the RunDetailPage summary column (fed by getRunSummary) — its own matrix is
// unit-covered in RunDetailPage.test.tsx. These WRAPPER tests prove the terminal
// reopen wiring: a terminal run surfaces the failure affordance (not a neutral
// empty preview), and a run with a deliverable still renders it (content preserved).
// ─────────────────────────────────────────────────────────────────
const AFFORDANCE_COPY = /this run did not complete successfully/i;
const CANCELLED_COPY = /this run was cancelled/i;
const NEUTRAL_COPY = /no preview available/i;
describe("WorkflowHistory — terminal-failure affordance on reopen (SHELL-03)", () => {
  it("a FAILED reopen surfaces the RunDetailPage failure banner + the failed agents' NAMES, and suppresses the neutral empty preview", async () => {
    const run = makeRun({
      type: "user_stories",
      status: "failed",
      output: "",
      error: "Pipeline failed — agent(s) failed: story-writer, story-estimator",
    });
    // The summary column resolves the failure + the failed-agent names.
    mockGetRunSummary.mockResolvedValue(
      summaryFor(run, [
        { agent_id: "story-writer", name: "Story Writer" },
        { agent_id: "story-estimator", name: "Story Estimator" },
      ]),
    );
    await renderAndOpenRun(run);
    expect(await screen.findByText(AFFORDANCE_COPY)).toBeInTheDocument();
    // The neutral empty-preview state is suppressed for a terminal-failure run.
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // Failed-agent NAMES (resolved from the summary agents), not raw ids.
    expect(screen.getAllByText("Story Writer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Story Estimator").length).toBeGreaterThan(0);
    // A failure is NOT a cancel.
    expect(screen.queryByText(CANCELLED_COPY)).not.toBeInTheDocument();
  });
  it("a CANCELLED reopen shows the cancelled-specific copy (via the summary column)", async () => {
    const run = makeRun({ type: "prototype", status: "cancelled", output: "", error: undefined });
    mockGetRunSummary.mockResolvedValue(summaryFor(run));
    await renderAndOpenRun(run);
    expect(await screen.findByText(CANCELLED_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });
  it("content wins — a FAILED run that produced a deliverable still renders it in the right column", async () => {
    // The deliverable preview is keyed on the persisted output, never a
    // client 'status==failed → hide content' guess. Summary column may error
    // (default reject) — the right column still shows the content.
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "failed",
        output: "# Partial user stories\n\nPartial content...",
        error: "Pipeline failed — agent(s) failed: story-writer",
      }),
    );
    expect(screen.getByTestId("userstory-preview")).toBeInTheDocument();
  });
  it("a COMPLETED run WITH content renders the content and no neutral empty state", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "completed",
        output: "# Real user stories\n\nAs a user...",
      }),
    );
    expect(screen.getByTestId("userstory-preview")).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });
});
// ─────────────────────────────────────────────────────────────────
// 40-06 — list-chrome restyle to the shell History mock: the "Run History"
// title kept (ND-W), the type-filter chips + Sort tabs, and the two distinct
// empty states (mock histZero + histFilterEmpty). The date-grouped rows +
// status/version badges are covered by RevisionFamilyView's own tests.
// ─────────────────────────────────────────────────────────────────
describe("WorkflowHistory — list chrome (40-06 restyle)", () => {
  it("renders the 'Run History' title (ND-W — NOT the mock's 'Workflow History')", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: [], total: 0 });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Run History" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Workflow History" })).not.toBeInTheDocument();
  });
  it("renders type-filter chips + the Sort segmented control over seeded runs", async () => {
    mockGetWorkflows.mockResolvedValue({
      runs: [
        makeRun({ id: "a", title: "Alpha stories", type: "user_stories", rootRunId: "a" }),
        makeRun({ id: "b", title: "Beta deck", type: "ppt", rootRunId: "b" }),
      ],
      total: 2,
    });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Alpha stories");
    // Type-filter chips (label + count) render from the live family counts.
    expect(screen.getByRole("button", { name: /^All/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^User Stories/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Presentation/ })).toBeInTheDocument();
    // Sort tabs (Recent / Tokens / Duration).
    expect(screen.getByRole("button", { name: /Sort by recent/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sort by tokens/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sort by duration/i })).toBeInTheDocument();
  });
  it("shows the ZERO empty-state (mock histZero) when there are no runs; Start a run → onBack", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: [], total: 0 });
    const onBack = vi.fn();
    renderWithProviders(<WorkflowHistory onBack={onBack} />);
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
    expect(screen.getByText("Your workflow runs will appear here.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Start a run" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
  it("shows the FILTER-EMPTY state (mock histFilterEmpty) when runs exist but none match; Show all runs restores", async () => {
    mockGetWorkflows.mockResolvedValue({
      runs: [
        makeRun({ id: "z", title: "Zebra deck", type: "ppt", rootRunId: "z" }),
      ],
      total: 1,
    });
    renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);
    await screen.findByText("Zebra deck");
    const search = screen.getByPlaceholderText("Search workflows...");
    await userEvent.type(search, "no-such-run-xyz");
    expect(await screen.findByText("No runs match this filter")).toBeInTheDocument();
    expect(screen.queryByText("Zebra deck")).not.toBeInTheDocument();
    // "Show all runs" clears the filter + search → the row returns.
    await userEvent.click(screen.getByRole("button", { name: "Show all runs" }));
    expect(await screen.findByText("Zebra deck")).toBeInTheDocument();
  });
});
