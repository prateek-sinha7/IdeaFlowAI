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
import type { Page } from "@playwright/test";

const WORKFLOW = "Generate product requirements"; // → user_stories (IdeaInputPage flow)
const IDEA = "Refunds backlog with multi-currency support";

// Phase 39 redesign: the ReviewGatePanel (right panel) now classifies its output
// by the DECLARED artifact kind OR the artifact's own wrapper tag in the payload
// (`<spec>` / `<tasks>` / `<analysis>`) — NEVER the agent-id anymore. So a spec
// payload must carry the `<spec>` wrapper for the panel to render the
// "Specification Review" heading + SpecPreview cards (the mock cannot set
// artifactKind, so the wrapper is the name-free classifier). The `## ` headings
// inside still become preview cards (SpecPreview strips the wrapper first).
const SPEC_OUTPUT = "<spec>\n## Overview\nThe spec.\n## Details\nMore.\n</spec>";

// The redesign renders the gate in TWO places: the right-panel ReviewGatePanel
// AND the inline lane gate (`chat-gate-actions`, "· review before continuing"
// lowercase). Both carry an Edit toggle + an "Approve … continue" button, so an
// un-scoped role locator is a strict-mode violation. gatePanel() scopes to the
// ReviewGatePanel root — anchored on its unique "Reject & cancel pipeline"
// button (the lane gate's reject reads "Reject & cancel", no "pipeline"), walking
// to the nearest ancestor div that also holds the panel's <h2> title.
function gatePanel(page: Page) {
  return page
    .getByRole("button", { name: "Reject & cancel pipeline" })
    .locator('xpath=ancestor::div[.//h2][1]');
}
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
    // getByText is case-insensitive, so the subtitle collides with the inline
    // lane gate's lowercase "· review before continuing" — scope to the panel.
    await expect(
      gatePanel(dashboard.page).getByText("Spec Writer · Review before continuing"),
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
    // getByText is case-insensitive, so the subtitle collides with the inline
    // lane gate's lowercase "· review before continuing" — scope to the panel.
    await expect(
      gatePanel(dashboard.page).getByText("Task Planner · Review before continuing"),
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

    // Toggle to Edit (the panel's mode-switch button labelled "Edit"). The inline
    // lane gate ALSO carries an "Edit" toggle, so scope the click to the panel.
    await gatePanel(dashboard.page).getByRole("button", { name: "Edit", exact: true }).click();

    // Helper line for edit mode.
    await expect(
      dashboard.page.getByText("Changes will be used by the next agent", { exact: false }),
    ).toBeVisible();

    // A prefilled editable textarea — the panel's edit pane's only textbox (the
    // redo box only mounts when redoable). Scope to the panel so the inline lane
    // gate's (closed) editor never collides; role survives the reskin.
    const textarea = gatePanel(dashboard.page).getByRole("textbox");
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
    // Scope the approve to the panel (the inline lane gate has the same label).
    await gatePanel(dashboard.page).getByRole("button", { name: /Approve.*continue/ }).click();

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

    // Edit the panel content, then approve — the label flips to "Approve with
    // edits". Both the Edit toggle and textarea are scoped to the panel (the
    // inline lane gate carries its own, independent editor).
    const panel = gatePanel(dashboard.page);
    await panel.getByRole("button", { name: "Edit", exact: true }).click();
    const textarea = panel.getByRole("textbox");
    const edited = SPEC_OUTPUT + "\n## Extra\nAdded by reviewer.";
    await textarea.fill(edited);
    await expect(
      panel.getByRole("button", { name: /Approve with edits & continue/ }),
    ).toBeVisible();
    await panel.getByRole("button", { name: /Approve.*continue/ }).click();

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
    // Reject is a two-step confirm in the panel: the "Reject & cancel pipeline"
    // button reveals a confirmation, then "Yes, cancel pipeline" sends the frame.
    await dashboard.rejectButton().click();
    await dashboard.page.getByRole("button", { name: "Yes, cancel pipeline" }).click();

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

    // Empty output cannot classify as a spec/tasks/analysis artifact (no wrapper
    // tag, no artifactKind), so the panel falls back to the GENERIC "Review"
    // heading — the redesign derives the label from the artifact kind, not the
    // agent-id. The defensive empty state still renders below it.
    await expect(
      dashboard.page.getByRole("heading", { name: "Review", exact: true }),
    ).toBeVisible();
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
