import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useHandoffPipelineState } from "./useHandoffPipelineState";
import type { HandoffStreamMessage } from "./types";

function setup() {
  const hook = renderHook(() => useHandoffPipelineState());
  const send = (msg: HandoffStreamMessage) => act(() => hook.result.current.handleMessage(msg));
  return { hook, send };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1000);
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useHandoffPipelineState", () => {
  it("starts pending with queued agents and no active agent", () => {
    const { hook } = setup();
    const s = hook.result.current.state;
    expect(s.pipelineStatus).toBe("pending");
    expect(s.done).toBe(false);
    expect(s.agents.coding_agent.status).toBe("queued");
    expect(hook.result.current.activeAgent).toBeNull();
  });

  it("records phase events, defaulting the section to unknown", () => {
    const { hook, send } = setup();
    send({ type: "phase_start", section: "plan" });
    send({ type: "phase_end" });
    expect(hook.result.current.state.phases).toEqual([
      { section: "plan", status: "start", data: {}, at: 1000 },
      { section: "unknown", status: "end", data: {}, at: 1000 },
    ]);
  });

  it("stores edit results on apply_edits phase_end only when results is an array", () => {
    const { hook, send } = setup();
    const results = [{ path: "a", operation: "modify", status: "applied" }];
    send({ type: "phase_end", section: "apply_edits", data: { results: "bad" } });
    expect(hook.result.current.state.editResults).toEqual([]);
    send({ type: "phase_end", section: "apply_edits", data: { results } });
    expect(hook.result.current.state.editResults).toEqual(results);
  });

  it.each([
    ["coding_agent"],
    ["test_agent"],
    ["compliance_agent"],
  ] as const)("marks %s as thinking and active", (id) => {
    const { hook, send } = setup();
    send({ type: "agent_thinking", data: { agent_id: id, thinking: "hmm" } });
    expect(hook.result.current.state.agents[id]).toMatchObject({ status: "thinking", thinking: "hmm", started_at: 1000 });
    expect(hook.result.current.activeAgent).toBe(id);
  });

  it("ignores events for unknown agents", () => {
    const { hook, send } = setup();
    const before = hook.result.current.state;
    send({ type: "agent_thinking", data: { agent_id: "nope" } });
    send({ type: "agent_error" });
    expect(hook.result.current.state.agents).toBe(before.agents);
  });

  it("completes the coding agent with its payload", () => {
    const { hook, send } = setup();
    send({
      type: "agent_complete",
      data: { agent_id: "coding_agent", summary: "s", rationale: "r", edits: [], edit_count: 2, tests_added: ["t"], follow_ups: ["f"] },
    });
    expect(hook.result.current.state.agents.coding_agent).toMatchObject({
      status: "complete", summary: "s", rationale: "r", edit_count: 2, tests_added: ["t"], follow_ups: ["f"], completed_at: 1000,
    });
  });

  it("defaults coding agent payload fields when absent", () => {
    const { hook, send } = setup();
    send({ type: "agent_complete", data: { agent_id: "coding_agent" } });
    expect(hook.result.current.state.agents.coding_agent).toMatchObject({
      summary: "", rationale: "", edits: [], edit_count: 0, tests_added: [], follow_ups: [],
    });
  });

  it("attaches reports for test and compliance agents", () => {
    const { hook, send } = setup();
    send({ type: "agent_complete", data: { agent_id: "test_agent", report: { verdict: "pass" } } });
    send({ type: "agent_complete", data: { agent_id: "compliance_agent", report: { verdict: "approve" } } });
    expect(hook.result.current.state.agents.test_agent.test_report).toEqual({ verdict: "pass" });
    expect(hook.result.current.state.agents.compliance_agent.compliance_report).toEqual({ verdict: "approve" });
  });

  it("records agent errors with custom or default message", () => {
    const { hook, send } = setup();
    send({ type: "agent_error", data: { agent_id: "test_agent", error: "boom" } });
    send({ type: "agent_error", data: { agent_id: "coding_agent" } });
    expect(hook.result.current.state.agents.test_agent).toMatchObject({ status: "error", error: "boom" });
    expect(hook.result.current.state.agents.coding_agent.error).toBe("Agent failed.");
  });

  it("stores PR info from pr_created", () => {
    const { hook, send } = setup();
    send({ type: "pr_created", data: { url: "http://pr", number: 7 } });
    expect(hook.result.current.state).toMatchObject({ prUrl: "http://pr", prNumber: 7 });
  });

  it("completes the pipeline and preserves prior values when fields are absent", () => {
    const { hook, send } = setup();
    send({ type: "pr_created", data: { url: "http://pr", number: 7 } });
    send({ type: "pipeline_complete" });
    expect(hook.result.current.state).toMatchObject({ done: true, pipelineStatus: "completed", prUrl: "http://pr", prNumber: 7 });
    send({
      type: "pipeline_complete",
      data: { resolved_mode: "test", branch_name: "b", pr_url: "u2", pr_number: 9 },
    });
    expect(hook.result.current.state).toMatchObject({ resolvedMode: "test", branchName: "b", prUrl: "u2", prNumber: 9 });
  });

  it("fails the pipeline with custom or default message", () => {
    const { hook, send } = setup();
    send({ type: "handoff_error", data: { message: "bad" } });
    expect(hook.result.current.state).toMatchObject({ done: true, pipelineStatus: "failed", error: "bad" });
    send({ type: "handoff_error" });
    expect(hook.result.current.state.error).toBe("Pipeline failed.");
  });

  it("ignores unknown event types", () => {
    const { hook, send } = setup();
    const before = hook.result.current.state;
    send({ type: "mystery" });
    expect(hook.result.current.state).toBe(before);
  });

  it("sets pipeline status and resets to the initial state", () => {
    const { hook, send } = setup();
    act(() => hook.result.current.setPipelineStatus("running"));
    expect(hook.result.current.state.pipelineStatus).toBe("running");
    send({ type: "agent_thinking", data: { agent_id: "coding_agent" } });
    act(() => hook.result.current.reset());
    expect(hook.result.current.state.pipelineStatus).toBe("pending");
    expect(hook.result.current.state.agents.coding_agent.status).toBe("queued");
  });
});
