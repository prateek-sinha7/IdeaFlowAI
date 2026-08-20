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

  it("does not show the live Output card before any output has streamed (no crash)", () => {
    render(<AgentDetailPanel agent={runningAgent({ output: "" })} onBack={() => {}} />);
    expect(screen.queryByText(/Output \(live\)/i)).not.toBeInTheDocument();
  });

  // Extended-thinking providers (Bedrock/Anthropic) always stream Reasoning to
  // completion before Output begins. Output stays unrendered while only Reasoning
  // is streaming; the moment the first output token arrives, Reasoning collapses
  // (and loses its live tag — reasoning is done by definition once output has
  // started) and Output takes over as the live one.
  it("shows only Reasoning (live) while output hasn't started yet", () => {
    render(
      <AgentDetailPanel
        agent={runningAgent({ output: "", thinkingText: "Considering the layout options" })}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText(/Reasoning \(live\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Considering the layout options/i)).toBeInTheDocument();
    expect(screen.queryByText(/Output \(live\)/i)).not.toBeInTheDocument();
  });

  it("collapses Reasoning and switches to live Output the moment output starts streaming", () => {
    const { rerender } = render(
      <AgentDetailPanel
        agent={runningAgent({ output: "", thinkingText: "Considering the layout options" })}
        onBack={() => {}}
      />,
    );
    expect(screen.getByText(/Reasoning \(live\)/i)).toBeInTheDocument();

    rerender(
      <AgentDetailPanel
        agent={runningAgent({
          output: "Building the prototype shell",
          thinkingText: "Considering the layout options",
        })}
        onBack={() => {}}
      />,
    );

    // Reasoning is no longer live (collapsed, but its header — sans "(live)" — is
    // still present; the body text is hidden once collapsed).
    expect(screen.queryByText(/Reasoning \(live\)/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^Reasoning$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Considering the layout options/i)).not.toBeInTheDocument();
    // Output is now the live one.
    expect(screen.getByText(/Output \(live\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Building the prototype shell/i)).toBeInTheDocument();
  });

  it("hides the live Output card once the agent is done (settled output takes over)", () => {
    render(
      <AgentDetailPanel
        agent={runningAgent({
          status: "done",
          output: "Final output text",
          thinkingText: "Considered the layout options",
        })}
        onBack={() => {}}
      />,
    );
    expect(screen.queryByText(/Output \(live\)/i)).not.toBeInTheDocument();
    // Reasoning stays visible but collapsed (output already started), no longer live.
    expect(screen.queryByText(/Considered the layout options/i)).not.toBeInTheDocument();
    expect(screen.getByText(/^Reasoning$/i)).toBeInTheDocument();
    expect(screen.queryByText(/Reasoning \(live\)/i)).not.toBeInTheDocument();
  });
});
