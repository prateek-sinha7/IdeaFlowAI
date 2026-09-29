/**
 * FR-027 / AC-25 — Chain pipeline brief delivery
 *
 * Verifies that `handleChainPipeline` and `handleChainFromHistory` send the bare
 * brief (without context enrichment) to `onStartPipeline`. Context is now delivered
 * via .context/ files by the chain_context provider, not injected as text into the
 * agent message.
 *
 * `handleChainPipeline`'s only reachable entry point is `RunChatLane`'s
 * `onSuggestion` prop (wired via `handleLaneSuggestion`, DashboardLayout.tsx:2547-
 * 2550, :3105-3106) — NOT `HomeLaunchGrid`, which never calls it.
 * `handleChainFromHistory`'s entry point is `WorkflowHistory`'s `onChainPipeline`
 * prop (DashboardLayout.tsx:2817). Both are stubbed here with a button that
 * invokes the real prop so the callbacks under test actually run.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, fireEvent, waitFor, screen } from "@/test/renderWithProviders";
import { cleanup } from "@testing-library/react";
import React from "react";
import type { PipelineRunState, WorkflowRun } from "@/types/index";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

const getChainContextMock = vi.fn(async (_token: string, _workflowId: string) => ({
  brief: "Context brief from source",
  // A distinctive marker string — if handleChainPipeline/handleChainFromHistory
  // ever inject this into the outgoing message again, these tests catch it.
  context_block: "=== CONTEXT FROM PREVIOUS PIPELINE (user_stories) ===\nSHOULD NOT BE SENT\n=== END PREVIOUS CONTEXT ===",
}));

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "test-token",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    // Indirected through a closure (not a direct reference) — vi.mock factories
    // are hoisted above `const getChainContextMock = …` below, so evaluating the
    // identifier here directly would throw a TDZ ReferenceError at import time.
    getChainContext: (token: string, workflowId: string) => getChainContextMock(token, workflowId),
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

// Stub heavy children that are not the seam under test.
vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ PreviewPanel: () => <div /> }));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => <div /> }));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({ HomeLaunchGrid: () => <div /> }));
vi.mock("@/components/home/CreationHub", () => ({ CreationHub: () => <div /> }));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => <div /> }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => <div /> }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => <div /> }));
vi.mock("@/components/workflow/IdeaInputPage", () => ({ IdeaInputPage: () => <div /> }));

// `handleChainPipeline`'s only caller: RunChatLane's `onSuggestion` prop. A
// non-wizard workflow id ("user_stories" has no entry in WIZARD_ROUTES) so the
// callback reaches the `onStartPipeline` branch instead of the wizard redirect.
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: (props: { onSuggestion?: (id: string) => void }) => (
    <button
      data-testid="trigger-chain-pipeline"
      onClick={() => props.onSuggestion?.("user_stories")}
    />
  ),
}));

// `handleChainFromHistory`'s only caller: WorkflowHistory's `onChainPipeline`
// prop. Reads the run to chain from off `recentRuns[0]` so each test controls
// the source run's `input` via render props, not module-level mutable state.
vi.mock("@/components/history/WorkflowHistory", () => ({
  WorkflowHistory: (props: {
    onChainPipeline?: (run: WorkflowRun, nextType: string) => void;
    recentRuns?: WorkflowRun[];
  }) => (
    <button
      data-testid="trigger-chain-from-history"
      onClick={() => {
        const run = props.recentRuns?.[0];
        if (run) props.onChainPipeline?.(run, "user_stories");
      }}
    />
  ),
}));

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";

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

function makeRun(input: string): WorkflowRun {
  return {
    id: "hist-run-1",
    title: "A source run",
    type: "user_stories",
    status: "completed",
    input,
    parentRunId: null,
    rootRunId: "hist-run-1",
    createdAt: "2026-09-01T00:00:00Z",
    agentCount: 1,
  };
}

beforeEach(() => {
  cleanup();
  sessionStorage.clear();
  getChainContextMock.mockClear();
});
afterEach(() => {
  sessionStorage.clear();
});

describe("DashboardLayout — chain pipeline brief delivery (FR-027)", () => {
  // NOTE: `workflowInput` is DashboardLayout-internal state (useState(""), not a
  // prop — see DashboardLayout.tsx:584) and can only be populated by
  // `handleRunPipeline`/the chain handlers themselves, so a fresh render always
  // starts with it empty. handleChainPipeline's `chainBrief` then falls through
  // to `ctxBrief` (the source run's brief fetched via `getChainContext`), which
  // is exactly the branch this test drives and asserts on.
  it("handleChainPipeline sends only the fetched brief, never the context block", async () => {
    const onStartPipelineSpy = vi.fn();

    renderWithProviders(
      <DashboardLayout
        {...baseProps({
          initialMainView: "execution",
          onStartPipeline: onStartPipelineSpy,
          connectionStatus: "connected",
          recentRuns: [],
          contentSourceRunId: "run-source-123",
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("trigger-chain-pipeline"));

    await waitFor(() => expect(onStartPipelineSpy).toHaveBeenCalled());

    expect(getChainContextMock).toHaveBeenCalledWith("test-token", "run-source-123");
    const [type, message] = onStartPipelineSpy.mock.calls[0];
    expect(type).toBe("user_stories");
    expect(message).toBe("Context brief from source");
    expect(message).not.toContain("SHOULD NOT BE SENT");
    expect(message).not.toContain("=== CONTEXT FROM PREVIOUS PIPELINE");
  });

  it("handleChainFromHistory sends the bare brief extracted from the source run's input", async () => {
    const onStartPipelineSpy = vi.fn();

    renderWithProviders(
      <DashboardLayout
        {...baseProps({
          initialMainView: "history",
          onStartPipeline: onStartPipelineSpy,
          connectionStatus: "connected",
          recentRuns: [makeRun("A tiny to-do list app")],
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("trigger-chain-from-history"));

    await waitFor(() => expect(onStartPipelineSpy).toHaveBeenCalled());

    expect(getChainContextMock).toHaveBeenCalledWith("test-token", "hist-run-1");
    const [type, message] = onStartPipelineSpy.mock.calls[0];
    expect(type).toBe("user_stories");
    expect(message).toBe("A tiny to-do list app");
    expect(message).not.toContain("SHOULD NOT BE SENT");
  });

  it("handleChainFromHistory strips a revision-request marker, sending only the instruction", async () => {
    const onStartPipelineSpy = vi.fn();
    const revisedInput =
      "Original brief\n\n=== REVISION REQUEST ===\nMake it more responsive\n=== END REQUEST ===";

    renderWithProviders(
      <DashboardLayout
        {...baseProps({
          initialMainView: "history",
          onStartPipeline: onStartPipelineSpy,
          connectionStatus: "connected",
          recentRuns: [makeRun(revisedInput)],
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("trigger-chain-from-history"));

    await waitFor(() => expect(onStartPipelineSpy).toHaveBeenCalled());

    const [, message] = onStartPipelineSpy.mock.calls[0];
    expect(message).toBe("Make it more responsive");
    expect(message).not.toContain("Original brief");
    expect(message).not.toContain("REVISION REQUEST");
    expect(message).not.toContain("SHOULD NOT BE SENT");
  });
});
