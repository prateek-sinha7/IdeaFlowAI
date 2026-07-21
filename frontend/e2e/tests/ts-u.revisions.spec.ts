/**
 * TS-U — Revision runs (F2 end-to-end), the mocked-UI-observable slice.
 *
 * The revision loop is driven entirely through the real per-preview "Revise"
 * bars (PPTPreview / UserStoryPreview), which only render when the live
 * execution surface wires their `onRevise` callback. The two dispatch shapes
 * differ by design and are asserted as the EXACT outbound frame:
 *
 *   - PPT      → handleRevisePpt (DashboardLayout). When a completed parent run
 *               id resolves from recentRuns it sends a `run_revision` frame:
 *               { type:"run_revision", parent_run_id, target_artifact_type, instruction }.
 *               The parent id comes from currentWorkflowRunId =
 *               recentRuns.find(r => (r.type===workflowType || r.type===workflowType+"_revision")
 *               && r.status==="completed"). After an od_ppt run completes the
 *               DashboardLayout normalises pipeline_type od_ppt → workflowType
 *               "ppt" (line 312), so the parent lookup is for a `ppt` run and the
 *               emitted target_artifact_type is "ppt_output" (NOT od_ppt_output —
 *               isOdPpt is computed from the normalised workflowType).
 *
 *   - user_stories → handleReviseUserStory → onStartPipeline("user_stories_revision",…)
 *               → useWorkflow.startPipeline → a `run_pipeline` frame with
 *               pipeline_type:"user_stories_revision" and the instruction embedded
 *               in the (delimited) message.
 *
 * Setup runs the parent pipeline through the home → "execution view" so the
 * preview's Revise bar mounts. od_ppt/user_stories both seed default agents and
 * mount the execution surface for any pipeline type (FIXTURE-CONTRACT §1).
 *
 * NOTE on the parent-run lookup: we seed mockApi.setRuns([... a completed run])
 * so currentWorkflowRunId resolves to a real id. After pipeline_complete the app
 * re-fetches GET /api/runs (page.tsx), which returns exactly mockApi.runs — so
 * the seeded run persists through the refresh.
 *
 * Cases TS-U-03/04/05/06/08 are backend/persistence/reconnect concerns not
 * observable in the mocked UI and are marked test.fixme with the BE/live owner.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, SAMPLE_DECK, SAMPLE_BACKLOG } from "../fixtures/scenarios";
import { makeRun } from "../fixtures/mockApi";

// A reopened od_ppt deliverable — non-deck narration text (the LV-02 shape: the
// validator streamed prose, not a parseable deck). Non-empty so the reopen seeds
// pptContent → the lane settles to "complete" and the confirm-first refinement
// chip is reachable, while userStoryContent stays empty (only od_ppt content set).
const OD_PPT_NARRATION = "Draft narration for the investor pitch — 6 slides covering market, product, and unit economics.";

// A *different* deck so the post-revision iframe content is provably the new one.
const REVISED_DECK = `<!DOCTYPE html><html><body>${Array.from({ length: 6 })
  .map((_, i) => `<section class="slide">Revised Slide ${i + 1}</section>`)
  .join("")}</body></html>`;

test.describe("TS-U — revision runs", () => {
  test("TS-U-01 od_ppt revise sends run_revision and renders the revised deck", async ({ dashboard, mockSse, mockApi }) => {
    // A completed parent run so currentWorkflowRunId resolves. After the od_ppt
    // run the workflowType normalises to "ppt", so the parent lookup matches a
    // run of type "ppt" (or "ppt_revision"). type:"ppt" is the match.
    mockApi.setRuns([makeRun({ id: "parent-ppt-1", title: "ROI deck", type: "ppt", status: "completed" })]);

    await dashboard.goto();
    // od_ppt from home routes to the templates wizard, so we can't go through the
    // home picker. Instead drive the execution surface directly: enter via the
    // user_stories home row to reach the execution view, then play the od_ppt run.
    // (The execution surface / preview mounts for whatever pipeline_start declares.)
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "An ROI deck" });

    // ── Complete an od_ppt run ───────────────────────────────────────────────
    const agents = AGENTS.od_ppt;
    mockSse.start(agents, { pipelineType: "od_ppt" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "od_ppt", finalOutput: SAMPLE_DECK });

    // The PPT preview renders the deck iframe.
    await expect(dashboard.deckIframe()).toBeVisible();
    // Phase 39: the per-preview Revise bar was absorbed into the run lane composer.
    // The settled ("complete") lane composer IS the revise-as-chat input, wired to
    // the SAME handleRevisePpt dispatch → a free-text send is a revision.
    const revInput = dashboard.page.getByPlaceholder(/Ask for a change or a follow-up/);
    await expect(revInput).toBeVisible();

    // ── Type a change + send → assert the outbound run_revision frame ──
    await revInput.fill("Add a slide about ROI");
    await dashboard.page.getByTestId("chat-send").click();
    // 44-02: a settled-run change request in the lane composer is HELD behind the
    // confirm-first refinement chip; confirm to launch the revision (decision 5).
    await dashboard.page.getByTestId("chat-refinement-confirm").click();

    const frame = await mockSse.waitForClientFrame("run_revision");
    // Phase 39: revising through the lane composer dispatches handleRevisePpt, which
    // links the parent to `contentSourceRunId` — the ON-SCREEN run (the od_ppt run
    // just completed = mockSse.currentRunId), not the seeded history run. This is the
    // faithful parent of the deck being revised.
    expect(frame.parent_run_id).toBe(mockSse.currentRunId);
    // od_ppt normalised → ppt ⇒ target is "ppt_output" (see header note).
    expect(frame.target_artifact_type).toBe("ppt_output");
    expect(frame.instruction).toBe("Add a slide about ROI");

    // ── Drive the revision run → revised deck shows ──────────────────────────
    mockSse.start(agents, { pipelineType: "od_ppt_revision" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "od_ppt_revision", finalOutput: REVISED_DECK });

    // The deck iframe is still present and now carries the revised content.
    const deck = dashboard.deckIframe();
    await expect(deck).toBeVisible();
    await expect
      .poll(async () => deck.getAttribute("srcdoc"), { timeout: 10000 })
      .toContain("Revised Slide");
  });

  test("TS-U-02 a revision run shows NO clarify questionnaire", async ({ dashboard, mockSse, mockApi }) => {
    mockApi.setRuns([makeRun({ id: "parent-ppt-2", title: "Deck", type: "ppt", status: "completed" })]);

    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "An ROI deck" });

    const agents = AGENTS.od_ppt;
    mockSse.start(agents, { pipelineType: "od_ppt" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "od_ppt", finalOutput: SAMPLE_DECK });

    await expect(dashboard.deckIframe()).toBeVisible();
    // Phase 39: revise via the settled lane composer (absorbed the per-preview bar).
    await dashboard.page.getByPlaceholder(/Ask for a change or a follow-up/).fill("Add a slide about ROI");
    await dashboard.page.getByTestId("chat-send").click();
    // 44-02: confirm the held refinement chip to launch the revision (decision 5).
    await dashboard.page.getByTestId("chat-refinement-confirm").click();
    await mockSse.waitForClientFrame("run_revision");

    // Drive the revision run to completion WITHOUT ever emitting questionnaire_ready
    // (revisions skip clarify — manifest planner: skip). The Quick Setup
    // questionnaire must never appear.
    mockSse.start(agents, { pipelineType: "od_ppt_revision" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "od_ppt_revision", finalOutput: REVISED_DECK });

    await expect(dashboard.deckIframe()).toBeVisible();
    // No clarify form at any point of the revision run.
    await expect(dashboard.questionnaireTitle()).toHaveCount(0);
  });

  test("TS-U-07 user-story revise sends a user_stories_revision run_pipeline frame", async ({ dashboard, mockSse }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    // ── Complete a user_stories run so the backlog + Revise bar render ───────
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

    await expect(dashboard.page.getByText("Product Backlog").first()).toBeVisible();
    // Phase 39: the per-preview Revise bar was absorbed into the run lane composer,
    // wired to the SAME handleReviseUserStory dispatch (a settled free-text send is
    // a revision → a user_stories_revision run_pipeline frame).
    const revInput = dashboard.page.getByPlaceholder(/Ask for a change or a follow-up/);
    await expect(revInput).toBeVisible();

    // ── Type a change + send → assert the outbound run_pipeline frame ─
    // The first run_pipeline (the parent run) was already sent by runWith, so we
    // wait for the SECOND one whose pipeline_type is the revision.
    await revInput.fill("Add a story for password reset");
    await dashboard.page.getByTestId("chat-send").click();
    // 44-02: confirm the held refinement chip to launch the revision (decision 5).
    await dashboard.page.getByTestId("chat-refinement-confirm").click();

    const frame = await mockSse.waitForClientFrame(
      (f) => f.type === "run_pipeline" && f.pipeline_type === "user_stories_revision",
    );
    expect(frame.pipeline_type).toBe("user_stories_revision");
    // The change instruction is embedded in the (delimited) revision message.
    expect(String(frame.message)).toContain("Add a story for password reset");
    expect(String(frame.message)).toContain("=== EXISTING PRODUCT BACKLOG ===");
  });

  test("TS-U-09 reopen-revise: a REOPENED od_ppt run fires exactly one POST /revisions (BUG-003)", async ({ dashboard, mockSse, mockApi }) => {
    // A COMPLETED od_ppt run in history/recents — reopened (not launched) so the
    // isRunning-gated workflowType sync never fires and workflowType stays stale
    // ("user_stories"). Before the fix the revise selector picked the WRONG handler
    // (handleReviseUserStory, whose empty-userStoryContent guard no-ops), so "Run
    // refinement" fired ZERO requests. The fix binds the selector to the VIEWED
    // run's TYPE → handleRevisePpt → the self-sufficient contentSourceRunId REST
    // path fires one POST /revisions.
    const parentId = "od-ppt-reopen-1";
    mockApi.setRuns([
      makeRun({ id: parentId, title: "Investor pitch deck", type: "od_ppt", status: "completed", input: "A B2B carbon-accounting pitch", output: OD_PPT_NARRATION }),
    ]);
    await dashboard.stubRunEvents(parentId, []);

    await dashboard.goto();
    await dashboard.openRecent("Investor pitch deck");

    // The reopened run settles to the "complete" lane → the revise-as-chat composer.
    const revInput = dashboard.page.getByPlaceholder(/Ask for a change or a follow-up/);
    await expect(revInput).toBeVisible();

    // Type a CHANGE → held behind the confirm chip → confirm launches the revision.
    await revInput.fill("Add a closing slide about carbon offsets");
    await dashboard.page.getByTestId("chat-send").click();
    await dashboard.page.getByTestId("chat-refinement-confirm").click();

    // Fail-before: NO run_revision fires (wrong handler no-ops). Pass-after: exactly
    // one POST /api/runs/{parent}/revisions, parented to the reopened run.
    const frame = await mockSse.waitForCommand(
      (c) => c.type === "run_revision" && c.parent_run_id === parentId,
    );
    expect(frame.instruction).toBe("Add a closing slide about carbon offsets");
    expect(mockSse.framesOfType("run_revision")).toHaveLength(1);
  });

  // ── Backend / persistence / reconnect concerns — not mocked-UI observable ──
  // These assert engine/DB behaviour (lineage rows, terminal-status fidelity,
  // surgical-diff merge, reconnect live-attach sectioning) that the mocked WS/UI
  // cannot exercise. They are covered by the Phase 14/15 backend tests and the
  // live campaign (TS-V); kept here as a visible register of the full suite.

  test.fixme(
    "TS-U-03 lineage: revision persists derived_from to the parent; failed revision writes nothing",
    () => {
      // Owner/workspace-scoped derived_from ref is a persistence concern (no row
      // is observable through the mocked REST/WS). Covered by Phase 14 BE tests.
    },
  );

  test.fixme(
    "TS-U-04 revision-of-revision resolves via FR-014 chain link and produces a 2nd deliverable",
    () => {
      // Chain-link resolution is engine/DB behaviour; the mocked UI has no parent
      // chain to resolve. Covered by Phase 14 BE tests + live TS-V.
    },
  );

  test.fixme(
    "TS-U-05 terminal fidelity: revision lands completed/degraded/failed/cancelled, never stuck 'revising'",
    () => {
      // The persisted terminal status (and the never-stuck-'revising' guarantee)
      // is a DB/state-machine assertion not surfaced by the mocked UI. Covered by
      // Phase 14/15 BE tests.
    },
  );

  test.fixme(
    "TS-U-06 surgical-diff prototype revise: agent returns only changed sections, engine merges full HTML",
    () => {
      // The diff-merge happens in the engine; the mocked WS just delivers a final
      // output. The merge correctness is a backend concern. Covered by BE tests;
      // UI authoring tracked in TEST-REGISTER.
    },
  );

  test.fixme(
    "TS-U-08 reconnect during revision: live-attach frames carry section={base}_output; panels rebuild",
    () => {
      // Mid-revision reconnect sectioning is a backend/live-attach concern; the
      // mocked harness has no durable replay backend. Covered live (29 frames) /
      // TS-V.
    },
  );
});
