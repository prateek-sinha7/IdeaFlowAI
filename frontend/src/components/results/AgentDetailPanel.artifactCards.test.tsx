import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel, deriveArtifactCardModel } from "./AgentDetailPanel";
import type { AgentRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// 42-09 Task 1 — the settled artifact-card DERIVATION (pure helper).
// The card TYPE is chosen by the shared name-free discriminator (spec/tasks/
// analysis), the data comes from in-state pipeline fields, and the handoff line
// derives from dagEdges → next-agent fallback. SC-001: never an agent-name/id
// literal. These tests assert selection + conditional degrade + handoff.
// ─────────────────────────────────────────────────────────────────────────────

function agent(over: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "a1",
    name: "Agent One",
    role: "worker",
    icon: "",
    status: "done",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...over,
  };
}

const SPEC_OUT = "<spec>\n# Title\n## Overview\nbody\n## Pages\nmore\n</spec>";
const TASKS_OUT = "<tasks>\n## Task 1: Build\n**Goal**: do it\n</tasks>";
const ANALYSIS_OUT =
  "<analysis>\n### Readiness verdict\nREADY TO BUILD\n### Coverage\nCoverage 100%\n</analysis>";

const protoTasks = [
  { number: 1, title: "Scaffold", summary: "s" },
  { number: 2, title: "Wire", summary: "s" },
  { number: 3, title: "Style", summary: "s" },
];

describe("deriveArtifactCardModel — card-type selection (name-free)", () => {
  it("selects the tasks card when output is <tasks> AND protoCompletedTasks is non-empty", () => {
    const m = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: TASKS_OUT }),
      0,
      [agent({ id: "planner", name: "Task Planner" })],
      { protoCompletedTasks: protoTasks, protoCompletedTaskCount: 3 },
    );
    expect(m.kind).toBe("tasks");
    expect(m.showTasks).toBe(true);
    expect(m.showChecks).toBe(false);
    expect(m.showPages).toBe(false);
    expect(m.taskCount).toBe(3);
    expect(m.tasks.map(t => t.title)).toEqual(["Scaffold", "Wire", "Style"]);
  });

  it("renders NO tasks card for a <tasks> agent when protoCompletedTasks is empty (single_shot)", () => {
    const m = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: TASKS_OUT }),
      0,
      [agent({ id: "planner" })],
      { protoCompletedTasks: [], protoCompletedTaskCount: 0 },
    );
    expect(m.kind).toBe("tasks");
    expect(m.showTasks).toBe(false);
    expect(m.tasks).toEqual([]);
  });

  it("selects the checks card for an <analysis> agent with the verdict badge from validation*", () => {
    const passed = deriveArtifactCardModel(
      agent({ id: "analyzer", output: ANALYSIS_OUT, validationPassed: true }),
      0,
      [agent({ id: "analyzer" })],
      {},
    );
    expect(passed.kind).toBe("analysis");
    expect(passed.showChecks).toBe(true);
    expect(passed.checksPassed).toBe(true);
    expect(passed.checksIssueCount).toBe(0);

    const blocked = deriveArtifactCardModel(
      agent({
        id: "analyzer",
        output: ANALYSIS_OUT,
        validationPassed: false,
        validationIssues: [{ severity: "high", message: "gap" } as never],
      }),
      0,
      [agent({ id: "analyzer" })],
      {},
    );
    expect(blocked.checksPassed).toBe(false);
    expect(blocked.checksIssueCount).toBe(1);
  });

  it("selects the pages/sections card for a <spec> agent", () => {
    const m = deriveArtifactCardModel(
      agent({ id: "spec", output: SPEC_OUT }),
      0,
      [agent({ id: "spec" })],
      {},
    );
    expect(m.kind).toBe("spec");
    expect(m.showPages).toBe(true);
    expect(m.showTasks).toBe(false);
    expect(m.showChecks).toBe(false);
  });

  it("renders NO card for an agent with no recognized artifact tag", () => {
    const m = deriveArtifactCardModel(
      agent({ id: "x", name: "Build Agent", output: "<!DOCTYPE html><html></html>" }),
      0,
      [agent({ id: "x" })],
      { protoCompletedTasks: protoTasks },
    );
    expect(m.kind).toBeNull();
    expect(m.showPages).toBe(false);
    expect(m.showTasks).toBe(false);
    expect(m.showChecks).toBe(false);
  });

  it("SC-001: selection ignores the agent name/id — a <tasks> output on a build-named agent still discriminates by content", () => {
    // An agent whose NAME/ID says "build/construct" but whose OUTPUT is <tasks>
    // must select the tasks card by content, never by a name literal.
    const m = deriveArtifactCardModel(
      agent({ id: "build-agent", name: "Build Agent", output: TASKS_OUT }),
      0,
      [agent({ id: "build-agent" })],
      { protoCompletedTasks: protoTasks, protoCompletedTaskCount: 3 },
    );
    expect(m.kind).toBe("tasks");
    // And a spec-NAMED agent with plain output selects NOTHING (no name gate).
    const plain = deriveArtifactCardModel(
      agent({ id: "spec-writer", name: "Spec Writer", output: "plain text" }),
      0,
      [agent({ id: "spec-writer" })],
      {},
    );
    expect(plain.kind).toBeNull();
  });
});

describe("deriveArtifactCardModel — handoff line", () => {
  const a0 = agent({ id: "planner", name: "Task Planner", output: TASKS_OUT, index: 0 });
  const a1 = agent({ id: "builder", name: "Build Agent", index: 1 });

  it("derives the handoff from dagEdges (producer→consumer + artifact label)", () => {
    const m = deriveArtifactCardModel(a0, 0, [a0, a1], {
      protoCompletedTasks: protoTasks,
      dagEdges: [{ from: "planner", to: "builder", artifact_type: "Validated plan" }],
    });
    expect(m.handoff).toEqual({ label: "Validated plan", to: "Build Agent" });
  });

  it("falls back to the next agent's name when dagEdges is absent", () => {
    const m = deriveArtifactCardModel(a0, 0, [a0, a1], {
      protoCompletedTasks: protoTasks,
    });
    expect(m.handoff).toEqual({ label: null, to: "Build Agent" });
  });

  it("yields no handoff for the last agent with no outgoing edge", () => {
    const m = deriveArtifactCardModel(a1, 1, [a0, a1], {});
    expect(m.handoff).toBeNull();
  });
});

// ─── Task 2 — the rendered cards + handoff line ───────────────────────────────
describe("AgentDetailPanel — settled artifact cards render", () => {
  const planner = agent({ id: "planner", name: "Task Planner", output: TASKS_OUT });
  const builder = agent({ id: "builder", name: "Build Agent", output: "<!DOCTYPE html>" });

  it("renders the tasks card ('N planned' + task rows) + handoff for a settled task-planner", () => {
    render(
      <AgentDetailPanel
        agent={planner}
        onBack={() => {}}
        agents={[planner, builder]}
        agentIndex={0}
        protoCompletedTasks={protoTasks}
        protoCompletedTaskCount={3}
        dagEdges={[{ from: "planner", to: "builder", artifact_type: "Validated plan" }]}
      />,
    );
    expect(screen.getByText(/3 planned/)).toBeInTheDocument();
    expect(screen.getByText(/Scaffold/)).toBeInTheDocument();
    expect(screen.getByText(/Validated plan → Build Agent/)).toBeInTheDocument();
  });

  it("renders the checks card with a Passed verdict badge for a settled analyzer", () => {
    const analyzer = agent({ id: "analyzer", name: "Analyzer", output: ANALYSIS_OUT, validationPassed: true });
    render(
      <AgentDetailPanel agent={analyzer} onBack={() => {}} agents={[analyzer]} agentIndex={0} />,
    );
    expect(screen.getByText(/Governance checks/)).toBeInTheDocument();
    expect(screen.getByText(/Passed/)).toBeInTheDocument();
  });

  it("renders the pages/sections card for a settled spec agent", () => {
    const spec = agent({ id: "spec", name: "Spec Writer", output: SPEC_OUT });
    render(<AgentDetailPanel agent={spec} onBack={() => {}} agents={[spec]} agentIndex={0} />);
    expect(screen.getByText(/Pages \/ sections/)).toBeInTheDocument();
  });

  it("renders NO artifact card (and no handoff) for a no-artifact build agent — unchanged", () => {
    render(
      <AgentDetailPanel agent={builder} onBack={() => {}} agents={[builder]} agentIndex={0} />,
    );
    expect(screen.queryByText(/Task plan/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Governance checks/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Pages \/ sections/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Handoff →/)).not.toBeInTheDocument();
  });
});
