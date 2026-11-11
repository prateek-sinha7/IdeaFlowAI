import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createLiveAnnouncer, type LiveAnnouncer } from "./liveAnnouncer";

describe("createLiveAnnouncer", () => {
  let messages: string[];
  let announcer: LiveAnnouncer;

  beforeEach(() => {
    vi.useFakeTimers();
    messages = [];
    announcer = createLiveAnnouncer((message) => messages.push(message));
  });

  afterEach(() => {
    announcer.dispose();
    vi.useRealTimers();
  });

  it("announces the first stage label at once", () => {
    announcer.stage("Reading the workflow");
    expect(messages).toEqual(["Reading the workflow"]);
  });

  it("announces at most one stage label per 3 s and the latest one wins", () => {
    announcer.stage("A");
    announcer.stage("B");
    announcer.stage("C");
    vi.advanceTimersByTime(2999);
    expect(messages).toEqual(["A"]);
    vi.advanceTimersByTime(1);
    expect(messages).toEqual(["A", "C"]);
  });

  it("announces a stage immediately once 3 s have passed since the last one", () => {
    announcer.stage("A");
    vi.advanceTimersByTime(3000);
    announcer.stage("B");
    expect(messages).toEqual(["A", "B"]);
  });

  it("does not repeat a label that was already announced", () => {
    announcer.stage("A");
    announcer.stage("A");
    announcer.stage("B");
    announcer.stage("A");
    vi.advanceTimersByTime(3000);
    expect(messages).toEqual(["A"]);
  });

  it("announces the applied-draft line without waiting for the throttle", () => {
    announcer.stage("A");
    announcer.draftApplied();
    expect(messages).toEqual(["A", "Workflow updated on the canvas"]);
  });

  it.each([
    ["finished", "Reply finished"],
    ["stopped", "Turn stopped"],
    ["failed", "Turn failed"],
  ] as const)("announces the %s turn-end line", (kind, line) => {
    announcer.turnEnded(kind);
    expect(messages).toEqual([line]);
  });

  it("drops a waiting stage label when the turn ends", () => {
    announcer.stage("A");
    announcer.stage("B");
    announcer.turnEnded("finished");
    vi.advanceTimersByTime(10000);
    expect(messages).toEqual(["A", "Reply finished"]);
  });

  it("drops a waiting stage label on dispose", () => {
    announcer.stage("A");
    announcer.stage("B");
    announcer.dispose();
    vi.advanceTimersByTime(10000);
    expect(messages).toEqual(["A"]);
  });
});
