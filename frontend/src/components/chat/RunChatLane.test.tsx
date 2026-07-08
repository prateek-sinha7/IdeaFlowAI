import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import type { ClarifyQuestion } from "../preview/QuestionnairePanel";
import { RunChatLane, type RunChatLaneProps } from "./RunChatLane";

// ─── RunChatLane — the run-screen composition root ────────────────────────────
// Transcript (aria-live/role=log) + narrator cards + agent blocks + a UNIFIED
// composer that switches mode per the GENERIC runState (D-12) and absorbs the
// AgentProgressPanel controls (Stop / revise / suggestions-as-chips). SC-001:
// the composer keys off runState, never a workflow name.

function userMsg(id: string, content: string): ChatMessage {
  return {
    id,
    chatSessionId: "s1",
    role: "user",
    content,
    createdAt: new Date().toISOString(),
  };
}

function assistantMsg(id: string, content: string): ChatMessage {
  return {
    id,
    chatSessionId: "s1",
    role: "assistant",
    content,
    createdAt: new Date().toISOString(),
  };
}

function baseProps(overrides: Partial<RunChatLaneProps> = {}): RunChatLaneProps {
  return {
    messages: [userMsg("u1", "hello")],
    runState: "idle",
    sendMessage: vi.fn(),
    ...overrides,
  };
}

describe("RunChatLane", () => {
  it("renders the transcript as an ARIA log region (role=log + aria-live)", () => {
    render(<RunChatLane {...baseProps()} />);
    const transcript = screen.getByTestId("chat-transcript");
    expect(transcript).toHaveAttribute("role", "log");
    expect(transcript).toHaveAttribute("aria-live", "polite");
  });

  it("renders a narrator turn as a ResultCard (deep-linkable)", () => {
    const onRequestOpenTab = vi.fn();
    const narrator: ChatMessage = {
      ...assistantMsg("n1", "Your deliverable is ready."),
      cardKind: "deliverable",
    };
    render(
      <RunChatLane
        {...baseProps({ messages: [narrator], onRequestOpenTab })}
      />,
    );
    expect(screen.getByTestId("chat-result-card")).toHaveAttribute(
      "data-card-kind",
      "deliverable",
    );
    fireEvent.click(screen.getByTestId("chat-result-card-link"));
    expect(onRequestOpenTab).toHaveBeenCalledWith("preview");
  });

  it("streaming turn shows the live cursor + markdown body", () => {
    const { container } = render(
      <RunChatLane
        {...baseProps({
          messages: [userMsg("u1", "hi"), assistantMsg("a1", "streaming…")],
          isStreaming: true,
          streamingContent: "partial answer",
        })}
      />,
    );
    expect(container.querySelector(".streaming-cursor")).not.toBeNull();
    expect(screen.getByText("partial answer")).toBeInTheDocument();
  });

  it("assistant turn renders the plan-01 agent block strip (tool card)", () => {
    render(
      <RunChatLane
        {...baseProps({
          messages: [assistantMsg("a1", "done")],
          eventsByMessageId: {
            a1: [
              { kind: "tool_use", id: "t1", name: "Bash" },
              { kind: "tool_result", id: "t1", result: "ok" },
            ],
          },
        })}
      />,
    );
    const tool = screen.getByTestId("chat-tool-card");
    expect(tool).toHaveAttribute("data-tool-name", "Bash");
    expect(tool).toHaveAttribute("data-tool-status", "success");
  });

  it("clarify mode mounts InlineClarifyActions", () => {
    const q: ClarifyQuestion = {
      id: "q1",
      question: "Which layout?",
      options: ["Grid", "List"],
      answerType: "single_choice",
    };
    render(
      <RunChatLane
        {...baseProps({
          runState: "clarify",
          clarifyQuestions: [q],
          onSubmitAnswers: vi.fn(),
        })}
      />,
    );
    expect(screen.getByTestId("chat-clarify-actions")).toBeInTheDocument();
    expect(screen.getByTestId("chat-composer")).toHaveAttribute(
      "data-composer-mode",
      "clarify",
    );
  });

  it("gate mode mounts InlineGateActions", () => {
    render(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          gate: {
            agentId: "a1",
            agentName: "Reviewer",
            output: "some output",
            gateKey: "g1",
          },
          onApprove: vi.fn(),
          onReject: vi.fn(),
        })}
      />,
    );
    expect(screen.getByTestId("chat-gate-actions")).toBeInTheDocument();
    expect(screen.getByTestId("chat-gate-approve")).toBeInTheDocument();
  });

  it("complete mode shows the revision affordance + suggestion chips", () => {
    const onSuggestion = vi.fn();
    render(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [{ id: "ppt", label: "Build a deck" }],
          onSuggestion,
        })}
      />,
    );
    expect(screen.getByTestId("chat-send")).toBeInTheDocument();
    const chip = screen.getByTestId("chat-suggestion-chip");
    fireEvent.click(chip);
    expect(onSuggestion).toHaveBeenCalledWith("ppt");
  });

  it("Stop is visible while running and fires its callback", () => {
    const onStop = vi.fn();
    render(
      <RunChatLane {...baseProps({ runState: "building", onStop })} />,
    );
    fireEvent.click(screen.getByTestId("chat-stop"));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("Stop hides on a terminal run", () => {
    render(
      <RunChatLane {...baseProps({ runState: "terminal", onStop: vi.fn() })} />,
    );
    expect(screen.queryByTestId("chat-stop")).toBeNull();
    expect(screen.getByTestId("chat-relaunch")).toBeInTheDocument();
  });

  it("a free-text send routes through sendMessage (transport-agnostic)", () => {
    const sendMessage = vi.fn();
    render(
      <RunChatLane {...baseProps({ runState: "building", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "keep going" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("keep going", []);
  });

  it("complete-mode free text routes through onRevise (revision turn)", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    render(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(onRevise).toHaveBeenCalledWith("make it shorter");
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("renders a confirm/reject chip pair for a held consequential proposal (D-05)", () => {
    const onConfirmProposal = vi.fn();
    const onRejectProposal = vi.fn();
    const proposal = {
      id: "concierge-proposal:m1:gate_action",
      channel: "gate_action",
      params: { action: "approve", rationale: "looks good" },
      summary: "Approve the current gate",
    };
    render(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          proposals: [proposal],
          onConfirmProposal,
          onRejectProposal,
        })}
      />,
    );
    // Confirm executes only through the confirm chip (T-33-04-01).
    fireEvent.click(screen.getByTestId("chat-proposal-confirm"));
    expect(onConfirmProposal).toHaveBeenCalledWith(proposal);
    // Reject dismisses — nothing executes.
    fireEvent.click(screen.getByTestId("chat-proposal-reject"));
    expect(onRejectProposal).toHaveBeenCalledWith(proposal.id);
    // Proposal summary is rendered as escaped text (no dangerouslySetInnerHTML).
    expect(screen.getByText("Approve the current gate")).toBeInTheDocument();
  });

  it("shows no proposal chips when there are no held proposals", () => {
    render(<RunChatLane {...baseProps({ runState: "gate" })} />);
    expect(screen.queryByTestId("chat-proposal-confirm")).toBeNull();
    expect(screen.queryByTestId("chat-proposals")).toBeNull();
  });

  it("surfaces the compact affordance when composed-context usage is high (D-08)", () => {
    const onCompact = vi.fn();
    render(
      <RunChatLane
        {...baseProps({
          runState: "building",
          onCompact,
          pipelineState: {
            isRunning: true,
            pipeline_type: "generic",
            agents: [],
            currentAgentIndex: 0,
            totalDuration: null,
            completedCount: 0,
            totalTokens: 5_000,
            totalInputTokens: 5_000,
            composedContextTokens: 92_000,
            contextBudgetTokens: 100_000,
          },
        })}
      />,
    );
    fireEvent.click(screen.getByTestId("chat-compact"));
    expect(onCompact).toHaveBeenCalledTimes(1);
  });

  it("hides the compact affordance when usage is low or absent", () => {
    render(
      <RunChatLane
        {...baseProps({
          runState: "building",
          onCompact: vi.fn(),
          pipelineState: {
            isRunning: true,
            pipeline_type: "generic",
            agents: [],
            currentAgentIndex: 0,
            totalDuration: null,
            completedCount: 0,
            totalTokens: 5_000,
            totalInputTokens: 5_000,
          },
        })}
      />,
    );
    expect(screen.queryByTestId("chat-compact")).toBeNull();
  });

  it("compactAvailable prop surfaces the affordance even without usage telemetry", () => {
    const onCompact = vi.fn();
    render(
      <RunChatLane
        {...baseProps({ runState: "complete", compactAvailable: true, onCompact })}
      />,
    );
    expect(screen.getByTestId("chat-compact")).toBeInTheDocument();
  });

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/RunChatLane.tsx"),
      "utf8",
    );
    expect(/"prototype"|od_ppt|app_builder|user_stories/.test(src)).toBe(false);
  });
});
