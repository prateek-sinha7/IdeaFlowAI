import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DraftRevisionOut, ToolActivity, TranscriptMessage } from "@/types/workflowBuilder";

import { BuilderTranscript, type BuilderTranscriptProps } from "./BuilderTranscript";
import type { RunningTurnView, TurnView } from "./builderReducer";

function message(overrides: Partial<TranscriptMessage> = {}): TranscriptMessage {
  return {
    id: "m1",
    seq: 1,
    role: "user",
    turn_id: "t1",
    reply_to_message_id: null,
    status: "completed",
    outcome: null,
    stop_reason: null,
    content: "Build a report workflow",
    thinking: null,
    model_id: "model-a",
    effort: null,
    skill_hash: null,
    skill_updated: false,
    error: null,
    revision: null,
    activity: [],
    activity_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    ended_at: null,
    ...overrides,
  };
}

function reply(overrides: Partial<TranscriptMessage> = {}): TranscriptMessage {
  return message({
    id: "a1",
    seq: 2,
    role: "assistant",
    reply_to_message_id: "m1",
    outcome: "reply",
    content: "Here is the plan",
    ...overrides,
  });
}

function revision(n: number, kind: DraftRevisionOut["kind"] = "accepted"): DraftRevisionOut {
  return {
    revision: n,
    kind,
    manifest: {},
    target_trust: "user",
    change_summary: null,
    launch_needs: [],
    source_turn_id: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

const tool: ToolActivity = {
  call_id: "c1",
  tool: "read_file",
  kind: "read",
  label: "Read the catalog",
  status: "ok",
  duration_ms: 500,
  command: null,
  exit_code: null,
  summary: null,
};

function running(overrides: Partial<RunningTurnView> = {}): RunningTurnView {
  return {
    kind: "running",
    turnId: "t2",
    origin: "this_tab",
    stage: "thinking",
    label: "Thinking",
    startedAt: Date.now(),
    lastSeq: 0,
    activity: [],
    checks: [],
    warnings: [],
    text: "",
    thinking: "",
    pendingDraft: null,
    ...overrides,
  };
}

function setup(overrides: Partial<BuilderTranscriptProps> = {}) {
  const props: BuilderTranscriptProps = {
    messages: [],
    revisions: [],
    turn: { kind: "idle" } as TurnView,
    ...overrides,
  };
  render(<BuilderTranscript {...props} />);
  return props;
}

describe("BuilderTranscript", () => {
  it("invites the user to describe a workflow when empty and idle", () => {
    setup();
    expect(screen.getByText("Describe the workflow you want to build.")).toBeInTheDocument();
  });

  it("is not a live region, so streamed text is never spoken", () => {
    const { container } = render(
      <BuilderTranscript
        messages={[message()]}
        revisions={[]}
        turn={running({ text: "streaming words" })}
      />,
    );
    expect(container.querySelector("[aria-live]")).toBeNull();
    expect(container.querySelector('[role="log"]')).toBeNull();
  });

  it("shows messages in seq order whatever order they arrive in", () => {
    setup({
      messages: [reply({ id: "a1", seq: 2, content: "Second" }), message({ seq: 1, content: "First" })],
    });
    const region = screen.getByRole("region", { name: "Conversation" });
    const text = region.textContent ?? "";
    expect(text.indexOf("First")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("First")).toBeLessThan(text.indexOf("Second"));
  });

  it("shows the stored activity of an ended reply as a collapsed summary", () => {
    setup({
      messages: [
        message(),
        reply({ activity: [tool], activity_summary: { actions: 1, checks: 0, duration_ms: 5_000 } }),
      ],
    });
    const summary = screen.getByText("1 action, 0 checks, 5 s");
    expect(summary.closest("details")).not.toHaveAttribute("open");
  });

  it("shows text and thinking of a running turn started in this tab", () => {
    setup({
      messages: [message()],
      turn: running({ text: "Drafting now", thinking: "Weighing options" }),
    });
    expect(screen.getByRole("article", { name: "Builder reply in progress" })).toBeInTheDocument();
    expect(screen.getByText("Drafting now")).toBeInTheDocument();
    expect(screen.getByText("Thinking")).toBeInTheDocument();
    expect(screen.queryByText("Still working")).toBeNull();
  });

  it("shows only Still working and the activity for a turn from another tab", () => {
    setup({
      messages: [message()],
      turn: running({
        origin: "other_tab",
        text: "hidden text",
        thinking: "hidden thought",
        activity: [tool],
      }),
    });
    expect(screen.getByText("Still working")).toBeInTheDocument();
    expect(screen.queryByText("hidden text")).toBeNull();
    expect(screen.queryByText("hidden thought")).toBeNull();
    expect(screen.getByText("Read the catalog")).toBeInTheDocument();
  });

  it("shows Still working for a stored running row after a reload", () => {
    setup({
      messages: [
        message(),
        reply({ status: "running", content: "", activity: [tool] }),
      ],
      turn: { kind: "idle" },
    });
    expect(screen.getByText("Still working")).toBeInTheDocument();
    expect(screen.getByText("Read the catalog")).toBeInTheDocument();
  });

  it("renders the live turn in place of its stored running row, once", () => {
    setup({
      messages: [message(), reply({ status: "running", turn_id: "t2", content: "" })],
      turn: running({ turnId: "t2", text: "Live words" }),
    });
    expect(screen.getAllByRole("article", { name: "Builder reply in progress" })).toHaveLength(1);
    expect(screen.getByText("Live words")).toBeInTheDocument();
  });

  it("shows the pending message with Sending while a send is in flight", () => {
    setup({ turn: { kind: "sending", clientMessageId: "abcdefgh", text: "Please build it" } });
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent(
      "Please build it",
    );
    expect(screen.getByText("Sending")).toBeInTheDocument();
  });

  it("shows no pending bubble for a retry that sends no text", () => {
    setup({
      messages: [message()],
      turn: { kind: "sending", clientMessageId: "abcdefgh", text: "" },
    });
    expect(screen.queryByText("Sending")).toBeNull();
  });

  it("keeps the user's message above the live reply while the turn runs", () => {
    setup({ turn: running({ text: "Working on it" }), pendingUserText: "Please build it" });
    const mine = screen.getByRole("article", { name: "Your message" });
    expect(mine).toHaveTextContent("Please build it");
    expect(screen.queryByText("Sending")).toBeNull();
    const reply = screen.getByText("Working on it");
    expect(mine.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the first message with Sending while its conversation is created", () => {
    setup({ turn: { kind: "idle" }, pendingUserText: "Make a brief", starting: true });
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent("Make a brief");
    expect(screen.getByText("Sending")).toBeInTheDocument();
    expect(screen.queryByText("Describe the workflow you want to build.")).toBeNull();
  });

  it("drops Sending for the first message once its turn runs", () => {
    setup({ turn: running({ text: "Working on it" }), pendingUserText: "Make a brief", starting: true });
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent("Make a brief");
    expect(screen.queryByText("Sending")).toBeNull();
  });

  it("shows no pending bubble once the host passes no pending text", () => {
    setup({ turn: running({ text: "Working on it" }), pendingUserText: null });
    expect(screen.queryByRole("article", { name: "Your message" })).toBeNull();
  });

  it("offers Retry only on a failed reply", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    setup({
      messages: [
        message(),
        reply({
          status: "failed",
          error: { code: "boom", message: "Something went wrong", retryable: true },
        }),
      ],
      onRetry,
    });
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("offers Continue on a stopped reply", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    setup({
      messages: [message(), reply({ status: "timed_out", stop_reason: "time" })],
      onContinue,
    });
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledOnce();
  });

  it("offers Undo on the latest accepted draft's message only", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    setup({
      messages: [
        message({ id: "u1", seq: 1 }),
        reply({ id: "a1", seq: 2, revision: 1 }),
        message({ id: "u2", seq: 3 }),
        reply({ id: "a2", seq: 4, revision: 2, content: "Second draft" }),
      ],
      revisions: [revision(1), revision(2)],
      onUndo,
    });
    const undo = screen.getAllByRole("button", { name: /Undo/ });
    expect(undo).toHaveLength(1);
    await user.click(undo[0]);
    expect(onUndo).toHaveBeenCalledOnce();
  });

  it("offers no Undo when the latest revision is an undo", () => {
    setup({
      messages: [message(), reply({ revision: 1 })],
      revisions: [revision(1), revision(2, "undo")],
      onUndo: vi.fn(),
    });
    expect(screen.queryByRole("button", { name: /Undo/ })).toBeNull();
  });

  it("contains the conversation in a labelled region", () => {
    setup({ messages: [message()] });
    const region = screen.getByRole("region", { name: "Conversation" });
    expect(within(region).getByText("Build a report workflow")).toBeInTheDocument();
  });
});
