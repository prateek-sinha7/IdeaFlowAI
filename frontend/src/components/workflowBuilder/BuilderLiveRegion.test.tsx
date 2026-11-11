import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BuilderLiveRegion } from "./BuilderLiveRegion";
import type { RunningTurnView, TurnView } from "./builderReducer";
import { STAGE_INTERVAL_MS } from "./liveAnnouncer";

function running(label: string, text = ""): RunningTurnView {
  return {
    kind: "running",
    turnId: "t1",
    origin: "this_tab",
    stage: "thinking",
    label,
    startedAt: 0,
    lastSeq: 0,
    activity: [],
    checks: [],
    warnings: [],
    text,
    thinking: "",
    pendingDraft: null,
  };
}

const IDLE: TurnView = { kind: "idle" };
const ENDED: TurnView = {
  kind: "ended",
  turnId: "t1",
  status: "completed",
  outcome: "reply",
  stopReason: null,
};

function region(container: HTMLElement): HTMLElement {
  const el = container.querySelector<HTMLElement>('[aria-live="polite"]');
  if (el === null) throw new Error("live region missing");
  return el;
}

describe("BuilderLiveRegion", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders one polite, visually hidden status element that starts empty", () => {
    const { container } = render(<BuilderLiveRegion turn={IDLE} draftRevision={0} />);
    const el = region(container);
    expect(container.querySelectorAll("[aria-live]")).toHaveLength(1);
    expect(el).toHaveAttribute("role", "status");
    expect(el).toHaveClass("sr-only");
    expect(el).toHaveTextContent("");
  });

  it("announces the stage label when a turn starts", () => {
    const { container, rerender } = render(<BuilderLiveRegion turn={IDLE} draftRevision={0} />);
    rerender(<BuilderLiveRegion turn={running("Reading the catalog")} draftRevision={0} />);
    expect(region(container)).toHaveTextContent("Reading the catalog");
  });

  it("does not announce streamed text", () => {
    const { container, rerender } = render(
      <BuilderLiveRegion turn={running("Writing the workflow")} draftRevision={0} />,
    );
    rerender(
      <BuilderLiveRegion
        turn={running("Writing the workflow", "SECRET streamed words")}
        draftRevision={0}
      />,
    );
    expect(region(container)).toHaveTextContent("Writing the workflow");
    expect(region(container)).not.toHaveTextContent("SECRET");
  });

  it("holds a second stage label until the 3 s interval has passed", () => {
    const { container, rerender } = render(<BuilderLiveRegion turn={IDLE} draftRevision={0} />);
    rerender(<BuilderLiveRegion turn={running("Reading")} draftRevision={0} />);
    rerender(<BuilderLiveRegion turn={running("Checking")} draftRevision={0} />);
    expect(region(container)).toHaveTextContent("Reading");
    act(() => {
      vi.advanceTimersByTime(STAGE_INTERVAL_MS);
    });
    expect(region(container)).toHaveTextContent("Checking");
  });

  it("announces the applied draft while a turn runs", () => {
    const { container, rerender } = render(
      <BuilderLiveRegion turn={running("Applying")} draftRevision={1} />,
    );
    rerender(<BuilderLiveRegion turn={running("Applying")} draftRevision={2} />);
    expect(region(container)).toHaveTextContent("Workflow updated on the canvas");
  });

  it("does not announce a draft that was already there when a session loaded", () => {
    const { container, rerender } = render(<BuilderLiveRegion turn={IDLE} draftRevision={0} />);
    rerender(<BuilderLiveRegion turn={IDLE} draftRevision={3} />);
    expect(region(container)).toHaveTextContent("");
  });

  it("announces the turn-end line when a running turn ends", () => {
    const { container, rerender } = render(
      <BuilderLiveRegion turn={running("Responding")} draftRevision={0} />,
    );
    rerender(<BuilderLiveRegion turn={ENDED} draftRevision={0} />);
    expect(region(container)).toHaveTextContent("Reply finished");
  });

  it("re-renders the node for a repeated line so it is spoken again", () => {
    const { container, rerender } = render(
      <BuilderLiveRegion turn={running("Responding")} draftRevision={0} />,
    );
    rerender(<BuilderLiveRegion turn={ENDED} draftRevision={0} />);
    const first = region(container).firstElementChild;
    rerender(<BuilderLiveRegion turn={{ ...running("Responding"), turnId: "t2" }} draftRevision={0} />);
    rerender(
      <BuilderLiveRegion turn={{ ...ENDED, turnId: "t2" }} draftRevision={0} />,
    );
    const second = region(container).firstElementChild;
    expect(second).toHaveTextContent("Reply finished");
    expect(second).not.toBe(first);
  });
});
