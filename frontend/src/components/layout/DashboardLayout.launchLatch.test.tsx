/**
 * BUG-007 — one UI launch must mint exactly ONE run.
 *
 * The od_prototype launch-consumer effect (DashboardLayout.tsx:636) and its
 * od_ppt twin (:685) guard only on `if (!pendingOdProtoParams) return;` and
 * clear the param ASYNCHRONOUSLY (onClearPendingOdProto). Under React
 * StrictMode's dev-only double mount-effect invoke both synchronous invocations
 * pass the guard before the async clear nulls the param → the pipeline is
 * started twice for one launch. A synchronous `useRef` object-identity latch
 * makes the same param object mint once while a NEW launch (new object) still
 * mints.
 *
 * We mount under <React.StrictMode> so the harness reproduces the real dev
 * double-invoke, and assert onStartPipeline fires exactly once per param object.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, rerenderWithProviders } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import React from "react";
import type { PipelineRunState } from "@/types/index";

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

// Heavy children stubbed to inert markers — we only care about the launch effect.
vi.mock("@/components/chat/RunChatLane", () => ({ RunChatLane: () => <div /> }));
vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
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

function renderStrict(props: DashboardLayoutProps) {
  return renderWithProviders(
    <React.StrictMode>
      <SkillsHooksProvider>
        <DashboardLayout {...props} />
      </SkillsHooksProvider>
    </React.StrictMode>,
  );
}

beforeEach(() => {
  cleanup();
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout — launch consumers mint once per param object (BUG-007)", () => {
  it("one od_prototype param object mints exactly once under a StrictMode double mount-invoke", () => {
    const spy = vi.fn();
    const paramsA = { brief: "test brief A", templateId: "t1", designSystemId: "ds1", discovery: undefined };
    renderStrict(baseProps({
      pendingOdProtoParams: paramsA,
      onClearPendingOdProto: vi.fn(),
      onStartPipeline: spy,
    }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toBe("prototype");
  });

  it("a genuinely new od_prototype param object still mints (latch keys on identity, not a permanent block)", () => {
    const spy = vi.fn();
    const paramsA = { brief: "test brief A", templateId: "t1", designSystemId: "ds1", discovery: undefined };
    const props = baseProps({
      pendingOdProtoParams: paramsA,
      onClearPendingOdProto: vi.fn(),
      onStartPipeline: spy,
    });
    const { rerender } = renderStrict(props);
    expect(spy).toHaveBeenCalledTimes(1);

    const paramsB = { brief: "test brief B", templateId: "t2", designSystemId: "ds2", discovery: undefined };
    rerenderWithProviders(
      <React.StrictMode>
        <SkillsHooksProvider>
          <DashboardLayout {...baseProps({
            pendingOdProtoParams: paramsB,
            onClearPendingOdProto: vi.fn(),
            onStartPipeline: spy,
          })} />
        </SkillsHooksProvider>
      </React.StrictMode>,
    );
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls[1][0]).toBe("prototype");
    expect(spy.mock.calls[1][1]).toBe("test brief B");
  });

  it("the od_ppt twin also mints exactly once under a StrictMode double mount-invoke", () => {
    const spy = vi.fn();
    const paramsPpt = { brief: "ppt brief", templateId: "pt1", designSystemId: "pds1", discovery: undefined };
    renderStrict(baseProps({
      pendingOdPptParams: paramsPpt,
      onClearPendingOdPpt: vi.fn(),
      onStartPipeline: spy,
    }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][0]).toBe("ppt");
  });
});
