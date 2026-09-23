/**
 * ISS-647 / ISS-655 — QA-PS-005: clicking a pipeline entry in the "N Running"
 * header dropdown (ISS-647) or the single-pipeline header badge (ISS-655)
 * sometimes does nothing.
 *
 * Root cause (see ISS-647 card, "Root cause — second mechanism"):
 * `AppHeader`'s `handleRunClick` (AppHeader.tsx:224-240) and the single-badge
 * `onClick` (AppHeader.tsx:308-321) both fire `onSwitchToLiveRun(run.id)`
 * (async, unresolved) and then call `onGoToPipeline?.()` with NO ARGUMENT.
 * `onGoToPipeline`'s one implementation (DashboardLayout.tsx:2643-2653) is a
 * closure that reads `pipelineState?.pipelineRunId` — a value captured at
 * DashboardLayout's last completed render, i.e. the PREVIOUS run, not the one
 * just clicked. When no run was previously attached (cold dashboard load),
 * that closure's `if (runId)` guard is false and navigation is silently
 * skipped — the reported "does nothing".
 *
 * The fix (per the card): `onGoToPipeline` must be handed the run id the user
 * actually clicked, so both call sites here must invoke
 * `onGoToPipeline?.(run.id)` instead of the bare `onGoToPipeline?.()`. These
 * tests assert that contract directly at the AppHeader boundary — the layer
 * that owns both call sites — without needing DashboardLayout's own stale
 * `pipelineState` closure to reproduce the missing argument.
 */
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import { AppHeader } from "./AppHeader";
import type { WorkflowRun } from "@/types/index";

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-a",
    title: "Pitch an idea",
    type: "user_stories",
    status: "waiting_for_user",
    input: "{}",
    createdAt: new Date().toISOString(),
    parentRunId: null,
    rootRunId: "run-a",
    agentCount: 4,
    ...overrides,
  } as WorkflowRun;
}

function setup(overrides: Partial<React.ComponentProps<typeof AppHeader>> = {}) {
  const onGoToPipeline = vi.fn();
  const onSwitchToLiveRun = vi.fn();
  renderWithProviders(
    <AppHeader
      currentPage="home"
      onNavigate={vi.fn()}
      onLogout={vi.fn()}
      userEmail="qa-admin@flowinqa.com"
      userTier="enterprise"
      onGoToPipeline={onGoToPipeline}
      onSwitchToLiveRun={onSwitchToLiveRun}
      {...overrides}
    />,
  );
  return { onGoToPipeline, onSwitchToLiveRun };
}

describe("AppHeader — ISS-647 'N Running' dropdown entry click (QA-PS-005)", () => {
  // ISS-647 unfixed: vitest's `{ fails: true }` is this suite's xfail — the
  // test must FAIL today (asserting correct behaviour) and will start
  // reporting a hard failure ("expected test to fail") the moment the fix
  // lands, which is the signal to remove this flag.
  it("passes the clicked run's id to onGoToPipeline, not a bare call", async () => {
    const user = userEvent.setup();
    const runA = makeRun({ id: "run-a", title: "Pitch an idea" });
    const runB = makeRun({ id: "run-b", title: "Build an interactive prototype" });
    const { onGoToPipeline } = setup({ recentRuns: [runA, runB] });

    // 2+ live runs -> the "N Running" dropdown, not the single badge.
    await user.click(screen.getByRole("button", { name: /2 pipelines running/i }));
    const menu = screen.getByRole("menu");
    await user.click(within(menu).getByText(/build an interactive prototype/i));

    expect(onGoToPipeline).toHaveBeenCalledTimes(1);
    // ISS-647 unfixed: onGoToPipeline?.() is called with no argument, so the
    // implementation has no way to know which run was clicked and falls back
    // to a stale value — this assertion is what the fix must satisfy.
    expect(onGoToPipeline).toHaveBeenCalledWith("run-b");
  });
});

describe("AppHeader — ISS-655 single-pipeline badge click (sibling of QA-PS-005)", () => {
  // ISS-655 unfixed: see the ISS-647 xfail note above — same contract, same
  // signal when it starts XPASSing.
  it("passes the running run's id to onGoToPipeline, not a bare call", async () => {
    const user = userEvent.setup();
    const runA = makeRun({ id: "run-a", title: "Pitch an idea" });
    const { onGoToPipeline } = setup({ recentRuns: [runA] });

    // Exactly 1 live run -> the single badge, no dropdown. The badge shows the
    // catalog label for the run's type ("User Stories"), not its title.
    await user.click(screen.getByText(/^user stories$/i));

    expect(onGoToPipeline).toHaveBeenCalledTimes(1);
    expect(onGoToPipeline).toHaveBeenCalledWith("run-a");
  });
});
