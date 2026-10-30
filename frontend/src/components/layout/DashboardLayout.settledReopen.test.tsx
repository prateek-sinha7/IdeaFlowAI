/**
 * DashboardLayout — finished-run reopen wiring (plan D6 / D7).
 *
 * - The revision-family effect fetches through the page's `loadRunFamily` (one
 *   shared, cached /family request per run) and only falls back to
 *   `getRunFamily` when no loader is handed down.
 * - The prototype/ppt "running" notification is never created for the run the
 *   page reopened as finished (`settledReopen`), even while its replay reads
 *   `isRunning`; any other prototype run still gets one.
 *
 * Harness copied from DashboardLayout.headerBridge.test.tsx ("wizard-launched
 * run notifications"): mocked at system boundaries only (next/navigation,
 * motion/react, @/lib/api, the SSE run connection, heavy leaf components). The
 * AppHeader stub renders the notification list DashboardLayout hands it.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { cleanup, waitFor } from "@testing-library/react";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import type { PipelineRunState, RunFamily, SettledReopen } from "@/types/index";
import { resetLiveNotificationsCache } from "@/hooks/useNotifications";
import { getRunFamily, getToken } from "@/lib/api";
import type { CompletionToast } from "@/components/ui/CompletionToast";

type ToastProps = React.ComponentProps<typeof CompletionToast>;

const { router } = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() },
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
type MotionStub = (props: { children?: React.ReactNode } & Record<string, unknown>) => React.ReactElement;
vi.mock("motion/react", () => {
  const cache = new Map<string, MotionStub>();
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, prop: string) => {
          let stub = cache.get(prop);
          if (!stub) {
            stub = ({ children, ...rest }) => {
              const cleaned = Object.fromEntries(
                Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
              );
              return React.createElement(prop, cleaned, children);
            };
            cache.set(prop, stub);
          }
          return stub;
        },
      },
    ),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: vi.fn(),
    getRunFamily: vi.fn(),
    getWorkflow: vi.fn(),
  };
});

vi.mock("@/providers/RunConnectionProvider", () => {
  const connection = { attachRun: vi.fn() };
  return { useRunConnection: () => connection };
});

vi.mock("@/components/catalog/HomeLaunchGrid", () => ({ HomeLaunchGrid: () => null }));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => null }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => null }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => null }));
vi.mock("@/components/savedworkflows/SavedWorkflowsPage", () => ({ SavedWorkflowsPage: () => null }));
vi.mock("@/components/workflow/composer/ComposerPage", () => ({ ComposerPage: () => null }));
vi.mock("@/components/preview/PreviewPanel", () => ({
  PreviewPanel: () => <section aria-label="Preview panel" />,
}));
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: () => <section aria-label="Run lane" />,
}));
vi.mock("@/components/workflow/IdeaInputPage", () => ({ IdeaInputPage: () => null }));
vi.mock("@/components/history/WorkflowHistory", () => ({ WorkflowHistory: () => null }));
// The bell list drops running entries, so a running notification is observed
// through what it becomes: the completion toast its run's completion raises.
vi.mock("@/components/ui/CompletionToast", () => ({
  CompletionToast: (props: ToastProps) => (
    <ul aria-label="Toasts">
      {props.toasts.map((t) => (
        <li key={t.id}>{`${t.title} (${t.status}) run=${t.workflowRunId ?? "none"}`}</li>
      ))}
    </ul>
  ),
}));

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <header /> }));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";

function pipeline(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

function baseProps(overrides: Partial<DashboardLayoutProps> = {}): DashboardLayoutProps {
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
    initialMainView: "execution",
    pipelineState: pipeline(),
    ...overrides,
  };
}

function renderLayout(overrides: Partial<DashboardLayoutProps> = {}) {
  return renderWithProviders(<DashboardLayout {...baseProps(overrides)} />);
}

function toastItems(): string[] {
  const list = screen.getByRole("list", { name: "Toasts" });
  return Array.from(list.querySelectorAll("li"), (li) => li.textContent ?? "");
}

const family: RunFamily = { root_id: "r1", members: [] };
const settled = (runId: string): SettledReopen => ({ runId, status: "completed", deliverableFilename: null });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  resetLiveNotificationsCache();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.mocked(getToken).mockReturnValue("tok");
  vi.mocked(getRunFamily).mockResolvedValue(family);
});

describe("DashboardLayout revision family loader", () => {
  it("fetches the family through loadRunFamily instead of getRunFamily when the page hands one down", async () => {
    const loadRunFamily = vi.fn().mockResolvedValue(family);

    renderLayout({ contentSourceRunId: "r1", loadRunFamily });

    await waitFor(() => expect(loadRunFamily).toHaveBeenCalledWith("r1"));
    expect(loadRunFamily).toHaveBeenCalledTimes(1);
    expect(getRunFamily).not.toHaveBeenCalled();
  });

  it("falls back to getRunFamily when no loader is handed down", async () => {
    renderLayout({ contentSourceRunId: "r1" });

    await waitFor(() => expect(getRunFamily).toHaveBeenCalledWith("tok", "r1"));
  });
});

describe("DashboardLayout running notification for a settled reopen", () => {
  const running = (type: string, runId: string) =>
    pipeline({ isRunning: true, pipeline_type: type, pipelineRunId: runId });

  /** Render a running pipeline, then report the run as completed in the background. */
  function runThenComplete(type: string, runId: string, settledReopen: SettledReopen | null) {
    const props = baseProps({ pipelineState: running(type, runId), settledReopen });
    const view = renderWithProviders(<DashboardLayout {...props} />);
    view.rerender(<DashboardLayout {...props} backgroundCompletedRunId={runId} />);
    return { props, view };
  }

  it("creates no running notification for a settled reopen even when pipelineState.isRunning is true", () => {
    runThenComplete("prototype", "run-od", settled("run-od"));

    // No notification was created, so the completion has nothing to announce.
    expect(toastItems()).toEqual([]);
  });

  it("still creates one for a prototype run that is not the settled reopen", () => {
    runThenComplete("prototype", "run-live", settled("run-od"));

    expect(toastItems()).toEqual(["Prototype (completed) run=run-live"]);
  });

  it("creates one once a live resume clears the settled reopen", () => {
    const props = baseProps({ pipelineState: running("ppt", "run-od"), settledReopen: settled("run-od") });
    const view = renderWithProviders(<DashboardLayout {...props} />);

    view.rerender(<DashboardLayout {...props} settledReopen={null} />);
    view.rerender(<DashboardLayout {...props} settledReopen={null} backgroundCompletedRunId="run-od" />);

    expect(toastItems()).toEqual(["Presentation (completed) run=run-od"]);
  });
});
