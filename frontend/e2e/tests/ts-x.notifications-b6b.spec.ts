/**
 * TS-X — B.6b: completion notifications fire over the SSE transport (mocked).
 *
 * Notifications are TRANSPORT-AGNOSTIC — the CompletionToast + the notification-bell
 * unread badge are derived by DashboardLayout from `pipelineState` (the reducer fed by
 * `useRunStream`), NOT from any WS-specific signal. So driving a run to
 * `pipeline_complete` over the mocked SSE down-channel (the 44-09 `mockSse` harness)
 * fully exercises B.6b: launch a run (which registers the run-scoped notification),
 * stream every agent to done, emit `pipeline_complete`, and assert BOTH the
 * bottom-right CompletionToast and the header bell's unread badge appear.
 *
 * Mocked project only (no backend, no Bedrock): the run is launched over the REST
 * up-channel mock and driven by the durable SSE tail.
 */
import { test, expect } from "../fixtures/test";
import { AGENTS, runAgent } from "../fixtures/scenarios";

test.describe("TS-X — B.6b completion notifications (mocked SSE)", () => {
  test("B.6b pipeline_complete fires the CompletionToast + bell unread badge", async ({
    dashboard,
    mockSse,
  }) => {
    await dashboard.goto();
    // Launch over REST — this registers the run-scoped notification (running) that
    // the completion effect later flips to "completed" + surfaces as unread.
    await dashboard.runWith({ workflow: "Generate product requirements", idea: "Refunds backlog" });

    // Drive the full run to pipeline_complete over the mocked SSE down-channel.
    const agents = AGENTS.user_stories;
    mockSse.start(agents, { pipelineType: "user_stories" });
    for (const a of agents) await runAgent(mockSse, a.id);
    mockSse.complete({ pipelineType: "user_stories", finalOutput: "# Product Backlog\n- story" });

    // ── CompletionToast (bottom-right, success) ──────────────────────────────
    // Text-located (no data-testid on the toast): the success card shows the
    // "<Workflow> complete" line and the unique "View results" affordance.
    await expect(dashboard.page.getByText("User Stories complete")).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: /View results/i })).toBeVisible();

    // ── Notification-bell unread badge ───────────────────────────────────────
    // The bell (aria-label="Notifications") gains an unread badge (count "1") once
    // the run's notification is marked completed (read:false). Assert WITHOUT
    // opening the panel — opening marks all read and would clear the badge.
    const bell = dashboard.page.getByRole("button", { name: "Notifications" }).first();
    await expect(bell).toBeVisible();
    await expect(bell.locator("span")).toHaveText("1");
  });
});
