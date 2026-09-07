/**
 * WorkflowHistory.modelChip.test.tsx — RFN-001 history-reopen data-flow coverage.
 *
 * WorkflowHistory's responsibility is to transform persisted `agent_outputs` JSON
 * (from the DB via `WorkflowRun.agentOutputs`) into `AgentRunState[]` objects
 * (`thinkingAgents`) that are passed to `AgentThinkingTab`. The model chip is
 * rendered by `AgentDetailPanel` (tested separately in
 * `AgentDetailPanel.modelChip.test.tsx`); this suite only asserts that the
 * `modelId` field is correctly threaded through the data pipeline.
 *
 * Approach: render WorkflowHistory with a mocked run, switch to the Thinking tab,
 * then check that `AgentThinkingTab` receives agents with `modelId` populated
 * by spying on the prop value via a render-capturing mock.
 *
 *  1. model_id in persisted agent_outputs is passed as modelId to AgentThinkingTab.
 *  2. No model_id in agent_outputs → modelId is undefined (graceful degrade).
 *  3. Build agent that ran twice → last model_id wins (keep-last dedup).
 *  4. No crash when agentOutputs is absent entirely.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { AgentRunState, WorkflowRun } from "@/types/index";
import { renderWithProviders } from "@/test/renderWithProviders";

// ─── Capture spy for AgentThinkingTab agents prop ────────────────────────────
// We want to inspect the agents array that WorkflowHistory passes to AgentThinkingTab
// so we can assert model_id was threaded through without needing to render a full
// interactive agent list.
let _capturedAgents: AgentRunState[] = [];

vi.mock("@/components/results/AgentThinkingTab", () => ({
  AgentThinkingTab: ({ agents }: { agents: AgentRunState[] }) => {
    // Capture the agents prop every time this renders
    _capturedAgents = agents;
    return <div data-testid="thinking-tab" />;
  },
}));

// ─── Other API + component mocks (same pattern as genericReopen tests) ────────
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<
  (token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>
>();
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
  PPTPreview: () => <div data-testid="ppt-preview" />,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: () => <div data-testid="userstory-preview" />,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: () => <div data-testid="prototype-preview" />,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: () => <div data-testid="markdown-preview" />,
}));
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: () => <div data-testid="appbuilder-preview" />,
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (_wt: string, _c?: string, fallback?: string) =>
    fallback || "deliverable",
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => ({ get: vi.fn(() => null) }),
}));

const _STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !_STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import { WorkflowHistory } from "./WorkflowHistory";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function agentOutputsJson(
  agents: Array<{
    agent_id: string;
    name: string;
    role?: string;
    icon?: string;
    output?: string;
    duration?: number | null;
    model_id?: string;
  }>,
) {
  return JSON.stringify(
    agents.map((a) => ({
      icon: "✍️",
      role: "Agent",
      output: "Agent output here.",
      duration: 12.0,
      input_tokens: 1000,
      output_tokens: 400,
      total_tokens: 1400,
      ...a,
    })),
  );
}

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-mc-1",
    title: "Model chip data-flow run",
    type: "custom",
    status: "completed",
    input: "build something",
    output: "# Done\n\nDeliverable.",
    createdAt: new Date("2026-09-07T10:00:00Z").toISOString(),
    completedAt: new Date("2026-09-07T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 2,
    parentRunId: null,
    rootRunId: "run-mc-1",
    ...overrides,
  };
}

async function renderAndSwitchToThinking(run: WorkflowRun) {
  _capturedAgents = [];
  mockGetWorkflows.mockResolvedValue({ runs: [run], total: 1 });
  mockGetWorkflow.mockResolvedValue(run);

  renderWithProviders(<WorkflowHistory onBack={vi.fn()} />);

  // Open the run detail
  const item = await screen.findByText(run.title);
  await userEvent.click(item);
  await waitFor(() =>
    expect(screen.getAllByText(run.title).length).toBeGreaterThan(0),
  );

  // Switch to the "Thinking" tab — it's a plain button with text "Thinking"
  const thinkingBtn = await screen.findByRole("button", { name: /^thinking$/i });
  await userEvent.click(thinkingBtn);

  // Wait for AgentThinkingTab to render (our spy sets _capturedAgents)
  await waitFor(() => expect(screen.getByTestId("thinking-tab")).toBeInTheDocument());
}

beforeEach(() => {
  cleanup();
  _capturedAgents = [];
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
});

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("WorkflowHistory — model chip data-flow (RFN-001)", () => {
  // ── 1. model_id flows from agent_outputs through thinkingAgents ───────────

  it("threads model_id from persisted agent_outputs into the modelId field of each AgentRunState passed to AgentThinkingTab", async () => {
    // RFN-001: run_commands.py persists model_id per-agent in agent_outputs.
    // WorkflowHistory must carry it into thinkingAgents → AgentRunState.modelId
    // so AgentDetailPanel can render the chip when a completed run is reopened.
    const run = makeRun({
      agentOutputs: agentOutputsJson([
        {
          agent_id: "spec-writer",
          name: "Spec Writer",
          model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        },
        {
          agent_id: "plan-agent",
          name: "Plan Agent",
          model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        },
      ]),
    });

    await renderAndSwitchToThinking(run);

    expect(_capturedAgents).toHaveLength(2);

    const specWriter = _capturedAgents.find((a) => a.id === "spec-writer");
    expect(specWriter?.modelId).toBe("eu.anthropic.claude-sonnet-4-5-20250929-v1:0");

    const planAgent = _capturedAgents.find((a) => a.id === "plan-agent");
    expect(planAgent?.modelId).toBe("eu.anthropic.claude-haiku-4-5-20251001-v1:0");
  });

  // ── 2. Absent model_id → modelId is undefined (graceful degrade) ──────────

  it("sets modelId to undefined when model_id is absent from agent_outputs (graceful degrade for pre-RFN-001 runs)", async () => {
    const run = makeRun({
      agentOutputs: agentOutputsJson([
        {
          agent_id: "spec-writer",
          name: "Spec Writer",
          // No model_id — simulates a run persisted before the engine change
        },
      ]),
    });

    await renderAndSwitchToThinking(run);

    expect(_capturedAgents).toHaveLength(1);
    expect(_capturedAgents[0].modelId).toBeUndefined();
  });

  // ── 3. Dedup keep-last: repeated agent keeps the last model_id ────────────

  it("keeps the last model_id for a repeated agent (build loop dedup keep-last semantics)", async () => {
    // Two entries for the same agent_id — first used Haiku, second used Sonnet.
    // The dedup branch must keep the last non-null model_id.
    const run = makeRun({
      agentOutputs: JSON.stringify([
        {
          agent_id: "build-agent",
          name: "Build Agent",
          role: "Builder",
          icon: "🔨",
          output: "First pass",
          duration: 30,
          input_tokens: 500,
          output_tokens: 200,
          total_tokens: 700,
          model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        },
        {
          agent_id: "build-agent",
          name: "Build Agent",
          role: "Builder",
          icon: "🔨",
          output: "Second pass",
          duration: 25,
          input_tokens: 480,
          output_tokens: 190,
          total_tokens: 670,
          model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        },
      ]),
    });

    await renderAndSwitchToThinking(run);

    // Dedup merges repeated agent_id entries → one entry for build-agent
    expect(_capturedAgents).toHaveLength(1);
    expect(_capturedAgents[0].id).toBe("build-agent");
    // Keep-last: Sonnet wins over Haiku
    expect(_capturedAgents[0].modelId).toBe("eu.anthropic.claude-sonnet-4-5-20250929-v1:0");
  });

  // ── 4. No crash when agentOutputs is absent ───────────────────────────────

  it("renders the Thinking tab without crashing when agentOutputs is null", async () => {
    const run = makeRun({ agentOutputs: undefined });

    await renderAndSwitchToThinking(run);

    // AgentThinkingTab renders with an empty agents array — no throw
    expect(_capturedAgents).toHaveLength(0);
  });
});
