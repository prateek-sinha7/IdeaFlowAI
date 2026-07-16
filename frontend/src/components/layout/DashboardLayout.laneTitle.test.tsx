/**
 * BUG-001 — the run-lane header title must track the VIEWED run
 * (contentSourceRunId), not `recentRuns[0]` (the most-recently-created run).
 *
 * DashboardLayout computes `runHeaderTitle` and passes it to RunChatLane as
 * `runTitle` (→ LaneRunHeader `data-testid="lane-run-title"`). The old code read
 * `recentRuns?.[0]?.title` unconditionally, so opening a NON-latest run from
 * history/recents showed the wrong (latest) run's title.
 *
 * RunChatLane is stubbed to echo its `runTitle` prop into `lane-run-title` so the
 * assertion targets DashboardLayout's title DERIVATION (the bug), not the lane
 * internals. Execution view is forced via the od_prototype.pending sessionStorage
 * latch the layout reads at mount (DashboardLayout.tsx:238-249).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";
import type { PipelineRunState, WorkflowRun } from "@/types/index";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

// The mount effect at DashboardLayout.tsx:313 fetches the viewed run's family
// (getRunFamily(getToken(), contentSourceRunId)) whenever contentSourceRunId is
// set. Override just those two so the render doesn't hit real fetch/localStorage;
// keep every other @/lib/api export real.
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

// The assertion target: RunChatLane's `runTitle` prop IS DashboardLayout's
// computed `runHeaderTitle` (DashboardLayout.tsx:1714). Echo it into the same
// testid LaneRunHeader uses so we test the derivation without the lane internals.
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: ({ runTitle, runType }: { runTitle?: string; runType?: string }) => (
    <>
      <div data-testid="lane-run-title">{runTitle}</div>
      <div data-testid="lane-run-type">{runType}</div>
    </>
  ),
}));

// Heavy siblings mounted in the execution view — stubbed to markers.
vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ PreviewPanel: () => <div data-testid="stub-preview" /> }));
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
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

function idlePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

function makeRun(id: string, title: string, type: WorkflowRun["type"] = "user_stories"): WorkflowRun {
  return {
    id,
    title,
    type,
    status: "completed",
    input: `brief for ${title}`,
    output: "# Stories\n\nbody",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: id,
  };
}

const RUN_A = makeRun("run-a", "Analytics dashboard for a fitness app");
const RUN_B = makeRun("run-b", "Shift-scheduling app for cafes");
const RUN_C = makeRun("run-c", "A URL shortener web app");

function renderLayout(overrides: Partial<DashboardLayoutProps>) {
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
    pipelineState: idlePipelineState(),
    ...overrides,
  };
  return render(
    <SkillsHooksProvider>
      <DashboardLayout {...props} />
    </SkillsHooksProvider>,
  );
}

beforeEach(() => {
  cleanup();
  // Force the execution view at mount (DashboardLayout reads this latch).
  sessionStorage.setItem("od_prototype.pending", "1");
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout — lane title tracks the viewed run (BUG-001)", () => {
  it("with contentSourceRunId set, the lane title is the VIEWED run's title (not recents[0])", () => {
    renderLayout({ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: RUN_B.id });
    expect(screen.getByTestId("lane-run-title")).toHaveTextContent(RUN_B.title);
    expect(screen.getByTestId("lane-run-title")).not.toHaveTextContent(RUN_A.title);
  });

  it("a viewed run deeper in the recents window still resolves its own title", () => {
    renderLayout({ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: RUN_C.id });
    expect(screen.getByTestId("lane-run-title")).toHaveTextContent(RUN_C.title);
  });

  it("launch flow (contentSourceRunId null) keeps the recents[0] title — byte-identical", () => {
    renderLayout({ recentRuns: [RUN_A, RUN_B, RUN_C], contentSourceRunId: null });
    expect(screen.getByTestId("lane-run-title")).toHaveTextContent(RUN_A.title);
  });
});

describe("DashboardLayout — lane-run-type chip tracks the viewed run (BUG-006)", () => {
  const APP_RUN = makeRun("run-app", "App builder for a CRM", "app_builder");
  const STORY_RUN = makeRun("run-story", "User stories for a booking flow", "user_stories");

  it("viewed app_builder run shows its own type, not the stale workflowType", () => {
    // recents[0] is NOT the viewed run; the viewed run's type is app_builder.
    renderLayout({ recentRuns: [RUN_A, APP_RUN, RUN_C], contentSourceRunId: APP_RUN.id });
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("app_builder");
  });

  it("a different viewed type deeper in the window resolves its own type", () => {
    renderLayout({ recentRuns: [APP_RUN, RUN_B, STORY_RUN], contentSourceRunId: STORY_RUN.id });
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("user_stories");
  });

  it("launch flow (contentSourceRunId null) shows the launched workflowType — no regression", () => {
    renderLayout({ recentRuns: [APP_RUN, RUN_B, RUN_C], contentSourceRunId: null });
    // Under the od_prototype.pending latch the launch consumer sets workflowType to "prototype".
    expect(screen.getByTestId("lane-run-type")).toHaveTextContent("prototype");
  });
});
