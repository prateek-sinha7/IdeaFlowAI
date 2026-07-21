/**
 * TS-S — Reconnect / durable replay (TEST-REGISTER suite TS-S).
 *
 * The trickiest surface: the WS drop/reload → reconnect handshake and the
 * three `pipeline_reconnected` branches the FE contract pins
 * (useWorkflow.reconnect.test.ts). Here we exercise the FULL browser path —
 * a real `page.reload()` re-auths (the auth token is re-seeded by
 * dashboard.goto's addInitScript, which re-runs on every load) and the
 * DashboardLayout reconnect effect re-emits `reconnect_pipeline` on the next
 * "connected" transition because sessionStorage `active_pipeline_run_id`
 * survives the same-tab reload (set on pipeline_start in useWorkflow).
 *
 * Mechanics that make reload-based reconnect work in mocked mode:
 *   - the SSE stream re-attaches after reload
 *     fires again, so `mockSse.connectionCount` increments (>= 2).
 *   - The `sent` array + the MockSse instance live node-side → they survive the
 *     reload, so waitForClientFrame still resolves the post-reload frame.
 *   - For the reconnect to fire, the run must NOT have terminated before reload
 *     — we emit pipeline_start + ≥1 agent event but NEVER pipeline_complete
 *     before reloading, so `active_pipeline_run_id` stays in sessionStorage.
 *   - after_seq = getLastSeq() = the max seq the FE saw. After a reload the FE
 *     state is fresh (lastSeqRef resets to 0) → after_seq is 0 (a valid >= 0
 *     full-tail replay offset). We only assert it is numeric and >= 0.
 *
 * After the handshake the backend would durably replay the tail; MockSse models
 * that by re-emitting pipeline_start (re-seeds cards) + the agent events, then
 * the `pipeline_reconnected{live,status}` verdict — so the UI assertions below
 * exercise the real post-replay state, not an empty fresh page.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS } from "../fixtures/scenarios";

test.describe("TS-S — reconnect / replay", () => {
  test("TS-S-01 reload re-attaches the run's SSE stream (native Last-Event-ID resume)", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Generate epics for a refunds workflow" });

    // A launched run is non-terminal → the RunConnectionProvider's server-derived
    // reattach (GET /api/runs) re-streams it after a reload. Keep it mid-flight
    // (start + one agent, NEVER pipeline_complete) so it stays reattach-eligible.
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id);
    // Phase 39: the run-level done badge only appears once the WHOLE run settles;
    // a single completed agent (run still mid-flight) is reflected by the lane
    // header's completed/total agents count.
    await expect(dashboard.page.getByText("1/3 agents")).toBeVisible();

    const connectionsBefore = mockSse.connectionCount;

    // Reload — re-auth (token via addInitScript) + the provider re-queries live
    // runs and re-attaches the stream (SSE has NO reconnect_pipeline command; the
    // resume is native, the fetch re-issued carrying Last-Event-ID = the cursor).
    await page.reload();

    // The run's stream re-attaches at least once more (stabilize the reload race).
    await expect.poll(() => mockSse.connectionCount, { timeout: 15000 }).toBeGreaterThan(connectionsBefore);
    expect(mockSse.connectionCount).toBeGreaterThanOrEqual(2);

    // The reattach carried the resume cursor (worst case null → full replay, made
    // idempotent by the downstream event_id dedup).
    const cursor = mockSse.lastAttachCursor;
    expect(cursor === null || (typeof cursor === "number" && cursor >= 0)).toBe(true);
  });

  test("TS-S-03 live:false + terminal 'completed' resolves the run (no stuck spinner)", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    const connectionsBefore = mockSse.connectionCount;
    await page.reload();
    await expect.poll(() => mockSse.connectionCount, { timeout: 15000 }).toBeGreaterThan(connectionsBefore);

    // Backend durably replays the tail: re-seed cards + put one agent running so
    // the run is visibly in-flight again, THEN the terminal verdict.
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();
    await expect(dashboard.stopButton()).toBeVisible();

    // live:false + terminal 'completed' → handler sweeps agents to done and
    // resolves isRunning=false (the anti-hang contract). No perpetual spinner.
    mockSse.reconnected({ live: false, status: "completed" });

    await expect(dashboard.stopButton()).toHaveCount(0);
    await expect(dashboard.runningBadge()).toHaveCount(0);
    await expect(dashboard.doneBadge().first()).toBeVisible();
  });

  test("TS-S-02 live:true keeps streaming the live tail to a normal completion", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Live-tail refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    mockSse.agentComplete(agents[0].id);
    // Phase 39: run mid-flight (1 of 3 done) reads via the lane header agent count,
    // not the now run-level done badge.
    await expect(dashboard.page.getByText("1/3 agents")).toBeVisible();

    const connectionsBefore = mockSse.connectionCount;
    await page.reload();
    await expect.poll(() => mockSse.connectionCount, { timeout: 15000 }).toBeGreaterThan(connectionsBefore);

    // Durable replay re-seeds cards; the first agent already finished.
    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentComplete(agents[0].id);

    // live:true (12-09 engine→WS attach) — keep running; the live task streams
    // the remaining tail through the queue.
    mockSse.reconnected({ live: true });

    // Continue the live tail to a normal terminal completion.
    for (const a of agents.slice(1)) {
      mockSse.agentStart(a.id);
      mockSse.agentComplete(a.id);
    }
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n" });

    // Phase 39 retired the "Done in …s" header; a settled run surfaces the Done
    // status token (lane-run-status, done tone).
    await expect(dashboard.doneBadge()).toBeVisible();
  });

  test("TS-S/TS-Y-04 JWT expiry (close 4001) clears the token and redirects to /login", async ({ dashboard, mockSse, page }) => {
    const agents = AGENTS.user_stories;
    await dashboard.goto();
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    mockSse.start(agents, { pipelineType: "user_stories" });
    mockSse.agentStart(agents[0].id);
    await expect(dashboard.runningBadge().first()).toBeVisible();

    // Server closes with code 4001 → useWebSocket.onclose clears the token and
    // sets window.location = "/login" (NO backoff reconnect on JWT expiry).
    mockSse.expireJwt();

    await expect(page).toHaveURL(/\/login/, { timeout: 15000 });
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  // TS-S-07 — cross-owner demotion (a reconnect by a different owner must be
  // refused / the run demoted) is enforced entirely on the backend (BE-RES-01).
  // There is no FE-observable surface to drive in mocked mode (the mock WS never
  // performs the ownership check), so this is documented as backend-gated. The
  // standalone fixme test keeps the case visible in the run report without
  // skipping its siblings.
  test("TS-S-07 cross-owner demotion (backend-gated)", () => {
    test.fixme(true, "cross-owner demotion is backend-gated (BE-RES-01)");
  });
});
