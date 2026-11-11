/**
 * TS-Z4 — AI Workflow Builder: the browser journey (Req 49.11).
 *
 * Mocked spec. The REST surface and the Session_Stream come from
 * `fixtures/workflowBuilderMocks.ts` (no backend, no model); the shell, the
 * Composer and the save endpoint come from the standard `mockApi` fixture.
 *
 *   01 create from /workflows: the entry opens a new canvas with the panel and no
 *      popup, the first message starts the session, see progress, the draft renders,
 *      Save, and the URL moves to the edit route without a remount (Req 1.4, 3.8, 9.3, 10.7)
 *   02 a turn that timed out keeps its work, and Continue sends "continue" (Req 13.8)
 *   03 a 503 `host_capacity_exhausted` shows the busy modal and keeps the typed
 *      text so it can be sent again (Req 13.10)
 *   04 docked at 360 px under the header from 1280 px; below that the panel is an
 *      overlay that leaves the canvas width alone (Req 3.1, 3.3)
 *
 * The panel is found by role and name. `tier` defaults to enterprise, which holds
 * the Custom_Entitlement (`canRunPipeline(tier, "custom")`).
 */
import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import {
  DRAFT_CHANGE_SUMMARY,
  DRAFT_MANIFEST,
  E2E_DEFAULT_EFFORT,
  E2E_DEFAULT_MODEL_ID,
  installWorkflowBuilderMocks,
} from "../fixtures/workflowBuilderMocks";

const PROMPT = "Research a topic and write a short brief with sources";
const SESSION_ID = "sess-e2e-1";
const DRAFT_REPLY = "I drafted a two-step workflow: an Analyst, then a Writer.";

function panelOf(page: Page) {
  return page.getByRole("complementary", { name: "AI workflow builder" });
}

/**
 * Type the first message into the open, empty panel and send it. No popup opens on
 * the way. Send waits for the model list.
 */
async function sendFromPanel(page: Page, text: string) {
  const panel = panelOf(page);
  await expect(panel).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(panel.getByRole("heading", { name: "What should this workflow do?" })).toBeVisible();
  await panel.getByRole("textbox", { name: "Message to the builder" }).fill(text);
  await panel.getByRole("button", { name: "Send", exact: true }).click();
}

test.describe("TS-Z4 — AI workflow builder journey", () => {
  test.use({ tier: "enterprise" });

  test("TS-Z4-01 create from /workflows: progress, draft renders, save moves the URL without a remount", async ({
    dashboard,
    mockApi,
    page,
  }) => {
    const builder = await installWorkflowBuilderMocks(page);
    await dashboard.goto();

    // Start from the Saved Workflows page: "Build with AI" opens a new canvas with the
    // panel open and empty, and creates nothing yet (Req 1.4).
    await page.getByRole("button", { name: "My Workflows" }).click();
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await page.getByRole("button", { name: "Build with AI" }).click();
    await page.waitForURL(/\/workflows\/new$/);
    const panel = panelOf(page);
    await expect(panel).toBeVisible();
    await expect(dashboard.composerEyebrow()).toBeVisible();
    expect(builder.requests.some((r) => r.method === "POST" && r.path === "/sessions")).toBe(false);

    // The first message from the panel creates the session and moves the URL (Req 1.8, 3.7).
    await sendFromPanel(page, PROMPT);
    await page.waitForURL(new RegExp(`/workflows/new\\?ai=${SESSION_ID}$`));
    await expect(panel).toBeVisible();

    // The session carries the picker's choice, and the first message follows it.
    const created = builder.requests.find((r) => r.method === "POST" && r.path === "/sessions");
    expect(created?.body).toMatchObject({
      mode: "create",
      model_id: E2E_DEFAULT_MODEL_ID,
      effort: E2E_DEFAULT_EFFORT,
    });
    const turn = await builder.nextTurn();
    expect(builder.messages).toHaveLength(1);
    expect(builder.messages[0]).toMatchObject({ sessionId: SESSION_ID, content: PROMPT });
    expect(Array.isArray(builder.messages[0].canvas_state.steps)).toBe(true);

    // ── See progress: stage label, activity line, check line (Req 16.1 to 16.3) ──
    const progress = panel.getByRole("region", { name: "Progress" });
    await turn.start();
    await expect(progress).toContainText("Starting");
    await turn.setStage("reading", "Reading the builder guide");
    await turn.toolStarted({
      callId: "call-1",
      tool: "read_file",
      kind: "read",
      label: "Read the builder guide",
    });
    await expect(progress).toContainText("Reading the builder guide");
    await expect(progress.getByText("Activity (1)")).toBeVisible();
    await turn.toolFinished({ callId: "call-1", summary: "Read the builder guide." });
    await turn.setStage("checking", "Checking the workflow");
    await turn.check();
    await expect(progress).toContainText("Checking the workflow");
    await expect(progress.getByRole("list", { name: "Checks" })).toBeVisible();

    // The user's own message stays on screen while the turn runs, exactly once, and
    // is no longer "Sending" once the server accepted it (open decision 22.10).
    const yourMessage = panel.getByRole("article", { name: "Your message" });
    await expect(yourMessage).toHaveCount(1);
    await expect(yourMessage).toHaveText(PROMPT);
    await expect(panel.getByText("Sending", { exact: true })).toHaveCount(0);

    // While the turn runs the canvas is read-only and Save is held (Req 9.3, 9.4).
    await expect(page.getByText("The builder is updating this workflow.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save workflow" })).toBeDisabled();

    // ── The draft renders on the canvas without a reload (Req 7.2) ──
    await turn.setStage("applying", "Applying the draft to the canvas");
    await turn.applyDraft({ manifest: DRAFT_MANIFEST, changeSummary: DRAFT_CHANGE_SUMMARY });
    await turn.complete({ status: "completed", content: DRAFT_REPLY });

    await expect(panel.getByText(DRAFT_REPLY)).toBeVisible();
    // After the reload the stored row replaces the pending one: still exactly one.
    await expect(yourMessage).toHaveCount(1);
    await expect(yourMessage).toHaveText(PROMPT);
    await expect(panel.getByText("Added: Analyst, Writer")).toBeVisible();
    await expect(dashboard.composerSummary()).toContainText("2 agents");
    await expect(dashboard.composerNameInput()).toHaveValue("AI research brief");
    await expect(page.getByRole("button", { name: "Rename Analyst", exact: true })).toBeVisible();
    await expect(page.getByText("The builder is updating this workflow.")).toHaveCount(0);

    // ── Save: tag the live page and the live name field, so a reload or a remount shows ──
    await page.evaluate(() => {
      const w = window as unknown as { __e2eSameDocument?: boolean };
      w.__e2eSameDocument = true;
      document.querySelector('input[name="workflow-name"]')?.setAttribute("data-e2e-mounted", "1");
    });
    await expect(page.getByRole("button", { name: "Save workflow" })).toBeEnabled();
    await page.getByRole("button", { name: "Save workflow" }).click();

    // The row is created through the existing endpoint with the draft as its manifest (Req 10.1).
    await expect
      .poll(() => mockApi.requests.some((r) => r.method === "POST" && r.url.endsWith("/api/user-workflows")))
      .toBe(true);
    const save = mockApi.requests.find(
      (r) => r.method === "POST" && r.url.endsWith("/api/user-workflows"),
    );
    expect(save?.body).toMatchObject({ name: "AI research brief", base_pipeline_type: "custom" });
    const manifest = (save?.body as { manifest?: { steps?: unknown[] } }).manifest;
    expect(manifest?.steps).toHaveLength(2);

    // The session is linked to the new row, and the address moves to its edit route (Req 3.8).
    await expect(page).toHaveURL(new RegExp(`/workflows/uw-[^/?]+/edit\\?ai=${SESSION_ID}$`));
    const savedId = /\/workflows\/([^/?]+)\/edit/.exec(page.url())?.[1] ?? "";
    expect(builder.links).toEqual([{ sessionId: SESSION_ID, workflowId: savedId }]);

    // No remount: same document, same name field node, panel still open, canvas still drawn,
    // and no cold-mount fetch of the row the composer just saved.
    expect(
      await page.evaluate(() => (window as unknown as { __e2eSameDocument?: boolean }).__e2eSameDocument),
    ).toBe(true);
    await expect(dashboard.composerNameInput()).toHaveAttribute("data-e2e-mounted", "1");
    await expect(panel).toBeVisible();
    await expect(dashboard.composerSummary()).toContainText("2 agents");
    expect(
      mockApi.requests.filter((r) => r.method === "GET" && r.url.endsWith(`/api/user-workflows/${savedId}`)),
    ).toHaveLength(0);
  });

  test("TS-Z4-02 a timed-out turn keeps its work and Continue sends 'continue'", async ({
    dashboard,
    page,
  }) => {
    const builder = await installWorkflowBuilderMocks(page);
    await dashboard.openComposer();
    await page.getByRole("button", { name: "Build with AI" }).click();
    await sendFromPanel(page, PROMPT);
    const panel = panelOf(page);
    await expect(panel).toBeVisible();

    // The first turn runs out of time before it proposes a draft (Req 13.8).
    const first = await builder.nextTurn();
    await first.start();
    await first.setStage("writing", "Writing the draft");
    await first.complete({
      status: "timed_out",
      outcome: "unfinished",
      stopReason: "time",
      content: "I outlined the Analyst step but ran out of time before the Writer.",
    });
    await expect(
      panel.getByText("This turn stopped at the time limit. The work so far is kept."),
    ).toBeVisible();
    await expect(panel.getByText(/ran out of time before the Writer/)).toBeVisible();
    await expect(dashboard.composerSummary()).toContainText("0 agents");

    // Continue sends "continue" as the next message, with the canvas as it is.
    await panel.getByRole("button", { name: "Continue" }).click();
    const second = await builder.nextTurn();
    expect(builder.messages.map((m) => m.content)).toEqual([PROMPT, "continue"]);
    expect(builder.messages[1]).toMatchObject({
      sessionId: SESSION_ID,
      model_id: E2E_DEFAULT_MODEL_ID,
      effort: E2E_DEFAULT_EFFORT,
    });
    expect(Array.isArray(builder.messages[1].canvas_state.steps)).toBe(true);

    // The continued turn finishes the job; the earlier reply and its notice stay in the transcript.
    await second.start();
    await second.setStage("writing", "Writing the draft");
    await expect(panel.getByRole("region", { name: "Progress" })).toContainText("Writing the draft");

    // While that turn runs, the user's "continue" stays on screen exactly once
    // (open decision 22.10).
    const continueMessage = panel
      .getByRole("article", { name: "Your message" })
      .filter({ hasText: /^continue$/ });
    await expect(continueMessage).toHaveCount(1);
    await expect(panel.getByText("Sending", { exact: true })).toHaveCount(0);

    await second.applyDraft({ manifest: DRAFT_MANIFEST, changeSummary: DRAFT_CHANGE_SUMMARY });
    await second.complete({ status: "completed", content: DRAFT_REPLY });
    await expect(panel.getByText(DRAFT_REPLY)).toBeVisible();
    // After the reload the stored row replaces the pending one: still exactly one.
    await expect(continueMessage).toHaveCount(1);
    await expect(dashboard.composerSummary()).toContainText("2 agents");
    await expect(panel.getByText(/ran out of time before the Writer/)).toBeVisible();
  });

  test("TS-Z4-03 a 503 busy answer shows the busy modal and keeps the typed text", async ({
    dashboard,
    page,
  }) => {
    const builder = await installWorkflowBuilderMocks(page);
    await dashboard.openComposer();
    await page.getByRole("button", { name: "Build with AI" }).click();
    await sendFromPanel(page, PROMPT);
    const panel = panelOf(page);
    await expect(panel).toBeVisible();

    const first = await builder.nextTurn();
    await first.start();
    await first.complete({
      status: "completed",
      outcome: "reply",
      content: "Who is the brief for, and how long should it be?",
    });
    await expect(panel.getByText(/Who is the brief for/)).toBeVisible();

    // The Capacity_Gate refuses the next message (Req 13.10).
    const followUp = "For executives, one page";
    const input = panel.getByRole("textbox", { name: "Message to the builder" });
    const send = panel.getByRole("button", { name: "Send", exact: true });
    await input.fill(followUp);
    builder.rejectNextMessageWithBusy();
    await send.click();

    const busy = page.getByRole("dialog");
    await expect(busy.getByRole("heading", { name: "Service is busy" })).toBeVisible();
    await expect(busy.getByText(/try again in about 90s/i)).toBeVisible();
    await busy.getByRole("button", { name: "Got it" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // The text is still in the box, nothing was stored, and the same text goes through next time.
    await expect(input).toHaveValue(followUp);
    expect(builder.messages.map((m) => m.content)).toEqual([PROMPT]);
    await expect(send).toBeEnabled();
    await send.click();
    await builder.nextTurn();
    expect(builder.messages.map((m) => m.content)).toEqual([PROMPT, followUp]);
    const posts = builder.requests.filter((r) => r.method === "POST" && r.path.endsWith("/messages"));
    expect(posts).toHaveLength(3);
  });

  test("TS-Z4-04 docked under the header from 1280 px, an overlay below that", async ({
    dashboard,
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    const builder = await installWorkflowBuilderMocks(page);
    await dashboard.openComposer();
    const nameInput = dashboard.composerNameInput();
    await page.getByRole("button", { name: "Build with AI" }).click();
    await sendFromPanel(page, PROMPT);
    const turn = await builder.nextTurn();
    await turn.start();
    await turn.complete({ status: "completed", outcome: "reply", content: "Tell me more." });

    // At 1280 px the panel is docked at 360 px under the Composer header: the header
    // keeps the full width (the panel does not push it right) and the canvas starts
    // right of the panel (Req 3.1).
    const docked = panelOf(page);
    await expect(docked).toBeVisible();
    await expect.poll(async () => (await docked.boundingBox())?.width).toBe(360);
    await expect.poll(async () => (await nameInput.boundingBox())?.x ?? 9999).toBeLessThan(360);
    const headerBottom = await nameInput.evaluate((el) => el.getBoundingClientRect().bottom);
    await expect.poll(async () => (await docked.boundingBox())?.y ?? 0).toBeGreaterThan(headerBottom);
    const canvas = page.getByTestId("canvas-view");
    await expect.poll(async () => (await canvas.boundingBox())?.x ?? 0).toBeGreaterThanOrEqual(360);

    // At 900 px it becomes an overlay with a backdrop; the canvas is not narrowed (Req 3.3).
    await page.setViewportSize({ width: 900, height: 800 });
    const overlay = page.getByRole("dialog", { name: "AI workflow builder" });
    await expect(overlay).toBeVisible();
    await expect(page.getByTestId("builder-backdrop")).toBeVisible();
    await expect(panelOf(page)).toHaveCount(0);
    await expect.poll(async () => (await canvas.boundingBox())?.x ?? 9999).toBeLessThan(360);

    // Escape collapses it; the AI button brings it back; a click on the backdrop collapses it.
    await page.keyboard.press("Escape");
    await expect(overlay).toHaveCount(0);
    await page.getByRole("button", { name: "Build with AI" }).click();
    await expect(overlay).toBeVisible();
    await page.getByTestId("builder-backdrop").click({ position: { x: 850, y: 400 } });
    await expect(overlay).toHaveCount(0);
  });
});
