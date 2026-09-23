/**
 * ISS-644 — QA-PS-002: Notification panel shows "0 of N agents" / 0% for
 * actively-running pipelines once the run is no longer the VIEWED one.
 *
 * Root cause (DashboardLayout.tsx, "Update notification progress as agents
 * complete" effect, ~line 937-941):
 *
 *   useEffect(() => {
 *     if (pipelineState?.isRunning && currentPipelineNotifId.current) {
 *       updateProgress(currentPipelineNotifId.current, pipelineState.completedCount);
 *     }
 *   }, [pipelineState?.completedCount, pipelineState?.isRunning]);
 *
 * `pipelineState` is DashboardLayout's own locally-mounted stream state for
 * whichever run is currently `runStore.viewed` (page.tsx) — it is NOT keyed
 * per run. Once the user navigates away from a run's own stream page,
 * `pipelineState` stops describing that run at all, so this effect never
 * fires for it again: the notification object created for that run
 * (`useNotifications.ts`, `agentsCompleted`/`agentsTotal`) is frozen at
 * whatever value it last held, even though the run keeps completing agents
 * server-side — matching the card's repro: "0 of 6 agents" in the panel while
 * the run's own stream page independently shows "3 / 6" at the same moment.
 *
 * This test drives the real launch effect (od_prototype path, the same one
 * DashboardLayout.launchLatch.test.tsx uses) to create a genuine notification
 * and let it pick up a live run id while viewed, then simulates "navigate
 * away" by reverting `pipelineState` to idle — and asserts on the
 * notification object itself (captured directly off `useNotifications()`,
 * the exact state ISS-644 names), not through any UI layer, so the test is
 * scoped to the specific defect rather than to how any particular consumer
 * happens to render it.
 *
 * Uses the `rerender` returned by `renderWithProviders` itself, NOT the
 * module's separate `rerenderWithProviders` helper — that helper builds a
 * brand-new `Wrapper` function on every call, which React treats as a
 * different component type than the one `render()` mounted with, so it
 * unmounts and remounts the whole tree (losing all component state,
 * including the notification just created) instead of updating in place.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import React from "react";
import type { PipelineRunState, AgentRunState } from "@/types/index";
import type { PipelineNotification } from "@/hooks/useNotifications";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "test-token",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  };
});

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("@/components/chat/RunChatLane", () => ({ RunChatLane: () => <div /> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ PreviewPanel: () => <div /> }));
vi.mock("@/components/workflow/AgentProgressPanel", () => ({ AgentProgressPanel: () => <div /> }));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => <div /> }));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({ HomeLaunchGrid: () => <div /> }));
vi.mock("@/components/home/CreationHub", () => ({ CreationHub: () => <div /> }));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => <div /> }));
vi.mock("@/components/history/WorkflowHistory", () => ({ WorkflowHistory: () => <div /> }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => <div /> }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => <div /> }));
vi.mock("@/components/workflow/IdeaInputPage", () => ({ IdeaInputPage: () => <div /> }));

// Capture the exact state `useNotifications()` hands DashboardLayout on every
// render — the real hook runs untouched; this only observes its return value,
// so we can assert on the notification object ISS-644 names without routing
// the assertion through any particular consumer's own merge/filter logic.
let lastNotifications: PipelineNotification[] = [];
vi.mock("@/hooks/useNotifications", async (importActual) => {
  const actual = await importActual<typeof import("@/hooks/useNotifications")>();
  return {
    ...actual,
    useNotifications: (...args: unknown[]) => {
      const real = actual.useNotifications as (...a: unknown[]) => ReturnType<typeof actual.useNotifications>;
      const result = real(...args);
      lastNotifications = result.notifications;
      return result;
    },
  };
});

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";

function idlePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "prototype",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

function agent(status: AgentRunState["status"]): AgentRunState {
  return { id: "a", name: "agent", status } as AgentRunState;
}

function runningPipelineState(runId: string, completedCount: number): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [
      agent("done"), agent("done"), agent("running"),
      agent("idle"), agent("idle"), agent("idle"),
    ],
    currentAgentIndex: 2,
    totalDuration: null,
    completedCount,
    pipelineRunId: runId,
  };
}

function baseProps(overrides: Partial<DashboardLayoutProps>): DashboardLayoutProps {
  return {
    activeChatId: null,
    messages: [],
    isStreaming: false,
    streamingContent: "",
    userStoryContent: "",
    pptContent: "",
    prototypeContent: "",
    connectionStatus: "connected",
    onSendMessage: vi.fn(),
    onSelectChat: vi.fn(),
    onNewChat: vi.fn(),
    onDeleteChat: vi.fn(),
    onLogout: vi.fn(),
    onReconnect: vi.fn(),
    pipelineState: idlePipelineState(),
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  lastNotifications = [];
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout — ISS-644 background progress freeze (QA-PS-002)", () => {
  // ISS-644 unfixed: `{ fails: true }` is vitest's xfail — this test must FAIL
  // today (asserting correct behaviour) and will start reporting a hard
  // failure ("expected fail... test did not fail") the moment the fix lands,
  // which is the signal to remove this flag.
  it("a run's notification keeps tracking completed-agent count after the run is no longer viewed", { fails: true }, () => {
    const runId = "run-iss644";
    const paramsA = {
      brief: "test brief", templateId: "t1", designSystemId: "ds1", discovery: undefined,
    };

    // 1. Launch, still idle (mirrors the real launch flow before the first
    //    pipeline_start frame arrives) — creates the notification.
    const { rerender } = renderWithProviders(<DashboardLayout {...baseProps({
      pendingOdProtoParams: paramsA,
      onClearPendingOdProto: vi.fn(),
      onStartPipeline: vi.fn(),
      pipelineState: idlePipelineState(),
    })} />);

    // 2. The run is now VIEWED and progressing: pipelineRunId arrives,
    //    2 of 6 agents done. This is the correct, working path — the
    //    notification's workflowRunId gets stamped and progress updates.
    rerender(<DashboardLayout {...baseProps({
      pendingOdProtoParams: paramsA,
      onClearPendingOdProto: vi.fn(),
      onStartPipeline: vi.fn(),
      pipelineState: runningPipelineState(runId, 2),
      runAgentsCompletedMap: { [runId]: 2 },
    })} />);

    let notif = lastNotifications.find((n) => n.workflowRunId === runId);
    expect(notif?.agentsCompleted).toBe(2);

    // 3. User navigates away from the run's stream page (e.g. to /dashboard).
    //    DashboardLayout's own `pipelineState` prop no longer describes this
    //    run (it reverts to idle, mirroring runStore.viewed switching away),
    //    but the run keeps progressing server-side — 5 of 6 agents are now
    //    done by the time the panel is checked.
    rerender(<DashboardLayout {...baseProps({
      pendingOdProtoParams: paramsA,
      onClearPendingOdProto: vi.fn(),
      onStartPipeline: vi.fn(),
      pipelineState: idlePipelineState(),
      runAgentsCompletedMap: { [runId]: 5 },
    })} />);

    notif = lastNotifications.find((n) => n.workflowRunId === runId);

    // Expected/correct behaviour: the notification must reflect the run's
    // real progress (5 of 6), matching what the run's own stream page would
    // show at this moment — not the stale count from before the user
    // navigated away.
    expect(notif?.agentsCompleted).toBe(5);
  });
});
