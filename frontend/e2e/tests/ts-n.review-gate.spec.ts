/**
 * TS-N — Mid-run HITL review gate (Phase 42 re-anchor: the INLINE Steps gate).
 *
 * When an agent declares a Human review gate, the backend emits
 * `review_gate_ready` mid-run. The dashboard stores it as `reviewGateData`.
 *
 * Phase 42-02/08 DELETED the full-screen right-panel `ReviewGatePanel`. The gate
 * quick-actions now render INLINE in the Steps spine (`InlineGateActions`, testid
 * `chat-gate-actions`): a "{agent} · review before continuing" header, a reused
 * `artifactPreview` plan-preview block (`chat-gate-preview`), an Edit toggle, and
 * TWO primary buttons — "Approve & build" (`chat-gate-approve`) / "Request changes"
 * (`chat-gate-request-changes`) — the redo / update-specs / reject channels folded
 * UNDER "Request changes". The lane composer during a gate is now a plain
 * phase-hint input (no gate actions there), so `chat-gate-actions` renders in
 * exactly ONE place (the Steps spine).
 *
 * The `approve_review` outbound channel is UNCHANGED (page.tsx onApproveReview /
 * onRejectReview):
 *   - approve : { type: "approve_review", gate_key, approved: true,
 *                 edited_content: <string|null> }
 *   - reject  : { type: "approve_review", gate_key, approved: false }
 * Both share the type `approve_review`; they are disambiguated by `approved`.
 *
 * Setup: select a workflow + Run + a `pipeline_start` (so the surface is live and
 * the Steps spine has data), fire `mockWs.reviewGateReady({...})`, then open the
 * Steps tab. The gate's `agentId` (prototype-specify / prototype-plan) does not
 * match the seeded user_stories agents, so the gate renders via the spine's
 * foot-of-list fallback — the panel is workflow-agnostic.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";
import type { Page } from "@playwright/test";

const WORKFLOW = "Generate product requirements"; // → user_stories (IdeaInputPage flow)
const IDEA = "Refunds backlog with multi-currency support";

// A spec payload carrying the `<spec>` wrapper so the artifactPreview discriminator
// classifies it as a spec (the mock cannot set artifactKind, so the wrapper is the
// name-free classifier). The `## ` headings become SpecPreview card headers.
const SPEC_OUTPUT = "<spec>\n## Overview\nThe spec.\n## Details\nMore.\n</spec>";

// A tasks body whose `## Task N:` blocks become the TasksPreview list.
const TASKS_OUTPUT = [
  "<tasks>",
  "## Task 1: Scaffold the project",
  "**Goal**: Create the base app shell.",
  "## Task 2: Wire the API",
  "**Goal**: Connect the data layer.",
  "</tasks>",
].join("\n");

/** The inline Steps gate root — the sole gate surface post-Phase-42. */
function gate(page: Page) {
  return page.getByTestId("chat-gate-actions");
}

/** Run + pipeline_start so the execution surface is mounted and live. */
async function liveRun(dashboard: import("../fixtures/dashboard").DashboardPage, mockWs: import("../fixtures/mockWs").MockWs) {
  await dashboard.runWith({ workflow: WORKFLOW, idea: IDEA });
  mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
}

test.describe("TS-N — mid-run review gate (inline Steps gate)", () => {
  test.beforeEach(async ({ dashboard }) => {
    await dashboard.goto();
  });

  test("TS-N-01 spec gate renders the inline gate header", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();
    // Inline gate header: "{agentName} · review before continuing".
    await expect(g.getByText("Spec Writer · review before continuing")).toBeVisible();
  });

  test("TS-N-01 tasks gate renders the inline gate header", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-plan",
      agentName: "Task Planner",
      output: TASKS_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();
    await expect(g.getByText("Task Planner · review before continuing")).toBeVisible();
  });

  test("TS-N-02 preview mode: spec sections render as cards", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    // The inline gate's plan-preview block reuses SpecPreview — each `## ` heading
    // becomes a card header and its body lines render inside.
    const g = gate(dashboard.page);
    await expect(g.getByTestId("chat-gate-preview")).toBeVisible();
    await expect(dashboard.page.getByText("Overview", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("Details", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByText("The spec.")).toBeVisible();
  });

  test("TS-N-02 preview mode: tasks render via the TasksPreview list", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-plan",
      agentName: "Task Planner",
      output: TASKS_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    // The inline gate's plan-preview block reuses TasksPreview: a "{n} tasks"
    // header + a row per parsed `## Task N:` block. (The old ReviewGatePanel's
    // "· Click ✕ to remove a task before building" affordance was retired with
    // that panel — the read-only artifactPreview list has no per-task removal.)
    const g = gate(dashboard.page);
    await expect(g.getByTestId("chat-gate-preview")).toBeVisible();
    await expect(g.getByText("2 tasks", { exact: false })).toBeVisible();
    await expect(dashboard.page.getByText("Scaffold the project")).toBeVisible();
    await expect(dashboard.page.getByText("Wire the API")).toBeVisible();
  });

  test("TS-N-03 edit mode: toggle reveals a prefilled mono textarea", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();

    // Toggle to Edit (the inline gate's "Edit" mode-switch button). The lane no
    // longer carries a gate editor, so this is the only "Edit" toggle.
    await g.getByRole("button", { name: "Edit", exact: true }).click();

    // A prefilled editable textarea (aria-label "Edit gate content") — while edit
    // is open the plan-preview block is replaced by it, so it is the gate's only
    // textbox.
    const textarea = g.getByRole("textbox");
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveValue(SPEC_OUTPUT);
  });

  test("TS-N-04 approve: sends approve_review(approved:true) then the gate clears on ack", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();
    // The mock's primary "Approve & build" button (chat-gate-approve).
    await g.getByTestId("chat-gate-approve").click();

    // Disambiguate the shared `approve_review` type by `approved: true`.
    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === true,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.approved).toBe(true);
    // No edits were made → edited_content is null (page.tsx maps undefined → null).
    expect(f.edited_content).toBeNull();

    // Server acks → review_gate_approved clears reviewGateData → the gate unmounts.
    mockWs.reviewGateApproved();
    await expect(g).toHaveCount(0);
  });

  test("TS-N-04b approve with edits: sends the edited content", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();

    // Edit the content, then approve — the primary label flips to "Approve with
    // edits & build" and the frame carries the edited copy.
    await g.getByRole("button", { name: "Edit", exact: true }).click();
    const textarea = g.getByRole("textbox");
    const edited = SPEC_OUTPUT + "\n## Extra\nAdded by reviewer.";
    await textarea.fill(edited);
    await expect(g.getByTestId("chat-gate-approve")).toHaveText(/Approve with edits & build/);
    await g.getByTestId("chat-gate-approve").click();

    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === true,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.edited_content).toBe(edited);
  });

  test("TS-N-05 reject: Request changes → two-step confirm sends approve_review(approved:false)", async ({ dashboard, mockWs }) => {
    await liveRun(dashboard, mockWs);
    mockWs.reviewGateReady({
      gateKey: "g1",
      agentId: "prototype-specify",
      agentName: "Spec Writer",
      output: SPEC_OUTPUT,
    });
    await dashboard.thinkingTab().click();

    const g = gate(dashboard.page);
    await expect(g).toBeVisible();

    // Reject now lives UNDER "Request changes" (the folded change channels), and is
    // a two-step confirm: "Reject & cancel" reveals the confirmation, then
    // "Yes, cancel" (chat-gate-reject) sends the frame.
    await g.getByTestId("chat-gate-request-changes").click();
    await g.getByRole("button", { name: "Reject & cancel", exact: true }).click();
    await g.getByTestId("chat-gate-reject").click();

    // Reject is the SAME type with approved:false and no edited_content.
    const f = await mockWs.waitForClientFrame(
      (frame) => frame.type === "approve_review" && frame.approved === false,
    );
    expect(f.gate_key).toBe("g1");
    expect(f.approved).toBe(false);
    expect(f.edited_content).toBeUndefined();

    // page.tsx onRejectReview clears reviewGateData locally → the gate unmounts.
    await expect(g).toHaveCount(0);
  });

  test.fixme("TS-N-06 empty-content gate shows the defensive empty state", async () => {
    // The old full-screen ReviewGatePanel rendered a defensive empty state ("No
    // content was produced for review." + a "Review" fallback heading) for an
    // empty-output gate. Phase 42-08 DELETED that panel; the inline Steps gate
    // (InlineGateActions) has NO empty-state affordance — an empty output simply
    // renders no plan-preview block while the Approve / Request-changes actions
    // stay available. This defensive branch has no inline equivalent; re-home it if
    // the inline gate grows an empty-output affordance. Replacement surface:
    // components/chat/InlineGateActions.tsx (chat-gate-actions).
  });
});
