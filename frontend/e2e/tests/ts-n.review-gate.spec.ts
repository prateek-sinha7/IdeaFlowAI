/**
 * TS-N — Mid-run HITL ReviewGatePanel.
 *
 * When an agent declares a Human review gate, the backend emits
 * `review_gate_ready` mid-run. The dashboard stores it as `reviewGateData`,
 * which mounts ReviewGatePanel in the right panel — taking precedence over the
 * planning overlay, questionnaire, AND preview (DashboardLayout.tsx ~L1230).
 *
 * Setup: select a workflow + Run (→ run_pipeline, execution view) + a
 * `pipeline_start` (so the surface mounts and the run is live), then fire
 * `mockWs.reviewGateReady({...})`. We carry the gate on the `user_stories`
 * surface — the panel is workflow-agnostic and replaces the right panel for any
 * live run; the gate's own `agentId` (prototype-specify / prototype-plan) drives
 * the spec-vs-tasks rendering, NOT the pipeline type.
 *
 * Outbound frame contract (page.tsx onApproveReview / onRejectReview):
 *   - approve : { type: "approve_review", gate_key, approved: true,
 *                 edited_content: <string|null> }
 *   - reject  : { type: "approve_review", gate_key, approved: false }
 * Both share the type `approve_review`; they are disambiguated by `approved`,
 * so we wait on a predicate over `approved`, not just the frame type.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

const WORKFLOW = "Generate product requirements"; // → user_stories (IdeaInputPage flow)
const IDEA = "Refunds backlog with multi-currency support";

// A spec body whose `## ` headings become preview cards.
const SPEC_OUTPUT = "## Overview\nThe spec.\n## Details\nMore.";
// A tasks body whose `## Task N:` blocks become the TasksPreview list.
const TASKS_OUTPUT = [
  "<tasks>",
  "## Task 1: Scaffold the project",
  "**Goal**: Create the base app shell.",
  "## Task 2: Wire the API",
  "**Goal**: Connect the data layer.",
  "</tasks>",
].join("\n");

/** Run + pipeline_start so the execution surface is mounted and live. */
async function liveRun(dashboard: import("../fixtures/dashboard").DashboardPage, mockWs: import("../fixtures/mockWs").MockWs) {
  await dashboard.runWith({ workflow: WORKFLOW, idea: IDEA });
  mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
}

test.describe("TS-N — mid-run review gate (ReviewGatePanel)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
  });

  test("TS-N-01 spec gate renders title + subtitle", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();
    await expect(
      dashboard.page.getByText("Spec Writer · Review before continuing"),
    ).toBeVisible();
  });

  test("TS-N-01 tasks gate renders Task Plan Review title", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-plan",
      agentName: "Task Planner",
      output: TASKS_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Task Plan Review")).toBeVisible();
    await expect(
      dashboard.page.getByText("Task Planner · Review before continuing"),
    ).toBeVisible();
  });

  test("TS-N-02 preview mode: spec sections render as cards", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();
    // SpecPreview turns each `## ` heading into a card header.
    await expect(dashboard.page.getByText("Overview", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("Details", { exact: true })).toBeVisible();
    // The body lines render inside the cards too.
    await expect(dashboard.page.getByText("The spec.")).toBeVisible();
  });

  test("TS-N-02 preview mode: tasks render with the TasksPreview header", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-plan",
      agentName: "Task Planner",
      output: TASKS_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Task Plan Review")).toBeVisible();
    // Two parsed Task blocks → "2 tasks · Click ✕ to remove a task before building".
    await expect(
      dashboard.page.getByText("2 tasks · Click", { exact: false }),
    ).toBeVisible();
    await expect(dashboard.page.getByText("to remove a task before building", { exact: false })).toBeVisible();
    // Each task title renders as a row.
    await expect(dashboard.page.getByText("Scaffold the project")).toBeVisible();
    await expect(dashboard.page.getByText("Wire the API")).toBeVisible();
  });

  test("TS-N-03 edit mode: toggle reveals a prefilled mono textarea + helper", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();

    // Toggle to Edit (the mode-switch button labelled "Edit").
    await dashboard.page.getByRole("button", { name: "Edit", exact: true }).click();

    // Helper line for edit mode.
    await expect(
      dashboard.page.getByText("Changes will be used by the next agent", { exact: false }),
    ).toBeVisible();

    // A mono textarea, prefilled with the agent output.
    const textarea = dashboard.page.locator("textarea.font-mono");
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(SPEC_OUTPUT);
  });

  test("TS-N-04 approve: sends approve_review(approved:true) then panel closes on ack", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();
    await dashboard.approveButton().click();

    // Disambiguate the shared `approve_review` type by `approved: true`.
    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === true,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.approved).toBe(true);
    // No edits were made → edited_content is null (not the original string).
    expect(f.edited_content).toBeNull();

    // Server acks → review_gate_approved clears reviewGateData → panel unmounts.
    mockWs.reviewGateApproved();
    await expect(dashboard.reviewGateTitle("Specification Review")).toHaveCount(0);
  });

  test("TS-N-04b approve with edits: sends the edited content", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();

    // Edit the content, then approve — the label flips to "Approve with edits".
    await dashboard.page.getByRole("button", { name: "Edit", exact: true }).click();
    const textarea = dashboard.page.locator("textarea.font-mono");
    const edited = SPEC_OUTPUT + "\n## Extra\nAdded by reviewer.";
    await textarea.fill(edited);
    await expect(
      dashboard.page.getByRole("button", { name: /Approve with edits & continue/ }),
    ).toBeVisible();
    await dashboard.approveButton().click();

    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === true,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.edited_content).toBe(edited);
  });

  test("TS-N-05 reject: sends approve_review(approved:false) and closes the panel", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();
    await dashboard.rejectButton().click();

    // Reject is the SAME type with approved:false and no edited_content.
    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === false,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.approved).toBe(false);
    expect(f.edited_content).toBeUndefined();

    // page.tsx onRejectReview clears reviewGateData locally → panel unmounts.
    await expect(dashboard.reviewGateTitle("Specification Review")).toHaveCount(0);
  });

  test("TS-N-06 empty-content gate shows the defensive empty state", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: "",
    });

    await expect(dashboard.reviewGateTitle("Specification Review")).toBeVisible();
    await expect(
      dashboard.page.getByText("No content was produced for review."),
    ).toBeVisible();
    await expect(
      dashboard.page.getByText(
        "The agent returned an empty result. Reject to cancel the pipeline, or approve to continue anyway.",
      ),
    ).toBeVisible();
  });
});
