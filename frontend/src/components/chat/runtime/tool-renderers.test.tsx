import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ChatBlock } from "./blocks.types";
import {
  GenericToolCard,
  deriveToolStatus,
  hasToolRenderer,
  registerToolRenderer,
  renderToolBlock,
} from "./tool-renderers";

// ─── open-design borrow #3 (31-02 Task 1) — tool-renderer registry + dispatch ─
// Three-tier resolution: registry (keyed on the GENERIC tool name) → generic
// fallback, each registered renderer try/catch-isolated. No branch references a
// workflow name (SC-001).

type ToolBlock = Extract<ChatBlock, { kind: "tool" }>;

function toolBlock(overrides: Partial<ToolBlock> = {}): ToolBlock {
  return { kind: "tool", name: "read_file", status: "pending", ...overrides };
}

describe("tool-renderer registry + dispatch", () => {
  it("uses a registered renderer for its generic tool name", () => {
    const unregister = registerToolRenderer("read_file", (p) => (
      <div data-testid="custom-read-file">custom:{p.name}</div>
    ));
    try {
      render(<>{renderToolBlock(toolBlock({ name: "read_file" }))}</>);
      expect(screen.getByTestId("custom-read-file")).toHaveTextContent(
        "custom:read_file",
      );
    } finally {
      unregister();
    }
    expect(hasToolRenderer("read_file")).toBe(false);
  });

  it("falls back to GenericToolCard for an unregistered tool name", () => {
    render(
      <>{renderToolBlock(toolBlock({ name: "never_registered_tool" }))}</>,
    );
    const card = screen.getByTestId("chat-tool-card");
    expect(card).toHaveAttribute("data-tool-name", "never_registered_tool");
    expect(card).toHaveTextContent("never_registered_tool");
    expect(card).toHaveTextContent("Running");
  });

  it("isolates a renderer that throws — falls back to the generic card, no throw propagates", () => {
    const boom = vi.fn(() => {
      throw new Error("renderer blew up");
    });
    const unregister = registerToolRenderer("exploding_tool", boom);
    try {
      expect(() =>
        render(<>{renderToolBlock(toolBlock({ name: "exploding_tool" }))}</>),
      ).not.toThrow();
      expect(boom).toHaveBeenCalledOnce();
      const card = screen.getByTestId("chat-tool-card");
      expect(card).toHaveAttribute("data-tool-name", "exploding_tool");
    } finally {
      unregister();
    }
  });

  it("reflects status derivation — pending vs success vs error — in the output", () => {
    const { rerender } = render(
      <>{renderToolBlock(toolBlock({ name: "t", status: "pending" }))}</>,
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveAttribute(
      "data-tool-status",
      "pending",
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveTextContent("Running");

    rerender(
      <>
        {renderToolBlock(
          toolBlock({ name: "t", status: "success", result: "ok" }),
        )}
      </>,
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveAttribute(
      "data-tool-status",
      "success",
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveTextContent("Completed");

    rerender(
      <>
        {renderToolBlock(
          toolBlock({ name: "t", status: "error", isError: true }),
        )}
      </>,
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveAttribute(
      "data-tool-status",
      "error",
    );
    expect(screen.getByTestId("chat-tool-card")).toHaveTextContent("Failed");
  });

  it("deriveToolStatus is pure: error > success > pending", () => {
    expect(deriveToolStatus({ isError: true, result: "x" })).toBe("error");
    expect(deriveToolStatus({ result: "x" })).toBe("success");
    expect(deriveToolStatus({})).toBe("pending");
  });

  it("dispatch keys ONLY on the generic name — an arbitrary name resolves to the same generic card (SC-001)", () => {
    // Two unrelated, arbitrary tool names both hit the generic fallback: the
    // dispatch has no per-name branch, so behavior is name-agnostic.
    render(<>{renderToolBlock(toolBlock({ name: "alpha_xyz" }))}</>);
    render(<>{renderToolBlock(toolBlock({ name: "beta_123" }))}</>);
    const cards = screen.getAllByTestId("chat-tool-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("alpha_xyz");
    expect(cards[1]).toHaveTextContent("beta_123");
  });

  it("GenericToolCard renders standalone with name + status", () => {
    render(<>{GenericToolCard({ status: "success", name: "solo", result: 1 })}</>);
    const card = screen.getByTestId("chat-tool-card");
    expect(card).toHaveTextContent("solo");
    expect(card).toHaveTextContent("Completed");
  });
});
