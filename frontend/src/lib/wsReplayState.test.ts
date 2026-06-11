import { describe, expect, it } from "vitest";
import { shouldApplyEvent, resetReplayState } from "./wsReplayState";
import type { WaveGroup } from "@/types/index";

describe("shouldApplyEvent (CR-05 dedup-before-routing)", () => {
  it("applies the first delivery of an event_id and DROPS the second (no-op)", () => {
    const seen = new Set<string>();
    // First delivery → apply.
    expect(shouldApplyEvent(seen, "ev-1")).toBe(true);
    // Second delivery of the SAME id against the SAME set → drop (no-op).
    // This is the CR-05 contract: a replayed/doubly-delivered event applies
    // at most once. If shouldApplyEvent were reverted to always-true this FAILS.
    expect(shouldApplyEvent(seen, "ev-1")).toBe(false);
  });

  it("applies a distinct event_id", () => {
    const seen = new Set<string>();
    expect(shouldApplyEvent(seen, "ev-1")).toBe(true);
    expect(shouldApplyEvent(seen, "ev-2")).toBe(true);
  });

  it("applies an undefined event_id (legacy/unstamped pass-through, undeduped)", () => {
    const seen = new Set<string>();
    expect(shouldApplyEvent(seen, undefined)).toBe(true);
    // A second undefined still applies — legacy events are never deduped.
    expect(shouldApplyEvent(seen, undefined)).toBe(true);
  });

  it("applies an empty-string event_id as legacy (undeduped)", () => {
    const seen = new Set<string>();
    expect(shouldApplyEvent(seen, "")).toBe(true);
    expect(shouldApplyEvent(seen, "")).toBe(true);
  });
});

describe("resetReplayState (WR-03 per-run reset)", () => {
  it("clears the seen-set, zeroes last-seq, and empties wave groups", () => {
    const seen = new Set<string>(["ev-1", "ev-2"]);
    let lastSeq = 500;
    let waveGroups: WaveGroup[] = [
      { waveIndex: 0, taskIds: ["t1"], status: "completed", workers: [] },
    ];

    resetReplayState({
      seen,
      setLastSeq: (n) => {
        lastSeq = n;
      },
      setWaveGroups: (g) => {
        waveGroups = g;
      },
    });

    expect(seen.size).toBe(0);
    expect(lastSeq).toBe(0);
    expect(waveGroups).toEqual([]);
  });

  it("truly clears the dedup set so run 2 is not poisoned by run 1's ids", () => {
    const seen = new Set<string>();
    // Run 1: apply ev-1.
    expect(shouldApplyEvent(seen, "ev-1")).toBe(true);
    expect(shouldApplyEvent(seen, "ev-1")).toBe(false);

    // New run starts → reset.
    resetReplayState({
      seen,
      setLastSeq: () => {},
      setWaveGroups: () => {},
    });

    // Run 2: the SAME event_id is treated as new again (reset cleared it).
    expect(shouldApplyEvent(seen, "ev-1")).toBe(true);
  });
});
