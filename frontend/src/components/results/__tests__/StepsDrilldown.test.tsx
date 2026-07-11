import { describe, expect, it, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import type { AgentRunState, PipelineRunState, WaveGroup } from "@/types/index";
import type { GateContext } from "@/components/chat/RunChatLane";
import type { ClarifyQuestion } from "@/components/preview/QuestionnairePanel";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 32 plan 08 (SC-2, STEPS-ARTIFACT-DERIVATION-CONTRACT) — the Steps
// drill-down construction contract, proven off SCRIPTED events. Re-anchored for
// the Phase 39 plan 02 three-level nav: the construction block (dual-source
// checklist + WaveTreePanel) now lives inside the construction agent's L2 detail,
// so each construction spec first DRILLS into the Build Agent row before asserting.
//   §2 dual-source: task_progress (completed_count) AND wave_*/subagent_*
//       (WaveTreePanel) both feed the construction block.
//   §3 KAN-99: the checklist caps at N-1 until agent_complete; completed_count
//       == total-1 is the expected fix-loop steady state, NOT a stall.
//   ISS-019: WaveTreePanel is mounted INSIDE the drill-down (not below the fold).
// The inline gate/clarify (unchanged surfaces) stay on the overview spine.
// TokenUsageSummary is stubbed (parity with the sibling AgentThinkingTab specs).
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "../AgentThinkingTab";

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Build",
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...partial,
  };
}

// Source B — the fan-out waves + workers (subagent_spawned → subagent_result).
const WAVES: WaveGroup[] = [
  {
    waveIndex: 0,
    step: "build",
    taskIds: ["t1", "t2"],
    status: "running",
    workers: [
      { agent: "worker-alpha", status: "done", worker: 0 },
      { agent: "worker-beta", status: "running", worker: 1 },
    ],
  },
  {
    waveIndex: 1,
    step: "build",
    taskIds: ["t3"],
    status: "pending",
    workers: [],
  },
];

function buildState(over: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [makeAgent({ id: "prototype-build", name: "Build Agent", status: "running" })],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    // Source A — the task-loop checklist (task_progress.completed_count).
    protoCompletedTaskCount: 2,
    ...over,
  };
}

/** Drill into the Build Agent's L2 detail (where the construction block lives). */
function openBuildDetail() {
  fireEvent.click(screen.getByRole("button", { name: /Build Agent/i }));
}

describe("Steps drill-down — construction dual-source + KAN-99 cap (SC-2)", () => {
  it("renders BOTH sources: the task_progress checklist AND the wave/subagent tree (ISS-019 mounted in the drill-down)", () => {
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState()}
        waves={WAVES}
      />,
    );
    openBuildDetail();

    // Source B — WaveTreePanel is mounted INSIDE the Steps drill-down (ISS-019).
    expect(screen.getByText("Wave / Subagent Tree")).toBeInTheDocument();
    expect(screen.getByText("Wave 0")).toBeInTheDocument();
    expect(screen.getByText("worker-alpha")).toBeInTheDocument();
    expect(screen.getByText("worker-beta")).toBeInTheDocument();

    // Source A — the task-loop checklist renders its progress counter.
    expect(screen.getByTestId("construction-progress")).toBeInTheDocument();
  });

  it("KAN-99: caps the checklist at N-1 while the pipeline runs (completed_count == total-1 is not a stall)", () => {
    // total tasks = unique wave taskIds = t1,t2,t3 = 3; completed_count = 2 = N-1.
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState({ isRunning: true, protoCompletedTaskCount: 2 })}
        waves={WAVES}
      />,
    );
    openBuildDetail();

    const progress = screen.getByTestId("construction-progress");
    // Capped at N-1 (2 / 3) — NOT prematurely 3 / 3.
    expect(progress).toHaveTextContent("2 / 3");
    // No stall / error affordance for the expected fix-loop steady state.
    const block = screen.getByTestId("construction-block");
    expect(within(block).queryByText(/stall|stalled|error/i)).toBeNull();
  });

  it("KAN-99: reaches N only on agent_complete (build done + pipeline terminal)", () => {
    render(
      <AgentThinkingTab
        agents={[makeAgent({ id: "prototype-build", name: "Build Agent", status: "done" })]}
        pipelineState={buildState({
          isRunning: false,
          protoCompletedTaskCount: 3,
          agents: [makeAgent({ id: "prototype-build", name: "Build Agent", status: "done" })],
        })}
        waves={WAVES.map((w) => ({ ...w, status: "completed" }))}
      />,
    );
    openBuildDetail();

    expect(screen.getByTestId("construction-progress")).toHaveTextContent("3 / 3");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Inline gate/clarify in the Steps drill-down — the plan-06/07 dormant gate/
// clarify passthrough is now CONSUMED via the REUSED generic InlineGateActions /
// InlineClarifyActions (KAN-101/95/100/98). Same generic approve_review /
// submit_questionnaire channels; the Update-the-Specs affordance is driven off
// updateSpecsEligible, never a workflow name (SC-001).
// ─────────────────────────────────────────────────────────────────────────────
describe("Steps drill-down — inline gate/clarify (SC-2, KAN cluster)", () => {
  const GATE: GateContext = {
    agentId: "gate-agent",
    agentName: "Spec Agent",
    output: "<spec>\n## Overview\nA thing.\n</spec>",
    gateKey: "run-1:gate",
    redoable: false,
    updateSpecsEligible: true,
    approveLabel: "Approve the spec",
  };

  function renderGate(over: Partial<GateContext> = {}, running = true) {
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState({ isRunning: running })}
        laneGate={{ ...GATE, ...over }}
        onApproveGate={vi.fn()}
        onRejectGate={vi.fn()}
        onUpdateSpecsGate={vi.fn()}
      />,
    );
  }

  it("renders the inline gate card via the reused InlineGateActions", () => {
    renderGate();
    expect(screen.getByTestId("chat-gate-actions")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-approve")).toBeInTheDocument();
  });

  it("shows Update-the-Specs ONLY when updateSpecsEligible (KAN-101, generic flag)", () => {
    renderGate({ updateSpecsEligible: true });
    expect(screen.getByTestId("chat-gate-update-specs")).toBeInTheDocument();
  });

  it("hides Update-the-Specs when NOT eligible", () => {
    renderGate({ updateSpecsEligible: false });
    expect(screen.queryByTestId("chat-gate-update-specs")).toBeNull();
  });

  it("KAN-100 terminal fence: renders NO gate actions once the pipeline is not running", () => {
    renderGate({}, false);
    expect(screen.queryByTestId("chat-gate-actions")).toBeNull();
  });

  it("renders the inline clarify card and emits the canonical [{question_id, answer}]", () => {
    const onSubmitClarify = vi.fn();
    const questions: ClarifyQuestion[] = [
      { id: "q1", question: "Which auth?", options: ["OAuth", "SAML"] } as ClarifyQuestion,
    ];
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState()}
        clarifyQuestions={questions}
        onSubmitClarify={onSubmitClarify}
        onSkipClarify={vi.fn()}
      />,
    );
    expect(screen.getByTestId("chat-clarify-actions")).toBeInTheDocument();
    fireEvent.click(screen.getAllByTestId("chat-clarify-chip")[0]);
    fireEvent.click(screen.getByTestId("chat-clarify-submit"));
    expect(onSubmitClarify).toHaveBeenCalledWith([{ question_id: "q1", answer: "OAuth" }]);
  });
});
