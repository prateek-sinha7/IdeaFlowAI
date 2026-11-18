import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BuilderEmptyState, EXAMPLE_PROMPT } from "./BuilderEmptyState";

function setup() {
  const onPickExample = vi.fn();
  render(<BuilderEmptyState onPickExample={onPickExample} />);
  return { onPickExample };
}

describe("BuilderEmptyState", () => {
  it("introduces the builder and offers exactly one example prompt", () => {
    setup();
    expect(screen.getByRole("heading", { name: "What should this workflow do?" })).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveTextContent(EXAMPLE_PROMPT);
    expect(buttons[0]).toHaveAccessibleDescription("Try an example");
  });

  it("hands the example's text to the host when the example is picked", async () => {
    const user = userEvent.setup();
    const { onPickExample } = setup();
    await user.click(screen.getByRole("button", { name: EXAMPLE_PROMPT }));
    expect(onPickExample).toHaveBeenCalledTimes(1);
    expect(onPickExample).toHaveBeenCalledWith(EXAMPLE_PROMPT);
  });

  it("shows no conversation history", () => {
    setup();
    expect(screen.queryByText("Recent conversations")).toBeNull();
    expect(screen.queryByRole("list")).toBeNull();
  });
});
