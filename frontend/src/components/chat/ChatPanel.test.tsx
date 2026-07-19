import { render, fireEvent, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import { ChatPanel, type ChatPanelProps } from "./ChatPanel";

// ─── ChatPanel — streaming-chat scroll manager (quick-260719-nwe) ─────────────
// Two glitches (footer jitter + question scrolled off-screen) shared ONE root
// cause: the old effect fired scrollIntoView({behavior:"smooth"}) on the
// below-footer anchor on every [messages, streamingContent, isStreaming] change
// (~192×/stream). The fix: pin a NEW user turn to the top (block:"start") and
// otherwise follow the bottom INSTANTLY (behavior:"auto") only when the user is
// already near it. Rows must expose data-message-id so the pin can query them.

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

function baseProps(overrides: Partial<ChatPanelProps> = {}): ChatPanelProps {
  return {
    messages: [],
    isStreaming: false,
    streamingContent: "",
    onSendMessage: vi.fn(),
    hideComposer: true,
    ...overrides,
  };
}

describe("ChatPanel scroll manager", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    // jsdom has no native scrollIntoView; drop any spy we installed.
    // @ts-expect-error — deleting the test-installed stub.
    delete Element.prototype.scrollIntoView;
  });

  it("every rendered transcript row exposes data-message-id matching its message id", () => {
    const messages = [
      userMsg("u1", "hello"),
      assistantMsg("a1", "hi there"),
      userMsg("u2", "one more"),
    ];
    const { container } = render(
      <ChatPanel {...baseProps({ messages })} />,
    );
    const rows = container.querySelectorAll("[data-message-id]");
    expect(rows).toHaveLength(messages.length);
    expect(
      Array.from(rows).map((r) => r.getAttribute("data-message-id")),
    ).toEqual(["u1", "a1", "u2"]);
  });

  it("does not throw when scrollIntoView is unavailable (jsdom guard)", () => {
    // No scrollIntoView on the prototype — the guarded effect must degrade.
    expect(() =>
      render(<ChatPanel {...baseProps({ messages: [userMsg("u1", "hi")] })} />),
    ).not.toThrow();
  });

  it("pins a NEW user turn to the top with block:\"start\" (fixes the disappearing question)", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    render(<ChatPanel {...baseProps({ messages: [userMsg("u1", "my question")] })} />);

    // The newest user turn is scrolled to the TOP of the container.
    expect(spy).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    // A new-turn pin is a smooth scroll-to-top, never a bottom follow.
    expect(spy).not.toHaveBeenCalledWith({ behavior: "auto" });
  });

  it("follows the bottom INSTANTLY (behavior:\"auto\", never smooth) during streaming when the user is at the bottom", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    const { container, rerender } = render(
      <ChatPanel {...baseProps({ messages: [userMsg("u1", "hi")] })} />,
    );
    // The initial render pinned the question (block:"start") and turned follow
    // OFF. Simulate the user sitting at the bottom: jsdom scroll geometry is all
    // zeros so dist = 0 < 120 → stickToBottom flips back on.
    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;
    act(() => {
      fireEvent.scroll(scrollEl);
    });
    spy.mockClear();

    // Now a streaming assistant chunk lands on the SAME turn (no new pin).
    rerender(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "hi"), assistantMsg("a1", "streaming…")],
          isStreaming: true,
          streamingContent: "partial answer",
        })}
      />,
    );

    // Bottom follow is INSTANT — no stacked smooth animations (fixes footer jank).
    expect(spy).toHaveBeenCalledWith({ behavior: "auto" });
    expect(spy).not.toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" }),
    );
  });

  it("does NOT follow the bottom right after pinning a new question (question stays visible)", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    const { rerender } = render(
      <ChatPanel {...baseProps({ messages: [userMsg("u1", "hi")] })} />,
    );
    // Pin fired; follow is OFF. No scroll-to-bottom event simulated.
    spy.mockClear();

    // The reply streams in below the pinned question.
    rerender(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "hi"), assistantMsg("a1", "reply")],
          isStreaming: true,
          streamingContent: "grow",
        })}
      />,
    );

    // With follow OFF the lane never yanks to the bottom — the question stays put.
    expect(spy).not.toHaveBeenCalledWith({ behavior: "auto" });
  });
});
