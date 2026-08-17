import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel, deriveArtifactCardModel } from "./AgentDetailPanel";
import { runFrames, type ReducerFrame } from "@/hooks/__fixtures__/reducerHarness";
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
// A three-task plan. ISS-087/D1: the card's rows and count come from THIS body, so the
// fixture has to contain the tasks it is asserted to show. It previously held one task
// while the assertions expected three, because the three came from run state instead.
const TASKS_OUT =
  "<tasks>\n## Task 1: Scaffold\n**Goal**: do it\n\n## Task 2: Wire\n**Goal**: do it\n\n## Task 3: Style\n**Goal**: do it\n</tasks>";
// A `<tasks>` artifact carrying no `## Task N:` rows — the conditional-degrade trigger.
const TASKS_OUT_EMPTY = "<tasks>\nNo plan could be produced.\n</tasks>";
const ANALYSIS_OUT =
  "<analysis>\n### Readiness verdict\nREADY TO BUILD\n### Coverage\nCoverage 100%\n</analysis>";

describe("deriveArtifactCardModel — card-type selection (name-free)", () => {
  it("selects the tasks card and counts the tasks in the <tasks> body", () => {
    // ISS-087/D1 — APPROVED BEHAVIOUR CHANGE. "Task plan · N planned" is the size of the
    // plan on screen. It used to be `protoCompletedTaskCount`, the build agent's
    // completed-task counter, which is a different quantity and was wrong on real runs
    // (d5dbc9f2: a 7-task plan rendered "6 planned").
    const m = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: TASKS_OUT }),
      0,
      [agent({ id: "planner", name: "Task Planner" })],
      {},
    );
    expect(m.kind).toBe("tasks");
    expect(m.showTasks).toBe(true);
    expect(m.showChecks).toBe(false);
    expect(m.showPages).toBe(false);
    expect(m.taskCount).toBe(3);
    expect(m.tasks.map(t => t.title)).toEqual(["Scaffold", "Wire", "Style"]);
  });

  it("shows a single_shot <tasks> agent its plan, and NO card when the body holds no tasks", () => {
    // ISS-087/D1 — APPROVED BEHAVIOUR CHANGE. This case used to assert that a `<tasks>`
    // agent with no build progress renders NO card, which hid the plan of every
    // single_shot workflow. A plan exists as soon as the agent has written one, so it
    // shows. The conditional degrade this case exists to protect is preserved below: it
    // now triggers on a `<tasks>` body that contains no task rows.
    const singleShot = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: TASKS_OUT }),
      0,
      [agent({ id: "planner" })],
      {},
    );
    expect(singleShot.kind).toBe("tasks");
    expect(singleShot.showTasks).toBe(true);
    expect(singleShot.taskCount).toBe(3);

    const empty = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: TASKS_OUT_EMPTY }),
      0,
      [agent({ id: "planner" })],
      {},
    );
    expect(empty.kind).toBe("tasks");
    expect(empty.showTasks).toBe(false);
    expect(empty.tasks).toEqual([]);
    expect(empty.taskCount).toBe(0);
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
      {},
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
      {},
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
      dagEdges: [{ from: "planner", to: "builder", artifact_type: "Validated plan" }],
    });
    expect(m.handoff).toEqual({ label: "Validated plan", to: "Build Agent" });
  });

  it("falls back to the next agent's name when dagEdges is absent", () => {
    const m = deriveArtifactCardModel(a0, 0, [a0, a1], {});
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
    // ISS-087/D1 — APPROVED BEHAVIOUR CHANGE. The card takes no run state now: the panel
    // is given no task props at all and still renders the plan, because the plan is in
    // the agent's own output. `getAllByText` for the row: an early task title also
    // appears in the (truncated) raw-output preview below the card.
    render(
      <AgentDetailPanel
        agent={planner}
        onBack={() => {}}
        agents={[planner, builder]}
        agentIndex={0}
        dagEdges={[{ from: "planner", to: "builder", artifact_type: "Validated plan" }]}
      />,
    );
    expect(screen.getByText(/3 planned/)).toBeInTheDocument();
    expect(screen.getAllByText(/Scaffold/).length).toBeGreaterThan(0);
    expect(screen.getByText("Style")).toBeInTheDocument();
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
    // The pages card renders as the mock's 3-col grid: "Specification · N pages"
    // label + one thumbnail cell per `## ` section heading.
    expect(screen.getByText(/Specification.*2 pages/)).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Pages")).toBeInTheDocument();
  });

  it("renders NO artifact card (and no handoff) for a no-artifact build agent — unchanged", () => {
    render(
      <AgentDetailPanel agent={builder} onBack={() => {}} agents={[builder]} agentIndex={0} />,
    );
    expect(screen.queryByText(/Task plan/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Governance checks/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Specification.*pages/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Handoff →/)).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ISS-087 / owner decision D1 — "Task plan · N planned" must count the PLAN.
//
// The card was fed `protoCompletedTasks` / `protoCompletedTaskCount`: the BUILD
// agent's `task_progress` completed-task stream. A card labelled "planned" therefore
// rendered the number COMPLETED — wrong even with no version selected, and frozen to
// the run while the version picker moved everything around it.
//
// Measured on `backend/dev.db` before the fix (read-only): run d5dbc9f2's plan holds
// SEVEN tasks and the card rendered "6 planned" with 6 rows, because the build
// reported `completed_count` 6. The two numbers are different quantities.
// ─────────────────────────────────────────────────────────────────────────────

/** A `<tasks>` artifact body — the shape prototype-plan actually writes. */
function tasksBody(titles: string[]): string {
  const blocks = titles
    .map((t, i) => `## Task ${i + 1}: ${t}\n**Goal**: deliver ${t}`)
    .join("\n\n");
  return `<tasks>\n${blocks}\n</tasks>`;
}

describe("deriveArtifactCardModel — ISS-087: the count is the plan's size", () => {
  it("counts the tasks in the artifact body, not the build agent's completed tasks", () => {
    // A two-task plan while the build has reported five completions. "Planned" must
    // read 2 — the number of things the plan contains.
    const m = deriveArtifactCardModel(
      agent({ id: "planner", name: "Task Planner", output: tasksBody(["Shell", "Register"]) }),
      0,
      [agent({ id: "planner" })],
      {},
    );
    expect(m.kind).toBe("tasks");
    expect(m.showTasks).toBe(true);
    expect(m.taskCount).toBe(2);
    expect(m.tasks.map(t => t.title)).toEqual(["Shell", "Register"]);
  });

  it("reads the plan even after the build's task_progress frames are delivered TWICE", () => {
    // The multiplicity guard (ISS-082's rule) applied to this card: replaying the wire
    // must not move the number. It cannot any more, because the card no longer reads an
    // accumulator at all — which is exactly what this asserts, using the ONE reducer
    // driver rather than a hand-rolled replay.
    //
    // Reproduces run d5dbc9f2: a SEVEN-task plan, six completed tasks reported.
    const PLAN = [
      "HTML Shell & Navigation Chrome",
      "Vendor Register (`#/register`)",
      "Vendor Detail + Onboarding Wizard (`#/vendor/:vendorId/review`)",
      "Reviewer Queue (`#/queue`)",
      "Reports & Analytics (`#/reports`)",
      "Settings (`#/settings`)",
      "Final Wiring & Validation",
    ];
    const roster = [
      { id: "prototype-plan", name: "Task Planner", role: "Planning", icon: "", order: 1 },
      { id: "prototype-build", name: "Build Agent", role: "Construction", icon: "", order: 2 },
    ];
    const onePass: ReducerFrame[] = [
      { type: "pipeline_start", pipeline_type: "od_prototype", agent_count: 2, agents: roster, event_id: "e1", seq: 1 },
      { type: "agent_start", agent_id: "prototype-plan", event_id: "e2", seq: 2 },
      { type: "agent_chunk", agent_id: "prototype-plan", chunk: tasksBody(PLAN), event_id: "e3", seq: 3 },
      { type: "agent_complete", agent_id: "prototype-plan", output: tasksBody(PLAN), event_id: "e4", seq: 4 },
      { type: "agent_start", agent_id: "prototype-build", event_id: "e5", seq: 5 },
      // Six completions — one short of the plan, exactly as the real run ended.
      ...PLAN.slice(0, 6).map((title, i) => ({
        type: "task_progress",
        agent_id: "prototype-build",
        completed_tasks: [{ number: i + 1, title, summary: "done" }],
        completed_count: i + 1,
        event_id: `t${i}`,
        seq: 10 + i,
      })),
    ];

    const state = runFrames([...onePass, ...onePass]);

    // The accumulator itself is unmoved by the second delivery AND still says 6 —
    // it is a truthful count of a different quantity, which is the whole point.
    expect(state.protoCompletedTaskCount).toBe(6);
    expect(state.protoCompletedTasks).toHaveLength(6);

    const planner = state.agents.find(a => a.id === "prototype-plan")!;
    const m = deriveArtifactCardModel(planner, 0, state.agents, {});
    expect(m.taskCount).toBe(7);
    expect(m.tasks).toHaveLength(7);
    expect(m.tasks[6].title).toBe("Final Wiring & Validation");
  });
});
