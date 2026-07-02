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
  // B2: WorkflowHistory now fetches the revision family on detail-open. This
  // suite doesn't assert the version timeline, so return an empty family
  // (VersionTimeline renders null for <2 members) — this only prevents the
  // undefined-mock-export throw that would otherwise crash render.
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
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
    parentRunId: null,
    rootRunId: "run-1",
    ...overrides,
  };
}

// ISS-024 — a persisted agent_output entry ({agent_id,name}) used as the
// history surface's id→name source for the failed-agents affordance.
function makeAgentOutput(
  agentId: string,
  name: string,
): import("@/types/index").AgentThinkingEntry {
  return {
    agent_id: agentId,
    name,
    role: "Agent",
    icon: "",
    thinking: "",
    output: "",
    duration: null,
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

// ─────────────────────────────────────────────────────────────────
// ISS-017 (gap-fix) — history-reopen terminal-failure affordance.
//
// The live PreviewPanel path showed a degraded/failed affordance for a
// terminal-empty run, but the REAL history surface (WorkflowHistory detail)
// showed the neutral "No preview available" — SC3 was only half-met. These
// cases prove the affordance now renders on the history-reopen path too,
// STRICTLY gated on the persisted server status (no client empty==failed guess).
// ─────────────────────────────────────────────────────────────────

const AFFORDANCE_COPY = /this run did not complete successfully/i;
const CANCELLED_COPY = /this run was cancelled/i;
const NEUTRAL_COPY = /no preview available/i;

describe("WorkflowHistory — terminal-failure affordance on reopen (ISS-017)", () => {
  it("reopening a FAILED run with empty output renders the affordance + the failed agents' NAMES (ISS-024), not raw ids", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "failed",
        output: "",
        // Persisted failed-agent ids parsed by the SHARED parseFailedAgentIds.
        error: "Pipeline failed — agent(s) failed: story-writer, story-estimator",
        // ISS-024: the history surface's id→name source is the persisted
        // agentOutputs ({agent_id,name}); the affordance must show the NAMES.
        agentOutputs: [
          makeAgentOutput("story-writer", "Story Writer"),
          makeAgentOutput("story-estimator", "Story Estimator"),
        ],
      }),
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    // ISS-024: the human NAMES appear (resolved from agentOutputs), not raw ids.
    // (queryByText for the id would also match the sidebar agent card, so we
    // assert presence of the names — the affordance list item — instead.)
    expect(screen.getAllByText("Story Writer").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Story Estimator").length).toBeGreaterThan(0);
    // A failure is NOT a cancel — keeps the failed/degraded copy.
    expect(screen.queryByText(CANCELLED_COPY)).not.toBeInTheDocument();
  });

  it("reopening a FAILED run whose agentOutputs DON'T name a failed id falls back to the raw id (ISS-024, never blank)", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "failed",
        output: "",
        error: "Pipeline failed — agent(s) failed: story-writer, ghost-agent",
        // Only one of the two failed ids has a name source — the other must
        // fall back to its raw id rather than render blank.
        agentOutputs: [makeAgentOutput("story-writer", "Story Writer")],
      }),
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    // Known id → resolved name.
    expect(screen.getAllByText("Story Writer").length).toBeGreaterThan(0);
    // Unknown id → raw-id fallback (no agentOutputs card for it, so this is the
    // affordance list item).
    expect(screen.getByText("ghost-agent")).toBeInTheDocument();
  });

  it("reopening a CANCELLED run with empty output renders the cancelled-specific copy (not failed/degraded, not neutral)", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "prototype",
        status: "cancelled",
        output: "",
        error: undefined,
      }),
    );

    // IN-03: a deliberate user Stop reads "cancelled", not "failed or degraded".
    expect(screen.getByText(CANCELLED_COPY)).toBeInTheDocument();
    expect(screen.queryByText(/failed or degraded/i)).not.toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });

  it("reopening a DEGRADED run with empty output renders the affordance + the wired failed-agent list", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "ppt",
        status: "degraded",
        output: "",
        error: "Run degraded — agent(s) failed: ppt-validator",
      }),
    );

    expect(screen.getByText(AFFORDANCE_COPY)).toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
    expect(screen.getByText("ppt-validator")).toBeInTheDocument();
    // A degraded reopen is NOT a cancel.
    expect(screen.queryByText(CANCELLED_COPY)).not.toBeInTheDocument();
  });

  it("reopening a COMPLETED run WITH content renders the content, NOT the affordance and NOT the neutral state", async () => {
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "completed",
        output: "# Real user stories\n\nAs a user...",
      }),
    );

    // The deliverable renders (mocked UserStoryPreview marker); no affordance.
    expect(screen.getByTestId("userstory-preview")).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
    expect(screen.queryByText(CANCELLED_COPY)).not.toBeInTheDocument();
    expect(screen.queryByText(NEUTRAL_COPY)).not.toBeInTheDocument();
  });

  it("reopening a FAILED run that DID produce content renders the content, NOT the affordance (content wins; server-status-gated only inside the empty branch)", async () => {
    // A failed run that still persisted a partial deliverable must show it — the
    // affordance fires only in the !selectedOutput neutral branch, never as a
    // client 'status==failed → hide content' guess.
    await renderAndOpenRun(
      makeRun({
        type: "user_stories",
        status: "failed",
        output: "# Partial user stories\n\nPartial content...",
        error: "Pipeline failed — agent(s) failed: story-writer",
      }),
    );

    expect(screen.getByTestId("userstory-preview")).toBeInTheDocument();
    expect(screen.queryByText(AFFORDANCE_COPY)).not.toBeInTheDocument();
  });
});
