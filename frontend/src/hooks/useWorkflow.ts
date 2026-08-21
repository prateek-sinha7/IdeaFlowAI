"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState, AttachedHook, ClarifyRound } from "@/types/index";
// Commands are sent up-channel over REST through the RunConnectionProvider (the
// SSE transport). SSE + REST is the sole transport (44-06 hard cutoff). The
// shared handlePipelineMessage reducer is transport-agnostic and untouched.
import { getToken, postAnswers } from "@/lib/api";
import { useRunConnection } from "@/providers/RunConnectionProvider";

export interface UseWorkflowReturn {
  pipelineState: PipelineRunState;
  // Returns the POST /api/runs promise resolving to the created run_id (so the
  // caller can attachRun it for launch->attach, R4). SSE + REST is the sole
  // transport (44-06).
  /**
   * ADR-0010 — the `attachedSkills` positional argument is GONE (it used to sit
   * between `agentIds` and `attachedHooks`). Skills are per-agent now: they ride
   * the composed manifest as `Step.skills`, not as a run-level bag applied to
   * every agent alike. Hooks keep their slot — they are still run-level.
   */
  startPipeline: (type: string, message: string, agentIds?: string[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>) => Promise<string | null>;
  resetPipeline: () => void;
  isRunning: boolean;
  handleMessage: (msg: { type: string; [key: string]: unknown }) => boolean;
  submitQuestionnaire: (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>, skipClarification?: boolean) => void;
  // Workstream C1 (POR §6.5) — append an answered clarify round to the run-scoped
  // state so the Q&A survives the questionnaire panel unmount. Reset per run.
  retainClarifyRound: (round: ClarifyRound) => void;
  // KAN-98 — overwrite an agent's retained output with the user's gate-approved
  // edit so a later Redo forwards the edited content, not the stale original.
  retainAgentEdit: (agentId: string, editedContent: string) => void;
  // ISS-126 — reconcile this state against a run's PERSISTED terminal status after
  // a durable replay that contained no terminal event. One-way (see
  // applyTerminalStatus): a non-terminal status is a no-op.
  reconcileTerminalStatus: (status: string) => void;
}

const INITIAL_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
  clarifications: [],
};

/**
 * Custom hook that manages workflow pipeline state. Launches runs over REST
 * (POST /api/runs via the RunConnectionProvider) and handles incoming pipeline
 * status updates. Includes `handleMessage` so the parent can route the SSE
 * pipeline down-channel events here.
 */
export function useWorkflow(): UseWorkflowReturn {
  const [pipelineState, setPipelineState] = useState<PipelineRunState>(INITIAL_STATE);
  const startTimeRef = useRef<number | null>(null);
  const agentStartTimesRef = useRef<Record<string, number>>({});

  // The app-level SSE run connection — commands ride its REST up-channel
  // (POST /api/runs, POST /api/runs/{id}/answers). SSE is the sole transport.
  const runConnection = useRunConnection();

  const startPipeline = useCallback(
    (type: string, message: string, agentIds?: string[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>): Promise<string | null> => {
      startTimeRef.current = Date.now();
      agentStartTimesRef.current = {};

      setPipelineState({
        isRunning: true,
        pipeline_type: type,
        agents: [],
        currentAgentIndex: -1,
        totalDuration: null,
        completedCount: 0,
        // Workstream C1 — the single canonical per-run boundary: a fresh live
        // run starts with no retained clarify rounds. The pipeline_start WS echo
        // spreads prev (downstream of this) so this reset holds.
        clarifications: [],
      });

      const payload: Record<string, unknown> = {
        type: "run_pipeline",
        pipeline_type: type,
        message,
      };

      if (agentIds && agentIds.length > 0) {
        payload.agent_ids = agentIds;
      }

      // Pass attached hooks as behavioral guidelines
      // The backend synthesizes these into system prompt instructions.
      // Send all available metadata so the backend can generate rich guidelines.
      if (attachedHooks && attachedHooks.length > 0) {
        payload.attached_hooks = attachedHooks.map(h => ({
          id: h.id,
          name: h.name,
          event: h.event,
          trigger: h.trigger,
          // Send the full description from the hook library if available,
          // so the Audit tab can display it in plain English (KAN-73)
          description: h.description || `${h.name}: ${h.trigger}`,
        }));
      }

      // Extra context fields are merged at the top level so the backend can
      // read them from message_data. This is the single ingress for run-level
      // params threaded through IdeaInputPage's `extraParams`, including:
      //   - `template_id` (od_prototype),
      //   - `gate_agent_ids` (Phase 6 per-run Human-review gate selection),
      //   - `model_overrides` (ISS-014 / MODEL-03 — agentId→modelId from the
      //     relocated per-agent AgentModelPicker; backend validates + persists
      //     it via _validate_model_overrides in websocket.py). Omitted when no
      //     model is picked, so the payload stays byte-identical for plain runs.
      // The generic Object.assign is the ONLY send site — do not also assign
      // `payload.model_overrides` separately or it would double-send.
      if (context) {
        Object.assign(payload, context);
      }

      // Send the `run_pipeline` payload up-channel over REST (POST /api/runs).
      // W1 (44-01): return the POST /api/runs promise (→ created run_id) so the
      // caller can attachRun it (launch->attach, R4).
      return runConnection.sendCommand(null, payload);
    },
    [runConnection]
  );

  const resetPipeline = useCallback(() => {
    setPipelineState(INITIAL_STATE);
    startTimeRef.current = null;
    agentStartTimesRef.current = {};
  }, []);

  const handleMessage = useCallback(
    (msg: { type: string; [key: string]: unknown }): boolean => {
      return handlePipelineMessage(msg, setPipelineState, agentStartTimesRef);
    },
    []
  );

  // Phase 2 — submit clarification answers to resume a paused pipeline.
  // The Clarify_Engine (inside the ExecutionEngine) is awaiting an asyncio.Event
  // keyed by pipeline_run_id; this sets it and resumes the run from the gate.
  // skipClarification (ISS-027): set by "Skip all & run directly" so the backend
  // ClarifyEngine force-proceeds immediately instead of re-asking up to 3 rounds.
  const submitQuestionnaire = useCallback(
    (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>, skipClarification = false) => {
      // Post the answers to POST /api/runs/{id}/answers (AnswersCommand) — which
      // takes `responses` with NO `message_id`, closing the R4 422 the /messages
      // (MessageCommand) path raised. The ISS-027 `skip_clarification`
      // force-proceed rides along.
      void postAnswers(getToken() ?? "", pipelineRunId, {
        responses,
        skip_clarification: skipClarification,
      }).catch((e) => console.error("postAnswers failed", e));
    },
    []
  );

  // Workstream C1 (POR §6.5) — fold an answered clarify round into run-scoped
  // state before the questionnaire panel clears, so the Q&A never vanishes.
  const retainClarifyRound = useCallback((round: ClarifyRound) => {
    setPipelineState((prev) => ({
      ...prev,
      clarifications: [...(prev.clarifications ?? []), round],
    }));
  }, []);

  // KAN-98: apply a human-edited agent output to the live agent state so the
  // Thinking tab displays the edited content (e.g. the reduced task list) rather
  // than the original pre-edit output from agent_complete. Called when
  // review_gate_approved arrives with edited:true, using the editedContent that
  // was sent on the gate approve command.
  const retainAgentEdit = useCallback((agentId: string, editedContent: string) => {
    setPipelineState((prev) => {
      const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
      if (agentIdx === -1) return prev;
      const updated = [...prev.agents];
      updated[agentIdx] = { ...updated[agentIdx], output: editedContent };
      return { ...prev, agents: updated };
    });
  }, []);

  // ISS-126: reconcile against the run's PERSISTED status after a durable replay
  // that carried no terminal event. Routed through the SAME applyTerminalStatus
  // the store path uses, so the two containers can never disagree about what
  // terminal means (INV-12).
  const reconcileTerminalStatus = useCallback((status: string) => {
    setPipelineState((prev) => applyTerminalStatus(prev, status));
  }, []);

  const isRunning = pipelineState.isRunning;

  return {
    pipelineState,
    startPipeline,
    resetPipeline,
    isRunning,
    handleMessage,
    submitQuestionnaire,
    retainClarifyRound,
    retainAgentEdit,
    reconcileTerminalStatus,
  };
}

/**
 * ISS-063/ISS-080/ISS-081 — which spec-revision cycle this run is in, derived from the
 * restart history in `agentStartEventIds`.
 *
 * An `update_specs` pass re-runs a contiguous head of the pipeline, so the number of
 * times the pipeline's FIRST step has started names the cycle: its first start is the
 * original pass and every start after it is one revision.
 *
 * ISS-081 — scoped to the HEAD, not `max` over every agent. A later step restarts for
 * reasons that are not revisions: a per-task agent loop restarts one step once per task
 * (11 starts on run 6e38b9a7, a run with ONE revision), and a partial resume re-drives
 * from the first incomplete step. `max` read those as revisions.
 * SC-001/INV-1: the head is POSITIONAL — the first step of whatever roster the compiled
 * manifest announced on `pipeline_start`. No agent id, no workflow name, no artifact
 * kind. A workflow whose revision window excludes step 0 under-reports (the banner
 * stays hidden) rather than over-reports.
 *
 * ISS-080 — counts DISTINCT event identities, never deliveries, so the value is a pure
 * function of the SET of events: order-independent and idempotent under ANY delivery
 * multiplicity rather than merely under the event dedup. A history reopen delivers each
 * durable event twice (the REST replay and the SSE replay).
 */
export function deriveSpecRevisionCount(
  state: Pick<PipelineRunState, "agents" | "agentStartEventIds"> | undefined,
): number {
  const headAgentId = state?.agents?.[0]?.id;
  if (!headAgentId) return 0;
  const headStarts = state?.agentStartEventIds?.[headAgentId]?.length ?? 0;
  return headStarts > 1 ? headStarts - 1 : 0;
}

/**
 * The durable identity of a frame. Every persisted `run_events` row and every live SSE
 * event carries `event_id` (and `seq`), and `getRunEvents` merges both onto the
 * replayed payload (lib/api.ts) — so the two transports' copies of one durable event
 * share a key. An UNSTAMPED frame has no identity and, exactly as `shouldApplyEvent`
 * treats it (lib/wsReplayState.ts), is never deduped: `positionKey` keeps each of its
 * deliveries distinct so legacy frames still count one apiece.
 */
function frameIdentity(msg: { [key: string]: unknown }, positionKey: number): string {
  if (typeof msg.event_id === "string" && msg.event_id) return msg.event_id;
  if (typeof msg.seq === "number") return `seq:${msg.seq}`;
  return `unstamped:${positionKey}`;
}

/**
 * ISS-082 — the frame types whose handler GROWS a field out of its previous value (string
 * `+` or `[...prev.x, y]`) instead of overwriting it. Every OTHER type is idempotent
 * because it overwrites, recomputes from overwritten values (the token totals at
 * `agent_complete` are the model), or keys on a stable id (`task_progress`'s Map on
 * `t.number`), so a second delivery of one changes nothing and none of them are gated here.
 *
 * A new accumulating case MUST be added to this set AND to the registry in
 * `useWorkflow.accumulators.test.ts`, whose GUARD-1 reads this file and fails until it is.
 */
const ACCUMULATING_FRAME_TYPES: ReadonlySet<string> = new Set([
  "agent_start",      // agentStartEventIds
  "agent_thinking",   // agents[].thinkingText
  "agent_chunk",      // agents[].output
  "tool_call",        // agents[].toolCalls
  "hook_run",         // hookRuns
  "validator_result", // agents[].validationIssues
]);

/** Has this accumulating frame already been folded into `prev`? */
function isRedelivery(prev: PipelineRunState, msg: { [key: string]: unknown }): boolean {
  if (typeof msg.seq === "number") {
    // Strictly `<=`: seq is allocated 1,2,3,… per run, so anything at or below the cursor
    // is a frame this run has already applied. `!== undefined` rather than a truthiness
    // test, because seq 0 is a legitimate cursor value.
    return prev.lastAppliedSeq !== undefined && msg.seq <= prev.lastAppliedSeq;
  }
  const eventId = typeof msg.event_id === "string" ? msg.event_id : "";
  // No identity at all → always apply. Two deliveries of an anonymous frame are
  // indistinguishable from two real ones, and dropping the second would lose data.
  return !!eventId && (prev.appliedUnsequencedIds ?? []).includes(eventId);
}

/** The cursor advance to merge into the state a handler just produced. */
function markApplied(
  prev: PipelineRunState,
  msg: { [key: string]: unknown },
): Partial<PipelineRunState> {
  if (typeof msg.seq === "number") return { lastAppliedSeq: msg.seq };
  const eventId = typeof msg.event_id === "string" ? msg.event_id : "";
  if (!eventId) return {};
  return { appliedUnsequencedIds: [...(prev.appliedUnsequencedIds ?? []), eventId] };
}

/**
 * ISS-126 — the SINGLE definition of what a terminal run status does to the run
 * state, and the single terminal-status vocabulary that goes with it.
 *
 * Before this, three event cases below each open-coded the same marker triad
 * (`isRunning:false` + `cancelled`/`failed`/`degraded`), and NOTHING anywhere in
 * `frontend/src` derived those markers from the server's `WorkflowRun.status`.
 * That gap is the ISS-126 bug: a terminal run whose durable `run_events` log
 * carries no terminal event (ISS-124's driver terminals, or a run corrupted by the
 * pre-FIX-240 seq collision) is rebuilt on reopen purely from that log, so
 * `isRunning` never resolves and the screen renders "Awaiting approval" + a live
 * Stop button on a run that ended.
 *
 * The three event cases now route through this map, so the number of places that
 * decide "what terminal looks like" goes from three to ONE — a fix that REDUCES
 * truth sources rather than adding a fourth (INV-12). `workflow_runs.status` is
 * already the lifecycle authority everywhere else (the boot restore scan, the
 * RunState fence, the history badges, FIX-240's own SSE guard); only the run
 * screen inverted it and treated the terminal EVENT as the source.
 *
 * Membership doubles as the terminal vocabulary — `null` means "terminal, but no
 * failure marker" (a clean completion), an absent key means "not terminal at all".
 * It is pinned equal to page.tsx's REOPEN_TERMINAL_STATUSES by
 * `terminalStatusReconcile.test.ts`, and both match the backend's
 * `TERMINAL_STATUSES` (chat_router.py).
 */
const TERMINAL_MARKER_BY_STATUS: Record<string, "cancelled" | "failed" | "degraded" | null> = {
  completed: null,
  cancelled: "cancelled",
  failed: "failed",
  degraded: "degraded",
  diverted: null,
};

/** The terminal marker patch for a terminal status. Callers pass a known member. */
export function terminalMarkers(status: string): Partial<PipelineRunState> {
  const marker = TERMINAL_MARKER_BY_STATUS[status];
  return marker ? { isRunning: false, [marker]: true } : { isRunning: false };
}

/**
 * Reconcile a run's state against the server's persisted terminal status.
 *
 * ONE-WAY BY CONSTRUCTION: a terminal status forces terminal UI, but a
 * non-terminal (or unknown) status returns `prev` UNCHANGED — never "non-terminal
 * status forces non-terminal UI". Without that asymmetry a slow `getWorkflow` on a
 * genuinely live run could clear a legitimately open review gate.
 */
export function applyTerminalStatus(
  prev: PipelineRunState,
  status: string,
): PipelineRunState {
  if (!Object.prototype.hasOwnProperty.call(TERMINAL_MARKER_BY_STATUS, status)) {
    return prev;
  }
  // Stand the run down: on a clean completion anything unfinished resolves to
  // done (mirrors pipeline_complete); on any failure terminal the still-animating
  // agents stop spinning but keep whatever status they earned (mirrors
  // pipeline_cancelled / pipeline_failed).
  const updated: AgentRunState[] = prev.agents.map((a) => {
    if (status === "completed") {
      return (a.status === "running" || a.status === "thinking" || a.status === "idle")
        ? { ...a, status: "done" as const, thinking: "" }
        : a;
    }
    return (a.status === "running" || a.status === "thinking")
      ? { ...a, status: "idle" as const, thinking: "" }
      : a;
  });
  return {
    ...prev,
    ...terminalMarkers(status),
    agents: updated,
    completedCount: updated.filter((a) => a.status === "done").length,
  };
}

/**
 * Process an incoming pipeline WebSocket message and update state.
 * Call this from the parent component's onMessage handler.
 */
export function handlePipelineMessage(
  msg: { type: string; [key: string]: unknown },
  setPipelineStateRaw: React.Dispatch<React.SetStateAction<PipelineRunState>>,
  agentStartTimesRef: React.MutableRefObject<Record<string, number>>
): boolean {
  // ISS-082 — the reducer's OWN identity gate, installed ONCE for every accumulating case
  // rather than open-coded per field. Wrapping the dispatcher (instead of the handlers)
  // is what makes a future accumulating case protected by adding its type to the set
  // above and nothing else. A partial re-delivery — an SSE resume from Last-Event-ID with
  // no intervening `agent_start` — used to append a second copy of the streamed output,
  // thinking text, tool calls, validation issues and hook rows.
  const setPipelineState: React.Dispatch<React.SetStateAction<PipelineRunState>> =
    ACCUMULATING_FRAME_TYPES.has(msg.type)
      ? (action) =>
          setPipelineStateRaw((prev) => {
            if (isRedelivery(prev, msg)) return prev;
            const next = typeof action === "function" ? action(prev) : action;
            // A handler that bailed (`return prev`, e.g. an unknown agent id) folded
            // nothing in, so the cursor must not advance past a frame that never applied.
            return next === prev ? prev : { ...next, ...markApplied(prev, msg) };
          })
      : setPipelineStateRaw;

  switch (msg.type) {
    case "pipeline_start": {
      const agents = (msg.agents as Array<{
        id: string;
        name: string;
        role: string;
        icon: string;
        order: number;
      }>) || [];

      // Capture pipeline_run_id — present on all pipeline_start events.
      // This is the most reliable way to get the run ID for all pipeline types,
      // including prototype which skips the planner (planner_start never fires).
      const pipelineRunIdFromStart = (msg.pipeline_run_id as string | undefined)
        || ((msg.data as Record<string, unknown>)?.pipeline_run_id as string | undefined);

      // KAN-120 BUG-2: resume_offset > 0 means this is a mid-build resume —
      // agents at indices < resume_offset already completed before the stop.
      // Mark them "done" immediately so the Steps panel shows the correct
      // status instead of resetting them all to "idle" and waiting for the
      // durable SSE replay to restore each one. 0 on normal (non-resume) runs
      // → byte-identical to the pre-fix behaviour (INV-3).
      const resumeOffset = (msg.resume_offset as number | undefined) ?? 0;

      setPipelineState((prev) => {
        // ISS-063/ISS-075/ISS-080 — THE predicate this branch is built on: a
        // `pipeline_start` naming the run we are ALREADY showing RE-ANNOUNCES it (a
        // resume, a restart while parked at a gate, or a durable replay from seq 0);
        // it does not start it. Everything it re-announces has already happened, so
        // nothing it carries may be rebuilt from zero. FIX-221 introduced this test
        // for one field; it now governs the whole branch (INV-12 — one concept, one
        // expression). Its sibling in dashboard/page.tsx gates `resetReplayState`.
        const isSameRunReannounce =
          !!pipelineRunIdFromStart && prev.pipelineRunId === pipelineRunIdFromStart;
        // Either shape of "this frame continues an in-flight run" — a mid-build resume
        // (KAN-120) or a re-announcement of the run on screen.
        const isContinuation = resumeOffset > 0 || isSameRunReannounce;

        // ISS-075: MERGE the roster on a re-announcement instead of rebuilding it. The
        // engine's `resume_offset` is the first INCOMPLETE step, which is 0 for a run
        // parked at a gate on step 0 — so rebuilding from it repainted a fully-run
        // trace as "nothing has run" (every Steps row then renders disabled, because
        // StepsOverviewSpine gates navigation on status !== "idle"). The live per-agent
        // state we already hold is the better evidence; the frame supplies identity.
        const carried = isSameRunReannounce
          ? new Map(prev.agents.map((a) => [a.id, a]))
          : undefined;
        const agentStates: AgentRunState[] = agents.map((a, idx) => {
          const identity = {
            id: a.id,
            name: a.name,
            role: a.role,
            icon: a.icon || "🤖",
            index: idx,
          };
          const existing = carried?.get(a.id);
          if (existing) return { ...existing, ...identity };
          return {
            ...identity,
            // KAN-120 BUG-2: agents before the resume offset are already done.
            status: idx < resumeOffset ? "done" : "idle",
            output: "",
            thinking: "",
            duration: null,
            error: null,
          };
        });
        // One rule on both paths: the roster is the evidence, the offset is the floor.
        // On a fresh run the two agree by construction (idx < resumeOffset ⇒ "done"),
        // so this is byte-identical to the old `resumeOffset > 0 ? resumeOffset : 0`.
        const completedCount = Math.max(
          agentStates.filter((a) => a.status === "done").length,
          resumeOffset,
        );

        return {
          ...prev,
          isRunning: true,
          pipeline_type: (msg.pipeline_type as string) || prev.pipeline_type,
          pipelineRunId: pipelineRunIdFromStart ?? prev.pipelineRunId,
          agents: agentStates,
          currentAgentIndex: isSameRunReannounce
            ? Math.max(prev.currentAgentIndex, resumeOffset, 0)
            : (resumeOffset > 0 ? resumeOffset : 0),
          // KAN-120 BUG-2: on resume, seed completedCount from the offset so
          // the progress bar shows correct proportion immediately.
          completedCount,
          // KAN-120 BUG-3: on a continuation, carry over protoCompletedTasks from prev
          // so task data already recorded before the stop is not wiped. The
          // task_progress max-wins handler below will extend it as new tasks
          // complete. On a fresh run prev.protoCompletedTasks is undefined/empty
          // → same as before (byte-identical, INV-3).
          protoCompletedTasks: isContinuation ? (prev.protoCompletedTasks ?? []) : [],
          protoCompletedTaskCount: isContinuation ? (prev.protoCompletedTaskCount ?? 0) : 0,
          // KAN-153: reset the known total on a fresh run; preserve on a continuation so
          // the ConstructionBlock keeps showing the full task list while catching up.
          protoTotalTasks: isContinuation ? (prev.protoTotalTasks ?? 0) : 0,
          protoPlannedTasks: isContinuation ? prev.protoPlannedTasks : undefined,
          // KAN-120: clear terminal markers so a resumed run does not stay in
          // the "terminal" state (cancelled/failed) after pipeline_start fires.
          // Without this, pipeline_complete resolves isRunning→false but
          // cancelled/failed is still true → runLaneState falls back to "terminal"
          // and shows "Cancelled by you" / "Run Again" instead of the deliverable.
          cancelled: undefined,
          failed: undefined,
          degraded: undefined,
          // Phase 39 (RUNUI-06): surface the run's created_at so the lane header can
          // render a relative age ("23h ago"). ADDITIVE optional — falls back to
          // the receipt time when the event omits it.
          createdAt: (msg.created_at as string) || prev.createdAt || new Date().toISOString(),
          // ISS-063: the restart history a re-announcement re-announces has already
          // happened, so carry it. Only a genuinely different run clears it. Without
          // this the trailing resume frame lands last on every replay and zeroes the
          // revision count the user is meant to be reading.
          //
          // FIX-222: do NOT carry agentStartEventIds when resuming from a terminal
          // state (cancelled/failed). "Run Again" on a cancelled run re-uses the same
          // run_id → isSameRunReannounce=true → BUT prev.isRunning=false (it was
          // cancelled). The existing ids cause deriveSpecRevisionCount to return 1
          // immediately on the first agent_start, showing a spurious "Spec Revision
          // Cycle 1" banner. Only carry ids on a LIVE reconnect (prev.isRunning=true).
          agentStartEventIds: (isSameRunReannounce && prev.isRunning) ? (prev.agentStartEventIds ?? {}) : {},
          // ISS-082: the frame-identity cursor's per-run boundary, on the SAME predicate.
          // A re-announcement continues this run, so its high-water mark must survive or
          // the replay it introduces would be applied a second time; a genuinely different
          // run must start from nothing, or run 1's cursor would swallow run 2's whole
          // trace (its seq restarts at 1). INV-2 — no cross-run state on shared state.
          lastAppliedSeq: isSameRunReannounce ? prev.lastAppliedSeq : undefined,
          appliedUnsequencedIds: isSameRunReannounce ? (prev.appliedUnsequencedIds ?? []) : [],
        };
      });

      // Persist pipeline_run_id to sessionStorage so reconnection works
      // even if the browser tab is closed and re-opened while a long-running
      // pipeline (2-6 hours) is still executing on the backend.
      if (pipelineRunIdFromStart) {
        try {
          sessionStorage.setItem("active_pipeline_run_id", pipelineRunIdFromStart);
          sessionStorage.setItem("active_pipeline_type", (msg.pipeline_type as string) || "");
        } catch { /* non-fatal */ }
      }

      return true;
    }

    case "agent_start": {
      const agentId = msg.agent_id as string;
      agentStartTimesRef.current[agentId] = Date.now();

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        // FIX-039: on (re)start, reset THIS agent's run-scoped accumulators to
        // their fresh-agent values BEFORE the next run's chunks accumulate.
        // Without this, a regenerate (2nd agent_start) leaves the prior run's
        // `output` in place and agent_chunk APPENDS onto it (:275), so
        // PrototypePipelineView.parseTasks reads the stale first <tasks> block.
        // Replayed agent_start events are deduped upstream by shouldApplyEvent
        // (dashboard/page.tsx:276), so a live output is never wiped on reconnect.
        // Identity fields (id/name/role/icon/index) are preserved via the spread.
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "running",
          // Accumulator fields rebuilt per run (agent_chunk/agent_thinking/
          // tool_call/validator_result/agent_error/gate_*):
          output: "",
          thinking: "",
          thinkingText: "",
          toolCalls: [],
          validationIssues: [],
          error: null,
          validationPassed: undefined,
          // Overwrite-only fields — reset too so a re-run that errors before
          // agent_complete/agent_input never shows the prior run's numbers:
          duration: null,
          inputTokens: undefined,
          outputTokens: undefined,
          totalTokens: undefined,
          estimatedCostUsd: undefined,
          inputPrompt: undefined,
          contextSources: undefined,
        };

        // ISS-063/ISS-080: the only writer of the restart history. Lives here, inside
        // the updater, so it reads `prev` rather than a post-commit ref — that is what
        // makes it correct during the synchronous durable-replay loop, where no React
        // commit can interleave between frames. Still a SET of identities and never a
        // tally (`+= 1`), because a history reopen replays the log over REST and again
        // over SSE and a tally cannot tell that apart from two real starts (ISS-080 — the
        // banner read 5 for 2 revisions). ISS-082 promoted FIX-225's per-field
        // `.includes` re-delivery check to the whole reducer, so it is gone from here
        // (INV-12 — one concept, one expression); the ARRAY stays, because it is what
        // `deriveSpecRevisionCount` reads.
        const priorStarts = prev.agentStartEventIds?.[agentId] ?? [];
        const startIdentity = frameIdentity(msg, priorStarts.length);
        return {
          ...prev,
          agents: updated,
          currentAgentIndex: agentIdx,
          agentStartEventIds: { ...(prev.agentStartEventIds ?? {}), [agentId]: [...priorStarts, startIdentity] },
        };
      });
      return true;
    }

    case "agent_thinking": {
      const agentId = msg.agent_id as string;
      const thinking = (msg.thinking as string) || "";

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "thinking",
          thinking,
          // Phase 3 (T043): accumulate into thinkingText for Thinking tab.
          // Plain concatenation, no separator — thinking now streams live as
          // small deltas (same granularity as agent_chunk/output), and each
          // delta already carries its own spacing from the model.
          thinkingText: (updated[agentIdx].thinkingText || "") + thinking,
        };

        return { ...prev, agents: updated };
      });
      return true;
    }

    case "agent_chunk": {
      const agentId = msg.agent_id as string;
      const chunk = (msg.chunk as string) || "";

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "running",
          output: updated[agentIdx].output + chunk,
        };

        return { ...prev, agents: updated };
      });
      return true;
    }

    case "agent_complete": {
      const agentId = msg.agent_id as string;
      const startTime = agentStartTimesRef.current[agentId];
      // Prefer an explicit server-provided duration; fall back to the measured
      // start→complete wall time. ADDITIVE — existing events (no `duration`)
      // keep the measured behavior unchanged.
      const measured = startTime ? (Date.now() - startTime) / 1000 : null;
      const duration =
        typeof msg.duration === "number" ? (msg.duration as number) : measured;

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "done",
          duration,
          thinking: "",
          inputTokens: (msg.input_tokens as number) || 0,
          outputTokens: (msg.output_tokens as number) || 0,
          totalTokens: (msg.total_tokens as number) || 0,
          estimatedCostUsd: (msg.estimated_cost_usd as number) || 0,
        };

        const completedCount = updated.filter((a) => a.status === "done").length;

        // Accumulate pipeline-level token totals
        const totalInput = updated.reduce((s, a) => s + (a.inputTokens ?? 0), 0);
        const totalOutput = updated.reduce((s, a) => s + (a.outputTokens ?? 0), 0);

        return {
          ...prev,
          agents: updated,
          completedCount,
          totalInputTokens: totalInput,
          totalOutputTokens: totalOutput,
          totalTokens: totalInput + totalOutput,
          cacheReadTokens: (msg.total_cache_read_tokens as number) || prev.cacheReadTokens || 0,
          cacheWriteTokens: (msg.total_cache_write_tokens as number) || prev.cacheWriteTokens || 0,
        };
      });
      return true;
    }

    case "agent_error": {
      const agentId = msg.agent_id as string;
      const error = (msg.error as string) || "Unknown error";

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "error",
          error,
          thinking: "",
        };

        return { ...prev, agents: updated };
      });
      return true;
    }

    case "pipeline_complete": {
      const totalDuration = (msg.total_duration as number) || null;

      // IN-03 (13 review fix): a degraded completion (WR-05) carries
      // status:"degraded" + agents_failed — agents that errored and never
      // completed. Surface them as per-agent error states (parity with the
      // pipeline_failed sweep) instead of flipping the whole run to success,
      // and expose the degraded flag on the pipeline state.
      const isDegraded = (msg.status as string) === "degraded";
      const degradedFailedIds = isDegraded ? ((msg.agents_failed as string[]) || []) : [];

      // Clear the persisted run ID — pipeline is done
      try {
        sessionStorage.removeItem("active_pipeline_run_id");
        sessionStorage.removeItem("active_pipeline_type");
      } catch { /* non-fatal */ }

      setPipelineState((prev) => {
        // Mark any agents still in running/thinking/idle state as done
        // (handles fast pipelines where agent_complete events were batched),
        // EXCEPT degraded-run failed agents, which resolve to error.
        const updated = prev.agents.map((a) => {
          if (degradedFailedIds.includes(a.id)) {
            return a.status === "error"
              ? a // already carries its own agent_error detail
              : { ...a, status: "error" as const, error: a.error || "Agent failed (run degraded)", thinking: "" };
          }
          return (a.status === "running" || a.status === "thinking" || a.status === "idle")
            ? { ...a, status: "done" as const, thinking: "" }
            : a;
        });
        return {
          ...prev,
          // ISS-126: the shared terminal vocabulary (INV-12) — this case no longer
          // open-codes `isRunning:false`. `degraded` is re-stated below with the
          // same value plus its agent list, so the spread order is immaterial.
          ...terminalMarkers(isDegraded ? "degraded" : "completed"),
          totalDuration,
          agents: updated,
          degraded: isDegraded || undefined,
          degradedFailedAgents: isDegraded ? degradedFailedIds : undefined,
          completedCount: updated.filter((a) => a.status === "done").length,
          // Prefer the backend's authoritative totals, but fall back to the
          // values accumulated from agent_complete so a missing field never
          // wipes the token card to zero.
          totalInputTokens: (msg.total_input_tokens as number) || prev.totalInputTokens || 0,
          totalOutputTokens: (msg.total_output_tokens as number) || prev.totalOutputTokens || 0,
          totalTokens: (msg.total_tokens as number) || prev.totalTokens || 0,
          estimatedCostUsd: (msg.estimated_cost_usd as number) || prev.estimatedCostUsd || 0,
          cacheReadTokens: (msg.total_cache_read_tokens as number) || prev.cacheReadTokens || 0,
          cacheWriteTokens: (msg.total_cache_write_tokens as number) || prev.cacheWriteTokens || 0,
          modelId: (msg.model_id as string) || prev.modelId || undefined,
          // Phase 39 (RUNUI-06): surface the deliverable filename/version that the
          // event already carries so the lane can render the mock's deliverable
          // card. ADDITIVE optional — undefined when the event omits them.
          deliverableFilename: (msg.deliverable_filename as string) || prev.deliverableFilename,
          deliverableVersion: (msg.deliverable_version as number) ?? prev.deliverableVersion,
        };
      });
      return true;
    }

    case "pipeline_failed": {
      // F3 (13-06): terminal failure — EVERY agent in the run hard-failed.
      // The backend emits this instead of pipeline_complete (no deliverable,
      // state machine in "failed"). Mirror pipeline_cancelled's teardown:
      // resolve isRunning, clear the persisted run id, and surface the failed
      // agents through the per-agent error state the hook already maintains
      // (each agent normally got its own agent_error first; this is the
      // belt-and-braces terminal sweep so nothing stays spinning).
      const totalDuration = (msg.total_duration as number) || null;
      const failedIds = (msg.agents_failed as string[]) || [];
      const error = (msg.error as string) || "Pipeline failed";

      try {
        sessionStorage.removeItem("active_pipeline_run_id");
        sessionStorage.removeItem("active_pipeline_type");
      } catch { /* non-fatal */ }

      setPipelineState((prev) => {
        const updated: AgentRunState[] = prev.agents.map((a) => {
          if (a.status === "error") return a; // already carries its own error
          if (failedIds.includes(a.id)) {
            return { ...a, status: "error" as const, error: a.error || error, thinking: "" };
          }
          // Any agent still animating resolves to idle (run is over).
          return a.status === "thinking" || a.status === "running"
            ? { ...a, status: "idle" as const, thinking: "" }
            : a;
        });
        return {
          ...prev,
          agents: updated,
          // ISS-017 (16-04): the additive server `failed` signal PreviewPanel keys
          // its terminal-empty affordance on — NOT a client-side empty==failed
          // guess. ISS-126: it and `isRunning:false` now come from the shared
          // terminal vocabulary instead of being open-coded here (INV-12).
          ...terminalMarkers("failed"),
          totalDuration,
          completedCount: updated.filter((a) => a.status === "done").length,
          failedAgents: failedIds,
        };
      });
      return true;
    }

    case "pipeline_cancelled": {
      // Clear the persisted run ID
      try {
        sessionStorage.removeItem("active_pipeline_run_id");
        sessionStorage.removeItem("active_pipeline_type");
      } catch { /* non-fatal */ }
      // Backend emits this on Stop / WebSocketDisconnect with an
      // `agents_completed` count and a partial `duration`. The previous
      // dispatcher omitted this case entirely so `isRunning` stayed true
      // forever after a cancel — UI showed a spinner that never resolved.
      // Reset any in-flight agent (status "thinking"/"running") back to
      // "idle" so the progress panel stops animating; completed agents
      // ("done") and already-errored agents are left untouched.
      //
      // NOTE: od_prototype sends duration nested inside `data.duration`
      // while the regular pipeline sends it flat at the top level.
      // Handle both shapes.
      const totalDuration = (msg.duration as number) || (msg.data as Record<string, unknown>)?.duration as number || null;
      setPipelineState((prev) => {
        const updated: AgentRunState[] = prev.agents.map((a) =>
          a.status === "thinking" || a.status === "running"
            ? { ...a, status: "idle", thinking: "" }
            : a
        );
        return {
          ...prev,
          agents: updated,
          // ISS-035 (SC-4): the terminal cancelled marker, so a downstream
          // selector derives the LIVE-STATE-CONTRACT §1 cancelled state
          // ("Cancelled by you") instead of falling through to idle. No chat
          // message is pushed from the reducer — RunChatLane renders the
          // transcript line off this marker + the generic RunLaneState (plan 06).
          // ISS-126: it and `isRunning:false` now come from the shared terminal
          // vocabulary instead of being open-coded here (INV-12).
          ...terminalMarkers("cancelled"),
          totalDuration,
          completedCount: updated.filter((a) => a.status === "done").length,
        };
      });
      return true;
    }

    case "pipeline_diverted": {
      // R-28/R-20 (014-conditional-gates, T38 live case): a `trigger: workflow`
      // route outcome fired — this run's dispatch loop ended (R-13) and a new,
      // separate WorkflowRun took over. Additive terminal event (contract
      // guarantee #1): mirrors pipeline_cancelled's teardown but does NOT set
      // the `cancelled` marker — a diverted run is not a cancellation, and the
      // run-view must render "Diverted to X" rather than "Cancelled"/"Completed".
      try {
        sessionStorage.removeItem("active_pipeline_run_id");
        sessionStorage.removeItem("active_pipeline_type");
      } catch { /* non-fatal */ }
      const divertedToRunId = msg.diverted_to_run_id as string;
      const divertedToWorkflow = msg.diverted_to_workflow as string;
      setPipelineState((prev) => {
        const updated: AgentRunState[] = prev.agents.map((a) =>
          a.status === "thinking" || a.status === "running"
            ? { ...a, status: "idle", thinking: "" }
            : a
        );
        return {
          ...prev,
          agents: updated,
          isRunning: false,
          divertedTo: { runId: divertedToRunId, workflowId: divertedToWorkflow },
          completedCount: updated.filter((a) => a.status === "done").length,
        };
      });
      return true;
    }

    case "pipeline_reconnected": {
      // Phase 12 / 12-08 (RESUME-04 FE half, UAT Gap 2b) — previously this
      // event was silently dropped, so after a backend restart mid-run the
      // open page reconnected, the backend replayed the durable tail and
      // reported the run's final status… and the FE ignored it: isRunning
      // never resolved ("running forever" hang, screenshot 51-runE2-stuck).
      //
      // Backend payload (websocket.py — flattened onto `msg` by page.tsx):
      //   { pipeline_run_id, live, status?, replayed_through_seq?, message }
      // The legacy live-reconnect path omits `live` entirely; the 12-09 bridge
      // adds `live: true` for an engine-attached resumed run.
      const live = msg.live as boolean | undefined;
      const status = (msg.status as string | null | undefined) ?? null;

      // live:true (12-09 engine→WS attach) or absent (legacy live reconnect):
      // a live task will stream the tail through the queue — keep running and
      // let the subsequent agent_*/wave_*/pipeline_complete events drive state.
      if (live !== false) return true;

      const TERMINAL_STATUSES = ["completed", "failed", "cancelled", "error", "diverted"];
      if (status && TERMINAL_STATUSES.includes(status)) {
        // No live task and the run already finished — the durable tail was
        // replayed by the WS layer before this event, so resolve the run out
        // of the running state (this is what stops the hang).
        try {
          sessionStorage.removeItem("active_pipeline_run_id");
          sessionStorage.removeItem("active_pipeline_type");
        } catch { /* non-fatal */ }

        setPipelineState((prev) => {
          // Mirror pipeline_complete's agent finalization on success; for
          // failed/cancelled/error leave agents as-is but still resolve.
          const updated = status === "completed"
            ? prev.agents.map((a) =>
                (a.status === "running" || a.status === "thinking" || a.status === "idle")
                  ? { ...a, status: "done" as const, thinking: "" }
                  : a
              )
            : prev.agents;
          return {
            ...prev,
            isRunning: false,
            agents: updated,
            completedCount: updated.filter((a) => a.status === "done").length,
          };
        });
        return true;
      }

      // live:false + NON-terminal (or missing) status: the run is still
      // in-flight on the backend but this connection has no live task to
      // attach to. Keep isRunning true (the UI showing "running" is correct —
      // the run IS running). Recovery (WR-02): the backend closes the
      // task-registered-before-queue race at the source — the live queue is
      // now registered synchronously with the driver task in
      // restore_non_terminal_runs — so this shape only occurs while the
      // restore scan has not yet reached the run. The SSE transport
      // (useRunStream) reconnects natively and replays from Last-Event-ID, so
      // the tail arrives without any client-side re-attach frame. No new retry
      // loop here (T-12-08-02).
      return true;
    }

    case "agent_input": {
      // Phase 3 (T043) — capture full input prompt and context sources for Thinking tab
      const agentId = msg.agent_id as string;
      const inputPrompt = (msg.context_message as string) || undefined;
      const contextSources = (msg.context_sources as import("@/types/index").ContextSource[]) || [];

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = { ...updated[agentIdx], inputPrompt, contextSources };
        return { ...prev, agents: updated };
      });
      return true;
    }

    case "agent_skills": {
      // The skills/hooks the backend ACTUALLY injected into this agent's system
      // prompt — not just what the run attached overall. Renders in
      // AgentDetailPanel next to the tool calls.
      const agentId = msg.agent_id as string;
      const attachedSkills =
        (msg.attached_skills as import("@/types/index").AttachedSkillEntry[]) || [];
      const attachedHooks =
        (msg.attached_hooks as import("@/types/index").AttachedHookEntry[]) || [];
      const skillsLoadErrors = (msg.skills_load_errors as string[]) || [];
      const estimatedTokens = msg.estimated_tokens as number | undefined;
      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          attachedSkills,
          attachedHooks,
          skillsLoadErrors,
          estimatedTokens,
        };
        return { ...prev, agents: updated };
      });
      return true;
    }

    case "tool_call": {
      const agentId = msg.agent_id as string;
      const entry: import("@/types/index").ToolCallEntry = {
        tool: (msg.tool as string) || "",
        args: (msg.args as Record<string, unknown>) || {},
        result: null,
        timestamp: new Date().toISOString(),
      };
      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          toolCalls: [...(updated[agentIdx].toolCalls || []), entry],
        };
        return { ...prev, agents: updated };
      });
      return true;
    }

    case "tool_result": {
      const agentId = msg.agent_id as string;
      const toolName = msg.tool as string;
      const result = (msg.result as string) || "";
      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        const toolCalls = [...(updated[agentIdx].toolCalls || [])];
        // Attach result to the last matching unresolved tool call
        for (let i = toolCalls.length - 1; i >= 0; i--) {
          if (toolCalls[i].tool === toolName && toolCalls[i].result === null) {
            toolCalls[i] = { ...toolCalls[i], result };
            break;
          }
        }
        updated[agentIdx] = { ...updated[agentIdx], toolCalls };
        return { ...prev, agents: updated };
      });
      return true;
    }

    // KAN-73 — real-time audit entry from the audit_logger hook
    case "hook_run": {
      const hookData = (msg.data as Record<string, unknown>) || {};
      const entry: import("@/types/index").HookRunEntry = {
        hook: (hookData.hook as string) || "audit_logger",
        event: (hookData.event as string) || "",
        outcome: (hookData.outcome as string) || "continue",
        detail: (hookData as import("@/types/index").HookRunEntry["detail"]) ?? null,
        created_at: (hookData.timestamp as string) || new Date().toISOString(),
      };
      setPipelineState((prev) => ({
        ...prev,
        hookRuns: [...(prev.hookRuns || []), entry],
      }));
      return true;
    }

    case "planner_start": {      // Universal Engine: Deep_Planner_Agent began. Capture pipeline_run_id
      // (needed for submit_questionnaire) and show a planning status.
      const data = (msg.data as Record<string, unknown>) || msg;
      const pipelineRunId = data.pipeline_run_id as string | undefined;
      setPipelineState((prev) => ({
        ...prev,
        isRunning: true,
        pipelineRunId: pipelineRunId ?? prev.pipelineRunId,
        plannerStatus: "running",
      }));

      // Also persist to sessionStorage for reconnection resilience
      if (pipelineRunId) {
        try {
          sessionStorage.setItem("active_pipeline_run_id", pipelineRunId);
        } catch { /* non-fatal */ }
      }

      return true;
    }

    case "planner_complete": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const planning = (data.planning_context as Record<string, unknown>) || {};
      const gate = (data.execution_gate as string) || (planning.execution_gate as string) || "PROCEED";
      setPipelineState((prev) => ({
        ...prev,
        plannerStatus: "complete",
        plannerSummary: (planning.inferred_intent as string) || prev.plannerSummary,
        executionGate: gate as "PROCEED" | "CLARIFY_REQUIRED",
      }));
      return true;
    }

    case "planner_timeout": {
      setPipelineState((prev) => ({ ...prev, plannerStatus: "timeout" }));
      return true;
    }

    case "planner_error": {
      setPipelineState((prev) => ({ ...prev, plannerStatus: "error" }));
      return true;
    }

    case "gate_status": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const verdict = (data.verdict as string) || "PROCEED";
      setPipelineState((prev) => ({
        ...prev,
        executionGate: verdict as "PROCEED" | "CLARIFY_REQUIRED",
      }));
      return true;
    }

    case "task_progress": {
      // Prototype build agent reported a task completion via report_task_complete tool
      const completedTasks = (msg.completed_tasks as Array<{ number: number; title: string; summary: string }>) || [];
      const completedCount = (msg.completed_count as number) || completedTasks.length;
      setPipelineState((prev) => {
        // KAN-120 BUG-3: on a mid-build resume the engine's task_loop strategy
        // only reports tasks completed IN THIS RESUME SESSION (tasks after the
        // skip cursor). A plain replace would wipe task 1 and task 2's data when
        // task 3 first completes. Merge instead: keep every existing task entry
        // that is NOT overridden by the new array, so pre-stop task data is
        // preserved throughout the resumed run. Tasks are keyed by .number (1-based).
        const existingByNumber = new Map((prev.protoCompletedTasks ?? []).map(t => [t.number, t]));
        for (const t of completedTasks) {
          // New data wins for any task the resumed run reports; existing data
          // is preserved for tasks the new array does not include.
          existingByNumber.set(t.number, t);
        }
        // Sort by task number so the Steps panel renders in order.
        const mergedTasks = [...existingByNumber.values()].sort((a, b) => a.number - b.number);
        // completedCount is authoritative from the backend; use the merged array
        // length as a lower bound so it never decreases past what we've seen.
        const newCount = Math.max(completedCount, mergedTasks.length, prev.protoCompletedTaskCount ?? 0);
        return {
          ...prev,
          protoCompletedTasks: mergedTasks,
          protoCompletedTaskCount: newCount,
        };
      });
      return true;
    }

    case "task_loop_progress": {
      // Engine-level: build loop started a new task iteration.
      // KAN-153: the event also carries `total_tasks` — store it so the
      // ConstructionBlock can show ALL tasks upfront with "pending" status
      // instead of revealing them one-by-one as task_progress events arrive.
      const taskNumber = (msg.task_number as number) || 0;
      const totalTasksFromLoop = (msg.total_tasks as number) || 0;
      const completedFromLoop = Math.max(0, taskNumber - 1);
      setPipelineState((prev) => {
        const currentCount = prev.protoCompletedTaskCount ?? 0;
        const currentTotal = prev.protoTotalTasks ?? 0;
        // Parse task titles from the planner agent's output on the FIRST iteration
        // (task_number === 1 and we don't yet have planned tasks). The planner output
        // uses `## Task N: Title` headings — extract each title cheaply with a regex.
        // INV-1: keyed on generic `## Task N:` pattern, never an agent-id literal.
        let plannedTasks = prev.protoPlannedTasks;
        if (taskNumber === 1 && !plannedTasks && totalTasksFromLoop > 0) {
          const allTitles: Array<{ number: number; title: string }> = [];
          // Find the planner agent output — the one that contains `## Task 1:`
          for (const agent of prev.agents) {
            const output = agent.output || "";
            if (output.includes("## Task 1:") || output.includes("## Task 1 :")) {
              // Extract all `## Task N: Title` lines
              const matches = output.matchAll(/^##\s+Task\s+(\d+)\s*:\s*(.+)$/gm);
              for (const m of matches) {
                const num = parseInt(m[1], 10);
                const title = m[2].trim();
                if (num > 0 && title) allTitles.push({ number: num, title });
              }
              if (allTitles.length > 0) break;
            }
          }
          if (allTitles.length > 0) plannedTasks = allTitles;
        }
        return {
          ...prev,
          protoCompletedTaskCount: completedFromLoop > currentCount ? completedFromLoop : currentCount,
          // Use Math.max so the total never decreases (handles event redelivery).
          protoTotalTasks: totalTasksFromLoop > currentTotal ? totalTasksFromLoop : currentTotal,
          protoPlannedTasks: plannedTasks,
          // Keep the in-flight task number and WHICH agent is running it. Both
          // are already on the event; the agent id was being discarded, which is
          // why the per-agent row could only ever say "Thinking…" during a build
          // loop instead of naming the task it is on.
          protoCurrentTask: taskNumber > 0 ? taskNumber : prev.protoCurrentTask,
          protoTaskAgentId: (msg.agent_id as string) || prev.protoTaskAgentId,
        };
      });
      return true;
    }

    case "clarification_limit_reached": {
      setPipelineState((prev) => ({ ...prev, clarificationLimitReached: true }));
      return true;
    }

    case "workflow_validated": {
      // Phase 3 (T064) — store DAG edges for the visual dependency graph
      const data = (msg.data as Record<string, unknown>) || msg;
      const dagEdges = (data.dag_edges as Array<{ from: string; to: string; artifact_type: string }>) || [];
      const unresolvedEdges = (data.unresolved_edges as Array<{ consuming_agent_id: string; artifact_type: string }>) || [];
      setPipelineState((prev) => ({ ...prev, dagEdges, unresolvedEdges }));
      return true;
    }

    case "validator_result": {
      // Phase 8 (API-03) — capture validation issues for display in Thinking tab.
      // These fire after a post_step: revision_validation (prototype revision)
      // or any other validator gate. Store them on the agent whose step triggered.
      const data = (msg.data as Record<string, unknown>) || msg;
      const agentId = (data.agent_id as string) || "";
      const issues = (data.issues as import("@/types/index").ValidationIssue[]) || [];
      if (agentId && issues.length > 0) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = {
            ...updated[agentIdx],
            validationIssues: [...(updated[agentIdx].validationIssues || []), ...issues],
          };
          return { ...prev, agents: updated };
        });
      }
      return true;
    }

    case "gate_passed": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const agentId = (data.agent_id as string) || "";
      if (agentId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = { ...updated[agentIdx], validationPassed: true };
          return { ...prev, agents: updated };
        });
      }
      return true;
    }

    case "gate_blocked": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const agentId = (data.agent_id as string) || "";
      if (agentId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = { ...updated[agentIdx], validationPassed: false };
          return { ...prev, agents: updated };
        });
      }
      return true;
    }

    default:
      return false;
  }
}
