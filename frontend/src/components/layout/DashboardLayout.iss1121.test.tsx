/**
 * ISS-1121 (QA-KB-102) — a resume that fails WITHOUT a pipeline_start must not leave the lane on
 * "Restarting run…". `runRestarting` is cleared only when `isPipelineRunning` turns true
 * (DashboardLayout.tsx:1148) or the POST errors (:2589); a new terminal frame never clears it.
 */
import { describe, expect, it, vi, afterEach } from "vitest";
import { renderWithProviders } from "@/test/renderWithProviders";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
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
    postResume: vi.fn(() => Promise.resolve({ run_id: "run-1" })),
  };
});
vi.mock("motion/react", () => ({
  motion: new Proxy({}, { get: (_t, prop: string) => ({ children }: { children?: React.ReactNode }) => React.createElement(prop, null, children) }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
// Lane stub: exposes exactly the two props under test.
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: (p: { onRelaunch?: () => void; runRestarting?: boolean }) => (
    <div>
      <button data-testid="relaunch" onClick={p.onRelaunch} />
      {p.runRestarting ? <span data-testid="restarting">Restarting run…</span> : null}
    </div>
  ),
}));
vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <div /> }));
vi.mock("@/components/preview/PreviewPanel", () => ({ PreviewPanel: () => <div /> }));
vi.mock("@/components/workflow/AgentProgressPanel", () => ({ AgentProgressPanel: () => <div /> }));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => <div /> }));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const failed = (): PipelineRunState => ({
  isRunning: false,
  pipelineRunId: "run-1",
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  failed: true,
} as unknown as PipelineRunState);

function props(): DashboardLayoutProps {
  return {
    activeChatId: null, messages: [], isStreaming: false, streamingContent: "",
    userStoryContent: "", pptContent: "", prototypeContent: "", connectionStatus: "connected",
    onSendMessage: vi.fn(), onSelectChat: vi.fn(), onNewChat: vi.fn(), onDeleteChat: vi.fn(),
    onLogout: vi.fn(), onReconnect: vi.fn(), pipelineState: failed(), initialMainView: "execution",
  } as DashboardLayoutProps;
}
const tree = () => (
  <SkillsHooksProvider>
    <DashboardLayout {...props()} />
  </SkillsHooksProvider>
);

afterEach(cleanup);

describe("DashboardLayout — resume that never starts (ISS-1121)", () => {
  it("clears 'Restarting run…' when a new terminal frame arrives with no pipeline_start", async () => {
    const { rerender } = renderWithProviders(tree());
    fireEvent.click(screen.getByTestId("relaunch"));
    await waitFor(() => expect(screen.getByTestId("restarting")).toBeTruthy());
    // The backend (after the ISS-1103 fix) delivers a fresh pipeline_failed; no pipeline_start.
    rerender(tree());
    await waitFor(() => expect(screen.queryByTestId("restarting")).toBeNull(), { timeout: 1500 });
  });
});
