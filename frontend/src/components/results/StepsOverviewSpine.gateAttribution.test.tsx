import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentRunState, PipelineRunState } from "@/types/index";
import type { GateContext } from "@/components/chat/RunChatLane";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

// ─── BUG A11-2 — a `before-human` gate reviews the PREVIOUS step's output ─────
// (agents/capabilities/gates/human.py), but review_gate_ready carries only the
// GATED step's own agentId/agentName — the wire has no discriminator. This
// pins StepsOverviewSpine's derivation of `reviewsPriorStepName` off the LIVE
// agent roster (the gated agent's own status is still "idle" for a before-gate,
// since gates run before the step's own strategy dispatch) and confirms it
// reaches InlineGateActions, which relabels ("What Plan Lead wrote") or
// suppresses (no prior step identifiable) the evidence accordingly.

function agent(overrides: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "agent",
    name: "Agent",
    role: "role",
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...overrides,
  };
}

function ps(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

function gate(overrides: Partial<GateContext> = {}): GateContext {
  return {
    agentId: "shell-builder",
    agentName: "Shell Builder",
    output: "{\"tasks\":[]}",
    gateKey: "run-1:shell-builder:0",
    artifactKind: "task_list",
    ...overrides,
  };
}

describe("BUG A11-2 — StepsOverviewSpine derives reviewsPriorStepName", () => {
  it("a before-gate on an idle step attributes the output to the nearest preceding DONE agent", () => {
    const planLead = agent({ id: "plan-lead", name: "Plan Lead", index: 0, status: "done" });
    const shellBuilder = agent({ id: "shell-builder", name: "Shell Builder", index: 1, status: "idle" });
    render(
      <StepsOverviewSpine
        agents={[planLead, shellBuilder]}
        pipelineState={ps({ agents: [planLead, shellBuilder] })}
        onOpenAgent={vi.fn()}
        laneGate={gate()}
        onApproveGate={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Approve Plan Lead’s output before Shell Builder runs?",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("What Plan Lead wrote")).toBeInTheDocument();
    expect(screen.queryByText("What Shell Builder wrote")).toBeNull();
  });

  it("a post-step gate (the gated agent already started/finished) is unaffected — no attribution override", () => {
    const analyzer = agent({ id: "analyzer", name: "Analyzer", index: 0, status: "done" });
    render(
      <StepsOverviewSpine
        agents={[analyzer]}
        pipelineState={ps({ agents: [analyzer] })}
        onOpenAgent={vi.fn()}
        laneGate={gate({ agentId: "analyzer", agentName: "Analyzer" })}
        onApproveGate={vi.fn()}
      />,
    );

    expect(screen.getByText("What Analyzer wrote")).toBeInTheDocument();
  });

  it("the fallback case (gated agent not yet in the roster at all) still attributes to the last done agent", () => {
    const planLead = agent({ id: "plan-lead", name: "Plan Lead", index: 0, status: "done" });
    render(
      <StepsOverviewSpine
        agents={[planLead]}
        pipelineState={ps({ agents: [planLead] })}
        onOpenAgent={vi.fn()}
        laneGate={gate()} // agentId "shell-builder" — not in `agents` yet
        onApproveGate={vi.fn()}
      />,
    );

    expect(screen.getByText("What Plan Lead wrote")).toBeInTheDocument();
  });

  it("a before-gate with no identifiable prior step suppresses the mismatched evidence instead of mislabeling it", () => {
    const shellBuilder = agent({ id: "shell-builder", name: "Shell Builder", index: 0, status: "idle" });
    render(
      <StepsOverviewSpine
        agents={[shellBuilder]}
        pipelineState={ps({ agents: [shellBuilder] })}
        onOpenAgent={vi.fn()}
        laneGate={gate()}
        onApproveGate={vi.fn()}
      />,
    );

    expect(screen.queryByText(/^What .* wrote$/)).toBeNull();
    expect(screen.getByTestId("chat-gate-evidence-suppressed")).toBeInTheDocument();
  });
});
