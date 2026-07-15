import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowRun, RunFamily } from "@/types/index";
import type { RunArtifactsResponse } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Workstream C2 (POR §5 D3+D4 / §6.6) — the REOPEN mount. On detail-open
// WorkflowHistory fetches getRunArtifacts(kind="clarifications") and threads
// selectedRun.input + the parsed rounds to the Thinking tab, where the real
// AgentThinkingTab renders StartingPointCard + ClarificationsCard. Cloned from
// the WorkflowHistory.family.test harness with getRunArtifacts in the mock.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>(
  () => Promise.resolve({ root_id: "", members: [] }),
);
const mockGetRunArtifacts = vi.fn<(token: string, id: string, opts?: { kind?: string; includeContent?: boolean }) => Promise<RunArtifactsResponse>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
  getRunArtifacts: (token: string, id: string, opts?: { kind?: string; includeContent?: boolean }) => mockGetRunArtifacts(token, id, opts),
}));

vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div /> }));
vi.mock("@/components/preview/UserStoryPreview", () => ({ UserStoryPreview: () => <div /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div /> }));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div data-testid="files-tab" /> }));
vi.mock("@/components/workflow/TokenUsageSummary", () => ({ TokenUsageSummary: () => <div data-testid="token-usage" /> }));

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
    id: "solo",
    title: "Landing page run",
    type: "prototype",
    status: "completed",
    input: "Build a plain landing page brief.",
    output: "<html>hi</html>",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 1,
    parentRunId: null,
    rootRunId: "solo",
    ...overrides,
  };
}

function clarifyArtifacts(): RunArtifactsResponse {
  return {
    workflow_id: "solo",
    // One artifact whose content is a JSON list spanning 1 round.
    artifacts: [
      { content: JSON.stringify([{ question_id: "q1", question_text: "Auth method?", impact_level: "high", answer: "OAuth", round: 1 }]) },
    ] as unknown as RunArtifactsResponse["artifacts"],
  };
}

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
  mockGetRunFamily.mockReset().mockResolvedValue({ root_id: "", members: [] });
  mockGetRunArtifacts.mockReset();
});

describe("WorkflowHistory reopen — clarify fetch + Starting point (C2)", () => {
  it("fetches getRunArtifacts(kind=clarifications) and renders the brief + clarify round on the Thinking tab", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: [makeRun()], total: 1 });
    mockGetWorkflow.mockResolvedValue(makeRun());
    mockGetRunArtifacts.mockResolvedValue(clarifyArtifacts());

    render(<WorkflowHistory onBack={vi.fn()} />);

    // Open the run's detail.
    fireEvent.click(await screen.findByText("Landing page run"));

    // The reopen effect fetches the clarify artifacts with the expected filter.
    await waitFor(() =>
      expect(mockGetRunArtifacts).toHaveBeenCalledWith("test-token", "solo", { kind: "clarifications", includeContent: true }),
    );

    // Switch to the Thinking tab → real AgentThinkingTab renders both C2 cards.
    fireEvent.click(screen.getByText("Thinking"));

    // StartingPointCard renders the run's brief (from selectedRun.input).
    await waitFor(() => expect(screen.getAllByText("Build a plain landing page brief.").length).toBeGreaterThan(0));
    // ClarificationsCard renders the fetched round.
    expect(screen.getByText("Auth method?")).toBeInTheDocument();
    expect(screen.getByText("✓ OAuth")).toBeInTheDocument();
  });

  it("shows NO ClarificationsCard for a PROCEED reopen (empty artifacts)", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: [makeRun()], total: 1 });
    mockGetWorkflow.mockResolvedValue(makeRun());
    mockGetRunArtifacts.mockResolvedValue({ workflow_id: "solo", artifacts: [] });

    render(<WorkflowHistory onBack={vi.fn()} />);
    fireEvent.click(await screen.findByText("Landing page run"));
    await waitFor(() => expect(mockGetRunArtifacts).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Thinking"));

    // Starting point still renders; Clarifications card is absent (PROCEED run).
    await waitFor(() => expect(screen.getAllByText("Build a plain landing page brief.").length).toBeGreaterThan(0));
    expect(screen.queryByText("Clarifications")).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────
// C-FLAG-1 + C-FLAG-2 (260703-174) — the REOPEN mount now threads
// revisionParentVersion (computed from the fetched family + selectedRun.parentRunId)
// AND originalBriefRootRunId, so on a revision reopen the StartingPointCard renders
// the "revision of v{n}" chip + the "Original brief (v1)" expander. This asserts at
// the MOUNT level (StartingPointCard's own chip rendering is unit-tested elsewhere).
// ─────────────────────────────────────────────────────────────────
describe("WorkflowHistory reopen — revision chip + Original-brief expander (C-FLAG-1/2)", () => {
  it("a revision reopen renders the 'revision of v1' chip + the Original-brief expander", async () => {
    const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
    const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
    const revisionRun = makeRun({
      id: "r1",
      title: "Revised run",
      type: "prototype_revision",
      input: "=== REVISION REQUEST ===\nmake the header blue\n=== END REQUEST ===",
      parentRunId: "root",
      rootRunId: "root",
    });
    mockGetWorkflows.mockResolvedValue({ runs: [revisionRun], total: 1 });
    mockGetWorkflow.mockResolvedValue(revisionRun);
    mockGetRunFamily.mockResolvedValue({
      root_id: "root",
      members: [
        { id: "root", type: "prototype", title: "v1", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
        { id: "r1", type: "prototype_revision", title: "v2", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
      ],
    } as unknown as RunFamily);
    // Empty clarify artifacts — isolates the chip/expander under test.
    mockGetRunArtifacts.mockResolvedValue({ workflow_id: "r1", artifacts: [] });

    render(<WorkflowHistory onBack={vi.fn()} />);
    fireEvent.click(await screen.findByText("Revised run"));

    // The reopen family fetch (keyed on the STABLE rootRunId) resolves →
    // revisionParentVersion becomes computable.
    await waitFor(() => expect(mockGetRunFamily).toHaveBeenCalledWith("test-token", "root"));

    fireEvent.click(screen.getByText("Thinking"));

    // Parent "root" is family index 0 → 1-based v1 → "revision of v1" chip.
    await waitFor(() => expect(screen.getByText(/revision of v1/i)).toBeInTheDocument());
    // Live/reopen symmetry — the Original-brief (v1) expander is present.
    expect(screen.getByRole("button", { name: /original brief version 1/i })).toBeInTheDocument();
  });
});
