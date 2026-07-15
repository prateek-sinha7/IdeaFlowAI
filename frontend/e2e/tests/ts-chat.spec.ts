/**
 * TS-CHAT — the run-screen chat lane, mounted live (Phase 31, CHATUI-01/02/03).
 *
 * Drives the REAL app (RunChatLane mounted in the execution left column by
 * 31-07) through the EXISTING mock-WS chat driver (Phase 29-06:
 * chatMessage / chatReply / streamAttached / waitForChatCommand) — no driver
 * rewrite (MOCKWS-CHAT-DRIVER-CONTRACT §4 additive). The flag-OFF legacy WS
 * transport is the active path (the SSE provider is unmounted), so these frames
 * ride the same /ws/chat socket the app already owns.
 *
 * Assertions ride the NEW data-testids (the codebase's first — run-chat-lane,
 * chat-transcript, chat-composer, chat-message, chat-gate-actions,
 * chat-clarify-actions) so they survive the Phase-32 reskin.
 *
 * DELTA discipline (CONTEXT e2e-BASELINE): these NEW specs must PASS; the
 * pre-existing feat/ui-2 red baseline (DEF-29-06-1) is not chased to green.
 * Fully offline — no backend, no Bedrock.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-CHAT — run chat lane (mounted live, mocked)", () => {
  // Reach the execution view WITHOUT the home CreationHub (its text locators are
  // red in the pre-existing feat/ui-2 baseline, DEF-29-06-1). A `pipeline_start`
  // flips `isRunning` → DashboardLayout auto-switches to the execution view and
  // mounts the lane in its D-12 "building" composer mode. Transport-independent.
  test.beforeEach(async ({ dashboard, mockWs }) => {
    await dashboard.goto();
    mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    await expect(dashboard.page.getByTestId("run-chat-lane")).toBeVisible();
  });

  // ── TS-CHAT-01 — send a turn: outbound command + optimistic echo reconcile ──
  test("TS-CHAT-01 a sent turn asserts the outbound command and renders ONE bubble (optimistic reconcile, no dupe)", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;
    const composer = page.getByLabel("Chat message input");
    await expect(composer).toBeVisible();

    await composer.fill("Tighten the acceptance criteria");
    await page.getByTestId("chat-send").click();

    // (1) the outbound chat command carries the client-minted message_id (the
    //     transport-agnostic sendMessage up-channel — legacy user_message here).
    const frame = await mockWs.waitForChatCommand(
      (f) => f.type === "user_message" && typeof f.message_id === "string",
    );
    expect(String(frame.text)).toBe("Tighten the acceptance criteria");
    const messageId = String(frame.message_id);

    // (2) the optimistic user turn rendered exactly one bubble.
    const bubbles = page.getByTestId("chat-message");
    await expect(bubbles).toHaveCount(1);
    await expect(page.getByTestId("chat-transcript")).toContainText("Tighten the acceptance criteria");

    // (3) the server echo with the SAME id reconciles in place — still ONE bubble.
    mockWs.chatMessage({ messageId, text: "Tighten the acceptance criteria" });
    await expect(bubbles).toHaveCount(1);
  });

  // ── TS-CHAT-02 — a11y streaming region + narrator markdown ──────────────────
  test("TS-CHAT-02 the transcript region exposes role=log + aria-live and narrator content renders markdown", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;
    const transcript = page.getByTestId("chat-transcript");

    // The open-design a11y landmine shipped correctly from day one (POR §7).
    await expect(transcript).toHaveAttribute("role", "log");
    await expect(transcript).toHaveAttribute("aria-live", "polite");

    // A narrator chat_reply renders react-markdown (bold → <strong>).
    mockWs.chatReply({ cardKind: "pipeline", text: "**Running** the pipeline now" });
    const card = page.getByTestId("chat-result-card");
    await expect(card).toBeVisible();
    await expect(card.locator("strong")).toHaveText("Running");
  });

  // ── TS-CHAT-03 — gate quick-actions: Approve fires + terminal fence hides ────
  test("TS-CHAT-03 a gate surfaces chat-gate-actions, Approve fires the command, terminal hides the actions (KAN-100)", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;

    // The Steps spine (which now hosts the gate quick-actions) mounts once the run
    // has activity; seed a running agent so the tab leaves its empty "Pipeline
    // trace" state (a real gated run always has an active agent + brief).
    mockWs.agentStart(AGENTS.user_stories[0].id);

    // Arm a review gate on the running pipeline. Phase 42-02 (§C) moved the gate
    // quick-actions OUT of the lane (its composer is now a plain phase-hint input)
    // and INTO the Steps spine (InlineGateActions after the paused agent's row).
    // The run auto-tabs to Steps on a gate; open it explicitly to be robust.
    mockWs.reviewGateReady({
      gateKey: "spec-gate",
      agentId: "story-writer",
      agentName: "Story Writer",
      output: "Draft spec ready for review.",
    });
    await dashboard.thinkingTab().click();
    const gate = page.getByTestId("chat-gate-actions");
    await expect(gate).toBeVisible();

    // Approve fires the shared approve_review channel.
    await page.getByTestId("chat-gate-approve").click();
    const approval = await mockWs.waitForClientFrame(
      (f) => f.type === "approve_review" && f.approved === true,
    );
    expect(String(approval.gate_key)).toBe("spec-gate");

    // A terminal event fences the gate actions off (KAN-100 — no live actions on
    // a dead pipeline): the lane leaves gate mode and the actions disappear.
    mockWs.complete({ pipelineType: "user_stories", finalOutput: "# Done" });
    await expect(gate).toHaveCount(0);
  });

  // ── TS-CHAT-04 — clarify quick-actions: chips submit answers ─────────────────
  test("TS-CHAT-04 a clarify state surfaces chat-clarify-actions and the chips submit answers", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;

    // The Steps spine (which now hosts the clarify quick-actions) mounts once the
    // run has activity; seed a running agent so the tab leaves its empty "Pipeline
    // trace" state (a real clarify always pauses an active planner + brief).
    mockWs.agentStart(AGENTS.user_stories[0].id);

    // A mid-run clarify gate. Phase 42-02 (§C) moved the clarify quick-actions OUT
    // of the lane (its composer is now a plain phase-hint input) and INTO the Steps
    // spine (InlineClarifyActions in the "Clarifications" card). The run auto-tabs
    // to Steps on a clarify; open it explicitly to be robust.
    mockWs.questionnaireReady([
      { id: "q1", text: "Which platform?", options: ["Web", "Mobile"] },
    ]);
    await dashboard.thinkingTab().click();
    const clarify = page.getByTestId("chat-clarify-actions");
    await expect(clarify).toBeVisible();

    // Pick a chip, then submit → the shared submit_questionnaire resume channel.
    await clarify.getByTestId("chat-clarify-chip").first().click();
    await page.getByTestId("chat-clarify-submit").click();

    const submit = await mockWs.waitForClientFrame((f) => f.type === "submit_questionnaire");
    expect(submit.type).toBe("submit_questionnaire");
  });
});
