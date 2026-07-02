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
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>();
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
    mockGetWorkflows.mockResolvedValue([makeRun()]);
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
    mockGetWorkflows.mockResolvedValue([makeRun()]);
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
