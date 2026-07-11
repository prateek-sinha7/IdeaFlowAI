/**
 * TS-CHAT-CARDS — narrator result cards + deep-link + attachments (Phase 31,
 * CHATUI-02/03).
 *
 * Drives the REAL mounted RunChatLane (31-07) through the EXISTING mock-WS chat
 * driver (Phase 29-06 chatReply) — no driver rewrite. Proves:
 *   (a) a `deliverable` chat_reply renders a "Deliverable" card (LOCK-F) whose
 *       deep-link switches the PreviewPanel tab via the nonce'd seam (borrow #6);
 *   (b) a `spec_revision` card reads "Revising spec — cycle N" (KAN-101 loop);
 *   (c) a dropped/picked attachment renders a chat-attach-chip.
 *
 * Assertions ride the NEW data-testids so they survive the Phase-32 reskin.
 * DELTA discipline: these NEW specs PASS; the pre-existing red baseline
 * (DEF-29-06-1) is not chased to green. Fully offline.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-CHAT-CARDS — result cards, deep-link, attachments (mocked)", () => {
  // Reach the execution view WITHOUT the home CreationHub (red in the feat/ui-2
  // baseline, DEF-29-06-1): a `pipeline_start` flips `isRunning` → the execution
  // view mounts. Seeding agents also keeps the right panel on the PreviewPanel
  // (tabs), not the planning overlay, and the lane in "building" composer mode.
  test.beforeEach(async ({ dashboard, mockWs }) => {
    await dashboard.goto();
    mockWs.start(AGENTS.user_stories, { pipelineType: "user_stories" });
    await expect(dashboard.page.getByTestId("run-chat-lane")).toBeVisible();
  });

  // ── TS-CHAT-CARDS-01 — deliverable card (LOCK-F) + deep-link tab switch ──────
  test("TS-CHAT-CARDS-01 a deliverable card is labeled 'Deliverable' and its deep-link switches the Preview tab", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;

    mockWs.chatReply({ cardKind: "deliverable", text: "Your output is ready to view." });

    const card = page.getByTestId("chat-result-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-card-kind", "deliverable");
    // LOCK-F: the run output is labeled "Deliverable" (never a workflow noun).
    await expect(card).toContainText("Deliverable");

    // Move OFF the default Preview tab so the deep-link switch is observable.
    // Phase 39 re-anchor: the redesigned tabs are role="tab" with an
    // aria-selected active-state (was a role="button" + text-gray-900 class).
    const previewTab = page.getByRole("tab", { name: /Preview/ });
    const filesTab = page.getByRole("tab", { name: /Files/ });
    await filesTab.click();
    await expect(filesTab).toHaveAttribute("aria-selected", "true");

    // Click the card's deep-link → the nonce'd seam opens the Preview tab.
    await page.getByTestId("chat-result-card-link").click();
    await expect(previewTab).toHaveAttribute("aria-selected", "true");
    await expect(filesTab).toHaveAttribute("aria-selected", "false");
  });

  // ── TS-CHAT-CARDS-02 — spec_revision card reads "Revising spec — cycle N" ────
  test("TS-CHAT-CARDS-02 a spec_revision card reads 'Revising spec — cycle N' (KAN-101 loop, distinct from a family revision)", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;

    mockWs.chatReply({ cardKind: "spec_revision", text: "Reworking the specification from the analysis." });

    const card = page.getByTestId("chat-result-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-card-kind", "spec_revision");
    await expect(card).toContainText("Revising spec — cycle 1");
  });

  // ── TS-CHAT-CARDS-03 — an attachment renders a chip ─────────────────────────
  test("TS-CHAT-CARDS-03 a picked file renders a chat-attach-chip in the composer tray", async ({ dashboard }) => {
    const page = dashboard.page;

    // The composer's attachment tray owns a hidden multi-file input; setInputFiles
    // routes the file through useChatAttachments → a removable preview chip.
    const fileInput = page.locator('[data-testid="chat-attachments"] input[type="file"]');
    await fileInput.setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("acceptance criteria notes"),
    });

    const chip = page.getByTestId("chat-attach-chip");
    await expect(chip.first()).toBeVisible();
    await expect(chip.first()).toContainText("notes.txt");
  });
});
