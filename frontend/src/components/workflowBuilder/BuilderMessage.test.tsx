import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TranscriptMessage } from "@/types/workflowBuilder";

import { BuilderMessage } from "./BuilderMessage";

function assistant(overrides: Partial<TranscriptMessage> = {}): TranscriptMessage {
  return {
    id: "m1",
    seq: 2,
    role: "assistant",
    turn_id: "t1",
    reply_to_message_id: "u1",
    status: "completed",
    outcome: "reply",
    stop_reason: null,
    content: "Hello **there**",
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

describe("BuilderMessage", () => {
  it("renders raw HTML in a reply as text, not elements", () => {
    const { container } = render(
      <BuilderMessage message={assistant({ content: "<script>alert(1)</script> <b>x</b>" })} />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("folds a skill report behind a collapsed Full report section", () => {
    render(
      <BuilderMessage
        message={assistant({
          content: "Context loaded this turn: a\nSummary line.\n\n## Details\nReport body.",
        })}
      />,
    );
    expect(screen.getByText(/Summary line\./)).toBeVisible();
    expect(screen.getByText("Full report").closest("details")).not.toHaveAttribute("open");
  });

  it("keeps the Thinking block collapsed and shows the skill-updated line", () => {
    render(
      <BuilderMessage message={assistant({ thinking: "pondering", skill_updated: true })} />,
    );
    expect(screen.getByText("Thinking").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("The builder was updated before this reply.")).toBeInTheDocument();
  });

  it("wraps a table in a keyboard-focusable scroll region", () => {
    render(<BuilderMessage message={assistant({ content: "| a | b |\n|---|---|\n| 1 | 2 |" })} />);
    const region = screen.getByRole("region", { name: /table/i });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region.querySelector("table")).not.toBeNull();
  });

  it("words the stop notice by stop_reason and calls Continue", async () => {
    const onContinue = vi.fn();
    render(
      <BuilderMessage
        message={assistant({ status: "timed_out", stop_reason: "tool_calls" })}
        onContinue={onContinue}
      />,
    );
    expect(screen.getByText(/stopped at the tool-call limit/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it("shows the error line with Retry on a failed message", async () => {
    const onRetry = vi.fn();
    render(
      <BuilderMessage
        message={assistant({
          status: "failed",
          error: { code: "llm_error", message: "The model call failed.", retryable: true },
        })}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText("The model call failed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("lists the change summary and launch needs for an accepted draft, with Undo", async () => {
    const onUndo = vi.fn();
    render(
      <BuilderMessage
        message={assistant({ revision: 3 })}
        draft={{
          change_summary: {
            added: ["Research"],
            removed: [],
            reordered: false,
            gates_changed: [],
            validators_changed: [],
            models_changed: [],
            prompts_changed: 2,
          },
          launch_needs: [{ kind: "connector", detail: "github" }],
        }}
        onUndo={onUndo}
      />,
    );
    expect(screen.getByText("Added: Research")).toBeInTheDocument();
    expect(screen.getByText("2 prompts changed")).toBeInTheDocument();
    expect(screen.getByText("A connector (github)")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("opens and closes the reading view dialog", async () => {
    render(<BuilderMessage message={assistant()} />);
    await userEvent.click(screen.getByRole("button", { name: "Open in reading view" }));
    expect(screen.getByRole("dialog", { name: "Reading view" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
