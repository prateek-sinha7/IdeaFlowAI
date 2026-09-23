/**
 * ISS-126 — a reopened TERMINAL run whose durable log has no terminal event
 * must still render as terminal.
 *
 * A run cancelled through one of the app-layer driver terminals (ISS-124) — or
 * corrupted by the pre-FIX-240 seq collision (ISS-121/ISS-123) — has a durable
 * `run_events` log that simply STOPS, often on a `review_gate_ready`. On reopen
 * the dashboard replays that log through the page router, so nothing ever sets
 * `isRunning:false` and the screen renders the run as live: header "Awaiting
 * approval", an armed Stop button and armed gate cards on a run that ended.
 *
 * The render chain (verified at ce2db22e) makes ONE state change sufficient —
 * every affected surface is AND-ed with `isRunning`:
 *   page.tsx:2494        displayedPipelineState = runStore.viewed.pipelineState
 *   DashboardLayout:806  isPipelineRunning = pipelineState?.isRunning
 *   DashboardLayout:1866 reviewGateData && isPipelineRunning ? "gate" : …
 *                  :1869 (failed || cancelled || degraded) ? "terminal"
 *   RunChatLane:1067     Stop derives isRunning from runState alone
 *   StepsOverviewSpine   gate cards gate on pipelineState.isRunning
 * so `isRunning:false` + the matching marker flips "gate" → "terminal", which
 * yields the "Cancelled" header and removes Stop and the gate cards together.
 * Clearing `reviewGateData` instead would be WORSE than nothing: runLaneState
 * would fall to "building" → header "Running", Stop still present.
 *
 * INV-12: `terminalMarkers` is the SINGLE definition of what a terminal status
 * does to the run state. The three live terminal event cases route through it,
 * so this fix REDUCES the number of places that decide "what terminal looks
 * like" from three to one rather than adding a fourth.
 */
import { describe, expect, it } from "vitest";
import { applyTerminalStatus, handlePipelineMessage, terminalMarkers } from "../useWorkflow";
import type { AgentRunState, PipelineRunState } from "@/types/index";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

function makeAgent(id: string, status: AgentRunState["status"]): AgentRunState {
  return {
    id, name: id, role: "test", icon: "🤖", status,
    output: "", thinking: "", duration: null, error: null, index: 0,
  };
}

/** A run paused at a review gate: still "running", one agent mid-flight. */
function gatedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "user_stories",
    pipelineRunId: "run-808612bf",
    agents: [makeAgent("domain-analyst", "running"), makeAgent("epic-architect", "done")],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 1,
  };
}

describe("terminalMarkers — the single terminal-marker vocabulary (ISS-126)", () => {
  it("cancelled resolves isRunning and stamps the cancelled marker", () => {
    expect(terminalMarkers("cancelled")).toEqual({ isRunning: false, cancelled: true });
  });

  it("failed stamps the failed marker", () => {
    expect(terminalMarkers("failed")).toEqual({ isRunning: false, failed: true });
  });

  it("degraded stamps the degraded marker", () => {
    expect(terminalMarkers("degraded")).toEqual({ isRunning: false, degraded: true });
  });

  it("completed resolves isRunning with no failure marker", () => {
    expect(terminalMarkers("completed")).toEqual({ isRunning: false });
  });
});

describe("applyTerminalStatus — reopen reconciliation (ISS-126)", () => {
  it("flips a gate-paused run to terminal-cancelled and stands the agents down", () => {
    const next = applyTerminalStatus(gatedState(), "cancelled");

    // The one state change every affected surface is AND-ed with.
    expect(next.isRunning).toBe(false);
    expect(next.cancelled).toBe(true);
    // The mid-flight agent stops animating; the finished one is untouched.
    expect(next.agents.find((a) => a.id === "domain-analyst")?.status).toBe("idle");
    expect(next.agents.find((a) => a.id === "epic-architect")?.status).toBe("done");
    expect(next.completedCount).toBe(1);
  });

  it("resolves a completed run's still-animating agents to done", () => {
    const next = applyTerminalStatus(gatedState(), "completed");
    expect(next.isRunning).toBe(false);
    expect(next.agents.every((a) => a.status === "done")).toBe(true);
    expect(next.completedCount).toBe(2);
    expect(next.cancelled).toBeUndefined();
  });

  it("is a no-op for a NON-terminal status — directionality is one-way", () => {
    // Terminal status forces terminal UI; a non-terminal status must NEVER force
    // non-terminal UI, or a slow getWorkflow on a live run would clear a
    // legitimately open gate.
    const prev = gatedState();
    expect(applyTerminalStatus(prev, "running")).toBe(prev);
  });

  it("does not disturb a stale reviewGateData — it MASKS it via isRunning", () => {
    // The gate row stays in the store; runLaneState's "gate" branch requires
    // `&& isPipelineRunning`, so resolving isRunning is what hides it.
    const next = applyTerminalStatus(gatedState(), "cancelled");
    expect(next.isRunning).toBe(false);
    expect(next.cancelled).toBe(true);
  });
});

describe("INV-12 — the live terminal events ROUTE THROUGH terminalMarkers", () => {
  const source = readFileSync(resolve(__dirname, "..", "useWorkflow.ts"), "utf8");
  const collapsed = source.replace(/\s+/g, " ");

  it("defines terminalMarkers exactly once", () => {
    expect((source.match(/export function terminalMarkers/g) || []).length).toBe(1);
  });

  it("pipeline_cancelled spreads terminalMarkers rather than re-declaring the marker", () => {
    expect(collapsed).toContain('...terminalMarkers("cancelled")');
  });

  it("pipeline_failed spreads terminalMarkers", () => {
    expect(collapsed).toContain('...terminalMarkers("failed")');
  });

  it("pipeline_complete spreads terminalMarkers, degraded-aware", () => {
    expect(collapsed).toContain('...terminalMarkers(isDegraded ? "degraded" : "completed")');
  });

  it("the marker map's membership equals page.tsx's REOPEN_TERMINAL_STATUSES", () => {
    // The gate (page.tsx:64) and the mapping (useWorkflow.ts) are separate
    // structures — this pins them EQUAL so they cannot drift into the fifth
    // divergent terminal-status list INV-12 exists to prevent. Both must also
    // match the backend's TERMINAL_STATUSES (chat_router.py).
    const page = readFileSync(
      resolve(__dirname, "..", "..", "app", "[...view]", "page.tsx"),
      "utf8",
    );
    const gate = page.match(/REOPEN_TERMINAL_STATUSES = new Set\(\[([^\]]*)\]\)/);
    expect(gate).not.toBeNull();
    const gateSet = (gate![1].match(/"([a-z]+)"/g) || []).map((s) => s.replace(/"/g, "")).sort();

    const map = source.match(
      /const TERMINAL_MARKER_BY_STATUS: Record<[^>]*> = \{([\s\S]*?)\};/,
    );
    expect(map).not.toBeNull();
    const mapKeys = (map![1].match(/^\s*([a-z]+):/gm) || [])
      .map((s) => s.replace(/[^a-z]/g, ""))
      .sort();

    expect(mapKeys).toEqual(gateSet);
    expect(mapKeys).toEqual(["cancelled", "completed", "degraded", "diverted", "failed"]);
  });

  it("behavioural proof of the routing: the EVENT still yields the same markers", () => {
    // A copy would drift; this pins the event path and the status path to the
    // same vocabulary. Drives handlePipelineMessage exactly as the ISS-035 suite does.
    let state = gatedState();
    const setPipelineState = ((updater: unknown) => {
      state = typeof updater === "function"
        ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
        : (updater as PipelineRunState);
    }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;

    handlePipelineMessage(
      { type: "pipeline_cancelled", duration: 1 },
      setPipelineState,
      { current: {} as Record<string, number> },
    );

    expect(state.isRunning).toBe(false);
    expect(state.cancelled).toBe(true);
    // and it agrees with the status path on the same run
    const viaStatus = applyTerminalStatus(gatedState(), "cancelled");
    expect(viaStatus.isRunning).toBe(state.isRunning);
    expect(viaStatus.cancelled).toBe(state.cancelled);
  });
});
