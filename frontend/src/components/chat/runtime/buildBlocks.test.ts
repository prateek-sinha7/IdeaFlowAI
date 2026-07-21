import { describe, expect, it } from "vitest";

import type { AgentEvent } from "./blocks.types";
import { buildBlocks } from "./buildBlocks";

// ─── open-design borrow #4 (31-01 Task 2) — events→blocks coalescing reducer ──
// Pure reducer over the ordered agent-event stream into the ChatBlock render
// union. Every branch keys on a GENERIC event kind, never a workflow name (SC-001).
describe("buildBlocks — events→blocks reducer", () => {
  it("empty input yields no blocks", () => {
    expect(buildBlocks([])).toEqual([]);
  });

  it("merges consecutive text deltas into one text block", () => {
    const events: AgentEvent[] = [
      { kind: "text", text: "Hel" },
      { kind: "text", text: "lo " },
      { kind: "text", text: "world" },
    ];
    expect(buildBlocks(events)).toEqual([{ kind: "text", text: "Hello world" }]);
  });

  it("merges consecutive thinking deltas and sums their durations", () => {
    const events: AgentEvent[] = [
      { kind: "thinking", text: "let me ", durationMs: 100 },
      { kind: "thinking", text: "think", durationMs: 50 },
    ];
    expect(buildBlocks(events)).toEqual([
      { kind: "thinking", text: "let me think", durationMs: 150 },
    ]);
  });

  it("keeps thinking then text as two ordered blocks", () => {
    const events: AgentEvent[] = [
      { kind: "thinking", text: "hmm" },
      { kind: "text", text: "answer" },
    ];
    expect(buildBlocks(events)).toEqual([
      { kind: "thinking", text: "hmm" },
      { kind: "text", text: "answer" },
    ]);
  });

  it("collapses a tool_use + matching tool_result into one resolved tool block", () => {
    const events: AgentEvent[] = [
      { kind: "tool_use", id: "t1", name: "search", args: { q: "cats" } },
      { kind: "tool_result", id: "t1", result: { hits: 3 } },
    ];
    expect(buildBlocks(events)).toEqual([
      {
        kind: "tool",
        name: "search",
        status: "success",
        args: { q: "cats" },
        result: { hits: 3 },
      },
    ]);
  });

  it("resolves a tool block to error when the result isError", () => {
    const events: AgentEvent[] = [
      { kind: "tool_use", id: "t1", name: "search" },
      { kind: "tool_result", id: "t1", result: "boom", isError: true },
    ];
    expect(buildBlocks(events)).toEqual([
      {
        kind: "tool",
        name: "search",
        status: "error",
        result: "boom",
        isError: true,
      },
    ]);
  });

  it("keeps two same-name tool runs as separate ordered blocks", () => {
    const events: AgentEvent[] = [
      { kind: "tool_use", id: "a", name: "grep" },
      { kind: "tool_result", id: "a", result: "1" },
      { kind: "tool_use", id: "b", name: "grep" },
      { kind: "tool_result", id: "b", result: "2" },
    ];
    const blocks = buildBlocks(events);
    expect(blocks).toEqual([
      { kind: "tool", name: "grep", status: "success", result: "1" },
      { kind: "tool", name: "grep", status: "success", result: "2" },
    ]);
  });

  it("keeps different-name tools as separate blocks in order", () => {
    const events: AgentEvent[] = [
      { kind: "tool_use", name: "read" },
      { kind: "tool_use", name: "write" },
    ];
    const blocks = buildBlocks(events);
    expect(blocks.map((b) => b.kind === "tool" && b.name)).toEqual([
      "read",
      "write",
    ]);
  });

  it("groups consecutive file_op events into one file_ops block", () => {
    const events: AgentEvent[] = [
      { kind: "file_op", path: "a.ts", op: "create" },
      { kind: "file_op", path: "b.ts", op: "edit" },
    ];
    expect(buildBlocks(events)).toEqual([
      {
        kind: "file_ops",
        files: [
          { path: "a.ts", op: "create" },
          { path: "b.ts", op: "edit" },
        ],
      },
    ]);
  });

  it("emits a trailing usage block and preserves non-mergeable ordering", () => {
    const events: AgentEvent[] = [
      { kind: "text", text: "done" },
      { kind: "usage", inputTokens: 10, outputTokens: 20, costUsd: 0.01 },
    ];
    expect(buildBlocks(events)).toEqual([
      { kind: "text", text: "done" },
      { kind: "usage", inputTokens: 10, outputTokens: 20, costUsd: 0.01 },
    ]);
  });

  it("carries no transcript block for a status event", () => {
    const events: AgentEvent[] = [
      { kind: "status", status: "running" },
      { kind: "text", text: "hi" },
    ];
    expect(buildBlocks(events)).toEqual([{ kind: "text", text: "hi" }]);
  });
});
