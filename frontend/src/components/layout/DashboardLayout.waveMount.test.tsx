/**
 * Phase 12 / 12-08 (WAVE-03 FE half, UAT Gap 1) — proves WaveTreePanel is
 * mounted on the dashboard EXECUTION surface (no longer dead UI inside the
 * legacy unrouted composer, which was deleted in ISS-014). Renders the real
 * DashboardLayout with
 * pipelineState.isRunning=true (which flips mainView to "execution") and
 * asserts the `waves` prop reaches WaveTreePanel:
 *   - non-empty waves → the "Wave / Subagent Tree" heading + the worker agent
 *     name render in the DOM;
 *   - waves=[] (and omitted entirely) → the "No waves running." empty state
 *     renders, so non-wave runs show the harmless empty panel.
 *
 * Heavy children (AppHeader, panels, preview) are stubbed — the assertion
 * target is the WaveTreePanel mount on the execution surface, which stays REAL.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ── Mocks ────────────────────────────────────────────────────────────────────

// next/navigation — DashboardLayout calls useRouter() at the top of the body.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

// motion/react does not run reliably under jsdom and none of these tests care
// about animation (same pattern as AgentProgressPanel.test.tsx): each
// `motion.X` renders the underlying tag with motion-specific props stripped.
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

// Stub the heavy children — only WaveTreePanel (the assertion target) stays
// real. Each stub renders a marker div so a missing mount is debuggable.
vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: () => <div data-testid="stub-app-header" />,
}));
vi.mock("@/components/home/CreationHub", () => ({
  CreationHub: () => <div data-testid="stub-creation-hub" />,
}));
// 22-07 (UXFIX-03): the data-driven WorkflowCatalog is now the default home
// landing — it mounts (briefly, on the initial "home" render before the
// isRunning effect flips to "execution") and its mount fetch calls getToken()
// → localStorage, which this jsdom env does not provide. Stub it like the rest
// of the heavy children so the wave-tree assertion target stays isolated.
vi.mock("@/components/catalog/WorkflowCatalog", () => ({
  WorkflowCatalog: () => <div data-testid="stub-workflow-catalog" />,
}));
vi.mock("@/components/library/LibraryPage", () => ({
  LibraryPage: () => <div data-testid="stub-library" />,
}));
vi.mock("@/components/history/WorkflowHistory", () => ({
  WorkflowHistory: () => <div data-testid="stub-history" />,
}));
vi.mock("@/components/settings/AccountSettings", () => ({
  AccountSettings: () => <div data-testid="stub-settings" />,
}));
vi.mock("@/components/analytics/AnalyticsPage", () => ({
  AnalyticsPage: () => <div data-testid="stub-analytics" />,
}));
vi.mock("@/components/workflow/IdeaInputPage", () => ({
  IdeaInputPage: () => <div data-testid="stub-idea-input" />,
}));
vi.mock("@/components/workflow/AgentProgressPanel", () => ({
  AgentProgressPanel: () => <div data-testid="stub-agent-progress" />,
}));
vi.mock("@/components/preview/PreviewPanel", () => ({
  PreviewPanel: () => <div data-testid="stub-preview" />,
}));
vi.mock("@/components/preview/QuestionnairePanel", () => ({
  QuestionnairePanel: () => <div data-testid="stub-questionnaire" />,
}));
vi.mock("@/components/preview/ReviewGatePanel", () => ({
  ReviewGatePanel: () => <div data-testid="stub-review-gate" />,
}));
vi.mock("@/components/ui/CompletionToast", () => ({
  CompletionToast: () => <div data-testid="stub-toast" />,
}));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { PipelineRunState, WaveGroup } from "@/types/index";

// ── Fixtures ─────────────────────────────────────────────────────────────────

function runningPipelineState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "custom",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

const RUNNING_WAVE: WaveGroup = {
  waveIndex: 0,
  step: "s",
  taskIds: ["t1"],
  status: "running",
  workers: [{ agent: "wave-worker-alpha", status: "running", worker: 0 }],
};

function renderLayout(waves?: WaveGroup[]) {
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
    // isRunning=true flips mainView to "execution" via the existing effect,
    // so the execution surface (left panel + wave tree) mounts.
    pipelineState: runningPipelineState(),
    ...(waves !== undefined ? { waves } : {}),
  };
  return render(
    <SkillsHooksProvider>
      <DashboardLayout {...props} />
    </SkillsHooksProvider>,
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("DashboardLayout — WaveTreePanel mount on the execution surface (12-08 Gap 1)", () => {
  it("renders the wave tree heading and the worker leaf when waves is non-empty", () => {
    renderLayout([RUNNING_WAVE]);

    // The execution surface mounted (AgentProgressPanel stub present) …
    expect(screen.getByTestId("stub-agent-progress")).toBeInTheDocument();
    // … and WaveTreePanel received + rendered the waves prop beside it.
    expect(screen.getByText("Wave / Subagent Tree")).toBeInTheDocument();
    expect(screen.getByText("Wave 0")).toBeInTheDocument();
    expect(screen.getByText("wave-worker-alpha")).toBeInTheDocument();
    expect(screen.queryByText("No waves running.")).not.toBeInTheDocument();
  });

  it("renders the empty state when waves=[] (non-wave run unchanged)", () => {
    renderLayout([]);

    expect(screen.getByTestId("stub-agent-progress")).toBeInTheDocument();
    expect(screen.getByText("Wave / Subagent Tree")).toBeInTheDocument();
    expect(screen.getByText("No waves running.")).toBeInTheDocument();
  });

  it("defaults to the empty state when the waves prop is omitted (existing callers unaffected)", () => {
    renderLayout(undefined);

    expect(screen.getByText("No waves running.")).toBeInTheDocument();
  });

  // ISS-019 — structural OFFLINE proof of the left-column flex budget.
  // jsdom has no layout engine, so we assert the className contract that
  // PRODUCES the layout (column flex parent; agent flexes; wave non-shrinking)
  // rather than pixel positions. The TRUE visual proof — the "Wave / Subagent
  // Tree" heading bottom ≤ 950 at 1440×950 WITHOUT scroll — runs in the
  // dedicated live Playwright pass after this phase (CONTEXT deferred item).
  it("flex-budgets the left execution column so the wave panel clears the fold", () => {
    renderLayout([RUNNING_WAVE]);

    // Anchor 1: the agent-panel wrapper — the AgentProgressPanel stub's parent.
    const agentWrapper = screen.getByTestId("stub-agent-progress").parentElement!;
    expect(agentWrapper.className).toContain("flex-1");
    expect(agentWrapper.className).toContain("min-h-0");

    // Anchor 2: the wave-panel wrapper — the nearest ancestor of the wave
    // heading that carries the flex-shrink-0 budget class.
    const waveWrapper = screen
      .getByText("Wave / Subagent Tree")
      .closest("div.flex-shrink-0");
    expect(waveWrapper).not.toBeNull();
    expect(waveWrapper!.className).toContain("max-h-[40%]");

    // Anchor 3: the column wrapper — the common flex-col parent that owns
    // height. Walk up from the agent wrapper (ErrorBoundary → column div).
    const column = agentWrapper.closest("div.flex.flex-col");
    expect(column).not.toBeNull();
    // The column itself must NOT scroll — scroll lives inside the two regions.
    expect(column!.className).not.toContain("overflow-y-auto");
    expect(column!.className).toContain("overflow-hidden");
  });
});
