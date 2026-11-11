"use client";

/**
 * useFollowScroll: keeps the Builder transcript at its newest content while the
 * reader is at the end, and leaves it alone once they scroll up (design 3.10.5).
 *
 * Attach `scrollRef` and `onScroll` to the scrolling element and `contentRef` to
 * the element inside it whose height grows as messages, streamed text and
 * activity arrive. A `ResizeObserver` on the content scrolls to the end on every
 * growth while the reader is within `END_SLACK_PX` of it. `scrollToEnd` pins the
 * view again, for example when the user sends a message.
 *
 * `contentRef` is a callback ref, so a panel that collapses and reopens (new
 * elements) is observed again. Without `ResizeObserver` (jsdom) it does nothing.
 */

import { useCallback, useRef, type RefCallback, type RefObject } from "react";

/**
 * Within this distance of the end, the reader counts as following the conversation.
 * The run chat's `ChatPanel` uses the same 120 px gate.
 */
export const END_SLACK_PX = 120;

export interface FollowScroll {
  scrollRef: RefObject<HTMLDivElement | null>;
  contentRef: RefCallback<HTMLElement>;
  onScroll: () => void;
  scrollToEnd: () => void;
}

export function useFollowScroll(): FollowScroll {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const followingRef = useRef(true);

  const jumpToEnd = useCallback(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, []);

  const onScroll = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
    followingRef.current = distance <= END_SLACK_PX;
  }, []);

  const scrollToEnd = useCallback(() => {
    followingRef.current = true;
    jumpToEnd();
  }, [jumpToEnd]);

  const contentRef = useCallback<RefCallback<HTMLElement>>(
    (node) => {
      if (node === null || typeof ResizeObserver === "undefined") return;
      // A freshly mounted transcript opens at its end.
      followingRef.current = true;
      const observer = new ResizeObserver(() => {
        if (followingRef.current) jumpToEnd();
      });
      observer.observe(node);
      return () => observer.disconnect();
    },
    [jumpToEnd],
  );

  return { scrollRef, contentRef, onScroll, scrollToEnd };
}
