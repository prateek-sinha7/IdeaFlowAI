import { render, fireEvent, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/types/index";
import { ChatPanel, type ChatPanelProps } from "./ChatPanel";

// ─── ChatPanel — streaming-chat scroll manager (quick-260719-nwe / -rqo) ──────
// Continuous stream-following is owned by a ResizeObserver on the transcript
// content wrapper (quick-260719-rqo): it pins the bottom on ANY rendered-height
// change while the user is following, so BOTH the chunk clock (props change) and
// the typewriter clock (useSmoothText grows the reply height between chunks, with
// no props change) follow through ONE path. That single path is what removes the
// Run-summary footer jitter — before the fix the follow effect only fired on
// chunk arrivals, so the footer drifted down between chunks then snapped back up.
// A separate effect still handles the "user just SENT a new turn" case: it forces
// scrollIntoView({behavior:"auto"}) on the below-footer anchor and re-arms follow.
// A scroll-up flips following off (near-bottom <120px gate) so nobody is yanked.
// jsdom has no native ResizeObserver / scrollIntoView, so tests stub them.

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

// Capture the ResizeObserver callback the panel installs so a test can drive a
// "height changed" tick (a chunk OR a typewriter frame) by hand.
let roCallback: (() => void) | null = null;
function stubResizeObserver() {
  roCallback = null;
  class MockResizeObserver {
    constructor(cb: () => void) {
      roCallback = cb;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
}

// Give a jsdom element real read/write scroll geometry (jsdom reports 0 and makes
// scrollHeight/clientHeight read-only). Returns a live view of scrollTop.
function primeScrollGeometry(
  el: HTMLElement,
  { scrollHeight, clientHeight, scrollTop }: {
    scrollHeight: number;
    clientHeight: number;
    scrollTop: number;
  },
) {
  let top = scrollTop;
  Object.defineProperty(el, "scrollHeight", {
    value: scrollHeight,
    configurable: true,
  });
  Object.defineProperty(el, "clientHeight", {
    value: clientHeight,
    configurable: true,
  });
  Object.defineProperty(el, "scrollTop", {
    get: () => top,
    set: (v: number) => {
      top = v;
    },
    configurable: true,
  });
  return { get: () => top };
}

describe("ChatPanel scroll manager", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    roCallback = null;
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

  it("does not throw when ResizeObserver / scrollIntoView are unavailable (jsdom guard)", () => {
    // No ResizeObserver, no scrollIntoView — both guarded effects must degrade.
    expect(() =>
      render(<ChatPanel {...baseProps({ messages: [userMsg("u1", "hi")] })} />),
    ).not.toThrow();
  });

  it("pins the transcript bottom on a rendered-height change while the user is following (the RO follow path)", () => {
    stubResizeObserver();

    const { container } = render(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question"), assistantMsg("a1", "reply")],
          isStreaming: true,
          streamingContent: "partial answer",
        })}
      />,
    );

    // The panel installed its ResizeObserver on mount (default stickToBottom=true).
    expect(roCallback).toBeInstanceOf(Function);

    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;
    const view = primeScrollGeometry(scrollEl, {
      scrollHeight: 1000,
      clientHeight: 300,
      scrollTop: 0,
    });

    // A height change (chunk OR typewriter frame) fires the observer → pin bottom.
    act(() => {
      roCallback!();
    });

    expect(view.get()).toBe(1000); // scrollTop pinned to scrollHeight
  });

  it("follows a TYPEWRITER FRAME (height grows with NO messages/streamingContent change) — the jitter fix", () => {
    // The regression: between chunks, useSmoothText grows the reply height on the
    // rAF clock with NO prop change, so the old chunk-only follow effect missed it
    // and the footer drifted. Here we drive the RO callback WITHOUT any rerender —
    // exactly a typewriter frame — and assert the bottom is still pinned. Before
    // the fix there was no RO at all (roCallback would be null → RED); after, it
    // pins (GREEN).
    stubResizeObserver();

    const { container } = render(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question"), assistantMsg("a1", "re")],
          isStreaming: true,
          streamingContent: "re",
        })}
      />,
    );

    expect(roCallback).toBeInstanceOf(Function);

    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;
    const view = primeScrollGeometry(scrollEl, {
      scrollHeight: 1400,
      clientHeight: 300,
      scrollTop: 500,
    });

    // No rerender — only the observer ticks (rendered height grew a typewriter
    // frame). The single follow path pins the bottom.
    act(() => {
      roCallback!();
    });

    expect(view.get()).toBe(1400);
  });

  it("does NOT pin the bottom via the RO after the user scrolls up (respects their position)", () => {
    stubResizeObserver();

    const { container } = render(
      <ChatPanel
        {...baseProps({
          messages: [userMsg("u1", "my question"), assistantMsg("a1", "reply")],
          isStreaming: true,
          streamingContent: "partial",
        })}
      />,
    );
    expect(roCallback).toBeInstanceOf(Function);

    const scrollEl = container.querySelector(
      '[data-testid="chat-transcript"]',
    ) as HTMLElement;
    // User scrolled UP: dist = 1000 - 42 - 300 = 658 ≥ 120 → listener clears
    // stickToBottom. Their current scrollTop (42) must be left untouched.
    const view = primeScrollGeometry(scrollEl, {
      scrollHeight: 1000,
      clientHeight: 300,
      scrollTop: 42,
    });
    act(() => {
      fireEvent.scroll(scrollEl);
    });

    // A chunk/typewriter height change ticks the observer — but we do NOT yank
    // the reader who scrolled away.
    act(() => {
      roCallback!();
    });

    expect(view.get()).toBe(42); // unchanged, not pinned to scrollHeight
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
