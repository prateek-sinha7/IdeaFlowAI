import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import type { PipelineRunState } from "@/types/index";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

const postRevision = vi.fn(() => Promise.resolve({ run_id: "" }));
vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "test-token",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    postRevision: (...args: unknown[]) => (postRevision as (...a: unknown[]) => unknown)(...args),
  };
});

vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children }: { children?: React.ReactNode }) => {
          return React.createElement(prop, {}, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => children,
}));

let capturedOnRevise: ((instruction: string) => void) | undefined;
type LaneSend = (text: string, attachments?: unknown[], options?: Record<string, unknown>) => void;
let capturedSend: LaneSend | undefined;
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: (props: { onRevise?: (i: string) => void; sendMessage?: LaneSend }) => {
    capturedOnRevise = props.onRevise;
    capturedSend = props.sendMessage;
    return <div />;
  },
}));
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
    initialMainView: "execution",
    pipelineState: idlePipelineState(),
    contentSourceRunId: "run-1",
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  postRevision.mockClear();
  capturedOnRevise = undefined;
  capturedSend = undefined;
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout - onRevise routing (spec 022 8.5 / 11.6)", () => {
  it("prototype_v2 run revises through postRevision, not onStartPipeline", () => {
    const onStartPipeline = vi.fn();
    renderWithProviders(<DashboardLayout {...baseProps({ contentSourceRunType: "prototype_v2", onStartPipeline })} />);
    expect(capturedOnRevise).toBeDefined();
    capturedOnRevise!("x");
    expect(postRevision).toHaveBeenCalledWith("test-token", "run-1", {
      target_artifact_type: "prototype_v2_output",
      instruction: "x",
    });
    expect(onStartPipeline).not.toHaveBeenCalled();
  });

  it("v1 prototype run with content launches prototype_revision, not postRevision", () => {
    const onStartPipeline = vi.fn();
    renderWithProviders(<DashboardLayout {...baseProps({
      contentSourceRunType: "prototype",
      prototypeContent: "<html></html>",
      onStartPipeline,
    })} />);
    expect(capturedOnRevise).toBeDefined();
    capturedOnRevise!("x");
    expect(onStartPipeline).toHaveBeenCalledTimes(1);
    expect(onStartPipeline.mock.calls[0][0]).toBe("prototype_revision");
    expect(postRevision).not.toHaveBeenCalled();
  });

  it("backlog run revises through postRevision with backlog_output", () => {
    const onStartPipeline = vi.fn();
    renderWithProviders(<DashboardLayout {...baseProps({ contentSourceRunType: "backlog", onStartPipeline })} />);
    expect(capturedOnRevise).toBeDefined();
    capturedOnRevise!("x");
    expect(postRevision).toHaveBeenCalledWith("test-token", "run-1", {
      target_artifact_type: "backlog_output",
      instruction: "x",
    });
    expect(onStartPipeline).not.toHaveBeenCalled();
  });
});

describe("DashboardLayout - a chat turn that launches a revision", () => {
  it("a plain chat send carries onRevisionLaunched, so the view follows a revision the Concierge starts", () => {
    const onRunChatSend = vi.fn();
    const onRevisionLaunched = vi.fn();
    renderWithProviders(<DashboardLayout {...baseProps({ contentSourceRunType: "backlog", onRunChatSend, onRevisionLaunched })} />);
    expect(capturedSend).toBeDefined();
    capturedSend!("fix the title", [], { concierge: true });
    expect(onRunChatSend).toHaveBeenCalledWith("fix the title", [], { concierge: true, onRevisionLaunched });
  });

  it("a caller's own onRevisionLaunched is kept", () => {
    const onRunChatSend = vi.fn();
    const own = vi.fn();
    renderWithProviders(<DashboardLayout {...baseProps({ onRunChatSend, onRevisionLaunched: vi.fn() })} />);
    capturedSend!("", [], { concierge: true, onRevisionLaunched: own });
    expect(onRunChatSend.mock.calls[0][2].onRevisionLaunched).toBe(own);
  });
});
