import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

// The engine streams the model's output via `agent_chunk` into `agent.output`, but
// emits NO separate reasoning/thinking stream, so `agent.thinkingText` is always
// empty for every agent. Before the fix the detail panel fed its live card from
// `thinkingText`, so a running agent showed a blank "Reasoning (live)" cursor with
// no text. The panel must instead surface the live `output` so every running agent
// (spec-writer, plan, analyze, build…) shows its work.
function runningAgent(overrides: Record<string, unknown> = {}) {
  return {
    id: "spec-writer",
    name: "Spec Writer",
    role: "Domain analysis",
    status: "running",
    output: "",
    thinkingText: "",
    thinking: "",
    contextSources: [],
    toolCalls: [],
    ...overrides,
  } as never;
}

describe("AgentDetailPanel — live output while running", () => {
  it("streams agent.output into the live card for a running agent (no separate reasoning stream)", () => {
    render(
      <AgentDetailPanel
        agent={runningAgent({ output: "Analyzing the domain model and drafting user stories" })}
        onBack={() => {}}
      />,
    );
    // The live card is labelled "Output (live)" (not the old empty "Reasoning (live)").
    expect(screen.getByText(/Output \(live\)/i)).toBeInTheDocument();
    // …and the streaming text is actually rendered.
    expect(screen.getByText(/Analyzing the domain model/i)).toBeInTheDocument();
  });

  it("shows the live card even before any output has streamed (no crash)", () => {
    render(<AgentDetailPanel agent={runningAgent({ output: "" })} onBack={() => {}} />);
    expect(screen.getByText(/Output \(live\)/i)).toBeInTheDocument();
  });
});
