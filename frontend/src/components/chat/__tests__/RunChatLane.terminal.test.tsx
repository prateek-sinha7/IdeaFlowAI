import { readFileSync } from "node:fs";
import { join } from "node:path";

import { renderWithProviders, screen, fireEvent } from "@/test/renderWithProviders";
import { describe, expect, it, vi } from "vitest";

import type { AgentRunState, ChatMessage, PipelineRunState } from "@/types/index";
import { RunChatLane, type RunChatLaneProps } from "../RunChatLane";

// ─── RunChatLane terminal states (SC-4, LIVE-STATE-CONTRACT §1) ───────────────
// The lane renders the faithful terminal cards — cancelled / failed / degraded —
// off the GENERIC RunLaneState terminal + the plan-05 pipelineState markers
// (cancelled / failed / degraded). Never a workflow-name literal (SC-001). The
// "What went wrong" / degraded cards surface only the SANITIZED error +
// agents_failed[] names, never a raw stack (T-32-06-01).

function userMsg(id: string, content: string): ChatMessage {
  return {
    id,
    chatSessionId: "s1",
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

function agent(id: string, name: string, over: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id,
    name,
    role: "",
    icon: "",
    status: "done",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...over,
  };
}

function pipeline(over: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...over,
  };
}

function baseProps(overrides: Partial<RunChatLaneProps> = {}): RunChatLaneProps {
  return {
    messages: [userMsg("u1", "hello")],
    runState: "terminal",
    sendMessage: vi.fn(),
    ...overrides,
  };
}

describe("RunChatLane — terminal states", () => {
  it("cancelled: renders 'Cancelled by you' ack + a 'Run again' relaunch", () => {
    const onRelaunch = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          pipelineState: pipeline({ cancelled: true }),
          onRelaunch,
        })}
      />,
    );
    expect(screen.getByTestId("chat-terminal-cancelled")).toBeInTheDocument();
    expect(screen.getByText(/Cancelled by you/i)).toBeInTheDocument();
    const relaunch = screen.getByTestId("chat-relaunch");
    expect(relaunch).toHaveTextContent(/Run Again/i);
    fireEvent.click(relaunch);
    expect(onRelaunch).toHaveBeenCalledTimes(1);
  });

  it("failed: renders a 'What went wrong' card naming failed agents + sanitized error + relaunch", () => {
    const onRelaunch = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          pipelineState: pipeline({
            failed: true,
            failedAgents: ["build"],
            agents: [
              agent("build", "Build Agent", {
                status: "error",
                error: "Model timed out\n  at run (engine.py:42)\n  at loop (engine.py:9)",
              }),
            ],
          }),
          onRelaunch,
        })}
      />,
    );
    expect(screen.getByTestId("chat-terminal-failed")).toBeInTheDocument();
    expect(screen.getByText(/What went wrong/i)).toBeInTheDocument();
    // Human agent NAME, not the raw id.
    expect(screen.getByText(/Build Agent/)).toBeInTheDocument();
    // Sanitized first line only — the raw stack frames must NOT be surfaced.
    expect(screen.getByText(/Model timed out/)).toBeInTheDocument();
    expect(screen.queryByText(/engine\.py:42/)).toBeNull();
    // Resume options (Phase 39 mock): primary = "Reopen & fix from the failed
    // step", secondary = "Edit brief & run again". Both relaunch.
    const relaunch = screen.getByTestId("chat-relaunch");
    expect(relaunch).toHaveTextContent(/Reopen & fix from the failed step/i);
    expect(screen.getByTestId("chat-relaunch-secondary")).toHaveTextContent(
      /Edit brief & run again/i,
    );
    fireEvent.click(relaunch);
    expect(onRelaunch).toHaveBeenCalledTimes(1);
  });

  it("degraded: renders a 'completed with issues' card naming the failed agents", () => {
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          pipelineState: pipeline({
            degraded: true,
            degradedFailedAgents: ["style"],
            agents: [agent("style", "Style Agent", { status: "error" })],
          }),
        })}
      />,
    );
    expect(screen.getByTestId("chat-terminal-degraded")).toBeInTheDocument();
    expect(screen.getByText(/completed with issues/i)).toBeInTheDocument();
    expect(screen.getByText(/Style Agent/)).toBeInTheDocument();
  });

  it("plain terminal (no marker): falls back to a generic relaunch", () => {
    renderWithProviders(<RunChatLane {...baseProps({ pipelineState: pipeline() })} />);
    expect(screen.getByTestId("chat-relaunch")).toBeInTheDocument();
    expect(screen.queryByTestId("chat-terminal-cancelled")).toBeNull();
    expect(screen.queryByTestId("chat-terminal-failed")).toBeNull();
  });

  // ISS-221 / ISS-233 (BUG-20260828-020430-runs-diverted): relaunchError is
  // computed by handleResumeRun and passed down as this prop; the
  // plain-terminal and degraded branches call the shared relaunch() helper,
  // which now renders it via the banner moved into that helper (FIX-329).
  it(
    "ISS-221: plain terminal (no marker, e.g. a diverted run) renders relaunchError",
    () => {
      renderWithProviders(
        <RunChatLane
          {...baseProps({
            pipelineState: pipeline(),
            relaunchError: "Could not resume the run — please try again.",
          })}
        />,
      );
      expect(
        screen.getByText(/Could not resume the run/i),
      ).toBeInTheDocument();
    },
  );

  it(
    "ISS-233: degraded branch's 'Run again' renders relaunchError",
    () => {
      renderWithProviders(
        <RunChatLane
          {...baseProps({
            pipelineState: pipeline({
              degraded: true,
              degradedFailedAgents: ["style"],
              agents: [agent("style", "Style Agent", { status: "error" })],
            }),
            relaunchError: "Could not resume the run — please try again.",
          })}
        />,
      );
      expect(
        screen.getByText(/Could not resume the run/i),
      ).toBeInTheDocument();
    },
  );

  it("SC-001: the terminal render path carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/RunChatLane.tsx"),
      "utf8",
    );
    expect(/"prototype"|od_ppt|app_builder|user_stories/.test(src)).toBe(false);
  });
});
