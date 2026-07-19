import { render, fireEvent, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import { ChatPanel, type ChatPanelProps } from "./ChatPanel";

// ─── ChatPanel — streaming-chat scroll manager (quick-260719-nwe) ─────────────
// The old effect fired scrollIntoView({behavior:"smooth"}) on the below-footer
// anchor on every [messages, streamingContent, isStreaming] change (~192×/stream),
// stacking smooth animations that janked the Run-summary footer. The behavior
// (chosen by the user): FOLLOW THE STREAM — keep the newest text in view as the
// reply generates, INSTANTLY (behavior:"auto", never smooth) so nothing stacks,
// and only while the user is near the bottom (a scroll-up flips following off so
// they are never yanked back down). Rows expose data-message-id (a stable test/
// debug hook). jsdom reports all scroll geometry as 0, so dist (0) < 120 → a lane
// starts "stuck to the bottom" unless we override the geometry.

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

  it("follows the stream INSTANTLY (behavior:\"auto\", never smooth or block:start) as the reply grows", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    const { rerender } = render(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question")],
          isStreaming: true,
          streamingContent: "partial",
        })}
      />,
    );
    spy.mockClear();

    // A streamed chunk grows the reply; at the bottom, the view follows the
    // newest text — instantly, so per-chunk updates never stack animations.
    rerender(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question"), assistantMsg("a1", "reply")],
          isStreaming: true,
          streamingContent: "partial answer",
        })}
      />,
    );

    expect(spy).toHaveBeenCalledWith({ behavior: "auto" });
    // Never a stacked smooth animation (the footer-jitter cause) and never the
    // old pin-to-top (the user chose follow-the-stream, not pinning).
    expect(spy).not.toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" }),
    );
    expect(spy).not.toHaveBeenCalledWith(
      expect.objectContaining({ block: "start" }),
    );
  });

  it("does NOT follow the bottom after the user scrolls up (respects their position)", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    const { container, rerender } = render(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question")],
          isStreaming: true,
          streamingContent: "partial",
        })}
      />,
    );
    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;

    // Simulate the user scrolling UP, away from the bottom: dist = 1000 - 0 - 300
    // = 700 ≥ 120, so the listener clears stickToBottom.
    Object.defineProperty(scrollEl, "scrollHeight", {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(scrollEl, "clientHeight", {
      value: 300,
      configurable: true,
    });
    Object.defineProperty(scrollEl, "scrollTop", {
      value: 0,
      configurable: true,
    });
    act(() => {
      fireEvent.scroll(scrollEl);
    });
    spy.mockClear();

    // A new chunk arrives, but the user is reading up-thread — do NOT yank them.
    rerender(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question"), assistantMsg("a1", "reply")],
          isStreaming: true,
          streamingContent: "partial answer",
        })}
      />,
    );

    expect(spy).not.toHaveBeenCalled();
  });

  it("forces scroll-to-bottom + re-arms following on a NEW user turn even after a scroll-up (Issue-1)", () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;

    const { container, rerender } = render(
      <ChatPanel {...baseProps({ messages: [userMsg("u1", "first")] })} />,
    );
    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;
    // User scrolls UP, away from the bottom (dist = 700 ≥ 120 → stickToBottom cleared).
    Object.defineProperty(scrollEl, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(scrollEl, "clientHeight", { value: 300, configurable: true });
    Object.defineProperty(scrollEl, "scrollTop", { value: 0, configurable: true });
    act(() => {
      fireEvent.scroll(scrollEl);
    });
    spy.mockClear();

    // User SENDS a new turn — even though they'd scrolled up, we scroll to the
    // bottom so their message + the incoming reply are visible (the Issue-1 fix).
    rerender(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "first"), userMsg("u2", "second question")],
        })}
      />,
    );

    expect(spy).toHaveBeenCalledWith({ behavior: "auto" });
  });
});
