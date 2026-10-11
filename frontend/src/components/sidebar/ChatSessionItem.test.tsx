import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatSessionItem } from "./ChatSessionItem";
import type { ChatSession } from "@/types/index";

const NOW = new Date("2025-06-15T12:00:00.000Z");

function makeSession(overrides: Partial<ChatSession> = {}): ChatSession {
  return {
    id: "chat-1",
    title: "My Chat",
    lastActivity: NOW.toISOString(),
    createdAt: NOW.toISOString(),
    ...overrides,
  };
}

function ago(ms: number): string {
  return new Date(NOW.getTime() - ms).toISOString();
}

const SEC = 1000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

describe("ChatSessionItem", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the session title", () => {
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} />);
    expect(screen.getByText("My Chat")).toBeInTheDocument();
  });

  it("falls back to 'Untitled Chat' when title is empty", () => {
    render(<ChatSessionItem session={makeSession({ title: "" })} isActive={false} onClick={vi.fn()} />);
    expect(screen.getByText("Untitled Chat")).toBeInTheDocument();
  });

  it.each([
    ["under a minute", 30 * SEC, "just now"],
    ["minutes", 5 * MIN, "5 min ago"],
    ["one hour", 1 * HOUR, "1 hour ago"],
    ["several hours", 3 * HOUR, "3 hours ago"],
    ["one day", 1 * DAY, "1 day ago"],
    ["several days", 3 * DAY, "3 days ago"],
  ])("shows relative time for %s", (_label, offset, expected) => {
    render(
      <ChatSessionItem session={makeSession({ lastActivity: ago(offset) })} isActive={false} onClick={vi.fn()} />,
    );
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("shows a short date when older than a week", () => {
    const iso = ago(10 * DAY);
    const expected = new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    render(<ChatSessionItem session={makeSession({ lastActivity: iso })} isActive={false} onClick={vi.fn()} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("marks the active item with aria-current", () => {
    render(<ChatSessionItem session={makeSession()} isActive onClick={vi.fn()} />);
    expect(screen.getByRole("button", { name: /My Chat/ })).toHaveAttribute("aria-current", "true");
  });

  it("omits aria-current when inactive", () => {
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} />);
    expect(screen.getByRole("button", { name: /My Chat/ })).not.toHaveAttribute("aria-current");
  });

  it("calls onClick when clicked", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClick = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: /My Chat/ }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it.each([["{Enter}"], [" "]])("activates via keyboard key %j", async (key) => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClick = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={onClick} />);
    screen.getByRole("button", { name: /My Chat/ }).focus();
    await user.keyboard(key);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("ignores other keys", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onClick = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={onClick} />);
    screen.getByRole("button", { name: /My Chat/ }).focus();
    await user.keyboard("a");
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not render a delete button without onDelete", () => {
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Delete chat" })).not.toBeInTheDocument();
  });

  it("first delete click asks for confirmation without deleting or selecting", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onDelete = vi.fn();
    const onClick = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={onClick} onDelete={onDelete} />);
    await user.click(screen.getByRole("button", { name: "Delete chat" }));
    expect(screen.getByRole("button", { name: "Confirm delete" })).toHaveTextContent("Delete?");
    expect(onDelete).not.toHaveBeenCalled();
    expect(onClick).not.toHaveBeenCalled();
  });

  it("second delete click deletes the session and resets the button", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onDelete = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} onDelete={onDelete} />);
    await user.click(screen.getByRole("button", { name: "Delete chat" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(onDelete).toHaveBeenCalledExactlyOnceWith("chat-1");
    expect(screen.getByRole("button", { name: "Delete chat" })).toBeInTheDocument();
  });

  it("confirmation expires after 2 seconds", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const onDelete = vi.fn();
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} onDelete={onDelete} />);
    await user.click(screen.getByRole("button", { name: "Delete chat" }));
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByRole("button", { name: "Delete chat" })).toBeInTheDocument();
    expect(onDelete).not.toHaveBeenCalled();
  });

  it("confirmation persists before the timeout elapses", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ChatSessionItem session={makeSession()} isActive={false} onClick={vi.fn()} onDelete={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Delete chat" }));
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByRole("button", { name: "Confirm delete" })).toBeInTheDocument();
  });
});
