/**
 * TS-X — Performance & timing budgets (TEST-REGISTER §TS-X).
 *
 * Scope here is the ACHIEVABLE, deterministic timing surface — real intervals
 * the app drives that a mocked WS / DOM can observe without flakiness:
 *   - TS-X-01  client keepalive ping every 20000ms while the WS is OPEN
 *              (useWebSocket pingInterval) — a genuine wall-clock keepalive
 *              assertion, hence test.slow().
 *   - TS-X-05  the 2000ms copy-toast revert (UserStoryPreview "Copy MD"→"Copied",
 *              and the PreviewPanel header [title="Copy"] icon swap).
 *   - TS-X-08  no-spinner-forever: every terminal path (complete / failed /
 *              cancelled) resolves isRunning → false within budget.
 *
 * Cross-refs (standalone-wrapped fixmes, see notes on each):
 *   - TS-X-03  questionnaire 300ms auto-advance — owned by TS-M-03.
 *   - TS-X-04  prototype tweaks 400ms debounce — deep prototype interaction.
 *
 * NEVER hard-sleep: all timing is asserted via waitForClientFrame / expect with
 * explicit timeouts so the run is deterministic, not wall-clock-padded.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent, playFailedRun, SAMPLE_BACKLOG } from "../fixtures/scenarios";

test.describe("TS-X — timing budgets", () => {
  // ── TS-X-01 — client ping every 20000ms while the WS is open ────────────────
  // useWebSocket starts a setInterval(…, 20000) on ws.onopen that sends
  // {type:"ping"} while readyState === OPEN. This is a real keepalive that keeps
  // long (2-4 min) build tasks alive through idle-dropping proxies. The only
  // honest way to assert it is to wait one interval for the frame to actually
  // arrive — so this is slow (≈21s) by nature. test.slow() grants the 3× timeout.
  test("TS-X-01 client sends a keepalive ping ~every 20s while the WS is open", async ({ dashboard, mockWs }) => {
    test.slow(); // 3× timeout — the first ping only fires after the full 20s interval.

    await dashboard.goto();
    // No run needed — the ping interval is armed on socket open, independent of
    // any pipeline. Wait just past one 20000ms interval for the first ping frame.
    const start = Date.now();
    const ping = await mockWs.waitForClientFrame("ping", 25000);
    const elapsedMs = Date.now() - start;

    expect(ping.type).toBe("ping");
    // It is a keepalive interval, so it must NOT fire immediately (would mean a
    // tight loop, not a 20s timer) and must land inside the wait window.
    expect(elapsedMs).toBeGreaterThan(15000);
    expect(elapsedMs).toBeLessThanOrEqual(25000);
    // Surface the observed latency so the report can record it.
    console.log(`[TS-X-01] first keepalive ping arrived after ${elapsedMs}ms`);
  });

  // ── TS-X-05 — copy toast reverts after 2000ms ──────────────────────────────
  // Two copy affordances both use setTimeout(()=>setCopied(false), 2000):
  //   1. UserStoryPreview header: "Copy MD" ⇄ "Copied" (TEXT — easy, primary).
  //   2. PreviewPanel header [title="Copy"]: <Copy/> ⇄ <Check class=…emerald-600>
  //      (ICON swap — asserted via the rendered lucide <svg> class).
  // We assert BOTH the success state appears and that it auto-reverts.
  test("TS-X-05 copy toast shows a success state then reverts (UserStoryPreview text + header icon)", async ({ dashboard, mockWs }) => {
    // Navigate + trigger a run so the WS is open and we're on the execution view.
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    // Drive a green user_stories run so the backlog (with content) renders.
    const agents = AGENTS.user_stories;
    mockWs.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockWs, a.id);
    mockWs.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

    // The parsed backlog renders the UserStoryPreview with its "Copy MD" button.
    const copyMd = dashboard.page.getByRole("button", { name: /Copy MD/ });
    await expect(copyMd).toBeVisible();

    // navigator.clipboard.writeText needs permission under Chromium headless —
    // grant it so the handler runs to the setCopied(true) branch.
    await dashboard.page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

    await copyMd.click();
    // Success state is TEXT-based: the button now reads "Copied".
    const copied = dashboard.page.getByRole("button", { name: /Copied/ });
    await expect(copied).toBeVisible();
    // …and it reverts to "Copy MD" within the 2000ms window (poll past the timer).
    await expect(dashboard.page.getByRole("button", { name: /Copy MD/ })).toBeVisible({ timeout: 4000 });

    // Also exercise the PreviewPanel header [title="Copy"] button. Its success
    // state is an ICON swap: <Copy/> → <Check class="…text-emerald-600">. Assert
    // the emerald check svg appears, then reverts. (Icon-only, so we target the
    // rendered lucide class — documented as the header's only visible change.)
    const headerCopy = dashboard.page.locator('button[title="Copy"]');
    await expect(headerCopy).toBeVisible();
    await headerCopy.click();
    const checkIcon = headerCopy.locator("svg.text-emerald-600");
    await expect(checkIcon).toBeVisible();
    // The icon reverts to the plain copy glyph within the 2000ms window.
    await expect(headerCopy.locator("svg.text-emerald-600")).toHaveCount(0, { timeout: 4000 });
  });

  // ── TS-X-08 — no spinner-forever: every terminal path resolves isRunning ────
  // Guards the cancel/reconnect regressions that previously left a run stuck in
  // RUNNING/isRunning. We prove ALL THREE terminal paths flip out of running:
  //   complete  → Stop button gone + "Done in …s"  (isRunning=false, all done)
  //   failed    → degraded affordance               (terminal, no stuck spinner)
  //   cancelled → "Pipeline stopped"                (live Stop ack, header flips)
  test.describe("TS-X-08 — no spinner-forever (every terminal path resolves)", () => {
    test.beforeEach(async ({ dashboard }) => {
      await dashboard.goto();
      await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });
    });

    test("complete → terminal: Stop disappears and 'Done in …s' appears", async ({ dashboard, mockWs }) => {
      const agents = AGENTS.user_stories;
      mockWs.start(agents, { pipelineType: "user_stories" });
      // While running, the Stop affordance (isRunning && !isCancelled) is present.
      mockWs.agentStart(agents[0].id);
      await expect(dashboard.stopButton()).toBeVisible();

      // Complete the whole pipeline (Done-in requires completedCount === total).
      for (const a of agents) await runAgent(mockWs, a.id);
      mockWs.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

      // Terminal: header shows wall-clock "Done in …s" (regex — never an exact
      // value) and the Stop button is gone → isRunning resolved to false.
      await expect(dashboard.page.getByText(/Done in \d+(\.\d)?s/)).toBeVisible();
      await expect(dashboard.stopButton()).toHaveCount(0);
      await expect(dashboard.runningBadge()).toHaveCount(0);
    });

    test("failed → terminal: degraded affordance appears (no stuck RUNNING)", async ({ dashboard, mockWs }) => {
      // playFailedRun: start → every agent errors → pipeline_failed (ISS-016).
      await playFailedRun(mockWs, "user_stories");

      await expect(dashboard.errorBadge().first()).toBeVisible();
      // Terminal degraded affordance — the failed run resolved, not spinning.
      await expect(dashboard.degradedHeading()).toBeVisible();
      await expect(dashboard.stopButton()).toHaveCount(0);
      await expect(dashboard.runningBadge()).toHaveCount(0);
    });

    test("cancelled → terminal: 'Pipeline stopped' appears after the Stop ack", async ({ dashboard, mockWs }) => {
      const agents = AGENTS.user_stories;
      mockWs.start(agents, { pipelineType: "user_stories" });
      mockWs.agentStart(agents[0].id);
      await expect(dashboard.runningBadge().first()).toBeVisible();

      // User stops the run; app sends cancel_pipeline, then the server acks.
      await dashboard.stopButton().click();
      await mockWs.waitForClientFrame("cancel_pipeline");
      mockWs.cancelled({ duration: 8 });

      // Terminal: header flips to "Pipeline stopped" and running cards clear.
      // (Live cancel sets NO degraded flag — FIXTURE-CONTRACT gotcha #8 — so it
      // is "Pipeline stopped", not the history-reopen "This run was cancelled".)
      await expect(dashboard.page.getByText("Pipeline stopped")).toBeVisible();
      await expect(dashboard.runningBadge()).toHaveCount(0);
      await expect(dashboard.stopButton()).toHaveCount(0);
    });
  });
});

// ── TS-X-03 — questionnaire auto-advance 300ms ────────────────────────────────
// Standalone-wrapped fixme: the 300ms post-MCQ-select auto-advance is already
// asserted end-to-end by TS-M-03 (ts-m.questionnaire.spec.ts) via expect.poll on
// q2's options becoming visible. Not re-implemented here to avoid a duplicate,
// flakier timer assertion of the same behavior.
test.describe("TS-X-03 — questionnaire auto-advance (cross-ref)", () => {
  test.fixme(true, "covered by TS-M-03 (questionnaire auto-advance 300ms)");
  test("questionnaire auto-advances ~300ms after MCQ select", async () => {
    // Intentionally empty — see TS-M-03.
  });
});

// ── TS-X-04 — prototype tweaks 400ms debounce ─────────────────────────────────
// Standalone-wrapped fixme: the 400ms token-change → iframe-rebuild debounce
// lives inside the TweaksPanel, reachable only through a deep prototype build
// interaction (templates → spec gate → plan gate → build → tweaks). Out of reach
// of the mocked-WS execution surface used here; deferred.
test.describe("TS-X-04 — prototype tweaks debounce (cross-ref)", () => {
  test.fixme(true, "tweaks debounce: deep prototype interaction, defer");
  test("prototype tweaks debounce 400ms before iframe rebuild", async () => {
    // Intentionally empty — deep prototype interaction; deferred.
  });
});
