import { describe, expect, it } from "vitest";
import { liveActivityLine } from "./StepsOverviewSpine";
import type { AgentRunState } from "@/types/index";

/**
 * Regression: an agent that streams OUTPUT but emits no reasoning stream and
 * calls no tools showed "Starting…" for its entire run.
 *
 * `agent_thinking` is emitted by the engine only for extended-thinking providers
 * (`agents/execution_engine/engine.py:4076-4082`), so `thinkingText` is empty for
 * most models — see the same finding already documented at
 * `AgentDetailPanel.tsx:971-978`, which falls back to `agent.output`.
 * `liveActivityLine` had no such fallback.
 */
function agent(over: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "a1",
    name: "Spec Writer",
    role: "writer",
    icon: "🤖",
    status: "running",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...over,
  };
}

const NOW = 1_700_000_000_000;

describe("liveActivityLine", () => {
  it("shows Starting… before the agent has produced anything", () => {
    expect(liveActivityLine(agent(), NOW)).toBe("Starting…");
  });

  it("shows Thinking… while a reasoning stream is arriving", () => {
    expect(liveActivityLine(agent({ thinkingText: "considering..." }), NOW)).toBe(
      "Thinking…",
    );
  });

  it("shows Writing… once output is streaming without any reasoning stream", () => {
    // The reported bug: output is visibly arriving, tools untouched, no
    // reasoning stream -> the row was stuck on "Starting…".
    const line = liveActivityLine(agent({ output: "# Heading\nsome text" }), NOW);
    expect(line).not.toBe("Starting…");
    // ...and specifically NOT "Thinking…": the user can see in the detail panel
    // that the populated block is Output, not the reasoning block.
    expect(line).toBe("Writing…");
  });

  it("keeps Thinking… and Writing… as distinct states", () => {
    expect(liveActivityLine(agent({ thinkingText: "hmm" }), NOW)).toBe("Thinking…");
    expect(liveActivityLine(agent({ output: "answer" }), NOW)).toBe("Writing…");
    // Both fields accumulate and never clear, so once an extended-thinking model
    // starts answering it must read as Writing… — not stay pinned on Thinking…
    // for the rest of the run.
    expect(
      liveActivityLine(agent({ thinkingText: "hmm", output: "answer" }), NOW),
    ).toBe("Writing…");
  });

  it("still prefers an in-flight tool call over streamed output", () => {
    const line = liveActivityLine(
      agent({
        output: "some text",
        toolCalls: [
          { tool: "write_file", args: {}, result: null, timestamp: new Date(NOW).toISOString() },
        ],
      } as Partial<AgentRunState>),
      NOW,
    );
    expect(line).toBe("Writing…");
  });

  it("treats whitespace-only output as nothing produced yet", () => {
    expect(liveActivityLine(agent({ output: "   \n  " }), NOW)).toBe("Starting…");
  });

  describe("task-loop progress", () => {
    const pipeline = { protoCurrentTask: 2, protoTotalTasks: 5, protoTaskAgentId: "a1" };

    it("names the in-flight task for the agent running the loop", () => {
      expect(liveActivityLine(agent(), NOW, pipeline)).toBe("Executing task 2 of 5…");
    });

    it("outranks a tool verb — a build loop calls tools constantly", () => {
      const line = liveActivityLine(
        agent({
          toolCalls: [
            { tool: "write_file", args: {}, result: null, timestamp: new Date(NOW).toISOString() },
          ],
        } as Partial<AgentRunState>),
        NOW,
        pipeline,
      );
      expect(line).toBe("Executing task 2 of 5…");
    });

    it("does NOT leak onto other agent rows", () => {
      const other = agent({ id: "a2", output: "text" });
      expect(liveActivityLine(other, NOW, pipeline)).toBe("Writing…");
    });

    it("omits the total until total_tasks is known", () => {
      const line = liveActivityLine(agent(), NOW, {
        protoCurrentTask: 1,
        protoTaskAgentId: "a1",
      });
      expect(line).toBe("Executing task 1…");
    });

    it("is inert when no task loop is running", () => {
      expect(liveActivityLine(agent(), NOW, {})).toBe("Starting…");
    });
  });
});
