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

// A self-contained styled HTML deliverable for the prototype iframe. The
// <style> already present means injectTweaksIntoHtml has something to override;
// any tweak appends/replaces a `<style id="flowin-tweaks">` block, changing the
// rendered HTML → a brand-new Blob URL (URL.createObjectURL is unique per call),
// which re-keys + re-srcs the iframe. That src change is what we observe.
const PROTOTYPE_HTML =
  "<!DOCTYPE html><html><head><style>body{background:#fff}</style></head><body><h1>App</h1></body></html>";

test.describe("TS-X — timing budgets", () => {
  // ── TS-X-01 — client keepalive ping (RETIRED with the WS transport) ──────────
  // The old WS client armed a 20s setInterval that sent {type:"ping"} to keep the
  // socket alive through idle-dropping proxies. SSE is now the sole transport
  // (44-06): the keepalive is SERVER-side (`pipeline_heartbeat`/`pong` frames the
  // client swallows) and liveness is maintained by the native fetch-stream +
  // Last-Event-ID reconnect (useRunStream) — there is NO client-sent ping frame to
  // observe. This case is retired; the SSE liveness/reconnect contract it guarded
  // is exercised by ts-sse-resilience (drop → reattach) + TS-Y-01. The standalone
  // fixme keeps the case visible in the report without skipping its siblings.
  test("TS-X-01 client keepalive ping (retired — SSE server-heartbeat + native reconnect)", () => {
    test.fixme(true, "client ping retired with the WS transport (44-06); SSE liveness = server heartbeat + native Last-Event-ID reconnect (ts-sse-resilience / TS-Y-01)");
  });

  // ── TS-X-05 — copy toast reverts after 2000ms ──────────────────────────────
  // The UserStoryPreview header "Copy MD" ⇄ "Copied" affordance uses
  // setTimeout(()=>setCopied(false), 2000). We assert the success state appears
  // and auto-reverts. (Phase 39: the old PreviewPanel-header [title="Copy"] icon
  // affordance was retired with the mock's run-header redesign — the mock header
  // carries Version/Share/Download, not a per-deliverable Copy — so only the
  // renderer-level Copy is exercised here.)
  test("TS-X-05 copy toast shows a success state then reverts (UserStoryPreview text)", async ({ dashboard, mockSse }) => {
    // Navigate + trigger a run so the WS is open and we're on the execution view.
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    // Drive a green user_stories run so the backlog (with content) renders.
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

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

    test("complete → terminal: Stop disappears and 'Done in …s' appears", async ({ dashboard, mockSse }) => {
      const agents = AGENTS.user_stories;
      mockSse.start(agents, { pipelineType: "user_stories" });
      // While running, the Stop affordance (isRunning && !isCancelled) is present.
      mockSse.agentStart(agents[0].id);
      await expect(dashboard.stopButton()).toBeVisible();

      // Complete the whole pipeline (Done-in requires completedCount === total).
      for (const a of agents) await runAgent(mockSse, a.id);
      mockSse.complete({ pipelineType: "user_stories", finalOutput: SAMPLE_BACKLOG });

      // Terminal: Phase 39 retired the AgentProgressPanel "Done in …s" header; the
      // settled run now surfaces the Done status token (lane-run-status, done tone)
      // and the Stop button is gone → isRunning resolved to false.
      await expect(dashboard.doneBadge()).toBeVisible();
      await expect(dashboard.stopButton()).toHaveCount(0);
      await expect(dashboard.runningBadge()).toHaveCount(0);
    });

    test("failed → terminal: new failed chrome appears (no stuck RUNNING)", async ({ dashboard, mockSse }) => {
      // playFailedRun: start → every agent errors → pipeline_failed (ISS-016).
      await playFailedRun(mockSse, "user_stories");

      await expect(dashboard.errorBadge().first()).toBeVisible();
      // Phase 42-03 (§D) RETIRED the amber DegradedRunAffordance on the run screen;
      // the terminal-failed signal is now the RunChatLane failure card + the failed
      // run-status token — the failed run resolved, not spinning.
      await expect(dashboard.degradedHeading()).toHaveCount(0);
      await expect(dashboard.page.getByText("What went wrong")).toBeVisible();
      await expect(dashboard.stopButton()).toHaveCount(0);
      await expect(dashboard.runningBadge()).toHaveCount(0);
    });

    test("cancelled → terminal: 'Pipeline stopped' appears after the Stop ack", async ({ dashboard, mockSse }) => {
      const agents = AGENTS.user_stories;
      mockSse.start(agents, { pipelineType: "user_stories" });
      mockSse.agentStart(agents[0].id);
      await expect(dashboard.runningBadge().first()).toBeVisible();

      // User stops the run; app sends cancel_pipeline, then the server acks.
      await dashboard.stopButton().click();
      await mockSse.waitForClientFrame("cancel_pipeline");
      mockSse.cancelled({ duration: 8 });

      // Terminal: Phase 39 replaced the "Pipeline stopped" header with the
      // RunChatLane terminal "Cancelled by you" card and running cards clear.
      // (Live cancel sets NO degraded flag — FIXTURE-CONTRACT gotcha #8 — so it
      // is "Cancelled by you", not the history-reopen "This run was cancelled".)
      await expect(dashboard.page.getByText("Cancelled by you")).toBeVisible();
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

// ── TS-X-04 — prototype tweaks 400ms debounce → iframe rebuild ────────────────
// The TweaksPanel is reachable in mocked mode the same way TS-O-05 reaches the
// prototype iframe: complete an od_prototype run with HTML final_output → the
// PrototypePreview renders iframe[title="Prototype Preview"] off a Blob URL,
// keyed on that URL. A tweak re-renders the HTML (injects a flowin-tweaks <style>
// block) → a fresh Blob URL → the iframe's src/key change. We assert that change.
//
// Two rebuild paths in PrototypePreview, both proven here:
//   • token change (Typography font button → onTokenChange → scheduleRebuild):
//     DEBOUNCED 400ms — this is the TS-X-04 budget under test.
//   • theme preset (Dark → onApplyPreset): IMMEDIATE (setTimeout 0).
// Both end in setRenderedHtml(injectTweaksIntoHtml(...)) → new Blob URL.
test.describe("TS-X-04 — prototype tweaks debounce → iframe rebuild", () => {
  test("a Tweaks change rebuilds the prototype iframe (token change debounced 400ms; preset immediate)", async ({
    dashboard,
    mockSse,
  }) => {
    // ── Reach the prototype preview (mirror TS-O-05) ──────────────────────────
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "A todo app" });

    const agents = AGENTS.od_prototype;
    mockSse.start(agents, { pipelineType: "od_prototype" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "od_prototype", finalOutput: PROTOTYPE_HTML });

    // PrototypePreview builds the Blob URL on an effect tick — poll for the iframe.
    const iframe = dashboard.prototypeIframe();
    await expect(iframe).toBeVisible({ timeout: 10000 });

    // Capture the pristine (no-tweaks) Blob URL the iframe currently points at.
    // It must be a blob: URL so a later inequality is meaningful, not "" → "".
    const beforeSrc = await iframe.getAttribute("src");
    expect(beforeSrc).toMatch(/^blob:/);

    // ── Open the Tweaks panel ─────────────────────────────────────────────────
    // NOTE: the toggle button ALSO has the accessible name "Tweaks" (its label
    // span), so we can't assert the panel by that text alone. Instead assert the
    // three collapsible Section header buttons (exact) — they exist only inside
    // the open panel — plus the Typography section's unique "Font family" label.
    await dashboard.page.locator('button[title="Open tweaks panel"]').click();
    for (const section of ["Theme", "Colors", "Typography"]) {
      await expect(dashboard.page.getByRole("button", { name: section, exact: true })).toBeVisible();
    }
    await expect(dashboard.page.getByText("Font family")).toBeVisible();

    // ── DEBOUNCED path (the TS-X-04 budget): change a typography token ─────────
    // Clicking a font option calls onTokenChange("--font-sans", …) → scheduleRebuild,
    // which setTimeout(400)s the setRenderedHtml. So the iframe src must change, but
    // only AFTER the debounce — we give it the 400ms + a rebuild/Blob margin (≤1.5s).
    // "Inter" differs from the default "System UI", so the token genuinely changes.
    await dashboard.page.getByRole("button", { name: "Inter", exact: true }).click();

    // The rebuild fires once: a NEW Blob URL replaces beforeSrc. expect.poll (never a
    // hard sleep) waits up to 1.5s for the debounced rebuild to land.
    await expect
      .poll(async () => iframe.getAttribute("src"), {
        message: "iframe src should change after the 400ms-debounced token tweak",
        timeout: 1500,
      })
      .not.toBe(beforeSrc);

    const afterTokenSrc = await iframe.getAttribute("src");
    expect(afterTokenSrc).toMatch(/^blob:/);

    // ── IMMEDIATE path: apply the Dark preset → another rebuild ───────────────
    // onApplyPreset rebuilds via setTimeout(0), so this src change should be quick.
    // Asserting a SECOND distinct rebuild proves tweaks repeatedly re-key the iframe
    // (not a one-shot), and exercises the immediate (non-debounced) branch too.
    await dashboard.page.getByRole("button", { name: "Dark", exact: true }).click();
    await expect
      .poll(async () => iframe.getAttribute("src"), {
        message: "iframe src should change again after the immediate Dark preset",
        timeout: 1500,
      })
      .not.toBe(afterTokenSrc);

    await expect(iframe).toBeVisible();
  });
});
