/**
 * ISS-065 — the agent detail panel must let you read an older version of the
 * artifact this agent produced.
 *
 * `AgentDetailPanel` rendered `agent.output` unconditionally, and `useWorkflow.ts`
 * clears that field on every `agent_start` (FIX-039), so after an update_specs cycle
 * the only in-memory copy of spec v1 is gone. The durable rows survive; the screen
 * did not show them.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

const getRunArtifacts = vi.fn();

vi.mock("@/lib/api", () => ({
  getRunArtifacts: (...args: unknown[]) => getRunArtifacts(...args),
  getToken: () => "test-token",
}));

function specNode(over: Record<string, unknown>): Record<string, unknown> {
  return {
    id: "n",
    kind: "spec",
    producer_step: "prototype-specify",
    producer_agent: "prototype-specify",
    task_id: null,
    version: 1,
    visibility: "private",
    retention: "run_ttl",
    location: "artifact_refs/prototype-specify",
    parents: [],
    derived_from: null,
    children: [],
    ...over,
  };
}

const NODES = [
  specNode({ id: "a1", version: 1, content_hash: "h1", content: "SPEC VERSION ONE BODY" }),
  specNode({ id: "a1b", kind: "prototype-specify", version: 1, content_hash: "h1", content: "SPEC VERSION ONE BODY" }),
  specNode({ id: "a2", version: 2, content_hash: "h2", content: "SPEC VERSION TWO BODY" }),
  specNode({ id: "a2b", kind: "prototype-specify", version: 2, content_hash: "h2", content: "SPEC VERSION TWO BODY" }),
];

function doneAgent(overrides: Record<string, unknown> = {}) {
  return {
    id: "prototype-specify",
    name: "Spec Writer Agent",
    role: "Specification & Architecture",
    status: "done",
    output: "SPEC VERSION TWO BODY",
    thinkingText: "",
    thinking: "",
    contextSources: [],
    toolCalls: [],
    ...overrides,
  } as never;
}

beforeEach(() => {
  getRunArtifacts.mockReset();
  getRunArtifacts.mockImplementation((_t: string, _r: string, opts?: { includeContent?: boolean }) =>
    Promise.resolve({
      workflow_id: "r1",
      artifacts: opts?.includeContent ? NODES : NODES.map(({ content: _c, ...n }) => n),
    }),
  );
});

describe("AgentDetailPanel — per-artifact version viewing", () => {
  it("selecting v1 renders v1's content instead of agent.output", async () => {
    // FAIL-BEFORE: the panel renders `agent.output` unconditionally — RED.
    render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} runId="r1" />);

    const trigger = await screen.findByTestId("artifact-version-picker");
    fireEvent.click(trigger);
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/SPEC VERSION ONE BODY/)).toBeInTheDocument());
    expect(screen.queryByText(/SPEC VERSION TWO BODY/)).not.toBeInTheDocument();
  });

  it("shows the read-only banner while an older version is on screen, and Back to latest restores agent.output", async () => {
    // Reuses the existing ReadOnlyVersionBanner — no second banner (INV-12).
    render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} runId="r1" />);

    fireEvent.click(await screen.findByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/Viewing v1 \(read-only\)/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    await waitFor(() => expect(screen.getByText(/SPEC VERSION TWO BODY/)).toBeInTheDocument());
    expect(screen.queryByText(/Viewing v1 \(read-only\)/i)).not.toBeInTheDocument();
  });

  it("renders no picker and behaves exactly as before without a runId", async () => {
    const { container } = render(<AgentDetailPanel agent={doneAgent()} onBack={() => {}} />);
    expect(container.querySelector('[data-testid="artifact-version-picker"]')).toBeNull();
    expect(getRunArtifacts).not.toHaveBeenCalled();
    expect(screen.getByText(/SPEC VERSION TWO BODY/)).toBeInTheDocument();
  });

  it("keeps an older version readable while the agent is re-running", async () => {
    // The whole point: during an update_specs cycle the agent goes back to "running"
    // and `agent.output` is reset to "" — the older version must still render.
    render(
      <AgentDetailPanel agent={doneAgent({ status: "running", output: "" })} onBack={() => {}} runId="r1" />,
    );

    fireEvent.click(await screen.findByTestId("artifact-version-picker"));
    fireEvent.click((await screen.findAllByRole("option"))[0]);

    await waitFor(() => expect(screen.getByText(/SPEC VERSION ONE BODY/)).toBeInTheDocument());
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ISS-085 — the picker moved the raw output but NOT the artifact cards, which are
// the prominent thing on screen. The panel held two answers to "what am I looking
// at": `shownOutput` for the output section and `agent.output` everywhere else
// (the card discriminator, parseSpecSections/parseSpecOverview, AnalysisPreview).
// These assert the CARDS follow the selection — the gap that let ISS-085 ship.
// ─────────────────────────────────────────────────────────────────────────────

const SPEC_V1 = "<spec>\n# Title\nOverview alpha sentence.\n## Alpha Page\nalpha body\n</spec>";
const SPEC_V2 =
  "<spec>\n# Title\nOverview beta sentence.\n## Beta Page\nbeta body\n## Gamma Page\ngamma body\n</spec>";
const ANALYSIS_V1 =
  "<analysis>\n### Summary\nfirst pass\n### Risk register\nRISK-ALPHA outstanding\n</analysis>";
const ANALYSIS_V2 =
  "<analysis>\n### Summary\nrevision response\n### Risk Mitigation Plan\nRISK-ALPHA mitigated\n</analysis>";

/** Two distinct versions for `agentId`, each written twice (typed kind + the
 *  `produces` alias) exactly as engine.py does — the shape collapseVersions sees. */
function twoVersions(agentId: string, kind: string, v1: string, v2: string) {
  const row = (id: string, k: string, version: number, hash: string, content: string) =>
    specNode({ id, kind: k, producer_step: agentId, producer_agent: agentId, version, content_hash: hash, content });
  return [
    row("v1", kind, 1, "hv1", v1),
    row("v1-alias", agentId, 1, "hv1", v1),
    row("v2", kind, 2, "hv2", v2),
    row("v2-alias", agentId, 2, "hv2", v2),
  ];
}

function mockNodes(nodes: Record<string, unknown>[]) {
  getRunArtifacts.mockImplementation((_t: string, _r: string, opts?: { includeContent?: boolean }) =>
    Promise.resolve({
      workflow_id: "r1",
      artifacts: opts?.includeContent ? nodes : nodes.map(({ content: _c, ...n }) => n),
    }),
  );
}

/** Open the picker and choose v1 (the first option). */
async function selectV1() {
  fireEvent.click(await screen.findByTestId("artifact-version-picker"));
  fireEvent.click((await screen.findAllByRole("option"))[0]);
}

describe("AgentDetailPanel — ISS-085: the artifact cards follow the selected version", () => {
  it("selecting v1 repaints the spec pages card, not just the raw output", async () => {
    mockNodes(twoVersions("prototype-specify", "spec", SPEC_V1, SPEC_V2));
    const spec = doneAgent({ id: "prototype-specify", output: SPEC_V2 });
    render(<AgentDetailPanel agent={spec} onBack={() => {}} runId="r1" agents={[spec]} agentIndex={0} />);

    // Latest first: the v2 grid.
    expect(await screen.findByText(/Specification\s*·\s*2 pages/)).toBeInTheDocument();

    await selectV1();

    // FAIL-BEFORE: SettledArtifactCards parses `agent.output`, so the card stays on
    // v2 ("2 pages" / "Beta Page") while only the raw output below it changes.
    await waitFor(() => expect(screen.getByText(/Specification\s*·\s*1 page/)).toBeInTheDocument());
    expect(screen.getByText("Alpha Page")).toBeInTheDocument();
    expect(screen.getByText("Overview alpha sentence.")).toBeInTheDocument();
    expect(screen.queryByText("Beta Page")).not.toBeInTheDocument();
    expect(screen.queryByText("Gamma Page")).not.toBeInTheDocument();
  });

  it("Back to latest returns the card to the newest version", async () => {
    mockNodes(twoVersions("prototype-specify", "spec", SPEC_V1, SPEC_V2));
    const spec = doneAgent({ id: "prototype-specify", output: SPEC_V2 });
    render(<AgentDetailPanel agent={spec} onBack={() => {}} runId="r1" agents={[spec]} agentIndex={0} />);

    await selectV1();
    await waitFor(() => expect(screen.getByText("Alpha Page")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    await waitFor(() => expect(screen.getByText(/Specification\s*·\s*2 pages/)).toBeInTheDocument());
    expect(screen.getByText("Beta Page")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Page")).not.toBeInTheDocument();
  });

  it("selecting v1 repaints the governance-checks card body (AnalysisPreview)", async () => {
    mockNodes(twoVersions("prototype-analyze", "summary", ANALYSIS_V1, ANALYSIS_V2));
    const analyzer = doneAgent({ id: "prototype-analyze", output: ANALYSIS_V2, validationPassed: true });
    render(<AgentDetailPanel agent={analyzer} onBack={() => {}} runId="r1" agents={[analyzer]} agentIndex={0} />);

    expect(await screen.findByText("Risk Mitigation Plan")).toBeInTheDocument();

    await selectV1();

    // FAIL-BEFORE: `<AnalysisPreview content={agent.output} />` keeps rendering v2.
    await waitFor(() => expect(screen.getByText("Risk register")).toBeInTheDocument());
    expect(screen.getByText("RISK-ALPHA outstanding")).toBeInTheDocument();
    expect(screen.queryByText("Risk Mitigation Plan")).not.toBeInTheDocument();
  });

  it("derives the artifact TYPE from the selected version, so a mid-re-run agent still gets its card", async () => {
    // FIX-039 clears `agent.output` on agent_start, so during an update_specs cycle
    // the latest output is "" and `discriminateArtifact("")` yields no card at all.
    // The selected version is what is on screen, so it is what picks the renderer.
    mockNodes(twoVersions("prototype-specify", "spec", SPEC_V1, SPEC_V2));
    const spec = doneAgent({ id: "prototype-specify", status: "running", output: "" });
    render(<AgentDetailPanel agent={spec} onBack={() => {}} runId="r1" agents={[spec]} agentIndex={0} />);

    expect(screen.queryByText(/Specification\s*·/)).not.toBeInTheDocument();

    await selectV1();

    await waitFor(() => expect(screen.getByText(/Specification\s*·\s*1 page/)).toBeInTheDocument());
    expect(screen.getByText("Alpha Page")).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ISS-087 / owner decision D1 — the TASKS card follows the selected version too.
//
// ISS-085 moved the spec + analysis cards onto the selected version, but the tasks
// card was not reading the artifact at all: its rows and its count came from the
// build agent's `task_progress` stream, so no selection could move them. These two
// cases replay the two shapes that exist in `backend/dev.db`.
// ─────────────────────────────────────────────────────────────────────────────

function tasksBody(titles: string[]): string {
  return `<tasks>\n${titles.map((t, i) => `## Task ${i + 1}: ${t}\n**Goal**: deliver ${t}`).join("\n\n")}\n</tasks>`;
}

// Run 6e38b9a7 — the plan was re-issued with an extra task and a re-cut task 4.
const PLAN_V1_10 = tasksBody([
  "HTML Shell & Navigation Chrome",
  "Accounts Register Page (`#/accounts`)",
  "Account Detail Page (`#/account`)",
  "Transaction Wizard Page (Steps 1-2) (`#/txn`)",
  "Transaction Wizard Page (Steps 3-5) (`#/txn`)",
  "Submissions Queue, Tasks, and Reports Pages",
  "Modals, Toasts, and Final Wiring & Validation",
  "Data Population & Content Finalization",
  "Final Testing & Validation",
  "Final Review & Delivery",
]);
const PLAN_V2_11 = tasksBody([
  "HTML Shell & Navigation Chrome",
  "Accounts Register Page (`#/accounts`)",
  "Account Detail & Supporting Modals (`#/account`)",
  "Submissions Queue & Tasks Pages",
  "Transaction Wizard Steps 1-5 (Part A)",
  "Transaction Wizard Steps 3-4",
  "Transaction Wizard Step 5 (Document Preview & Finalization)",
  "Reports Page & Data Population",
  "Modals, Toasts, & Auto-Save Implementation",
  "Integration Testing & Final Validation",
  "Final QA & Deliverable",
]);

// Run 5ecb990f — SAME task count in both versions, only the titles were re-worded.
// A count-only assertion passes here while the screen is still wrong, which is why
// this case asserts a title.
const CLAIMS_V1_8 = tasksBody([
  "HTML Shell & Navigation Chrome",
  "Claims Register (`#/register`)",
  "Claim Detail (`#/claims/{id}`)",
  "Intake Wizard (`#/wizard/new` and `#/wizard/{id}`)",
  "Adjuster Task Queue (`#/tasks`)",
  "Reports (`#/reports`)",
  "Claim Edit / Notes Modal (`#/claims/{id}/notes`)",
  "Final Wiring & Validation",
]);
const CLAIMS_V2_8 = tasksBody([
  "HTML Shell & Navigation Chrome",
  "Claims Register Page (`#/register`)",
  "Claim Detail Page (`#/claims/{id}`)",
  "Intake Wizard Page (`#/wizard/new` or `#/wizard/{id}`)",
  "Adjuster Task Queue Page (`#/tasks`)",
  "Reports Page (`#/reports`)",
  "Claim Edit / Notes Modal (`#/claims/{id}/notes`)",
  "Final Wiring & Validation",
]);

describe("AgentDetailPanel — ISS-087: the tasks card follows the selected version", () => {
  it("selecting v1 repaints the task rows and the 'N planned' count (run 6e38b9a7)", async () => {
    mockNodes(twoVersions("prototype-plan", "task_list", PLAN_V1_10, PLAN_V2_11));
    const planner = doneAgent({ id: "prototype-plan", name: "Task Planner", output: PLAN_V2_11 });
    render(
      <AgentDetailPanel agent={planner} onBack={() => {}} runId="r1" agents={[planner]} agentIndex={0} />,
    );

    expect(await screen.findByText(/11 planned/)).toBeInTheDocument();

    await selectV1();

    // FAIL-BEFORE: the rows and the count came from protoCompletedTasks, so nothing
    // here moved — and with no such prop supplied, no card rendered at all.
    await waitFor(() => expect(screen.getByText(/10 planned/)).toBeInTheDocument());
    expect(screen.getByText(/Transaction Wizard Page \(Steps 1-2\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Final QA & Deliverable/)).not.toBeInTheDocument();
    expect(screen.queryByText(/11 planned/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Back to latest/i }));
    await waitFor(() => expect(screen.getByText(/11 planned/)).toBeInTheDocument());
    expect(screen.getByText(/Final QA & Deliverable/)).toBeInTheDocument();
  });

  it("repaints the task TITLES when both versions plan the same number (run 5ecb990f)", async () => {
    mockNodes(twoVersions("prototype-plan", "task_list", CLAIMS_V1_8, CLAIMS_V2_8));
    const planner = doneAgent({ id: "prototype-plan", name: "Task Planner", output: CLAIMS_V2_8 });
    render(
      <AgentDetailPanel agent={planner} onBack={() => {}} runId="r1" agents={[planner]} agentIndex={0} />,
    );

    expect(await screen.findByText(/8 planned/)).toBeInTheDocument();
    // `getAllBy`: an early task title appears twice on this screen — once as a card row
    // and once inside the (truncated) raw-output preview below it. Both are v2 here.
    expect(screen.getAllByText(/Claims Register Page/).length).toBeGreaterThan(0);

    await selectV1();

    // The count is identical across these two versions, so only the titles prove the
    // card actually re-read the artifact. The absence assertions are the discriminating
    // ones: v2's wording must be gone from the whole panel.
    await waitFor(() => expect(screen.getAllByText(/Claims Register \(/).length).toBeGreaterThan(0));
    expect(screen.getByText(/8 planned/)).toBeInTheDocument();
    expect(screen.queryByText(/Claims Register Page/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Intake Wizard Page/)).not.toBeInTheDocument();
  });
});
