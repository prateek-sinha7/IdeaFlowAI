"use client";

/**
 * useRunStateStore — per-run state store for concurrent pipeline isolation.
 *
 * PROBLEM THIS SOLVES:
 * The dashboard had a single set of React state variables (pipelineState,
 * questionnaireData, reviewGateData, waveGroups, content, submittedBrief, etc.)
 * shared across ALL concurrent runs. When 3 PPT + User Stories runs are active,
 * SSE frames from all runs share one reducer, causing cross-contamination:
 *   - PPT clarify questions showing in User Stories Steps panel
 *   - User Stories agents showing in PPT run
 *   - Review gates from one run blocking another
 *   - Switching via badge showing wrong questions/agents/content
 *
 * TRANSPORT: SSE down-channel (GET /api/runs/{id}/events/stream via run_stream.py)
 *            + REST up-channel (POST /api/runs/{id}/gate|answers|cancel|messages)
 *            RunConnectionProvider fans out SSE frames to handleWebSocketMessage
 *            with _sourceRunId stamped per stream.
 *
 * SOLUTION — Run-Scoped State Store (Viewport Pattern):
 *   1. Every run has its own PerRunState entry in a Map<runId, PerRunState>
 *   2. SSE frames ALWAYS write to store.update(sourceRunId, ...) — never dropped
 *   3. The "viewport" (viewedRunId) decides which run's state the UI sees
 *   4. switchViewTo(newRunId): instantly project the new run's state to React
 *   5. No guards, no races, no timing holes — isolation is structural
 *
 * USAGE:
 *   const store = useRunStateStore();
 *
 *   // On SSE frame arrival for any run (sourceRunId from _sourceRunId injection):
 *   store.update(sourceRunId, { questionnaireData: mapped });
 *
 *   // On badge/notification click (switch viewport):
 *   store.switchViewTo(runId);
 *
 *   // Render using projected state:
 *   const { pipelineState, questionnaireData, reviewGateData } = store.viewed;
 */

import { useCallback, useRef, useState } from "react";
import type React from "react";
import type { PipelineRunState, WorkflowType, RunFamily } from "@/types/index";
import { deriveSpecRevisionCount, handlePipelineMessage } from "@/hooks/useWorkflow";

// ─── Per-run state shape ───────────────────────────────────────────────────────

export interface PerRunState {
  // Identity
  runId: string;
  runType: WorkflowType | null;

  // Pipeline execution state (drives Steps/Agents panel + runLaneState)
  pipelineState: PipelineRunState;

  // Wave/subagent tree (Steps drill-down)
  waveGroups: WaveGroup[];

  // Clarify gate state (drives clarify form in Steps)
  questionnaireData: QuestionnaireData | null;

  // Review gate state (drives approval panel in Steps)
  reviewGateData: ReviewGateData | null;

  // The run id that is paused at the clarify gate (for answer submission routing)
  activePipelineRunId: string | null;

  // Deliverable content (drives Preview panel)
  userStoryContent: string;
  pptContent: string;
  prototypeContent: string;
  genericDeliverable: GenericDeliverable | undefined;

  // Run input brief (drives Starting point card)
  submittedBrief: string;

  // Run family for version timeline
  runFamily: RunFamily | null;

  // ISS-063 — which spec-revision cycle this run is in, derived from the pipeline
  // head's entry in pipelineState.agentStartEventIds. Written in exactly one place
  // (handleFrame); the arm/consume detector that used to compute this in page.tsx
  // is deleted, not shadowed.
  specRevisionCount: number;

  // Terminal state (history reopen)
  reopenedRunStatus: string | undefined;
  reopenedFailedAgents: FailedAgent[] | undefined;
  reopenedAgentNameById: Record<string, string> | undefined;

  // Last cancelled run (for Run Again)
  lastCancelledRunId: string | null;
}

// ─── Supporting types ──────────────────────────────────────────────────────────

export interface QuestionnaireData {
  questions: Array<{
    id: string;
    question: string;
    options: string[];
    answerType?: string;
    recommendedAnswer?: string;
    recommendedReasoning?: string;
    recommendedDisplay?: string;
    ambiguityCategory?: string;
    impactLevel?: string;
  }>;
}

export interface ReviewGateData {
  gateKey: string;
  agentId: string;
  agentName: string;
  output: string;
  pipelineRunId: string;
  redoable?: boolean;
  updateSpecsEligible?: boolean;
  artifactKind?: string;
  // ISS-052: the per-FIRING revision discriminator. Held per-run so a gate re-opened
  // after a spec-revision pass is still identifiable when the run is re-projected.
  revisionCycle?: number;
  revisionInFlight?: boolean;
}

export interface WaveGroup {
  waveIndex: number;
  step?: string;
  taskIds: string[];
  status: string;
  workers: Array<{ agent: string; status: string; worker?: number }>;
}

export interface GenericDeliverable {
  content: string;
  mimeType?: string;
  filename?: string;
}

export interface FailedAgent {
  id: string;
  name: string;
  error?: string;
}

// ─── Initial per-run state ─────────────────────────────────────────────────────

const INITIAL_PIPELINE_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  clarifications: [],
};

export function makeInitialRunState(runId: string): PerRunState {
  return {
    runId,
    runType: null,
    pipelineState: { ...INITIAL_PIPELINE_STATE },
    waveGroups: [],
    questionnaireData: null,
    reviewGateData: null,
    activePipelineRunId: null,
    userStoryContent: "",
    pptContent: "",
    prototypeContent: "",
    genericDeliverable: undefined,
    submittedBrief: "",
    runFamily: null,
    specRevisionCount: 0,
    reopenedRunStatus: undefined,
    reopenedFailedAgents: undefined,
    reopenedAgentNameById: undefined,
    lastCancelledRunId: null,
  };
}

// ─── Partial update type ───────────────────────────────────────────────────────

export type PerRunStateUpdate = Partial<Omit<PerRunState, "runId">>;

// ─── Store return type ─────────────────────────────────────────────────────────

export interface RunStateStoreReturn {
  /** The currently projected (viewed) run state — what the UI renders */
  viewed: PerRunState;

  /** The ID of the run currently in the viewport */
  viewedRunId: string | null;

  /**
   * Process a pipeline SSE frame for a specific run.
   * Uses handlePipelineMessage (from useWorkflow) to update that run's pipelineState.
   * Also handles waveGroups updates for wave_* / subagent_* event types.
   * If runId === viewedRunId, also projects the updated state to React (re-renders UI).
   * If runId !== viewedRunId, stores silently — no re-render (background run).
   * 
   * This is the PRIMARY entry point for all pipeline SSE frames. Replace all
   * handlePipelineMsgRef.current() calls with store.handleFrame(sourceRunId, msg).
   */
  handleFrame: (runId: string, msg: { type: string; [key: string]: unknown }) => void;

  /**
   * Update state for a specific run in the map (for non-pipeline state:
   * questionnaireData, reviewGateData, submittedBrief, content, etc.).
   * If runId === viewedRunId, also projects the update to React state (re-renders UI).
   * If runId !== viewedRunId, stores silently — no re-render (background run).
   */
  update: (runId: string, patch: PerRunStateUpdate) => void;

  /**
   * Update pipelineState for a specific run using a reducer function.
   * Necessary for immutable array updates (agents, clarifications, etc.)
   */
  updatePipelineState: (runId: string, reducer: (prev: PipelineRunState) => PipelineRunState) => void;

  /**
   * Update waveGroups for a specific run using a reducer function.
   */
  updateWaveGroups: (runId: string, reducer: (prev: WaveGroup[]) => WaveGroup[]) => void;

  /**
   * Switch the viewport to a different run.
   * Projects that run's stored state to React state immediately (synchronous).
   * If the run has no entry yet, creates one with initial state.
   */
  switchViewTo: (runId: string) => void;

  /**
   * Initialize or reset a run's state entry (called on launch or replay start).
   * If viewedRunId === runId, also re-projects to UI.
   */
  initRun: (runId: string, initialState?: Partial<PerRunState>) => void;

  /**
   * Get raw state for a run without affecting the viewport.
   * Returns undefined if the run has no entry.
   */
  get: (runId: string) => PerRunState | undefined;

  /**
   * Check if a run entry exists in the store.
   */
  has: (runId: string) => boolean;

  /**
   * Remove a run's state entry (called on terminal completion / cleanup).
   */
  remove: (runId: string) => void;
}

// ─── Hook implementation ───────────────────────────────────────────────────────

/**
 * useRunStateStore — per-run state store implementing the viewport pattern.
 *
 * The store is a Map<runId, PerRunState> held in a ref (no re-render on writes
 * to background runs). A separate React state (viewedState) holds the projected
 * copy of the currently-viewed run's state — this IS React state and triggers
 * re-renders when updated.
 *
 * Architecture:
 *   Map[runA] ─── background, no re-renders on write
 *   Map[runB] ─── background, no re-renders on write
 *   Map[runC] ─── VIEWED ──── writes ALSO update viewedState (React, re-renders)
 *                             ↓
 *                         <UI renders runC's state>
 */
export function useRunStateStore(): RunStateStoreReturn {
  // The actual per-run store — a ref so background run updates don't re-render.
  const storeRef = useRef<Map<string, PerRunState>>(new Map());

  // Per-run agent start time refs (needed by handlePipelineMessage for duration calc).
  // Keyed by runId, each value is a Record<agentId, startTimeMs>.
  const agentStartTimesMapRef = useRef<Map<string, React.MutableRefObject<Record<string, number>>>>(new Map());

  // Which run is currently in the viewport.
  //
  // Kept as a REF for all internal reads: frame handling mutates and reads it
  // synchronously within a single SSE frame, so it must not lag behind a React
  // state flush (a stale read here would project the wrong run's state).
  const viewedRunIdRef = useRef<string | null>(null);
  // ...and mirrored into STATE purely for the value this hook returns. Returning
  // `viewedRunIdRef.current` directly is a render-time ref read
  // (react-hooks/refs): React does not re-render when a ref mutates, so any
  // consumer reading `viewedRunId` would silently keep the value from whichever
  // render it last happened to run in. The two are written together in
  // `setViewedRun` below so they can never diverge.
  const [viewedRunId, setViewedRunIdState] = useState<string | null>(null);

  // The single writer for the viewed-run pair — keeps ref (sync) and state
  // (render-safe) in lockstep. Never assign `viewedRunIdRef.current` directly.
  const setViewedRun = useCallback((runId: string | null) => {
    viewedRunIdRef.current = runId;
    setViewedRunIdState(runId);
  }, []);

  // The projected React state — triggers re-renders when the viewed run updates.
  const [viewedState, setViewedState] = useState<PerRunState>(() =>
    makeInitialRunState("__initial__")
  );

  // FIX-224: track the last pipelineState reference that was projected so we can
  // skip project() when the fakeSetState result is unchanged. Without this, the
  // bail-out in project() never fires because handleFrame always spreads entry into
  // a new outer object (`{ ...entry }`), making prev !== state at the outer level
  // even when pipelineState itself didn't change. This caused setViewedState to fire
  // on every SSE frame → rapid re-renders → flickering agent circles and L2 views.
  const lastProjectedPipelineStateRef = useRef<object | null>(null);

  // ── Internal helpers ─────────────────────────────────────────────────────────

  const getOrCreate = useCallback((runId: string): PerRunState => {
    if (!storeRef.current.has(runId)) {
      storeRef.current.set(runId, makeInitialRunState(runId));
    }
    return storeRef.current.get(runId)!;
  }, []);

  const getAgentStartTimes = useCallback((runId: string): React.MutableRefObject<Record<string, number>> => {
    if (!agentStartTimesMapRef.current.has(runId)) {
      agentStartTimesMapRef.current.set(runId, { current: {} });
    }
    return agentStartTimesMapRef.current.get(runId)!;
  }, []);

  // Project a run's state to React (triggers re-render).
  // Uses Object.assign to create a new outer object but only triggers re-render
  // if the state object reference changes (which it always does here for simplicity;
  // React 18 batches multiple setViewedState calls within the same flush cycle).
  const project = useCallback((state: PerRunState) => {
    setViewedState((prev) => {
      // Bail out if pipelineState and key visible fields are reference-equal.
      // This prevents infinite re-render loops when project() is called on every
      // SSE frame even if the viewed state didn't meaningfully change.
      if (
        prev.pipelineState === state.pipelineState &&
        prev.questionnaireData === state.questionnaireData &&
        prev.reviewGateData === state.reviewGateData &&
        prev.waveGroups === state.waveGroups &&
        prev.runId === state.runId
      ) {
        return prev; // bail out — React won't re-render
      }
      return { ...state };
    });
  }, []);

  // ── Public API ───────────────────────────────────────────────────────────────

  /**
   * handleFrame — route a pipeline SSE frame to the correct run's pipelineState.
   * This replaces the old single-run handlePipelineMsgRef.current() call.
   * Uses handlePipelineMessage (from useWorkflow) as the per-run reducer.
   * Also handles wave_* / subagent_* events for per-run waveGroups.
   */
  const handleFrame = useCallback((runId: string, msg: { type: string; [key: string]: unknown }) => {
    const entry = getOrCreate(runId);
    const agentStartTimes = getAgentStartTimes(runId);

    // Auto-set viewport on first pipeline_start if no run is currently viewed.
    // This covers the async launch window: the POST .then() (which calls switchViewTo)
    // may not have resolved yet when the first SSE frames arrive. Without this,
    // agent frames accumulate in the store but never project to the UI.
    // Note: the primary path is the pre-registration in pipeline_start handler
    // (handleWebSocketMessage) which calls runStoreSwitchViewToRef.current() directly.
    // This auto-set only handles the null case (very first run of the session).
    if (msg.type === "pipeline_start" && viewedRunIdRef.current === null) {
      setViewedRun(runId);
    }
    const WAVE_EVENT_TYPES = [
      "wave_started", "wave_completed", "wave_failed",
      "subagent_spawned", "subagent_result",
    ];
    if (WAVE_EVENT_TYPES.includes(msg.type)) {
      const data = (msg.data as Record<string, unknown> | undefined) ?? msg;
      const waveIndex = typeof data.wave_index === "number" ? (data.wave_index as number) : undefined;
      if (waveIndex === undefined) return;
      const step = typeof data.step === "string" ? (data.step as string) : undefined;

      const prev = entry.waveGroups;
      const next = prev.map((w) => ({ ...w, workers: [...w.workers] }));
      let group = next.find((w) => w.waveIndex === waveIndex && w.step === step);
      if (!group) {
        group = { waveIndex, step, taskIds: [], status: "pending", workers: [] };
        next.push(group);
      }

      if (msg.type === "wave_started") {
        group.taskIds = Array.isArray(data.task_ids)
          ? (data.task_ids as unknown[]).map((t) => String(t))
          : group.taskIds;
        group.status = "running";
      } else if (msg.type === "wave_completed") {
        group.status = "completed";
      } else if (msg.type === "wave_failed") {
        group.status = "failed";
      } else if (msg.type === "subagent_spawned" || msg.type === "subagent_result") {
        const agent = typeof data.agent === "string" ? data.agent as string
          : typeof data.agent_id === "string" ? data.agent_id as string : "worker";
        const status = typeof data.status === "string" ? data.status as string
          : msg.type === "subagent_spawned" ? "running" : "completed";
        const workerIndex = typeof data.worker === "number" ? data.worker as number : undefined;
        const existing = group.workers.find((wk) =>
          workerIndex !== undefined ? wk.worker === workerIndex : wk.worker === undefined && wk.agent === agent
        );
        if (existing) { existing.status = status; existing.agent = agent; }
        else group.workers.push({ agent, status, worker: workerIndex });
      }

      entry.waveGroups = next;
      if (runId === viewedRunIdRef.current) project({ ...entry });
      return;
    }

    // Pipeline frames: use handlePipelineMessage (the shared reducer from useWorkflow)
    // to update this run's pipelineState. We create a fake setPipelineState that writes
    // directly to the store entry instead of React state.
    const pipelineFrameTypes = [
      "pipeline_start", "agent_start", "agent_thinking", "agent_chunk",
      "agent_complete", "agent_error", "pipeline_complete", "pipeline_failed",
      "pipeline_cancelled", "planner_start", "planner_complete", "planner_timeout",
      "planner_error", "gate_status", "clarification_limit_reached",
      "agent_input", "tool_call", "tool_result", "workflow_validated",
      "task_progress", "task_loop_progress", "pipeline_reconnected",
    ];

    if (!pipelineFrameTypes.includes(msg.type)) return;

    // Flatten msg.data into the message (handlePipelineMessage expects flat msg).
    const flatMsg = msg.data && typeof msg.data === "object"
      ? { type: msg.type, ...msg as Record<string, unknown>, ...(msg.data as Record<string, unknown>) }
      : msg;

    // Create a dispatch function that writes to the store entry synchronously.
    const fakeSetState = (updater: React.SetStateAction<PipelineRunState>) => {
      const prev = entry.pipelineState;
      const next = typeof updater === "function" ? updater(prev) : updater;
      entry.pipelineState = next;
    };

    handlePipelineMessage(flatMsg, fakeSetState as React.Dispatch<React.SetStateAction<PipelineRunState>>, agentStartTimes);

    // ISS-063: the ONE writer of specRevisionCount. Derived from the restart history
    // the reducer just accumulated, so the banner reports the same number live, after
    // a reload, and after an SSE reconnect replays the log from zero.
    entry.specRevisionCount = deriveSpecRevisionCount(entry.pipelineState);

    // Always project after any frame for the viewed run.
    // FIX-224: skip project() when pipelineState reference is unchanged — the
    // reducer returned prev unchanged (idempotent re-delivery). This stops the
    // rapid re-renders that caused flickering agent circles and L2 agent views.
    if (runId === viewedRunIdRef.current) {
      if (entry.pipelineState !== lastProjectedPipelineStateRef.current) {
        lastProjectedPipelineStateRef.current = entry.pipelineState;
        project({ ...entry });
      }
    }
  }, [getOrCreate, getAgentStartTimes, project, setViewedRun]);

  const update = useCallback((runId: string, patch: PerRunStateUpdate) => {
    const entry = getOrCreate(runId);
    Object.assign(entry, patch);
    // Project to UI only if this is the currently viewed run
    if (runId === viewedRunIdRef.current) {
      project({ ...entry });
    }
  }, [getOrCreate, project]);

  const updatePipelineState = useCallback((
    runId: string,
    reducer: (prev: PipelineRunState) => PipelineRunState,
  ) => {
    const entry = getOrCreate(runId);
    entry.pipelineState = reducer(entry.pipelineState);
    if (runId === viewedRunIdRef.current) {
      project({ ...entry });
    }
  }, [getOrCreate, project]);

  // ISS-157: `syncPipelineStateOnly` was DELETED here. dev added it alongside FIX-220
  // ("for future use") as a second, never-called mechanism for the same behaviour the
  // rAF coalescing already handles — the dual implementation INV-12 forbids. Its own
  // premise was also false: it justified skipping `project()` on the grounds that
  // "the UI projection is already handled by handleFrame's project() on every SSE
  // frame", but handleFrame returns early — before any projection — on both
  // `waveIndex === undefined` and `!pipelineFrameTypes.includes(msg.type)`. Wiring it
  // would have silently dropped UI updates for every frame type outside that set.

  const updateWaveGroups = useCallback((
    runId: string,
    reducer: (prev: WaveGroup[]) => WaveGroup[],
  ) => {
    const entry = getOrCreate(runId);
    entry.waveGroups = reducer(entry.waveGroups);
    if (runId === viewedRunIdRef.current) {
      project({ ...entry });
    }
  }, [getOrCreate, project]);

  const switchViewTo = useCallback((runId: string) => {
    setViewedRun(runId);
    // FIX-224: reset the projection guard when switching views so the new run's
    // pipelineState is always projected fresh (not gated on the old run's ref).
    lastProjectedPipelineStateRef.current = null;
    const entry = getOrCreate(runId);
    project({ ...entry });
  }, [getOrCreate, project, setViewedRun]);

  const initRun = useCallback((runId: string, initialState?: Partial<PerRunState>) => {
    const fresh = makeInitialRunState(runId);
    if (initialState) Object.assign(fresh, initialState);
    storeRef.current.set(runId, fresh);
    // Reset agent start times for a fresh run
    agentStartTimesMapRef.current.set(runId, { current: {} });
    if (runId === viewedRunIdRef.current) {
      project({ ...fresh });
    }
  }, [project]);

  const get = useCallback((runId: string): PerRunState | undefined => {
    return storeRef.current.get(runId);
  }, []);

  const has = useCallback((runId: string): boolean => {
    return storeRef.current.has(runId);
  }, []);

  const remove = useCallback((runId: string) => {
    storeRef.current.delete(runId);
    agentStartTimesMapRef.current.delete(runId);
  }, []);

  return {
    viewed: viewedState,
    viewedRunId,
    handleFrame,
    update,
    updatePipelineState,
    updateWaveGroups,
    switchViewTo,
    initRun,
    get,
    has,
    remove,
  };
}
