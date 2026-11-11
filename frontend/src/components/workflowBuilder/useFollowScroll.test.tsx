import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { END_SLACK_PX, useFollowScroll } from "./useFollowScroll";

/** A ResizeObserver stand-in: the test fires the size change itself. */
class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  readonly observed: Element[] = [];
  disconnected = false;
  constructor(private readonly callback: () => void) {
    FakeResizeObserver.instances.push(this);
  }
  observe(target: Element) {
    this.observed.push(target);
  }
  unobserve() {}
  disconnect() {
    this.disconnected = true;
  }
  /** Report that the observed content grew. */
  grow() {
    this.callback();
  }
}

/** Give the scroller fixed geometry; jsdom does no layout. */
function setGeometry(element: HTMLElement, scrollHeight: number, clientHeight: number) {
  Object.defineProperty(element, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(element, "clientHeight", { configurable: true, value: clientHeight });
}

function Transcript() {
  const { scrollRef, contentRef, onScroll, scrollToEnd } = useFollowScroll();
  const [open, setOpen] = useState(true);
  return (
    <div>
      <button type="button" onClick={scrollToEnd}>
        Jump to end
      </button>
      <button type="button" onClick={() => setOpen((value) => !value)}>
        Toggle
      </button>
      {open ? (
        <div data-testid="scroller" ref={scrollRef} onScroll={onScroll}>
          <div ref={contentRef}>content</div>
        </div>
      ) : null}
    </div>
  );
}

const scroller = () => screen.getByTestId("scroller");
const lastObserver = () => FakeResizeObserver.instances.at(-1) as FakeResizeObserver;

beforeEach(() => {
  FakeResizeObserver.instances = [];
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useFollowScroll", () => {
  it("scrolls to the newest content while the reader is at the end", () => {
    render(<Transcript />);
    setGeometry(scroller(), 1000, 200);

    lastObserver().grow();

    expect(scroller().scrollTop).toBe(1000);
  });

  it("leaves the view alone once the reader scrolls up", () => {
    render(<Transcript />);
    setGeometry(scroller(), 1000, 200);
    scroller().scrollTop = 100;
    fireEvent.scroll(scroller());

    lastObserver().grow();

    expect(scroller().scrollTop).toBe(100);
  });

  it("keeps following when the reader stays within the slack of the end", () => {
    render(<Transcript />);
    setGeometry(scroller(), 1000, 200);
    scroller().scrollTop = 800 - END_SLACK_PX;
    fireEvent.scroll(scroller());
    setGeometry(scroller(), 1200, 200);

    lastObserver().grow();

    expect(scroller().scrollTop).toBe(1200);
  });

  it("pins the view to the end again on scrollToEnd", () => {
    render(<Transcript />);
    setGeometry(scroller(), 1000, 200);
    scroller().scrollTop = 100;
    fireEvent.scroll(scroller());

    fireEvent.click(screen.getByRole("button", { name: "Jump to end" }));
    expect(scroller().scrollTop).toBe(1000);

    setGeometry(scroller(), 1400, 200);
    lastObserver().grow();
    expect(scroller().scrollTop).toBe(1400);
  });

  it("stops observing a removed transcript and observes the one that replaces it", () => {
    render(<Transcript />);
    const first = lastObserver();

    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    expect(first.disconnected).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Toggle" }));
    const second = lastObserver();
    expect(second).not.toBe(first);
    expect(second.observed).toHaveLength(1);
  });

  it("does nothing without ResizeObserver", () => {
    vi.stubGlobal("ResizeObserver", undefined);
    render(<Transcript />);
    setGeometry(scroller(), 1000, 200);

    expect(scroller().scrollTop).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Jump to end" }));
    expect(scroller().scrollTop).toBe(1000);
  });
});
