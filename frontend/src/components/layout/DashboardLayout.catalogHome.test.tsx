/**
 * Phase 22 / 22-07 (UXFIX-03 / D-20) — catalog-as-home.
 *
 * Proves the data-driven `HomeLaunchGrid` (GET /api/workflows) is the DEFAULT
 * home landing in DashboardLayout — NOT the hardcoded `CreationHub.WORKFLOWS`
 * array. The default `mainView` is "home" (no run staged); this test asserts
 * that the "home" view mounts HomeLaunchGrid and does NOT mount CreationHub,
 * so the hardcoded workflow-name list no longer drives the default landing
 * (SC-001: no hardcoded name list on the default view).
 *
 * Heavy children are stubbed to data-testid markers — the assertion target is
 * WHICH surface mounts as the default landing, not the surface internals.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// next/navigation — DashboardLayout calls useRouter() at the top of the body.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

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

// Stub the two competing landing surfaces with distinct markers + the rest of
// the heavy children so the default landing renders in isolation.
vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: () => <div data-testid="stub-app-header" />,
}));
vi.mock("@/components/home/CreationHub", () => ({
  CreationHub: () => <div data-testid="stub-creation-hub" />,
}));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({
  HomeLaunchGrid: () => <div data-testid="stub-workflow-catalog" />,
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
vi.mock("@/components/ui/CompletionToast", () => ({
  CompletionToast: () => <div data-testid="stub-toast" />,
}));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { PipelineRunState } from "@/types/index";

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

function renderLayout() {
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
    // idle (no run, nothing staged) → the DEFAULT landing renders.
    pipelineState: idlePipelineState(),
  };
  return render(
    <SkillsHooksProvider>
      <DashboardLayout {...props} />
    </SkillsHooksProvider>,
  );
}

describe("DashboardLayout — catalog-as-home (22-07 UXFIX-03 / D-20)", () => {
  it("renders the data-driven HomeLaunchGrid as the DEFAULT home landing", () => {
    renderLayout();
    expect(screen.getByTestId("stub-workflow-catalog")).toBeInTheDocument();
  });

  it("does NOT mount CreationHub (the hardcoded WORKFLOWS array) as the default landing", () => {
    renderLayout();
    expect(screen.queryByTestId("stub-creation-hub")).not.toBeInTheDocument();
  });
});
