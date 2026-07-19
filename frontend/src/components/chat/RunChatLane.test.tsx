import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

  it("clarify mode: lane composer is a plain phase-hint input (NOT a duplicate answer form) — Steps is the sole answer surface (Group C)", () => {
    const q: ClarifyQuestion = {
      id: "q1",
      question: "Which layout?",
      options: ["Grid", "List"],
      answerType: "single_choice",
    };
    const sendMessage = vi.fn();
    render(
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
    // A free-text turn routes as a steering note through the shared send seam.
    fireEvent.change(input, { target: { value: "one more thing" } });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("one more thing", []);
  });

  it("gate mode: lane composer is a plain phase-hint input (NOT a duplicate approval form) — Steps is the sole answer surface (Group C)", () => {
    const sendMessage = vi.fn();
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

  it("complete mode shows the revision composer and NO suggestion chips (mock fidelity)", () => {
    render(
      <RunChatLane
        {...baseProps({
          runState: "complete",
          suggestions: [{ id: "ppt", label: "Build a deck" }],
          onSuggestion: vi.fn(),
        })}
      />,
    );
    // The settled composer is just the "Ask for a change…" input.
    expect(screen.getByTestId("chat-send")).toBeInTheDocument();
    // The unregistered "Suggested next steps" block is removed from the lane.
    expect(screen.queryByTestId("chat-suggestion-chip")).toBeNull();
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

  // ─── 44-02 (W3a) — the confirm-first refinement chip ─────────────────────────
  // On a SETTLED run a CHANGE request no longer auto-launches a revision: it is
  // HELD behind a "Run a refinement with this change?" confirm chip. onRevise
  // fires ONLY on explicit confirm; dismiss launches nothing (T-44-02-01).

  it("settled-run CHANGE holds a confirm chip and does NOT auto-launch onRevise (44-02)", () => {
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
    // The confirm chip surfaces with the held instruction; nothing launched yet.
    const chip = screen.getByTestId("chat-refinement-chip");
    expect(chip).toHaveTextContent("Run a refinement with this change?");
    expect(chip).toHaveTextContent("make it shorter");
    expect(onRevise).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("settled-run CHANGE → confirm chip → Confirm launches onRevise exactly once (44-02)", () => {
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
    fireEvent.click(screen.getByTestId("chat-refinement-confirm"));
    // The *_revision launch fires exactly once, only after confirm.
    expect(onRevise).toHaveBeenCalledTimes(1);
    expect(onRevise).toHaveBeenCalledWith("make it shorter");
    expect(sendMessage).not.toHaveBeenCalled();
    // The chip clears after confirming.
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run CHANGE → confirm chip → Dismiss launches nothing (44-02)", () => {
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
    fireEvent.click(screen.getByTestId("chat-refinement-dismiss"));
    // Dismiss clears the hold — no revision, no message.
    expect(onRevise).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run CHANGE with no onRevise falls back to a plain sendMessage (no chip)", () => {
    const sendMessage = vi.fn();
    render(
      <RunChatLane {...baseProps({ runState: "complete", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "make it shorter" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("make it shorter", []);
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  it("settled-run ASK still routes to the Concierge with NO refinement chip (43-02 unchanged)", () => {
    const onRevise = vi.fn();
    const sendMessage = vi.fn();
    render(
      <RunChatLane
        {...baseProps({ runState: "complete", onRevise, sendMessage })}
      />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(sendMessage).toHaveBeenCalledWith("what's the status?", [], {
      concierge: true,
    });
    expect(onRevise).not.toHaveBeenCalled();
    expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
  });

  // ─── 43-02 (A.1 CRUX) — settled-run ask-vs-change routing matrix ─────────────
  // On a SETTLED (complete) run the free-text turn is CLASSIFIED generically
  // (SC-001/INV-1): an ASK is answered by the Concierge (sendMessage with
  // { concierge: true }); a CHANGE REQUEST still launches the revision pipeline
  // (onRevise). Change-intent is weighed FIRST so a question-SHAPED change routes
  // as a change (case 5) — a bare question-mark heuristic would misroute it.
  const routeCases: Array<{
    text: string;
    expect: "ask" | "change";
    why: string;
  }> = [
    { text: "what's the status?", expect: "ask", why: "status question" },
    { text: "is the login page done?", expect: "ask", why: "yes/no progress question" },
    { text: "why did the build fail?", expect: "ask", why: "explanatory question" },
    { text: "make it dark mode", expect: "change", why: "imperative change" },
    {
      text: "can you make the button bigger?",
      expect: "change",
      why: "TRAP: question-shaped but change-intent",
    },
  ];

  for (const c of routeCases) {
    it(`settled route: "${c.text}" → ${c.expect} (${c.why})`, () => {
      const sendMessage = vi.fn();
      const onRevise = vi.fn();
      render(
        <RunChatLane
          {...baseProps({ runState: "complete", sendMessage, onRevise })}
        />,
      );
      fireEvent.change(screen.getByLabelText("Chat message input"), {
        target: { value: c.text },
      });
      fireEvent.click(screen.getByTestId("chat-send"));

      if (c.expect === "ask") {
        // Answered by the Concierge — NOT launched as a revision, no chip.
        expect(sendMessage).toHaveBeenCalledWith(c.text, [], { concierge: true });
        expect(onRevise).not.toHaveBeenCalled();
        expect(screen.queryByTestId("chat-refinement-chip")).toBeNull();
      } else {
        // A CHANGE is HELD behind the confirm chip — NOT auto-launched (44-02).
        // The revision fires only on confirm; classification still routes here.
        expect(screen.getByTestId("chat-refinement-chip")).toBeInTheDocument();
        expect(onRevise).not.toHaveBeenCalled();
        expect(sendMessage).not.toHaveBeenCalled();
      }
    });
  }

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
    render(<RunChatLane {...baseProps({ runState: "building" })} />);
    expect(screen.getByTestId("lane-run-status")).toHaveTextContent("Running");
  });

  it("clarify state renders an Awaiting-you status card that deep-links to Steps", () => {
    const onRequestOpenTab = vi.fn();
    render(
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
    render(
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
    render(
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
    const mini = screen.getByTestId("lane-pipeline-mini");
    expect(mini).toHaveTextContent("Pipeline · 5 agents");
    expect(mini).toHaveTextContent("3 / 5");
    fireEvent.click(mini);
    expect(onRequestOpenTab).toHaveBeenCalledWith("thinking");
  });

  it("settled state renders the pipeline mini from live agents", () => {
    render(
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
    render(
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
    render(
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
    render(
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
    render(<RunChatLane {...baseProps({ runState: "complete", messages: [brief] })} />);
    const chips = screen.getAllByTestId("lane-run-attach-chip");
    expect(chips).toHaveLength(2);
    expect(screen.getByTestId("lane-run-attachments")).toHaveTextContent("brief.md");
    expect(screen.getByTestId("lane-run-attachments")).toHaveTextContent("reference.png");
  });

  it("failed lane has a composer that feeds the reopen/revise flow", () => {
    const onRevise = vi.fn();
    render(
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
    render(<RunChatLane {...baseProps({ runState: "complete", messages: [brief] })} />);
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
    render(<RunChatLane {...baseProps({ runState: "complete", sendMessage })} />);
    // Idle before the ask — the settled-run pipeline stream is off.
    expect(screen.queryByTestId("typing-indicator")).toBeNull();
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // RED on HEAD: isStreaming is false and there is no replyPending, so nothing
    // renders. GREEN: the lane-local replyPending drives the thinking affordance.
    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalledWith("what's the status?", [], {
      concierge: true,
    });
  });

  it("the ASK TypingIndicator auto-hides once the assistant chat_reply is the tail", () => {
    const sendMessage = vi.fn(() => "mid-1");
    const { rerender } = render(
      <RunChatLane {...baseProps({ runState: "complete", sendMessage })} />,
    );
    fireEvent.change(screen.getByLabelText("Chat message input"), {
      target: { value: "what's the status?" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(screen.getByTestId("typing-indicator")).toBeInTheDocument();
    // The late chat_reply lands as the assistant tail → indicator drops.
    rerender(
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
    const { rerender } = render(
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
    rerender(
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

  it("SC-001: the source carries no workflow-name literal", () => {
    const src = readFileSync(
      join(process.cwd(), "src/components/chat/RunChatLane.tsx"),
      "utf8",
    );
    expect(/"prototype"|od_ppt|app_builder|user_stories/.test(src)).toBe(false);
  });
});
