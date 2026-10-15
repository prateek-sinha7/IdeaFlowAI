/**
 * TS-U — Revision runs (F2 end-to-end), the mocked-UI-observable slice.
 *
 * Re-anchored to the Concierge revision flow (FIX-210 / ISS-054 / KAN-160): a
 * free-text change typed into a SETTLED run's lane composer is no longer held by
 * a local "refinement" chip nor dispatched client-side as `run_revision` /
 * `user_stories_revision`. It is sent as a Concierge turn
 * (`POST /api/runs/{id}/messages`, `concierge: true`); the backend classifies it
 * and, for a change, writes a durable `concierge_proposal` row
 * (channel "revision"). The lane renders that as a held proposal card; Confirm
 * replays the turn with `confirm_proposal: { channel, params }` (forwarding the
 * ASK's message_id) and the backend launches the revision, answering
 * `{ proposal: { revision_run_id } }` so the UI attaches the revision run.
 *
 * The mock stands in for the backend Concierge: it emits / writes the pending
 * `concierge_proposal` while handling the ASK turn (before answering, like the
 * backend), and answers the confirm with a revision_run_id (a child run whose
 * tail the mock owns from that moment, or the same run when none is configured).
 *
 * Deck runs use the `ppt` pipeline and are served by the mock's lazy attach: since 015-frontend-routing a
 * launch persists its run TYPE across the /runs/{id}/stream remount, so launching
 * user_stories and announcing ppt is a state the real backend never produces.
 *
 * Cases TS-U-03/04/05/06/08 are backend/persistence/reconnect concerns not
 * observable in the mocked UI; they were deleted from this file. See the note at
 * the end of the describe for the owner that covers each.
 */
import { test, expect, type StubRunEventRow } from "../fixtures/test";
import { AGENTS, runAgent, SAMPLE_DECK, SAMPLE_BACKLOG } from "../fixtures/scenarios";
import { makeRun } from "../fixtures/mockApi";
import type { DashboardPage } from "../fixtures/dashboard";
import type { MockSse } from "../fixtures/mockSse";

// A reopened ppt deliverable — non-deck narration text (the LV-02 shape: the
// validator streamed prose, not a parseable deck). Non-empty so the reopen seeds
// pptContent → the lane settles to "complete" and the revise-as-chat composer is
// reachable, while userStoryContent stays empty (only ppt content set).
const OD_PPT_NARRATION = "Draft narration for the investor pitch — 6 slides covering market, product, and unit economics.";

// A *different* deck so the post-revision iframe content is provably the new one.
const REVISED_DECK = `<!DOCTYPE html><html><body>${Array.from({ length: 6 })
  .map((_, i) => `<section class="slide">Revised Slide ${i + 1}</section>`)
  .join("")}</body></html>`;

/** Play a full ppt deck run over the lazy attach (no launch). */
async function completeDeckRun(mockSse: MockSse, pipelineType: string, finalOutput: string) {
  const agents = AGENTS.ppt;
  mockSse.start(agents, { pipelineType });
  await mockSse.ready();
  for (const a of agents) await runAgent(mockSse, a.id);
  mockSse.complete({ pipelineType, finalOutput });
}

/**
 * Type a change into the settled lane composer and confirm the Concierge-held
 * revision proposal. Returns the ASK and the CONFIRM up-channel commands.
 */
async function requestRevision(
  dashboard: DashboardPage,
  mockSse: MockSse,
  instruction: string,
  // A REOPENED terminal run has no live stream: the Concierge's durable row is
  // delivered by the post-send re-fetch of GET /events (the stubbed rows).
  durableRows?: StubRunEventRow[],
) {
  const page = dashboard.page;
  const revInput = page.getByPlaceholder(/Ask for a change or a follow-up/);
  await expect(revInput).toBeVisible({ timeout: 20000 });
  // A late durable replay / run-state remount can swap the composer and drop the
  // typed text; re-fill until Send is enabled (text accepted) instead of racing it.
  // (2) The backend Concierge holds the ASK as a consequential revision proposal.
  // Like the real backend, the pending proposal is written INSIDE the ASK turn,
  // before the POST is answered — so the post-send durable re-fetch (the only
  // delivery path on a settled run) always sees it. Armed before the send.
  let proposalIssued = false;
  mockSse.onConciergeAsk = (ask) => {
    if (proposalIssued || ask.concierge !== true || ask.text !== instruction) return;
    proposalIssued = true;
    const proposal = {
      channel: "revision",
      status: "pending",
      message_id: ask.message_id,
      params: { instruction },
      run_id: ask.run_id,
    };
    if (durableRows) {
      const seq = durableRows.length + 1;
      const event_id = `concierge-proposal:${String(ask.message_id)}:revision`;
      durableRows.push({ seq, event_id, type: "concierge_proposal", payload_json: { ...proposal, event_id, seq } });
    } else {
      mockSse.emit("concierge_proposal", proposal);
    }
  };

  await expect(async () => {
    await revInput.fill(instruction);
    await page.getByTestId("chat-send").click({ timeout: 2000 });
  }).toPass({ timeout: 15000 });

  // (1) The change goes up as a Concierge turn — never a client-side revision.
  const ask = await mockSse.waitForCommand(
    (c) => c.type === "user_message" && c.concierge === true && c.text === instruction,
  );
  expect(mockSse.framesOfType("run_revision")).toHaveLength(0);
  mockSse.onConciergeAsk = null;

  const confirmBtn = page.getByTestId("chat-proposal-confirm");
  await expect(confirmBtn).toBeVisible();
  await confirmBtn.click();

  // (3) Confirm replays the proposal verbatim, keyed to the ASK's message_id.
  const confirm = await mockSse.waitForCommand(
    (c) =>
      c.type === "user_message" &&
      (c.confirm_proposal as { channel?: string } | undefined)?.channel === "revision",
  );
  expect(confirm.confirm_proposal).toEqual({ channel: "revision", params: { instruction } });
  expect(confirm.message_id).toBe(ask.message_id);
  return { ask, confirm };
}

test.describe("TS-U — revision runs", () => {
  test("TS-U-01 ppt revise sends run_revision and renders the revised deck", async ({ dashboard, mockSse, mockApi }) => {
    // The backend creates the revision child on confirm; GET /api/runs reports it
    // with its real type so the remounted run screen resolves the deck renderer.
    mockApi.setRuns([makeRun({ id: "run-e2e-rev", title: "ROI deck (revision)", type: "ppt_revision", status: "running" })]);
    // Declared up front: the run list already reports the child, so the mock must
    // know it has no events until the confirm creates it.
    mockSse.revisionRunId = "run-e2e-rev";
    await dashboard.goto();
    await completeDeckRun(mockSse, "ppt", SAMPLE_DECK);

    // The PPT preview renders the deck iframe.
    await expect(dashboard.deckIframe()).toBeVisible();

    // The revision is requested through the Concierge and confirmed — parented
    // to the ON-SCREEN run (the deck just completed).
    const parentId = mockSse.currentRunId;
    const { confirm } = await requestRevision(dashboard, mockSse, "Add a slide about ROI");
    expect(confirm.run_id).toBe(parentId);

    // ── Drive the revision CHILD run (its own id + tail) → revised deck shows ──
    // The confirm answered revision_run_id, so the UI attaches + routes to it.
    await dashboard.page.waitForURL(/\/runs\/run-e2e-rev\/stream/, { waitUntil: "commit" });
    await completeDeckRun(mockSse, "ppt_revision", REVISED_DECK);

    // The deck iframe is still present and now carries the revised content.
    const deck = dashboard.deckIframe();
    await expect(deck).toBeVisible();
    await expect
      .poll(async () => deck.getAttribute("srcdoc"), { timeout: 10000 })
      .toContain("Revised Slide");
  });

  test("TS-U-02 a revision run shows NO clarify questionnaire", async ({ dashboard, mockSse }) => {
    await dashboard.goto();
    await completeDeckRun(mockSse, "ppt", SAMPLE_DECK);
    await expect(dashboard.deckIframe()).toBeVisible();

    await requestRevision(dashboard, mockSse, "Add a slide about ROI");

    // Drive the revision run to completion WITHOUT ever emitting questionnaire_ready
    // (revisions skip clarify — manifest planner: skip). The Quick Setup
    // questionnaire must never appear.
    await completeDeckRun(mockSse, "ppt_revision", REVISED_DECK);

    await expect(dashboard.deckIframe()).toBeVisible();
    // No clarify form at any point of the revision run.
    await expect(dashboard.questionnaireTitle()).toHaveCount(0);
  });

  test("TS-U-07 user-story revise sends a user_stories_revision run_pipeline frame", async ({ dashboard, mockSse }) => {
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    // ── Complete a user_stories run so the backlog + revise composer render ──
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

    await expect(dashboard.doneBadge()).toBeVisible();
    await dashboard.openPreview();
    await expect(dashboard.page.getByText("Product Backlog").first()).toBeVisible();

    // The change is classified + launched by the backend Concierge, so the client
    // sends NO second run_pipeline (the old client-side user_stories_revision
    // dispatch is retired) — only the Concierge ASK + CONFIRM turns.
    const { confirm } = await requestRevision(dashboard, mockSse, "Add a story for password reset");
    expect(confirm.run_id).toBe(mockSse.currentRunId);
    expect(mockSse.framesOfType("run_pipeline")).toHaveLength(1);
  });

  test("TS-U-09 reopen-revise: a REOPENED ppt run fires exactly one POST /revisions (BUG-003)", async ({ dashboard, mockSse, mockApi }) => {
    // A COMPLETED ppt run in history/recents — reopened (not launched). BUG-003:
    // the revise path on a reopened run must fire exactly ONE revision request,
    // parented to the reopened run. Under the Concierge flow that request is the
    // single revision CONFIRM turn, POSTed to the reopened run's id.
    const parentId = "od-ppt-reopen-1";
    mockApi.setRuns([
      makeRun({ id: parentId, title: "Investor pitch deck", type: "ppt", status: "completed", input: "A B2B carbon-accounting pitch", output: OD_PPT_NARRATION }),
    ]);
    const durableRows: StubRunEventRow[] = [];
    await dashboard.stubRunEvents(parentId, durableRows);

    await dashboard.goto();
    await dashboard.openRecent("Investor pitch deck");

    const { ask, confirm } = await requestRevision(dashboard, mockSse, "Add a closing slide about carbon offsets", durableRows);
    expect(ask.run_id).toBe(parentId);
    expect(confirm.run_id).toBe(parentId);
    const revisionConfirms = mockSse
      .framesOfType("user_message")
      .filter((c) => (c.confirm_proposal as { channel?: string } | undefined)?.channel === "revision");
    expect(revisionConfirms).toHaveLength(1);
  });

  // ── Deleted from the mocked project: engine/DB concerns with no browser surface ──
  // TS-U-03/04/05/06/08 were empty skipped bodies kept as a "register". The mock has
  // no persistence or engine, so they could only ever be skipped here. Owners:
  //   TS-U-03 lineage (derived_from → parent) — backend/tests/integration/agents/
  //     test_run_revision_fe_contract.py::test_fe_exact_run_revision_dispatches_real_pipeline.
  //     KNOWN GAP: "a failed revision writes no ref" has no backend test.
  //   TS-U-04 revision-of-revision (FR-014 chain link 1) — same file
  //     ::test_revision_of_revision_resolves_via_exact_kind_chain_link_1.
  //   TS-U-05 terminal fidelity, never stuck "revising" — backend/tests/integration/
  //     api/test_rest_revisions_api.py::test_driver_happy_path_completed,
  //     ::test_driver_degraded_completion_records_degraded,
  //     ::test_driver_pipeline_failed_records_failed,
  //     ::test_driver_cancellation_records_cancelled.
  //   TS-U-06 surgical-diff merge — inapplicable: the engine has no section-merge
  //     step (the revision agent is prompted to preserve unchanged sections and
  //     returns the whole artifact), so there is no merge to assert.
  //   TS-U-08 reconnect mid-revision `section={base}_output` frames — inapplicable:
  //     that was the WS-era `stream` sectioning; the SSE client never reads it.
  //     Reattach-and-replay is owned by ts-s.reconnect.spec.ts TS-S-01/02/03.
});
