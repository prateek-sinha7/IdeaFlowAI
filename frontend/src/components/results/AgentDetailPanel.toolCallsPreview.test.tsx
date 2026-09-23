import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

// ISS-355: the collapsed one-line tool-call summary coerces array/object argument
// values with bare `String(v)`, producing the literal text "[object Object]" instead
// of a readable preview. Reproduced on a completed run's write_todos calls.
//
// ISS-585: ToolCallsSection (the component rendering that summary) has no
// isRunning gate, so the identical broken text should also appear while a run is
// still `running` (live), not only once it is `completed`.
function agentWithToolCalls(status: string, overrides: Record<string, unknown> = {}) {
  return {
    id: "deck-engineer",
    name: "Deck Engineer Agent",
    role: "Deck assembly",
    status,
    output: "",
    thinkingText: "",
    thinking: "",
    contextSources: [],
    toolCalls: [
      {
        tool: "write_todos",
        args: { todos: [{ content: "Draft outline", status: "in_progress" }] },
        result: status === "completed" ? "ok" : null,
        timestamp: "2026-08-28T08:00:00Z",
      },
    ],
    ...overrides,
  } as never;
}

describe("AgentDetailPanel — tool-call collapsed preview (ISS-355 / ISS-585)", () => {
  it(
    "ISS-355: shows a readable preview, not [object Object], for an array-of-objects arg on a completed run",
    () => {
      render(<AgentDetailPanel agent={agentWithToolCalls("completed")} onBack={() => {}} />);
      expect(screen.getByText("write_todos")).toBeInTheDocument();
      expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
    },
  );

  it(
    "ISS-585: shows a readable preview, not [object Object], for an array-of-objects arg on a still-running run",
    () => {
      render(<AgentDetailPanel agent={agentWithToolCalls("running")} onBack={() => {}} />);
      expect(screen.getByText("write_todos")).toBeInTheDocument();
      expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
    },
  );
});
