import { readFileSync } from "node:fs";
import { join } from "node:path";

import { act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithProviders, rerenderWithProviders, screen, fireEvent } from "@/test/renderWithProviders";

import type { ChatMessage } from "@/types/index";
import type { ClarifyQuestion } from "@/types/index";
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
    renderWithProviders(<RunChatLane {...baseProps()} />);
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
    renderWithProviders(
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
    const { container } = renderWithProviders(
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
    renderWithProviders(
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

  it("clarify mode: lane composer is a plain phase-hint input (NOT a duplicate answer form) — Steps is the sole answer surface (Group C)", () => {
    const q: ClarifyQuestion = {
      id: "q1",
      question: "Which layout?",
      options: ["Grid", "List"],
      answerType: "single_choice",
    };
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "clarify",
          clarifyQuestions: [q],
          onSubmitAnswers: vi.fn(),
          sendMessage,
        })}
      />,
    );
    // The full inline answer form is gone from the LANE composer (it now lives
    // only in Steps).
    expect(screen.queryByTestId("chat-clarify-actions")).toBeNull();
    // The composer is the plain hint input with the clarify phase cue.
    expect(screen.getByTestId("chat-composer")).toHaveAttribute(
      "data-composer-mode",
      "clarify",
    );
    const input = screen.getByLabelText("Chat message input");
    expect(input).toHaveAttribute(
      "placeholder",
      "Answer the questions above to continue…",
    );
    // A free-text turn routes through Concierge (FIX-210 routing).
    fireEvent.change(input, { target: { value: "one more thing" } });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("one more thing", [], { concierge: true });
  });

  it("gate mode: lane composer is a plain phase-hint input (NOT a duplicate approval form) — Steps is the sole answer surface (Group C)", () => {
    const sendMessage = vi.fn();
    renderWithProviders(
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
          sendMessage,
        })}
      />,
    );
    // The full inline gate/approve form is gone from the LANE composer.
    expect(screen.queryByTestId("chat-gate-actions")).toBeNull();
    expect(screen.queryByTestId("chat-gate-approve")).toBeNull();
    // The composer is the plain hint input with the gate phase cue.
    expect(screen.getByTestId("chat-composer")).toHaveAttribute(
      "data-composer-mode",
      "gate",
    );
    const input = screen.getByLabelText("Chat message input");
    expect(input).toHaveAttribute(
      "placeholder",
      "Approve the plan above, or add a note…",
    );
    fireEvent.change(input, { target: { value: "add a note" } });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("add a note", []);
  });

  it("complete mode renders the chain-suggestion chips above the input and clicks through to onSuggestion (c72)", () => {
    const onSuggestion = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [{ id: "ppt", label: "Build a deck" }],
          onSuggestion,
        })}
      />,
    );
    // The settled composer is still the "Ask for a change…" input …
    expect(screen.getByTestId("chat-send")).toBeInTheDocument();
    // … and the chain-suggestion chips are restored above it (c72, user-requested).
    const chips = screen.getAllByTestId("chat-chain-suggestion-chip");
    expect(chips).toHaveLength(1);
    expect(screen.getByTestId("chat-chain-suggestions")).toHaveTextContent(
      "Build a deck",
    );
    fireEvent.click(chips[0]);
    expect(onSuggestion).toHaveBeenCalledWith("ppt");
  });

  it("chain chips are ABSENT when suggestions are empty/undefined, and on a non-complete run (c72)", () => {
    // No suggestions supplied on a completed run → no chip row.
    const { rerender } = renderWithProviders(
      <RunChatLane {...baseProps({ runState: "complete", onSuggestion: vi.fn() })} />,
    );
    expect(screen.queryByTestId("chat-chain-suggestions")).toBeNull();
    expect(screen.queryByTestId("chat-chain-suggestion-chip")).toBeNull();

    // Suggestions supplied but the run is NOT complete (building) → still no chips.
    rerenderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "building",
          suggestions: [{ id: "ppt", label: "Build a deck" }],
          onSuggestion: vi.fn(),
        })}
      />,
    );
    expect(screen.queryByTestId("chat-chain-suggestions")).toBeNull();
    expect(screen.queryByTestId("chat-chain-suggestion-chip")).toBeNull();
  });

  it("the chat textarea auto-grows to the capped max then resets on send (c72)", () => {
    // jsdom reports scrollHeight as 0 — stub it above the cap so autoGrow clamps to 132px.
    const proto = HTMLTextAreaElement.prototype;
    const original = Object.getOwnPropertyDescriptor(proto, "scrollHeight");
    let stubHeight = 300;
    Object.defineProperty(proto, "scrollHeight", {
      configurable: true,
      get() {
        return stubHeight;
      },
    });
    try {
      const sendMessage = vi.fn();
      renderWithProviders(
        <RunChatLane {...baseProps({ runState: "building", sendMessage })} />,
      );
      const textarea = screen.getByLabelText(
        "Chat message input",
      ) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: "line one\nline two\nline three" } });
      // Clamped to the cap (min(scrollHeight=300, 132)).
      expect(textarea.style.height).toBe("132px");
      // After sending, restore normal scrollHeight behavior so empty textarea has normal height
      stubHeight = 0;
      fireEvent.click(screen.getByTestId("chat-send"));
      // The box is reset after send; autoGrow sets it based on the now-empty textarea.
      // With scrollHeight=0 (empty), the height will be set by autoGrow.
      expect(textarea.style.height).not.toBe("132px");
    } finally {
      if (original) Object.defineProperty(proto, "scrollHeight", original);
      else delete (proto as unknown as Record<string, unknown>).scrollHeight;
    }
  });

  it("a settled-run ASK with chain suggestions folds chain_hints onto the concierge send (c72)", () => {
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [{ id: "ppt", label: "Build a deck" }],
          onSuggestion: vi.fn(),
          sendMessage,
        })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("what's the status?", [], {
      concierge: true,
      chain_hints: [{ id: "ppt", label: "Build a deck" }],
    });
  });

  it("Stop is visible while running and fires its callback", () => {
    const onStop = vi.fn();
    renderWithProviders(
      <RunChatLane {...baseProps({ runState: "building", onStop })} />,
    );
    fireEvent.click(screen.getByTestId("chat-stop"));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("Stop hides on a terminal run", () => {
    renderWithProviders(
      <RunChatLane {...baseProps({ runState: "terminal", onStop: vi.fn() })} />,
    );
    expect(screen.queryByTestId("chat-stop")).toBeNull();
    expect(screen.getByTestId("chat-relaunch")).toBeInTheDocument();
  });

  it("a free-text send routes through sendMessage (transport-agnostic)", () => {
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane {...baseProps({ runState: "building", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "keep going" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("keep going", [], { concierge: true });
  });

  // ─── 44-02 (W3a) — FIX-210 Concierge classification ──────────────────────
  // On a SETTLED run free text is classified by the backend Concierge (FIX-210).
  // All text routes to Concierge with { concierge: true }; the Concierge decides
  // whether it's an ask or change request. The frontend no longer holds changes
  // behind a refinement chip — that classification is now backend-driven (ISS-054).

  it("settled-run change request routes to Concierge for backend classification (FIX-210)", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // All complete-run free text routes to Concierge with { concierge: true };
    // backend handles ask/change classification.
    expect(sendMessage).toHaveBeenCalledWith("make it shorter", [], expect.objectContaining({ concierge: true }));
    // No frontend refinement chip appears (classification is backend-driven).
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run free text routes to Concierge; backend decides ask vs change (FIX-210)", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // All text routes to Concierge; backend decides if it's a change.
    expect(sendMessage).toHaveBeenCalledWith("make it shorter", [], expect.objectContaining({ concierge: true }));
    // Frontend no longer processes changes—backend decides and sends proposal.
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run text always routes to Concierge (FIX-210); no frontend dismiss needed", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // Text routes to Concierge immediately; no local refinement chip to dismiss.
    expect(sendMessage).toHaveBeenCalledWith("make it shorter", [], expect.objectContaining({ concierge: true }));
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
    expect(screen.queryByTestId("chat-refinement-dismiss")).toBeNull();
  });

  it("settled-run text routes to Concierge regardless of onRevise availability (FIX-210)", () => {
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane {...baseProps({ runState: "complete", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // All complete-run text routes to Concierge; backend handles classification.
    expect(sendMessage).toHaveBeenCalledWith("make it shorter", [], expect.objectContaining({ concierge: true }));
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run text routes to Concierge with chain hints if suggestions available (FIX-210)", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // Text routes to Concierge; backend decides ask/change.
    expect(sendMessage).toHaveBeenCalledWith("what's the status?", [],
      expect.objectContaining({ concierge: true })
    );
    expect(onRevise).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  // ─── FIX-210 — settled-run classification moved to backend Concierge ────────
  // On a SETTLED (complete) run the free-text turn routes to the Concierge with
  // { concierge: true }. Classification (ask/change) is now BACKEND-DRIVEN
  // (ISS-054); the frontend no longer holds changes behind a chip. All text types
  // (questions, imperatives, etc.) route the same way — the Concierge's system
  // prompt handles intent recognition and routing.
  const routeCases: Array<{
    text: string;
    why: string;
  }> = [
    { text: "what's the status?", why: "status question" },
    { text: "is the login page done?", why: "yes/no progress question" },
    { text: "why did the build fail?", why: "explanatory question" },
    { text: "make it dark mode", why: "imperative change" },
    {
      text: "can you make the button bigger?",
      why: "question-shaped but change-intent",
    },
  ];

  for (const c of routeCases) {
    it(`settled route: "${c.text}" → Concierge (${c.why}, FIX-210)`, () => {
      const sendMessage = vi.fn();
      const onRevise = vi.fn();
      renderWithProviders(
        <RunChatLane
          {...baseProps({ runState: "complete", sendMessage, onRevise })}
        />,
      );
      fireEvent.change(screen.getByLabelText("Chat message input"), {
        target: { value: c.text },
      });
      fireEvent.click(screen.getByTestId("chat-send"));

      // All text routes to Concierge; backend classifies intent.
      expect(sendMessage).toHaveBeenCalledWith(c.text, [],
        expect.objectContaining({ concierge: true })
      );
      // No frontend refinement chips (classification is backend-driven).
      expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
      // Backend classifies; frontend doesn't auto-launch onRevise.
      expect(onRevise).not.toHaveBeenCalled();
    });
  }

  // ─── BUG-1 (quick-260720-ec4) — "<transform> into <target>" chains, not revises ─
  // On a SETTLED run a transform phrase whose TAIL names a currently-available
  // chain suggestion fires onSuggestion(id) (the chain seam), BEFORE the ask/change
  // split — so "convert it into presentation" chains into a new workflow instead of
  // misrouting to a *_revision of THIS run. A transform phrase with NO matching (or
  // no) available target keeps the exact existing change→held-refinement path.

  it("settled-run 'convert it into presentation' with a matching chain target fires onSuggestion(ppt) and does NOT revise", () => {
    const onSuggestion = vi.fn();
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [
            { id: "ppt", label: "Presentation" },
            { id: "prototype", label: "Prototype" },
          ],
          onSuggestion,
          onRevise,
          sendMessage,
        })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "convert it into presentation" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(onSuggestion).toHaveBeenCalledTimes(1);
    expect(onSuggestion).toHaveBeenCalledWith("ppt");
    expect(onRevise).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run transform phrase with NO matching target routes to Concierge (FIX-210)", () => {
    const onSuggestion = vi.fn();
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [
            { id: "ppt", label: "Presentation" },
            { id: "prototype", label: "Prototype" },
          ],
          onSuggestion,
          onRevise,
          sendMessage,
        })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "convert the buttons into pills" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(onSuggestion).not.toHaveBeenCalled();
    // No matching chain target; text routes to Concierge for backend classification.
    expect(sendMessage).toHaveBeenCalledWith("convert the buttons into pills", [],
      expect.objectContaining({ concierge: true })
    );
    expect(onRevise).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run chain phrase with no suggestions supplied routes to Concierge (FIX-210)", () => {
    const onSuggestion = vi.fn();
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", onSuggestion, onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "convert it into presentation" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // No suggestions available; text routes to Concierge for backend classification.
    expect(onSuggestion).not.toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledWith("convert it into presentation", [],
      expect.objectContaining({ concierge: true })
    );
    expect(onRevise).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
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
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          proposals: [proposal],
          onConfirmProposal,
          onRejectProposal,
        })}
      />,
    );
    // Proposal summary is rendered as escaped text (no dangerouslySetInnerHTML).
    expect(screen.getByText("Approve the current gate")).toBeInTheDocument();
    // Both confirm and reject buttons are visible initially.
    const confirmBtn = screen.getByTestId("chat-proposal-confirm");
    const rejectBtn = screen.getByTestId("chat-proposal-reject");
    expect(confirmBtn).toBeInTheDocument();
    expect(rejectBtn).toBeInTheDocument();
    // Confirm executes through the confirm chip (T-33-04-01).
    fireEvent.click(confirmBtn);
    expect(onConfirmProposal).toHaveBeenCalledWith(proposal);
  });

  it("proposal reject button dismisses the proposal", () => {
    const onConfirmProposal = vi.fn();
    const onRejectProposal = vi.fn();
    const proposal = {
      id: "concierge-proposal:m1:gate_action",
      channel: "gate_action",
      params: { action: "approve", rationale: "looks good" },
      summary: "Approve the current gate",
    };
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          proposals: [proposal],
          onConfirmProposal,
          onRejectProposal,
        })}
      />,
    );
    // Reject dismisses the proposal.
    fireEvent.click(screen.getByTestId("chat-proposal-reject"));
    expect(onRejectProposal).toHaveBeenCalledWith(proposal.id);
    expect(onConfirmProposal).not.toHaveBeenCalled();
  });

  it("shows no proposal chips when there are no held proposals", () => {
    renderWithProviders(<RunChatLane {...baseProps({ runState: "gate" })} />);
    expect(screen.queryByTestId("chat-proposal-confirm")).toBeNull();
    expect(screen.queryByTestId("chat-proposals")).toBeNull();
  });

  it("surfaces the compact affordance when composed-context usage is high (D-08)", () => {
    const onCompact = vi.fn();
    renderWithProviders(
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
    renderWithProviders(
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
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "complete", compactAvailable: true, onCompact })}
      />,
    );
    expect(screen.getByTestId("chat-compact")).toBeInTheDocument();
  });

  // ─── Phase 39 (RUNUI-06/08) — structured transcript adornments ──────────────

  const ps = (overrides: Record<string, unknown> = {}) => ({
    isRunning: false,
    pipeline_type: "generic",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  });

  it("run header renders a Running phase pill while building", () => {
    renderWithProviders(<RunChatLane {...baseProps({ runState: "building" })} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Running");
  });

  it("clarify state renders an Awaiting-you status card that deep-links to Steps", () => {
    const onRequestOpenTab = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "clarify",
          clarifyQuestions: [
            { id: "q1", question: "Which?", options: ["a", "b"], answerType: "single_choice" },
          ],
          onRequestOpenTab,
        })}
      />,
    );
    const card = screen.getByTestId("lane-clarify-status");
    expect(card).toHaveTextContent("Awaiting you");
    expect(card).toHaveTextContent("1 question for you");
    fireEvent.click(card);
    expect(onRequestOpenTab).toHaveBeenCalledWith("thinking");
  });

  it("gate state renders an Awaiting-you approval card that deep-links to Steps", () => {
    const onRequestOpenTab = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          gate: { agentId: "a1", agentName: "Rev", output: "o", gateKey: "g1" },
          onApprove: vi.fn(),
          onReject: vi.fn(),
          onRequestOpenTab,
        })}
      />,
    );
    const card = screen.getByTestId("lane-gate-status");
    expect(card).toHaveTextContent("needs approval");
    fireEvent.click(card);
    expect(onRequestOpenTab).toHaveBeenCalledWith("thinking");
  });

  it("building state renders the live pipeline mini (k/N from pipelineState)", () => {
    const onRequestOpenTab = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "building",
          onRequestOpenTab,
          pipelineState: ps({
            isRunning: true,
            completedCount: 3,
            agents: [1, 2, 3, 4, 5].map((n) => ({
              id: `a${n}`,
              name: `Agent ${n}`,
              role: "",
              icon: "",
              status: n <= 3 ? "done" : n === 4 ? "running" : "idle",
              output: "",
              thinking: "",
              duration: null,
              error: null,
              index: n,
            })),
          }),
        }) as RunChatLaneProps}
      />,
    );
    // Pipeline mini is rendered as a collapsible with toggle button header.
    // The toggle button shows the header text and progress counter.
    const toggle = screen.getByTestId("lane-pipeline-mini-toggle");
    expect(toggle).toHaveTextContent("Pipeline · 5 agents");
    expect(toggle).toHaveTextContent("3 / 5");
    // The toggle button controls expand/collapse; onRequestOpenTab is available
    // through other interactions (e.g., on the Steps row if there are clarify questions).
  });

  it("settled state renders the pipeline mini from live agents", () => {
    renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "complete",
          onRequestOpenTab: vi.fn(),
          pipelineState: ps({
            completedCount: 2,
            agents: [1, 2].map((n) => ({
              id: `a${n}`,
              name: `Agent ${n}`,
              role: "",
              icon: "",
              status: "done",
              output: "",
              thinking: "",
              duration: 12,
              error: null,
              index: n,
            })),
          }),
        }) as RunChatLaneProps)}
      />,
    );
    // BUG-018 Part B: the settled footer is collapsed by default — expand first.
    fireEvent.click(screen.getByTestId("lane-adornments-toggle"));
    expect(screen.getByTestId("lane-pipeline-mini")).toHaveTextContent(
      "Pipeline · 2 agents",
    );
  });

  it("failed terminal renders What-went-wrong (live error + agents) + Resume options", () => {
    const onRelaunch = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "terminal",
          onRelaunch,
          pipelineState: ps({
            failed: true,
            failedAgents: ["a1"],
            agents: [
              {
                id: "a1",
                name: "Build Agent",
                role: "",
                icon: "",
                status: "error",
                output: "",
                thinking: "",
                duration: null,
                error: "Blocked by the security gate\nstack frame hidden",
                index: 1,
              },
            ],
          }),
        }) as RunChatLaneProps)}
      />,
    );
    const card = screen.getByTestId("chat-terminal-failed");
    expect(card).toHaveTextContent("What went wrong");
    expect(card).toHaveTextContent("Build Agent");
    expect(card).toHaveTextContent("Resume options");
    // Sanitized to the first line only — no stack frame leaks (T-39-01-01).
    const err = screen.getByTestId("chat-terminal-error");
    expect(err).toHaveTextContent("Blocked by the security gate");
    expect(err).not.toHaveTextContent("stack frame hidden");
    // The header reads Failed.
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Failed");
    // Both resume actions relaunch.
    fireEvent.click(screen.getByTestId("chat-relaunch"));
    fireEvent.click(screen.getByTestId("chat-relaunch-secondary"));
    expect(onRelaunch).toHaveBeenCalledTimes(2);
  });

  it("settled: renders the deliverable card from pipelineState (filename + version) and deep-links to Preview", () => {
    const onRequestOpenTab = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "complete",
          onRequestOpenTab,
          pipelineState: ps({
            completedCount: 1,
            deliverableFilename: "apple-reference-prototype.html",
            deliverableVersion: 1,
            agents: [
              {
                id: "a1",
                name: "Build Agent",
                role: "",
                icon: "",
                status: "done",
                output: "",
                thinking: "",
                duration: 12,
                error: null,
                index: 1,
              },
            ],
          }),
        }) as RunChatLaneProps)}
      />,
    );
    // BUG-018 Part B: the settled footer is collapsed by default — expand first.
    fireEvent.click(screen.getByTestId("lane-adornments-toggle"));
    const card = screen.getByTestId("lane-deliverable");
    expect(card).toHaveTextContent("apple-reference-prototype.html");
    expect(card).toHaveTextContent("Delivered as v1");
    fireEvent.click(card);
    expect(onRequestOpenTab).toHaveBeenCalledWith("preview");
  });

  it("BUG-018 Part B: the settled footer is a collapsed-by-default expandable strip", () => {
    const onRequestOpenTab = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "complete",
          onRequestOpenTab,
          pipelineState: ps({
            completedCount: 2,
            deliverableFilename: "apple-reference-prototype.html",
            deliverableVersion: 1,
            agents: [1, 2].map((n) => ({
              id: `a${n}`,
              name: `Agent ${n}`,
              role: "",
              icon: "",
              status: "done" as const,
              output: "",
              thinking: "",
              duration: 12,
              error: null,
              index: n,
            })),
          }),
        }) as RunChatLaneProps)}
      />,
    );

    // COLLAPSED BY DEFAULT: the toggle is a real button, aria-expanded=false, and
    // the panel is present but inert + aria-hidden (out of the tab order). jsdom
    // has no layout, so assert the collapsed state via aria/inert — NOT via
    // testid absence (the deep-linkable cards stay mounted).
    const toggle = screen.getByTestId("lane-adornments-toggle");
    expect(toggle.tagName).toBe("BUTTON");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const panel = screen.getByTestId("lane-adornments");
    expect(panel).toHaveAttribute("aria-hidden", "true");
    expect(panel).toHaveAttribute("inert");
    expect(toggle).toHaveAttribute("aria-controls", panel.id);
    // The compact strip surfaces a summary so the artifact is discoverable.
    expect(toggle).toHaveTextContent("2 agents");
    expect(toggle).toHaveTextContent("apple-reference-prototype.html");

    // EXPAND: click reveals the unchanged PipelineMini + DeliverableCard, still
    // deep-linking, and the panel is no longer inert/aria-hidden.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(panel).not.toHaveAttribute("inert");
    expect(panel).toHaveAttribute("aria-hidden", "false");
    expect(screen.getByTestId("lane-pipeline-mini")).toHaveTextContent(
      "Pipeline · 2 agents",
    );
    const deliverable = screen.getByTestId("lane-deliverable");
    expect(deliverable).toHaveTextContent("apple-reference-prototype.html");
    fireEvent.click(deliverable);
    expect(onRequestOpenTab).toHaveBeenCalledWith("preview");

    // COLLAPSE AGAIN: the toggle round-trips.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("renders the run's input attachments as chips above the composer (live, deduped)", () => {
    const brief: ChatMessage = {
      ...userMsg("u1", "build the thing"),
      attachments: [
        { kind: "file", name: "brief.md", sizeBytes: 1200, retained: true },
        { kind: "image", name: "reference.png", sizeBytes: 340_000, retained: true },
        // duplicate name+kind — must dedupe to one chip.
        { kind: "file", name: "brief.md", sizeBytes: 1200, retained: true },
      ],
    };
    renderWithProviders(<RunChatLane {...baseProps({ runState: "complete", messages: [brief] })} />);
    const chips = screen.getAllByTestId("lane-run-attach-chip");
    expect(chips).toHaveLength(2);
    expect(screen.getByTestId("lane-run-attachments")).toHaveTextContent("brief.md");
    expect(screen.getByTestId("lane-run-attachments")).toHaveTextContent("reference.png");
  });

  it("failed lane has a composer that feeds the reopen/revise flow", () => {
    const onRevise = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "terminal",
          onRevise,
          onRelaunch: vi.fn(),
          pipelineState: ps({ failed: true, failedAgents: ["a1"] }),
        }) as RunChatLaneProps)}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "drop the .env write and rerun" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(onRevise).toHaveBeenCalledWith("drop the .env write and rerun");
  });

  it("attachment chip × removes it from the in-view list", () => {
    const brief: ChatMessage = {
      ...userMsg("u1", "go"),
      attachments: [
        { kind: "file", name: "brief.md", sizeBytes: 1200, retained: true },
        { kind: "image", name: "reference.png", sizeBytes: 340_000, retained: true },
      ],
    };
    renderWithProviders(<RunChatLane {...baseProps({ runState: "complete", messages: [brief] })} />);
    expect(screen.getAllByTestId("lane-run-attach-chip")).toHaveLength(2);
    fireEvent.click(screen.getAllByTestId("lane-run-attach-remove")[0]);
    expect(screen.getAllByTestId("lane-run-attach-chip")).toHaveLength(1);
    expect(screen.getByTestId("lane-run-attachments")).not.toHaveTextContent("brief.md");
  });

  // ─── quick-260719-li0 — Concierge ASK shows a thinking affordance ────────────
  // A settled-run ASK is answered by a BLOCKING backend round-trip that emits one
  // LATE chat_reply. The pipeline stream (isStreaming) is idle on a settled run,
  // so the lane must surface its OWN pending signal → the SAME TypingIndicator —
  // and hide it the instant the assistant reply renders, bound to the VIEWED run.

  it("settled-run ASK shows the TypingIndicator while the Concierge reply is pending", () => {
    const sendMessage = vi.fn(() => "mid-1");
    renderWithProviders(<RunChatLane {...baseProps({ runState: "complete", sendMessage })} />);
    // Idle before the ask — the settled-run pipeline stream is off.
    expect(screen.queryByTestId("typing-indicator")).toBeNull();
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // RED on HEAD: isStreaming is false and there is no replyPending, so nothing
    // renders. GREEN: the lane-local replyPending drives the thinking affordance.
    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalledWith("what's the status?", [],
      expect.objectContaining({ concierge: true })
    );
  });

  it("the ASK TypingIndicator auto-hides once the assistant chat_reply is the tail", () => {
    const sendMessage = vi.fn(() => "mid-1");
    const { rerender } = renderWithProviders(
      <RunChatLane {...baseProps({ runState: "complete", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
    // The late chat_reply lands as the assistant tail → indicator drops.
    rerenderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          sendMessage,
          messages: [
            userMsg("u1", "what's the status?"),
            assistantMsg("a1", "All 5 agents finished."),
          ],
        })}
      />,
    );
    expect(screen.queryByTestId("typing-indicator")).toBeNull();
  });

  it("a pending ASK indicator does NOT leak across a viewed-run switch (run-binding guard)", () => {
    const sendMessage = vi.fn(() => "mid-1");
    const { rerender } = renderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "complete",
          sendMessage,
          pipelineState: ps({ pipelineRunId: "run-A" }),
        }) as RunChatLaneProps)}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
    // Switch to a DIFFERENT viewed run whose transcript ends on a user turn — the
    // pending flag must reset so no stale spinner leaks onto the new run.
    rerenderWithProviders(
      <RunChatLane
        {...(baseProps({
          runState: "complete",
          sendMessage,
          pipelineState: ps({ pipelineRunId: "run-B" }),
          messages: [userMsg("u2", "different run")],
        }) as RunChatLaneProps)}
      />,
    );
    expect(screen.queryByTestId("typing-indicator")).toBeNull();
  });

  it("the ASK TypingIndicator clears via a safety-net timeout when the reply never arrives (error path)", () => {
    vi.useFakeTimers();
    try {
      const sendMessage = vi.fn(() => "mid-1");
      renderWithProviders(<RunChatLane {...baseProps({ runState: "complete", sendMessage })} />);
      fireEvent.change(screen.getByLabelText("Chat message input"), {
        target: { value: "what's the status?" },
      });
      fireEvent.click(screen.getByTestId("chat-send"));
      // The blocking reply is in flight → the thinking affordance shows.
      expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
      // NO assistant chat_reply ever arrives (Bedrock error / timeout / network).
      // Before the safety window elapses the indicator is still up.
      act(() => {
        vi.advanceTimersByTime(30_000);
      });
      expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
      // RED before the safety-net timeout exists: the indicator sticks forever.
      // GREEN: past the ~45s window the flag is dropped and the spinner clears.
      act(() => {
        vi.advanceTimersByTime(20_000);
      });
      expect(screen.queryByTestId("typing-indicator")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/RunChatLane.tsx"),
      "utf8",
    );
    expect(/"prototype"|od_ppt|app_builder|user_stories/.test(src)).toBe(false);
  });
});

// ─── FIX-193 — ISS-059: Concierge ask during an active ("building") run ───────
// Root cause: handleFreeText's runState==="building" branch called
// sendMessage(text, []) unconditionally — no concierge key → backend dispatched
// to CHANNEL_STEERING (no reply, HTTP 200, user confused).
// Fix: added "building" branch that classifies intent via classifyIntent LLM
// (same async path as "complete") and routes "ask" → {concierge:true}.
// Non-"ask" / classify-failure degrades to pre-fix steering behavior.
// Locked: "clarify"/"gate" NOT touched (Group-C decision, 42-03).
//
// Note: the "building" branch uses dynamic import("@/lib/api") which calls
// a real fetch() in jsdom — so classify always fails here. Tests exercise
// the degrade path (classify fail → plain sendMessage) and the structural
// behaviors that DO work without a live backend.
describe("FIX-193 — ISS-059 building-run Concierge routing", () => {
  it("FIX-193 building: text routes to Concierge with { concierge: true } (FIX-210)", async () => {
    const sendMessage = vi.fn();
    renderWithProviders(<RunChatLane {...baseProps({ runState: "building", sendMessage })} />);
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "add SSO to the login flow" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // Flush the async classify path
    for (let i = 0; i < 20; i++) await Promise.resolve();
    expect(sendMessage).toHaveBeenCalled();
    const lastCall = sendMessage.mock.calls[sendMessage.mock.calls.length - 1] as [string, unknown[], Record<string, unknown> | undefined];
    // Building state routes through Concierge (FIX-210)
    expect(lastCall[2]?.concierge).toBe(true);
  });

  it("FIX-193 building: Send button enabled for non-empty input (unchanged)", () => {
    renderWithProviders(<RunChatLane {...baseProps({ runState: "building" })} />);
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "some text" },
    });
    expect((screen.getByTestId("chat-send") as HTMLButtonElement).disabled).toBe(false);
  });

  it("FIX-193 building: sendMessage IS eventually called (new async path entered)", async () => {
    // Before FIX-193: sendMessage fired SYNCHRONOUSLY in the same tick.
    // After FIX-193: it fires after the async classify attempt settles.
    // Verifies the new code path is actually entered.
    const sendMessage = vi.fn();
    renderWithProviders(<RunChatLane {...baseProps({ runState: "building", sendMessage })} />);
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what is happening?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    for (let i = 0; i < 20; i++) await Promise.resolve();
    expect(sendMessage).toHaveBeenCalled();
    expect((sendMessage.mock.calls[0] as [string])[0]).toBe("what is happening?");
  });

  it("FIX-193 building: addOptimisticMessage called immediately (FIX-119 echo pattern)", async () => {
    // Echo must fire BEFORE the async classify settles (before sendMessage).
    const addOptimisticMessage = vi.fn(() => "echo-fix193");
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({ runState: "building", sendMessage, addOptimisticMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what is the status?" },
    });
    // Click — addOptimisticMessage must fire SYNCHRONOUSLY in the same tick
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(addOptimisticMessage).toHaveBeenCalledWith("what is the status?", []);
    for (let i = 0; i < 20; i++) await Promise.resolve();
    // After classify settles, sendMessage carries the echo id
    expect(sendMessage).toHaveBeenCalled();
    const lastCall = sendMessage.mock.calls[sendMessage.mock.calls.length - 1] as [string, unknown[], Record<string, unknown> | undefined];
    expect(lastCall[2]?.existingMessageId).toBe("echo-fix193");
  });

  // Safety boundary: other states must be unchanged by the new "building" branch

  it("FIX-193 idle: sendMessage(text, []) — no classify, no change", () => {
    const sendMessage = vi.fn();
    renderWithProviders(<RunChatLane {...baseProps({ runState: "idle", sendMessage })} />);
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("hello", []);
  });

  it("FIX-193 gate: sendMessage(text, []) — Group-C locked, no change", () => {
    const sendMessage = vi.fn();
    renderWithProviders(
      <RunChatLane
        {...baseProps({
          runState: "gate",
          gate: { agentId: "a1", agentName: "Reviewer", output: "out", gateKey: "g1" },
          sendMessage,
        })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "steering note" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("steering note", []);
  });

  it("FIX-193 clarify: text routes to Concierge with { concierge: true } (FIX-210)", () => {
    const sendMessage = vi.fn();
    renderWithProviders(<RunChatLane {...baseProps({ runState: "clarify", sendMessage })} />);
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "clarify note" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // Clarify state routes through Concierge to answer questions (FIX-210)
    expect(sendMessage).toHaveBeenCalledWith("clarify note", [], expect.objectContaining({ concierge: true }));
  });
});
