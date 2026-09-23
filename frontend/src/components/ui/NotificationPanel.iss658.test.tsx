/**
 * ISS-658 — QA-PS-002 escalation: ISS-644's fix target never reaches the
 * notification panel.
 *
 * RETIRED (2026-09-17, test-writer): this test asserted the wrong mechanism.
 * It expects the panel to merge a fabricated `notifications` entry's
 * `agentsCompleted` into a live row, but the panel deliberately drops
 * running/gate items from `notifications` (`NotificationPanel.tsx:212-214`)
 * and production never hands DashboardLayout a running notification to begin
 * with (`DashboardLayout.tsx:2695`). Turning this test green would require
 * unreachable-in-production code reading the same stale field ISS-644's own
 * theory was superseded over. Re-pointed coverage lives in
 * `frontend/src/hooks/useRunStateStore.iss658.test.tsx`, which reproduces the
 * confirmed mechanism (ISS-679): a page remount between a backgrounded run's
 * `pipeline_start` and its `agent_complete` frames drops that run's whole
 * roster, so its completed count never advances. Skipped, not deleted, to
 * keep the history of what was tried.
 */
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

import { NotificationPanel } from "./NotificationPanel";
import type { PipelineNotification } from "@/hooks/useNotifications";

function makeNotif(overrides: Partial<PipelineNotification> = {}): PipelineNotification {
  return {
    id: "pipeline-run-A",
    workflowRunId: "run-A",
    workflowType: "user_stories",
    title: "My run",
    status: "running",
    agentsCompleted: 0,
    agentsTotal: 6,
    createdAt: new Date(),
    read: false,
    ...overrides,
  };
}

async function openPanel() {
  const bell = screen.getByRole("button", { name: /notifications/i });
  await userEvent.click(bell);
}

describe("NotificationPanel — ISS-658: live row ignores the notification's real progress", () => {
  it.skip("shows the run's true completed-agent count, not liveRuns' stale one (retired — see useRunStateStore.iss658.test.tsx)", async () => {
    // The notification object tracks the run's true, live-updated progress
    // (what a correct fix to the underlying data path would produce).
    const correctlyTrackedNotification = makeNotif({ agentsCompleted: 5, agentsTotal: 6 });

    // liveRuns is what the panel actually reads for a running row today — the
    // frozen/stale value QA-PS-002 observes (AppHeader's runningPipelines).
    const staleLiveRun = makeNotif({ agentsCompleted: 0, agentsTotal: 6 });

    renderWithProviders(
      <NotificationPanel
        notifications={[correctlyTrackedNotification]}
        liveRuns={[staleLiveRun]}
        unreadCount={1}
        onMarkAllRead={vi.fn()}
        onClearAll={vi.fn()}
        onGoToPipeline={vi.fn()}
        onViewResults={vi.fn()}
        recentRuns={[]}
      />,
    );

    await openPanel();

    expect(screen.getByText("5 of 6 agents")).toBeInTheDocument();
    expect(screen.queryByText("0 of 6 agents")).not.toBeInTheDocument();
  });
});
