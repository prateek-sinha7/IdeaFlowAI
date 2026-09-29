import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

// The reported defect: a wave step showed DONE while three of its four worker
// rows still spun "Running…" forever, and each row was labelled with a 64-char
// content hash. A row that never resolves claims work is still in flight after
// the run ended — the opposite of what happened.

function agent(overrides: Record<string, unknown> = {}) {
  return {
    id: "fi-readers", name: "Readers", role: "A user-defined workflow agent",
    status: "done", output: "", thinkingText: "", thinking: "",
    contextSources: [], toolCalls: [], ...overrides,
  } as never;
}

describe("AgentDetailPanel — wave worker terminal states", () => {
  it("shows the author's shard id, not the hashed task key", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{
        taskId: "27c3e4721766ef4abb454f56aaf01e9b1aa34e7e6fc9ef2c987a9cde5ae36740",
        taskAuthorId: "s01", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 1,
      }],
    })} />);
    expect(screen.getByTestId("wave-worker-row").textContent).toContain("s01");
    expect(screen.getByTestId("wave-worker-row").textContent).not.toContain("27c3e47");
  });

  it("falls back to the task id when no author id was sent", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{ taskId: "t1", status: "done", workerIndex: 0 }],
    })} />);
    expect(screen.getByTestId("wave-worker-row").textContent).toContain("t1");
  });

  it("never leaves a worker spinning, and never calls an unfinished one done", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [
        { taskId: "k1", taskAuthorId: "s01", status: "done",     workerIndex: 0 },
        { taskId: "k2", taskAuthorId: "s02", status: "stranded", workerIndex: 1 },
        { taskId: "k3", taskAuthorId: "s03", status: "failed",   workerIndex: 2 },
      ],
    })} />);

    const rows = screen.getAllByTestId("wave-worker-row");
    expect(rows.map(r => r.getAttribute("data-status")))
      .toEqual(["done", "stranded", "failed"]);
    // No row is left claiming it is still working.
    expect(rows.some(r => r.textContent?.includes("Running…"))).toBe(false);
    // The count stays honest: 1 done, and the other two are called out.
    // The header counts waves; the per-wave row is where the task count lives.
    expect(screen.getByTestId("wave-section-progress").textContent).toBe("1 / 3 done");
    expect(screen.getByTestId("wave-workers-unresolved").textContent)
      .toContain("2 without a result");
  });

  it("says nothing extra when every worker resolved cleanly", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{ taskId: "k1", taskAuthorId: "s01", status: "done", workerIndex: 0 }],
    })} />);
    expect(screen.queryByTestId("wave-workers-unresolved")).toBeNull();
  });
});

describe("AgentDetailPanel — task agents nested under their shard", () => {
  const waveGroups = [{
    waveIndex: 0, step: "fi-readers", taskIds: ["s01", "s02"], status: "completed",
    workers: [
      // the two wave members themselves — no parentTaskId, so not children
      { agent: "fi-readers", status: "complete", worker: 0, taskId: "k1" },
      { agent: "fi-readers", status: "complete", worker: 1, taskId: "k2" },
      // the task agents each of them spawned
      { agent: "fi-readers", status: "complete", worker: 0, parentTaskId: "s01" },
      { agent: "fi-readers", status: "complete", worker: 1, parentTaskId: "s01" },
      { agent: "fi-readers", status: "failed",   worker: 0, parentTaskId: "s02" },
    ],
  }];

  it("nests each task agent under the shard that spawned it", () => {
    render(<AgentDetailPanel onBack={() => {}} waveGroups={waveGroups as never} agent={agent({
      waveWorkers: [
        { taskId: "k1", taskAuthorId: "s01", status: "done", workerIndex: 0 },
        { taskId: "k2", taskAuthorId: "s02", status: "done", workerIndex: 1 },
      ],
    })} />);

    // s01 -> Task 1, Task 2   ·   s02 -> Task 1
    const lists = screen.getAllByTestId("wave-child-list");
    expect(lists).toHaveLength(2);
    expect(lists[0].querySelectorAll("[data-testid='wave-child-row']")).toHaveLength(2);
    expect(lists[1].querySelectorAll("[data-testid='wave-child-row']")).toHaveLength(1);
    expect(lists[0].textContent).toContain("Task 1");
    expect(lists[0].textContent).toContain("Task 2");
    // a child's own outcome is its own, not its parent's
    expect(lists[1].querySelector("[data-testid='wave-child-row']")?.getAttribute("data-status"))
      .toBe("failed");
  });

  it("draws no child list for a shard that spawned nothing", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{ taskId: "k9", taskAuthorId: "s09", status: "done", workerIndex: 0 }],
    })} />);
    expect(screen.queryByTestId("wave-child-list")).toBeNull();
  });
});

describe("AgentDetailPanel — a failed row says WHY", () => {
  it("shows the backend's reason on a failed shard, not just 'Failed'", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{
        taskId: "k1", taskAuthorId: "s01", status: "failed", workerIndex: 0,
        error: "reserving 3 subagent(s) on top of 24 already spent would exceed max_subagents=24 (FANOUT-09)",
      }],
    })} />);
    const row = screen.getByTestId("wave-worker-row");
    expect(row.textContent).toContain("max_subagents=24");
    expect(screen.getByTestId("wave-worker-error")).toBeInTheDocument();
  });

  it("explains a stranded row rather than leaving it blank", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{
        taskId: "k1", taskAuthorId: "s01", status: "stranded", workerIndex: 0,
        error: "the step ended before this worker reported a result",
      }],
    })} />);
    expect(screen.getByTestId("wave-worker-error").textContent)
      .toContain("ended before this worker reported");
  });

  it("shows a task agent's own reason on its own row", () => {
    const waveGroups = [{
      waveIndex: 0, step: "fi-readers", taskIds: ["s01"], status: "completed",
      workers: [
        { agent: "fi-readers", status: "complete", worker: 0, taskId: "k1" },
        { agent: "fi-readers", status: "failed", worker: 0, parentTaskId: "s01",
          error: "ToolException: extract_text path not found" },
      ],
    }];
    render(<AgentDetailPanel onBack={() => {}} waveGroups={waveGroups as never} agent={agent({
      waveWorkers: [{ taskId: "k1", taskAuthorId: "s01", status: "done", workerIndex: 0 }],
    })} />);
    expect(screen.getByTestId("wave-child-error").textContent)
      .toContain("extract_text path not found");
  });

  it("adds no reason text when a row succeeded", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{ taskId: "k1", taskAuthorId: "s01", status: "done", workerIndex: 0 }],
    })} />);
    expect(screen.queryByTestId("wave-worker-error")).toBeNull();
  });
});

describe("AgentDetailPanel — waves are their own openable sections", () => {
  // The real shape now: wave 1 reads the shards, wave 2 rolls each document up.
  // Wave 2 only starts once wave 1 is done, so flattening them hides the ordering.
  const twoWaves = {
    waveWorkers: [
      { taskId: "k1", taskAuthorId: "1-crimson-s01", status: "done" as const, workerIndex: 0, waveIndex: 0 },
      { taskId: "k2", taskAuthorId: "1-crimson-s02", status: "done" as const, workerIndex: 1, waveIndex: 0 },
      { taskId: "k3", taskAuthorId: "1-crimson-rollup", status: "running" as const, workerIndex: 0, waveIndex: 1 },
    ],
  };

  it("renders one section per wave, in order, not one flat list", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent(twoWaves)} />);
    const sections = screen.getAllByTestId("wave-section");
    expect(sections).toHaveLength(2);
    expect(sections.map(s => s.getAttribute("data-wave-index"))).toEqual(["0", "1"]);
  });

  it("counts each wave separately", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent(twoWaves)} />);
    const progress = screen.getAllByTestId("wave-section-progress").map(e => e.textContent);
    expect(progress).toEqual(["2 / 2 done", "0 / 1 done"]);
  });

  it("opens the wave still running and collapses the finished one", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent(twoWaves)} />);
    const bodies = screen.getAllByTestId("wave-section-body");
    // only wave 2 (the in-flight one) is expanded
    expect(bodies).toHaveLength(1);
    expect(bodies[0].textContent).toContain("1-crimson-rollup");
  });

  it("expands a collapsed wave when its header is clicked", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    render(<AgentDetailPanel onBack={() => {}} agent={agent(twoWaves)} />);
    await userEvent.click(screen.getAllByTestId("wave-section-toggle")[0]);
    const bodies = screen.getAllByTestId("wave-section-body");
    expect(bodies).toHaveLength(2);
    expect(bodies[0].textContent).toContain("1-crimson-s01");
    expect(bodies[0].textContent).toContain("1-crimson-s02");
  });

  it("a single wave is open by default — nothing to bury", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({
      waveWorkers: [{ taskId: "k1", taskAuthorId: "s01", status: "done" as const, workerIndex: 0, waveIndex: 0 }],
    })} />);
    expect(screen.getAllByTestId("wave-section-body")).toHaveLength(1);
  });
});

describe("AgentDetailPanel — a wave row is a link, not an expander", () => {
  // Rows must NOT expand inline. Clicking one opens that member's own page,
  // which is the SAME AgentDetailPanel a step uses.
  const members = {
    waveWorkers: [
      { taskId: "k1", taskAuthorId: "1-crimson-s01", status: "done" as const, workerIndex: 0, waveIndex: 0,
        toolCalls: [
          { tool: "read_file", args: {}, result: "ok", timestamp: "" },
          { tool: "write_file", args: {}, result: "ok", timestamp: "" },
        ] },
      { taskId: "k2", taskAuthorId: "2-amber-s01", status: "done" as const, workerIndex: 1, waveIndex: 0,
        toolCalls: [{ tool: "read_file", args: {}, result: "ok", timestamp: "" }] },
    ],
  };

  it("shows each member's own call count, not the step's pooled one", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent(members)} />);
    expect(screen.getAllByTestId("wave-worker-toolcount").map(e => e.textContent))
      .toEqual(["2 calls", "1 call"]);
  });

  it("never expands inline", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const seen: string[] = [];
    render(<AgentDetailPanel onBack={() => {}} onOpenWorker={(id) => seen.push(id)} agent={agent(members)} />);
    await userEvent.click(screen.getAllByTestId("wave-worker-row")[0]);
    expect(screen.queryByTestId("wave-worker-detail")).toBeNull();
    expect(screen.queryByTestId("wave-worker-toolcall")).toBeNull();
  });

  it("clicking a row asks to open THAT member", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const seen: string[] = [];
    render(<AgentDetailPanel onBack={() => {}} onOpenWorker={(id) => seen.push(id)} agent={agent(members)} />);
    await userEvent.click(screen.getAllByTestId("wave-worker-row")[1]);
    expect(seen).toEqual(["k2"]);
  });

  it("a row is inert when there is nowhere to go", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent(members)} />);
    expect(screen.getAllByTestId("wave-worker-row")[0]).toBeDisabled();
  });
});

describe("AgentDetailPanel — breadcrumb", () => {
  it("defaults to Steps / {agent}", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({})} />);
    expect(screen.getByTestId("agent-detail-breadcrumb").textContent).toContain("Steps");
    expect(screen.getByTestId("agent-detail-breadcrumb").textContent).toContain("Readers");
  });

  it("renders the trail a wave member supplies, same panel otherwise", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={agent({})}
      breadcrumb={["Steps", "Readers", "Wave 1", "1-crimson-s01"]} />);
    const text = screen.getByTestId("agent-detail-breadcrumb").textContent ?? "";
    expect(text).toContain("Readers");
    expect(text).toContain("Wave 1");
    expect(text).toContain("1-crimson-s01");
  });
});

describe("AgentDetailPanel — a wave member's page carries the same sections", () => {
  // Rendered through the SAME panel a step uses, so whatever a step shows, a
  // member shows — from its OWN events, never the step's pooled ones.
  const member = {
    id: "k1", name: "1-crimson-s01", role: "Wave 1 member of Readers",
    status: "done", icon: "", index: 0, duration: 42, error: null,
    output: "shard 1-crimson-s01, 2 pages read, 4 files written",
    thinking: "", thinkingText: "I own shard 1-crimson-s01. Reading page 01 first.",
    inputPrompt: "Shard 1-crimson-s01. Document 1-crimson, pdf, pages 1-2.",
    totalTokens: 31400,
    contextSources: [{ type: "run_input", label: "prompt.md", size_chars: 60 }],
    toolCalls: [{ tool: "read_file", args: { file_path: "x" }, result: "ok", timestamp: "" }],
  } as never;

  it("shows the member's own output, reasoning, input and context", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={member}
      breadcrumb={["Steps", "Readers", "Wave 1", "1-crimson-s01"]} />);
    const body = document.body.textContent ?? "";
    // Same sections a step page has, in the same collapsed/expanded states.
    expect(body).toContain("4 files written");        // its own output, expanded
    expect(body).toContain("Reasoning");              // its own reasoning card
    expect(body).toContain("Full input prompt");      // its own input, collapsed
    expect(body).toContain("Context received");       // its own context rail
    expect(body).toContain("prompt.md");              // that context source
    expect(body).toContain("Tool calls");             // its own tool calls
    expect(body).toContain("31.4K tok");              // its own token usage
    expect(body).toContain("42s");                    // its own duration
  });

  it("does not list its siblings as its own children", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={member}
      breadcrumb={["Steps", "Readers", "Wave 1", "1-crimson-s01"]} />);
    // waveWorkers is cleared for a member — no wave block on its own page
    expect(screen.queryByTestId("wave-workers-block")).toBeNull();
  });
});

describe("AgentDetailPanel — a member page is the step page, every section", () => {
  // "same page but with different data" — so every field a step renders must be
  // populated from the member's own events, not silently left empty.
  const full = {
    id: "k1", name: "1-crimson-s01", role: "Wave 1 member of Readers",
    status: "done", icon: "", index: 0, duration: 42, error: null,
    output: "shard 1-crimson-s01, 2 pages read, 4 files written",
    thinking: "", thinkingText: "I own shard 1-crimson-s01.",
    inputPrompt: "Shard 1-crimson-s01, pdf, pages 1-2.",
    inputTokens: 29000, outputTokens: 2400, totalTokens: 31400,
    estimatedCostUsd: 0.041,
    contextSources: [{ type: "run_input", label: "prompt.md", size_chars: 60 }],
    toolCalls: [{ tool: "read_file", args: { file_path: "x" }, result: "ok", timestamp: "" }],
    attachedSkills: [{ name: "file_extract", description: "extract text" }],
    attachedHooks: [{ name: "secret_scan", event: "before_write" }],
    validationPassed: true, validationIssues: [],
  } as never;

  const crumbs = ["Steps", "Readers", "Wave 1", "1-crimson-s01"];

  it("renders every section a step page renders", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={full} breadcrumb={crumbs} />);
    const body = document.body.textContent ?? "";
    for (const section of [
      "Reasoning", "Tool calls", "Full input prompt", "Agent output", "Context received",
    ]) expect(body, `missing section: ${section}`).toContain(section);
  });

  it("fills them with THIS member's data", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={full} breadcrumb={crumbs} />);
    const body = document.body.textContent ?? "";
    expect(body).toContain("4 files written");   // output
    expect(body).toContain("prompt.md");         // context
    expect(body).toContain("31.4K tok");         // tokens
    expect(body).toContain("42s");               // duration
    expect(body).toContain("1-crimson-s01");     // identity
  });

  it("carries skills and hooks the member actually got", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={full} breadcrumb={crumbs} />);
    const body = document.body.textContent ?? "";
    expect(body).toContain("file_extract");
    expect(body).toContain("secret_scan");
  });

  it("shows the member's breadcrumb, not the step's", () => {
    render(<AgentDetailPanel onBack={() => {}} agent={full} breadcrumb={crumbs} />);
    const text = screen.getByTestId("agent-detail-breadcrumb").textContent ?? "";
    expect(text).toContain("Steps");
    expect(text).toContain("Readers");
    expect(text).toContain("Wave 1");
    expect(text).toContain("1-crimson-s01");
  });
});

describe("wave member duration", () => {
  // A member's events ride fanout.py's side-channel QUEUE and can drain together,
  // so a measured start->complete gap of ~0 is a queue artefact, not a fast agent.
  // "0s" next to 78.7K tokens is a lie; showing nothing is not.
  it("prefers the server's duration over the measured gap", async () => {
    const { handlePipelineMessage } = await import("@/hooks/useWorkflow");
    let state: unknown = { agents: [{ id: "fi-readers", waveWorkers: [] }] };
    const setState = (fn: unknown) => { state = typeof fn === "function" ? (fn as (s: unknown) => unknown)(state) : fn; };
    handlePipelineMessage(
      { type: "agent_start", agent_id: "fi-readers", task_id: "k1" } as never,
      setState as never, { current: {} } as never,
    );
    handlePipelineMessage(
      { type: "agent_complete", agent_id: "fi-readers", task_id: "k1", duration: 87 } as never,
      setState as never, { current: {} } as never,
    );
    const w = (state as never as { agents: { waveWorkers: { durationMs?: number }[] }[] })
      .agents[0].waveWorkers[0];
    expect(w.durationMs).toBe(87_000);
  });

  it("reports nothing rather than 0s when only a queue-artefact gap is available", async () => {
    const { handlePipelineMessage } = await import("@/hooks/useWorkflow");
    let state: unknown = { agents: [{ id: "fi-readers", waveWorkers: [] }] };
    const setState = (fn: unknown) => { state = typeof fn === "function" ? (fn as (s: unknown) => unknown)(state) : fn; };
    handlePipelineMessage(
      { type: "agent_start", agent_id: "fi-readers", task_id: "k2" } as never,
      setState as never, { current: {} } as never,
    );
    handlePipelineMessage(
      { type: "agent_complete", agent_id: "fi-readers", task_id: "k2" } as never,
      setState as never, { current: {} } as never,
    );
    const w = (state as never as { agents: { waveWorkers: { durationMs?: number }[] }[] })
      .agents[0].waveWorkers[0];
    expect(w.durationMs).toBeUndefined();
  });
});
