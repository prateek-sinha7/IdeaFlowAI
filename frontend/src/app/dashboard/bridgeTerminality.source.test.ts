import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { applyTerminalStatus } from "@/hooks/useWorkflow";
import type { PipelineRunState } from "@/types";

// ─────────────────────────────────────────────────────────────────
// ISS-138 + ISS-157 — the FIX-201 legacy→store bridge must be
// TERMINALITY-PRESERVING, and dev's never-called `syncPipelineStateOnly`
// must be gone.
//
// WHY THIS IS A SOURCE-LOCK AND A SEMANTIC TEST, NOT A LIVE TEST: the visible
// symptom is already masked. FIX-245 works around ISS-138 by reconciling BOTH
// containers through `applyTerminalStatus`, so a live reopen of a cancelled run
// renders correctly on the pre-fix build too — verified by an A/B against a
// pre-fix frontend on 2026-08-13, 7 samples over 30s, identical on both. What
// the fix removes is the LATENT hazard the ISS-138 row names explicitly: "the
// hazard remains for the next person who patches store state directly."
//
// The original evidence (quick-260812-wir, live-instrumented): the store entry
// was seen flipping back to `isRunning:true` ~4s after being set false, with no
// handleFrame involved — the bridge's `() => pipelineState` total replacement
// copying stale legacy state over a store-only correction.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const storeSource = readFileSync(
  resolve(__dirname, "../../hooks/useRunStateStore.ts"),
  "utf8",
);
const collapsed = pageSource.replace(/\s+/g, " ");
const collapse = (s: string) => s.replace(/\s+/g, " ");

describe("ISS-138 — the legacy→store bridge preserves terminality", () => {
  it("derives the store's terminal verdict from its own explicit markers", () => {
    // FAIL-BEFORE: the reducer was `() => snapshot` — no reference to prev at all.
    expect(collapsed).toContain(
      collapse(`const storeTerminal =
          prev.cancelled ? "cancelled"
          : prev.failed ? "failed"
          : prev.degraded ? "degraded"
          : (reopened ?? "");`),
    );
  });

  it("re-applies that verdict through the SHARED applyTerminalStatus (INV-12)", () => {
    // FAIL-BEFORE: page.tsx never called applyTerminalStatus from inside the bridge,
    // so "terminal" had a second, implicit definition here (namely: none).
    expect(collapsed).toContain(
      collapse("return applyTerminalStatus(snapshot, storeTerminal);"),
    );
  });

  it("no longer does a blind wholesale replace", () => {
    // FAIL-BEFORE: this exact call was the ISS-138 defect.
    expect(collapsed).not.toContain(
      collapse("runStore.updatePipelineState(runId, () => snapshot);"),
    );
  });

  it("re-runs when the reopened run's server status changes", () => {
    // The reopen path is the one that arms this hazard: activelyBuildingRunIdRef is
    // only ever assigned — never cleared — and reopening from history assigns it, so
    // a TERMINAL run reaches the bridge. If reopenedRunStatus were not a dep the
    // effect would hold a stale `undefined` for a run reopened after the last frame.
    expect(collapsed).toContain(collapse("}, [pipelineState, reopenedRunStatus]);"));
  });
});

describe("ISS-157 — dev's never-called syncPipelineStateOnly is deleted", () => {
  it("is absent from the store implementation, interface and return", () => {
    // FAIL-BEFORE: 3 code occurrences — interface decl, useCallback impl, return
    // object. Asserted on CODE, not on the bare name: the tombstone comment that
    // records why it went still names it, and that comment is the point.
    const code = storeSource
      .replace(/\/\*[\s\S]*?\*\//g, "")      // block comments
      .replace(/^\s*\/\/.*$/gm, "");         // line comments
    expect(code).not.toContain("syncPipelineStateOnly:");        // interface member
    expect(code).not.toContain("const syncPipelineStateOnly");   // implementation
    expect(code).not.toContain("syncPipelineStateOnly,");        // return object
  });

  it("records WHY it was removed rather than deleting it silently", () => {
    expect(storeSource).toContain("ISS-157");
  });
});

describe("ISS-138 — the semantics the bridge now has", () => {
  const base: PipelineRunState = {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
  // What the legacy container hands the bridge on a reopened terminal run whose
  // terminal event was lost: it replayed the whole run and still thinks it is live.
  const staleLegacySnapshot: PipelineRunState = { ...base, isRunning: true };

  // The exact expression page.tsx now runs, exercised against the real helper.
  const bridge = (
    prev: PipelineRunState,
    snapshot: PipelineRunState,
    reopened?: string,
  ) => {
    const storeTerminal = prev.cancelled
      ? "cancelled"
      : prev.failed
        ? "failed"
        : prev.degraded
          ? "degraded"
          : (reopened ?? "");
    return applyTerminalStatus(snapshot, storeTerminal);
  };

  it("a stale 'still running' snapshot CANNOT resurrect a cancelled run", () => {
    const prev = { ...base, cancelled: true };
    const out = bridge(prev, staleLegacySnapshot);
    expect(out.isRunning).toBe(false);
    expect(out.cancelled).toBe(true);
  });

  it("likewise for failed and degraded", () => {
    expect(bridge({ ...base, failed: true }, staleLegacySnapshot).isRunning).toBe(false);
    expect(bridge({ ...base, degraded: true }, staleLegacySnapshot).isRunning).toBe(false);
  });

  it("a reopened run's persisted server status is honoured", () => {
    const out = bridge(base, staleLegacySnapshot, "completed");
    expect(out.isRunning).toBe(false);
  });

  it("a GENUINELY LIVE run still passes straight through — no over-blocking", () => {
    // The whole point of the bridge. A fresh entry carries isRunning:false too, so a
    // guard keyed on `isRunning` alone would freeze every real run at launch. The
    // markers/reopened-status signal is explicit precisely to avoid that.
    const out = bridge(base, staleLegacySnapshot);
    expect(out.isRunning).toBe(true);
  });

  it("a non-terminal reopened status is a no-op, not a stand-down", () => {
    const out = bridge(base, staleLegacySnapshot, "running");
    expect(out.isRunning).toBe(true);
  });
});
