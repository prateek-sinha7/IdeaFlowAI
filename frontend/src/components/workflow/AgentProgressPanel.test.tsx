import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentProgressPanel } from "./AgentProgressPanel";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";

// Mock `motion/react`. The library doesn't run reliably under jsdom and
// none of these tests care about animation. Each `motion.X` access
// (e.g. `motion.button`) returns a component that renders the same
// underlying HTML tag — so role-based queries (`getByRole("button")`)
// still work. Motion-specific props (`initial`, `animate`, `transition`)
// are stripped so React doesn't warn about unknown DOM attributes.
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

// React must be in scope for the createElement call above.
import React from "react";

function makeAgent(id: string, status: AgentRunState["status"] = "done"): AgentRunState {
  return {
    id,
    name: id.replace(/-/g, " "),
    role: "test role",
    icon: "🤖",
    status,
    output: "",
    thinking: "",
    duration: 1,
    error: null,
    index: 0,
  };
}

function makeCompletedState(agentIds: string[]): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "ppt",
    agents: agentIds.map((id) => makeAgent(id, "done")),
    currentAgentIndex: agentIds.length - 1,
    totalDuration: 42,
    completedCount: agentIds.length,
  };
}

function makeRunningState(agentIds: string[]): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "ppt",
    agents: agentIds.map((id, i) => makeAgent(id, i === 0 ? "running" : "idle")),
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
  };
}

// ─────────────────────────────────────────────────────────────────
// "Suggested next steps" rendering rules
// ─────────────────────────────────────────────────────────────────

describe("AgentProgressPanel — Suggested next steps", () => {
  it("hides the chain panel while the pipeline is running", () => {
    render(
      <AgentProgressPanel
        pipelineState={makeRunningState(["a1", "a2"])}
        workflowType={"ppt" as WorkflowType}
        onChainPipeline={vi.fn()}
      />,
    );
    expect(screen.queryByText(/suggested next steps/i)).not.toBeInTheDocument();
  });

  it("hides the chain panel when onChainPipeline is not provided", () => {
    // Guards the gate at DashboardLayout:454 — if the parent decides
    // the workflow is non-chainable, the panel must not render even
    // if the pipeline has completed.
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"custom" as WorkflowType}
      />,
    );
    expect(screen.queryByText(/suggested next steps/i)).not.toBeInTheDocument();
  });

  it("shows the chain panel with all sibling targets after a base run completes", () => {
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"ppt" as WorkflowType}
        onChainPipeline={vi.fn()}
      />,
    );
    expect(screen.getByText(/suggested next steps/i)).toBeInTheDocument();
    // Use button-role queries so the workflow's own header label
    // ("Presentation" appears in the top-of-panel pipeline label too)
    // can't false-positive the chain-tile check.
    expect(screen.getByRole("button", { name: /user stories/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prototype/i })).toBeInTheDocument();
    // The just-completed base type must not be offered back to itself.
    expect(screen.queryByRole("button", { name: /^presentation/i })).not.toBeInTheDocument();
  });

  it("treats a `_revision` completion the same as its base for the filter", () => {
    // The bug fix: after a `ppt_revision`, "Presentation" must not be
    // re-suggested as a chain target.
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"ppt_revision" as WorkflowType}
        onChainPipeline={vi.fn()}
      />,
    );
    expect(screen.getByText(/suggested next steps/i)).toBeInTheDocument();
    // Query the chain TILES by button role: "Presentation" also appears as the
    // panel's own header label (the current run's display name), so a plain
    // getByText would false-positive on the header — mirror the sibling test.
    expect(screen.queryByRole("button", { name: /^presentation/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /user stories/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prototype/i })).toBeInTheDocument();
  });

  it("respects completedPipelineTypes (multi-chain history)", () => {
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"ppt" as WorkflowType}
        completedPipelineTypes={["user_stories"]}
        onChainPipeline={vi.fn()}
      />,
    );
    expect(screen.getByText(/suggested next steps/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prototype/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /user stories/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^presentation/i })).not.toBeInTheDocument();
  });

  it("calls onChainPipeline with the picked workflow type when a tile is clicked", async () => {
    const onChainPipeline = vi.fn();
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"ppt" as WorkflowType}
        onChainPipeline={onChainPipeline}
      />,
    );
    await userEvent.click(screen.getByText("User Stories"));
    expect(onChainPipeline).toHaveBeenCalledTimes(1);
    expect(onChainPipeline).toHaveBeenCalledWith("user_stories");
  });

  it("hides the chain panel when every base type is already complete", () => {
    render(
      <AgentProgressPanel
        pipelineState={makeCompletedState(["a1"])}
        workflowType={"ppt" as WorkflowType}
        completedPipelineTypes={["user_stories", "prototype"]}
        onChainPipeline={vi.fn()}
      />,
    );
    expect(screen.queryByText(/suggested next steps/i)).not.toBeInTheDocument();
  });
});
