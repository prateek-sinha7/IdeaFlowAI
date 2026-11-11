import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DraftRevisionOut, ToolActivity, TranscriptMessage } from "@/types/workflowBuilder";

import { BuilderTranscript, type BuilderTranscriptProps } from "./BuilderTranscript";
import type { RunningTurnView, TurnStep, TurnView } from "./builderReducer";

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
    steps: null,
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

const textStep = (text: string): TurnStep => ({ kind: "text", id: `text-${text}`, text });
const thinkingStep = (text: string): TurnStep => ({ kind: "thinking", id: `thinking-${text}`, text });

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
    steps: [],
    warnings: [],
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
        turn={running({ steps: [textStep("streaming words")] })}
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

  describe("a finished reply with stored steps", () => {
    const lookup: ToolActivity = {
      ...tool,
      call_id: "c2",
      label: "Looked up the catalog",
      status: "stopped",
    };
    const finished = (overrides: Partial<TranscriptMessage> = {}) =>
      reply({
        thinking: "First thought. Second thought.",
        activity: [tool, lookup],
        activity_summary: { actions: 2, checks: 0, duration_ms: 5_000 },
        steps: [
          { kind: "thinking", text: "First thought." },
          { kind: "tools", call_ids: ["c1"] },
          { kind: "thinking", text: "Second thought." },
          { kind: "tools", call_ids: ["c2"] },
        ],
        ...overrides,
      });

    it("shows thinking and tool calls in the order they happened, inside the summary", async () => {
      const user = userEvent.setup();
      setup({ messages: [message(), finished()] });
      await user.click(screen.getByText("2 actions, 0 checks, 5 s"));
      const text = screen.getByRole("region", { name: "Conversation" }).textContent ?? "";
      const positions = [
        "First thought.",
        "Read the catalog",
        "Second thought.",
        "Looked up the catalog",
      ].map((mark) => text.indexOf(mark));
      expect(positions.every((p) => p >= 0)).toBe(true);
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
    });

    it("labels a stopped call Stopped", async () => {
      const user = userEvent.setup();
      setup({ messages: [message(), finished()] });
      await user.click(screen.getByText("2 actions, 0 checks, 5 s"));
      expect(screen.getByText("Stopped")).toBeInTheDocument();
      expect(screen.queryByText("Failed")).toBeNull();
    });

    it("does not repeat the thinking in a separate Thinking block under the summary", () => {
      setup({ messages: [message(), finished()] });
      const article = screen.getByRole("article", { name: "Builder reply" });
      expect(within(article).queryByText("Thinking")).toBeNull();
    });

    it("keeps the older layout and the Thinking block when the steps are null", () => {
      setup({ messages: [message(), finished({ steps: null })] });
      const article = screen.getByRole("article", { name: "Builder reply" });
      expect(within(article).getByText("Thinking")).toBeInTheDocument();
    });

    it("keeps the Thinking block for a thinking-only turn with no tool calls", () => {
      setup({
        messages: [
          message(),
          finished({
            activity: [],
            activity_summary: { actions: 0, checks: 0, duration_ms: 1_000 },
            steps: [{ kind: "thinking", text: "Only a thought." }],
          }),
        ],
      });
      const article = screen.getByRole("article", { name: "Builder reply" });
      expect(within(article).getByText("Thinking")).toBeInTheDocument();
    });
  });

  it("shows text and thinking of a running turn started in this tab", () => {
    setup({
      messages: [message()],
      turn: running({ steps: [thinkingStep("Weighing options"), textStep("Drafting now")] }),
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
        activity: [tool],
        steps: [
          { kind: "tools", id: "tools-2", callIds: ["c1"] },
          textStep("hidden text"),
          thinkingStep("hidden thought"),
        ],
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
      turn: running({ turnId: "t2", steps: [textStep("Live words")] }),
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
    setup({ turn: running({ steps: [textStep("Working on it")] }), pendingUserText: "Please build it" });
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
    setup({
      turn: running({ steps: [textStep("Working on it")] }),
      pendingUserText: "Make a brief",
      starting: true,
    });
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent("Make a brief");
    expect(screen.queryByText("Sending")).toBeNull();
  });

  it("shows no pending bubble once the host passes no pending text", () => {
    setup({ turn: running({ steps: [textStep("Working on it")] }), pendingUserText: null });
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
