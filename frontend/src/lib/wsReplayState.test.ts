import { describe, expect, it } from "vitest";
import { shouldApplyEvent, resetReplayState, resolveFrameRunId } from "./wsReplayState";
import type { WaveGroup } from "@/types/index";

describe("resolveFrameRunId (ISS-082 — the store-routing decision)", () => {
  it("prefers the per-stream _sourceRunId the SSE provider injects", () => {
    expect(
      resolveFrameRunId({ type: "agent_chunk", _sourceRunId: "run-A", data: { pipeline_run_id: "run-B" } }, "run-C"),
    ).toBe("run-A");
  });

  it("falls back to data.pipeline_run_id for the lifecycle frames that carry it", () => {
    expect(resolveFrameRunId({ type: "pipeline_start", data: { pipeline_run_id: "run-B" } }, "run-C")).toBe("run-B");
  });

  it("resolves a LIVE agent frame, which carries NEITHER key", () => {
    // THE regression this function exists for. `dashboard/page.tsx` subscribes with
    // `handleWebSocketMessage({ type: m.type, data: m.data }, m._sourceRunId)` — the
    // rebuilt message drops `_sourceRunId`, and agent payloads never carry
    // `pipeline_run_id`. The old inline expression saw only those two and returned
    // undefined, so the per-run store was never handed a live agent frame.
    expect(resolveFrameRunId({ type: "agent_chunk", data: { agent_id: "a1", chunk: "hi" } }, "run-C")).toBe("run-C");
  });

  it("resolves a REST-REPLAYED agent frame, which also carries neither key", () => {
    // The durable-replay callers pass the run id explicitly as the argument
    // (`handleWebSocketMessage({ type, data }, runId)`), which is the only identity a
    // replayed agent_* frame has. Losing it is what made FIX-201 add a second, undeduped
    // replay pass — the double delivery ISS-082 removes.
    expect(resolveFrameRunId({ type: "agent_start", data: { agent_id: "a1", seq: 4, event_id: "e4" } }, "run-R")).toBe("run-R");
  });

  it("returns undefined for a genuinely unattributable frame", () => {
    // Infra events (Concierge /messages) have no run at all; the guards downstream key on
    // that to pass them through, so an invented id would be worse than none.
    expect(resolveFrameRunId({ type: "chat_reply", data: {} }, undefined)).toBeUndefined();
  });

  it("ignores empty-string ids rather than adopting them as a run", () => {
    expect(resolveFrameRunId({ type: "agent_chunk", _sourceRunId: "", data: { pipeline_run_id: "" } }, "run-C")).toBe("run-C");
  });
});

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
