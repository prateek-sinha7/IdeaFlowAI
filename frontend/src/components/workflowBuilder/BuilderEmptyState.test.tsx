import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SessionSummary } from "@/types/workflowBuilder";

import {
  BuilderEmptyState,
  EMPTY_STATE_RECENT_SESSIONS,
  EXAMPLE_PROMPTS,
  type BuilderEmptyStateProps,
} from "./BuilderEmptyState";

function session(id: string, title: string): SessionSummary {
  return {
    id,
    title,
    mode: "create",
    workflow_id: null,
    model_id: "model-a",
    effort: null,
    running: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function setup(overrides: Partial<BuilderEmptyStateProps> = {}) {
  const props: BuilderEmptyStateProps = {
    onPickExample: vi.fn(),
    recentSessions: [],
    onSelectSession: vi.fn(),
    ...overrides,
  };
  render(<BuilderEmptyState {...props} />);
  return props;
}

describe("BuilderEmptyState", () => {
  it("introduces the builder and offers three to four example prompts", () => {
    setup();
    expect(screen.getByRole("heading", { name: "What should this workflow do?" })).toBeInTheDocument();
    const examples = within(screen.getByRole("list", { name: "Try an example" })).getAllByRole("button");
    expect(examples.map((button) => button.textContent)).toEqual([...EXAMPLE_PROMPTS]);
    expect(examples.length).toBeGreaterThanOrEqual(3);
    expect(examples.length).toBeLessThanOrEqual(4);
  });

  it("hands the example's text to the host when an example is picked", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: EXAMPLE_PROMPTS[2] }));
    expect(props.onPickExample).toHaveBeenCalledWith(EXAMPLE_PROMPTS[2]);
    expect(props.onSelectSession).not.toHaveBeenCalled();
  });

  it("lists no recent conversations when there are none", () => {
    setup();
    expect(screen.queryByRole("list", { name: "Recent conversations" })).toBeNull();
  });

  it("lists only the newest conversations and opens the one picked", async () => {
    const user = userEvent.setup();
    const sessions = Array.from({ length: EMPTY_STATE_RECENT_SESSIONS + 2 }, (_, i) =>
      session(`s${i}`, `Workflow ${i}`),
    );
    const props = setup({ recentSessions: sessions });
    const list = screen.getByRole("list", { name: "Recent conversations" });
    expect(within(list).getAllByRole("button")).toHaveLength(EMPTY_STATE_RECENT_SESSIONS);
    expect(within(list).queryByRole("button", { name: /Workflow 6/ })).toBeNull();
    await user.click(within(list).getByRole("button", { name: /Workflow 1/ }));
    expect(props.onSelectSession).toHaveBeenCalledWith("s1");
  });
});
