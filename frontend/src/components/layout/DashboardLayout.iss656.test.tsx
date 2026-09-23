/**
 * ISS-656 — sibling of QA-PS-005 (ISS-647): WorkflowHistory's "view running
 * pipeline" resume button is a structural clone of the confirmed
 * stale-closure navigation bug.
 *
 * `onViewRunningPipeline` (DashboardLayout.tsx:2859-2873), passed to
 * `WorkflowHistory`, is:
 *
 *   onViewRunningPipeline={() => {
 *     const runId = pipelineState?.pipelineRunId;
 *     if (runId) {
 *       onSwitchToLiveRun?.(runId);
 *       setMainView("execution");
 *       router.push(routes.runStream(runId));
 *     }
 *   }}
 *
 * Same shape as the confirmed-buggy `onGoToPipeline` (ISS-647): it takes no
 * argument and re-derives the run id from DashboardLayout's own
 * `pipelineState` instead of trusting the run the caller actually means. The
 * card's fix directs this callback to navigate using a passed-in runId
 * argument instead — matching the already-correct `onSelectWorkflowRun`/
 * `onViewResults` shape in this same file.
 *
 * This test captures the REAL `onViewRunningPipeline` closure DashboardLayout
 * wires up (via a WorkflowHistory mock, not a re-implementation) and invokes
 * it exactly as the fixed WorkflowHistory would — passing the run id of the
 * pipeline actually being resumed. Today's implementation ignores that
 * argument and silently no-ops instead of navigating, because
 * `pipelineState.pipelineRunId` is unset (the exact "user never revisited the
 * run's own stream page" scenario the card describes).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import type { PipelineRunState } from "@/types/index";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "test-token",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
  };
});

vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children }: { children?: React.ReactNode }) => {
          const React = require("react");
          return React.createElement(prop, {}, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => children,
}));

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("@/components/chat/RunChatLane", () => ({ RunChatLane: () => <div /> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ PreviewPanel: () => <div /> }));
vi.mock("@/components/workflow/AgentProgressPanel", () => ({ AgentProgressPanel: () => <div /> }));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => <div /> }));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({ HomeLaunchGrid: () => <div /> }));
vi.mock("@/components/home/CreationHub", () => ({ CreationHub: () => <div /> }));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => <div /> }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => <div /> }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => <div /> }));
vi.mock("@/components/workflow/IdeaInputPage", () => ({ IdeaInputPage: () => <div /> }));

// Capture the real `onViewRunningPipeline` closure DashboardLayout builds for
// WorkflowHistory, without re-implementing DashboardLayout's own logic.
let capturedOnViewRunningPipeline: ((runId?: string) => void) | undefined;
vi.mock("@/components/history/WorkflowHistory", () => ({
  WorkflowHistory: (props: { onViewRunningPipeline?: (runId?: string) => void }) => {
    capturedOnViewRunningPipeline = props.onViewRunningPipeline;
    return <div />;
  },
}));

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
    initialMainView: "history",
    pipelineState: idlePipelineState(),
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  push.mockClear();
  capturedOnViewRunningPipeline = undefined;
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout — ISS-656 History 'view running pipeline' resume button (sibling of QA-PS-005)", () => {
  // ISS-656 unfixed: this must FAIL today (asserting correct behaviour) and
  // will start reporting a hard failure ("expected test to fail") the moment
  // the fix lands — the signal to remove the flag.
  it("resumes the pipeline that is actually running, not whatever pipelineState last held", () => {
    const onSwitchToLiveRun = vi.fn();

    // The user started run "run-live" but is on the History page having never
    // revisited that run's own stream page — pipelineState never attached to
    // it, exactly the card's "What would confirm this" scenario.
    renderWithProviders(<DashboardLayout {...baseProps({
      onSwitchToLiveRun,
      pipelineState: idlePipelineState(), // pipelineRunId is unset
    })} />);

    expect(capturedOnViewRunningPipeline).toBeDefined();
    // Simulate the FIXED WorkflowHistory, which already knows the run this
    // resume button is for (`run.id`) and would pass it through.
    capturedOnViewRunningPipeline?.("run-live");

    // Today's implementation ignores the argument entirely and reads the
    // stale/unset `pipelineState.pipelineRunId` instead, so it silently does
    // nothing here.
    expect(onSwitchToLiveRun).toHaveBeenCalledWith("run-live");
    expect(push).toHaveBeenCalledWith(expect.stringContaining("run-live"));
  });
});
