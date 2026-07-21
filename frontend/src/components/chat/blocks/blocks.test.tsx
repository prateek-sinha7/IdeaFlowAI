import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChatBlock } from "../runtime/blocks.types";
import { ThinkingBlock } from "./ThinkingBlock";
import { FileOpsSummary } from "./FileOpsSummary";

// ─── open-design borrow #7 (31-02 Task 3) — thinking / todo / file-ops blocks ─
// The codebase's first data-testids land on these chat block surfaces (CONTEXT).

type ThinkingData = Extract<ChatBlock, { kind: "thinking" }>;
type FileOpsData = Extract<ChatBlock, { kind: "file_ops" }>;

describe("ThinkingBlock", () => {
  it("renders its testid and is collapsed by default (body hidden)", () => {
    const block: ThinkingData = { kind: "thinking", text: "secret reasoning" };
    render(<ThinkingBlock block={block} />);
    expect(screen.getByTestId("chat-thinking-block")).toBeInTheDocument();
    // Collapsed: the reasoning body is not in the document.
    expect(screen.queryByText("secret reasoning")).not.toBeInTheDocument();
    // Toggle exposes its collapsed state to AT.
    const toggle = screen.getByRole("button");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("expands to reveal the reasoning body when toggled", () => {
    const block: ThinkingData = { kind: "thinking", text: "step by step" };
    render(<ThinkingBlock block={block} />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("step by step")).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  });

  it('shows the "Thought for Xs" label once a duration is provided', () => {
    const block: ThinkingData = {
      kind: "thinking",
      text: "…",
      durationMs: 2400,
    };
    render(<ThinkingBlock block={block} />);
    expect(screen.getByText("Thought for 2s")).toBeInTheDocument();
  });

  it('falls back to "Thought process" with no duration', () => {
    const block: ThinkingData = { kind: "thinking", text: "…" };
    render(<ThinkingBlock block={block} />);
    expect(screen.getByText("Thought process")).toBeInTheDocument();
  });
});

describe("FileOpsSummary", () => {
  it("renders its testid and a files-this-turn strip", () => {
    const block: FileOpsData = {
      kind: "file_ops",
      files: [
        { path: "src/a.ts", op: "create" },
        { path: "src/b.ts", op: "edit" },
      ],
    };
    render(<FileOpsSummary block={block} />);
    expect(screen.getByTestId("chat-file-ops")).toBeInTheDocument();
    expect(screen.getByTestId("chat-file-ops")).toHaveTextContent(
      "2 files this turn",
    );
    expect(screen.getByText("src/a.ts")).toBeInTheDocument();
    expect(screen.getByText("src/b.ts")).toBeInTheDocument();
  });
});
