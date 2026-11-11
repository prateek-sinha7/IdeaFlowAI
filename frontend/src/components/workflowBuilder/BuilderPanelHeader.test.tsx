import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SessionSummary } from "@/types/workflowBuilder";

import { BuilderPanelHeader, type BuilderPanelHeaderProps } from "./BuilderPanelHeader";

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

function setup(overrides: Partial<BuilderPanelHeaderProps> = {}) {
  const props: BuilderPanelHeaderProps = {
    sessions: [session("s1", "Report workflow"), session("s2", "Email triage")],
    currentSessionId: "s1",
    hasMoreSessions: false,
    onShowMore: vi.fn(),
    onSelectSession: vi.fn(),
    onDeleteSession: vi.fn(),
    onNewConversation: vi.fn(),
    onCollapse: vi.fn(),
    ...overrides,
  };
  render(<BuilderPanelHeader {...props} />);
  return props;
}

const openMenu = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", { name: /Conversations/ }));

describe("BuilderPanelHeader", () => {
  it("shows the title and the header buttons", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Build with AI" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Collapse builder panel" })).toBeInTheDocument();
  });

  it("shows the open conversation's title as the heading", () => {
    setup({ title: "Report workflow" });
    expect(screen.getByRole("heading", { name: "Report workflow" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Build with AI" })).toBeNull();
  });

  it("closes the menu on a click outside it", async () => {
    const user = userEvent.setup();
    setup();
    await openMenu(user);
    expect(screen.getByRole("button", { name: "Report workflow" })).toBeInTheDocument();
    await user.click(document.body);
    expect(screen.queryByRole("button", { name: "Report workflow" })).toBeNull();
    expect(screen.getByRole("button", { name: /Conversations/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("reports New conversation and collapse clicks", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    await user.click(screen.getByRole("button", { name: "Collapse builder panel" }));
    expect(props.onNewConversation).toHaveBeenCalledOnce();
    expect(props.onCollapse).toHaveBeenCalledOnce();
  });

  it("disables New conversation while a turn runs", () => {
    setup({ newConversationDisabled: true });
    expect(screen.getByRole("button", { name: "New conversation" })).toBeDisabled();
  });

  it("opens the menu with the sessions, marks the current one and tells the host", async () => {
    const user = userEvent.setup();
    const onMenuOpen = vi.fn();
    setup({ onMenuOpen });
    const toggle = screen.getByRole("button", { name: /Conversations/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await openMenu(user);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(onMenuOpen).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Report workflow" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: "Email triage" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("selects a session and closes the menu", async () => {
    const user = userEvent.setup();
    const props = setup();
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Email triage" }));
    expect(props.onSelectSession).toHaveBeenCalledWith("s2");
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("says when there are no conversations", async () => {
    const user = userEvent.setup();
    setup({ sessions: [], currentSessionId: null });
    await openMenu(user);
    expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
  });

  it("shows Show more when another page exists and loads it on click", async () => {
    const user = userEvent.setup();
    const props = setup({ hasMoreSessions: true });
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Show more" }));
    expect(props.onShowMore).toHaveBeenCalledOnce();
  });

  it("hides Show more on the last page", async () => {
    const user = userEvent.setup();
    setup({ hasMoreSessions: false });
    await openMenu(user);
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  it("closes the menu on Escape", async () => {
    const user = userEvent.setup();
    setup();
    await openMenu(user);
    screen.getByRole("button", { name: "Report workflow" }).focus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: "Report workflow" })).toBeNull();
  });

  it("asks for confirmation before deleting and deletes only after Delete", async () => {
    const user = userEvent.setup();
    const props = setup();
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Delete conversation Email triage" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this conversation?" });
    expect(props.onDeleteSession).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/"Email triage" and its messages will be deleted/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    expect(props.onDeleteSession).toHaveBeenCalledWith("s2");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves the session untouched when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const props = setup();
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Delete conversation Email triage" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onDeleteSession).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves the session untouched when the confirmation is dismissed with Escape", async () => {
    const user = userEvent.setup();
    const props = setup();
    await openMenu(user);
    await user.click(screen.getByRole("button", { name: "Delete conversation Report workflow" }));
    await user.keyboard("{Escape}");
    expect(props.onDeleteSession).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
