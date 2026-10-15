/**
 * BUG-024 / QA-KB-049, with ISS-956 (every run screen), ISS-957 (keyed on
 * isRunning, not status), ISS-958 (in-app opens) and ISS-959 (Back bounce).
 *
 * The pipelineState.isRunning effect in DashboardLayout.tsx pushed
 * routes.runStream(incomingRunId) without reading the URL, so a cold load of
 * any /runs/{id}/<tab> of a live run was rewritten to /stream. It must skip the
 * push when the URL already addresses that run, and still push when the URL
 * names no run (a fresh launch) or a different run (a revision).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import type { PipelineRunState } from "@/types/index";
import { routes } from "@/lib/routes";

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

vi.mock("motion/react", async () => {
  const React = await import("react");
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, prop: string) =>
          ({ children }: { children?: React.ReactNode }) => React.createElement(prop, {}, children),
      },
    ),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => children,
  };
});

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

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";

function runningState(runId: string): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    pipelineRunId: runId,
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

function renderAt(url: string, runId: string) {
  window.history.replaceState(null, "", url);
  const props: DashboardLayoutProps = {
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
    initialMainView: "execution",
    pipelineState: runningState(runId),
  };
  renderWithProviders(<DashboardLayout {...props} />);
}

beforeEach(() => {
  cleanup();
  push.mockClear();
});
afterEach(() => {
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

describe("DashboardLayout isRunning funnel — BUG-024 keeps a live run's own URL", () => {
  it.each([
    routes.runDetail("run-live"),
    routes.runSteps("run-live"),
    routes.runStepsAgent("run-live", "agent-1"),
    routes.runFiles("run-live"),
    routes.runWorkspace("run-live"),
    routes.runAudit("run-live"),
    routes.runVersion("run-live", "2"),
    routes.runFiles("run-live", "2"),
    routes.runPreviewFull("run-live"),
  ])("does not rewrite %s to /stream", (url) => {
    renderAt(url, "run-live");
    expect(push).not.toHaveBeenCalledWith(routes.runStream("run-live"));
  });

  it.each([
    [routes.dashboard(), "run-live"],
    [routes.createPpt(), "run-live"],
    [routes.runAudit("run-parent"), "run-child"],
  ])("still pushes /stream from %s for %s", (url, runId) => {
    renderAt(url, runId);
    expect(push).toHaveBeenCalledWith(routes.runStream(runId));
  });
});
