"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState, AttachedHook, ClarifyRound, WaveWorkerEntry } from "@/types/index";
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
  // A14 — optional second arg: the run's persisted `warnings`, forwarded
  // verbatim to applyTerminalStatus (see its own doc for the undefined rule).
  reconcileTerminalStatus: (status: string, warnings?: string[], usage?: Parameters<typeof applyTerminalStatus>[3]) => void;
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
  const reconcileTerminalStatus = useCallback(
    (status: string, warnings?: string[], usage?: Parameters<typeof applyTerminalStatus>[3]) => {
      setPipelineState((prev) => applyTerminalStatus(prev, status, warnings, usage));
    },
    [],
  );

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
  "agent_complete",   // agents[].cumulativeDuration
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
 * The frame types that can change whether the run is BUSY or WAITING. Everything else
 * (chunks, thinking, tool calls) happens strictly inside an interval one of these opens.
 */
const TIMELINE_FRAME_TYPES: ReadonlySet<string> = new Set([
  "pipeline_start", "agent_start", "agent_complete", "agent_error", "agent_skipped",
  "review_gate_ready", "review_gate_approved",
  "pipeline_complete", "pipeline_failed", "pipeline_cancelled",
]);

/**
 * Fold the interval [last timeline event, `ts`) into the busy/waiting split.
 *
 * Called BEFORE the case that handles the frame, because that interval was spent under
 * the condition the state is in NOW — the gate that is about to close was open for it,
 * the agent that is about to start was not yet running.
 *
 * Busy is derived from "is any agent non-terminal", which makes it an interval UNION for
 * free: five readers running concurrently keep it true exactly once, so the 199s they
 * overlap in run faba87c9 is counted once rather than five times. A naive sum of the
 * per-step numbers cannot reconcile against the header for precisely that reason.
 *
 * Driven by the event's own `ts` (stamped by the engine, forwarded verbatim by
 * run_stream.py's replay) and never `Date.now()`, so a reopened run accounts identically
 * to a live one. That also makes it self-gating against re-delivery — a replayed frame
 * carries a `ts` at or behind the cursor, so `dt <= 0` folds nothing in — which is why it
 * runs on the RAW setter: routing it through the ISS-082 identity gate would advance
 * `lastAppliedSeq` and make the real handler for the same frame look like a re-delivery.
 */
export function advanceTimeline(prev: PipelineRunState, ts: string): PipelineRunState {
  const now = Date.parse(ts);
  if (Number.isNaN(now)) return prev;
  if (!prev.timelineTs) return { ...prev, timelineTs: ts };
  const dt = (now - Date.parse(prev.timelineTs)) / 1000;
  // Re-delivered, out of order, or same-instant (step_end and agent_complete share a ts):
  // fold nothing, and do NOT rewind the cursor either.
  if (!(dt > 0)) return prev;
  const busy = prev.agents.some((a) => a.status === "running" || a.status === "thinking");
  return {
    ...prev,
    timelineTs: ts,
    busySeconds: (prev.busySeconds ?? 0) + (busy ? dt : 0),
    // Time with nothing running is only WAITING if it is waiting on a person. Anything
    // else is engine overhead and stays unattributed rather than being quietly absorbed.
    waitingSeconds: (prev.waitingSeconds ?? 0) + (!busy && prev.gateOpen ? dt : 0),
  };
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
  // A14 — the run's persisted `warnings` (e.g. from a reopened `WorkflowRun`),
  // additive/optional so every existing 2-arg call site keeps compiling.
  // Undefined (whether omitted or explicit) leaves `prev.warnings` untouched,
  // so a caller that hasn't been taught about warnings yet (page.tsx's two
  // call sites, pending A24) cannot accidentally wipe a value the live
  // `pipeline_complete` reducer case already set on `prev`.
  warnings?: string[],
  // ISS-304 — the run's PERSISTED `token_usage`, same additive/optional
  // contract as `warnings` above.
  //
  // A reopened run's totals are rebuilt by replaying its durable events, and
  // the `agent_complete` case sums the per-agent figures. That sum is the best
  // available reading WHILE a run streams, but it is not the run's total: work
  // not attributed to a top-level agent row (wave workers, sub-agents) never
  // lands in it. Measured on run 26a7e162 — the header read 13.6M where the
  // run's own `token_usage.total_tokens` was 19.7M, a 6.1M shortfall on the
  // one number a user would check a bill against.
  //
  // The server's persisted usage is authoritative for a settled run, so it
  // wins here, in the same after-the-replay reconciliation that already
  // restores the persisted STATUS (ISS-126). Undefined leaves the replayed
  // values untouched, so every existing call site keeps its behaviour.
  usage?: {
    total_tokens?: number;
    total_input_tokens?: number;
    total_output_tokens?: number;
    total_cache_read_tokens?: number;
    total_cache_write_tokens?: number;
    estimated_cost_usd?: number;
  },
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
    ...(warnings !== undefined ? { warnings } : {}),
    ...(usage
      ? {
          ...(usage.total_tokens !== undefined ? { totalTokens: usage.total_tokens } : {}),
          ...(usage.total_input_tokens !== undefined ? { totalInputTokens: usage.total_input_tokens } : {}),
          ...(usage.total_output_tokens !== undefined ? { totalOutputTokens: usage.total_output_tokens } : {}),
          ...(usage.total_cache_read_tokens !== undefined ? { cacheReadTokens: usage.total_cache_read_tokens } : {}),
          ...(usage.total_cache_write_tokens !== undefined ? { cacheWriteTokens: usage.total_cache_write_tokens } : {}),
          ...(usage.estimated_cost_usd !== undefined ? { estimatedCostUsd: usage.estimated_cost_usd } : {}),
        }
      : {}),
  };
}

/** Upsert one wave worker's child row onto its parent agent, keyed by
 *  `task_id` (a worker's agent_start THEN agent_complete both carry the same
 *  task_id, so the second call updates the first's entry rather than adding
 *  a duplicate). wave_index/worker_index/wave_total are re-stamped from the
 *  incoming event when present, else carried over from the existing entry. */
function upsertWaveWorker(
  agent: AgentRunState,
  msg: { [key: string]: unknown },
  status: WaveWorkerEntry["status"],
): AgentRunState {
  const taskId = msg.task_id as string;
  const workers = agent.waveWorkers ? [...agent.waveWorkers] : [];
  const idx = workers.findIndex((w) => w.taskId === taskId);
  const prior = idx !== -1 ? workers[idx] : undefined;
  const entry: WaveWorkerEntry = {
    taskId,
    status,
    workerIndex: typeof msg.worker_index === "number" ? (msg.worker_index as number) : prior?.workerIndex,
    waveIndex: typeof msg.wave_index === "number" ? (msg.wave_index as number) : prior?.waveIndex,
    waveTotal: typeof msg.wave_total === "number" ? (msg.wave_total as number) : prior?.waveTotal,
    taskAuthorId: typeof msg.task_author_id === "string"
      ? (msg.task_author_id as string) : prior?.taskAuthorId,
    error: typeof msg.error === "string" ? (msg.error as string) : prior?.error,
    // Carried forward, never cleared — a member's tool calls and reasoning
    // accumulate across its events, and its output arrives on agent_complete.
    toolCalls: prior?.toolCalls,
    thinking: prior?.thinking,
    contextSources: prior?.contextSources,
    // Output is accumulated from this member's chunks; agent_complete carries no
    // output text, so it must never overwrite what the chunks built.
    output: prior?.output,
    inputPrompt: typeof msg.input_prompt === "string" && msg.input_prompt
      ? (msg.input_prompt as string)
      : typeof msg.task_block === "string" && msg.task_block
      ? (msg.task_block as string)
      : prior?.inputPrompt,
    estimatedCostUsd: typeof msg.estimated_cost_usd === "number"
      ? (msg.estimated_cost_usd as number) : prior?.estimatedCostUsd,
    attachedSkills: prior?.attachedSkills,
    attachedHooks: prior?.attachedHooks,
    validationIssues: prior?.validationIssues,
    validationPassed: prior?.validationPassed,
    inputTokens: typeof msg.input_tokens === "number" ? (msg.input_tokens as number) : prior?.inputTokens,
    outputTokens: typeof msg.output_tokens === "number" ? (msg.output_tokens as number) : prior?.outputTokens,
    totalTokens: typeof msg.total_tokens === "number" ? (msg.total_tokens as number) : prior?.totalTokens,
    // Start the clock on the FIRST event for this member, whatever it is — its
    // agent_start is not guaranteed to be the first thing we see.
    startedAt: prior?.startedAt ?? Date.now(),
    // Prefer the server's own duration (seconds), same as the parent step does
    // at :1018. The measured wall time is only a fallback, and a WEAK one for a
    // wave member: its events ride a queue (fanout.py's side channel) and can
    // drain together, so start and complete land milliseconds apart. A model
    // call cannot finish in under a second, so a sub-second measurement is a
    // queue artefact — report nothing rather than a confident "0s".
    durationMs: typeof msg.duration === "number"
      ? (msg.duration as number) * 1000
      : status === "done" || status === "failed"
      ? (prior?.startedAt && Date.now() - prior.startedAt >= 1000
          ? Date.now() - prior.startedAt
          : prior?.durationMs)
      : prior?.durationMs,
  };
  if (idx === -1) workers.push(entry);
  else workers[idx] = entry;
  return { ...agent, waveWorkers: workers };
}

/** Append reasoning text to the wave member that produced it, keyed by task_id.
 *  Every clone in a wave reports the parent's agent_id, so without this split the
 *  five readers' reasoning interleaves into one unreadable stream on the step. */
function appendWorkerThinking(
  agent: AgentRunState,
  taskId: string,
  text: string,
): AgentRunState {
  const workers = agent.waveWorkers ? [...agent.waveWorkers] : [];
  const idx = workers.findIndex((w) => w.taskId === taskId);
  const prior = idx === -1 ? { taskId, status: "running" as const } : workers[idx];
  const next = { ...prior, thinking: (prior.thinking ?? "") + text };
  if (idx === -1) workers.push(next);
  else workers[idx] = next;
  return { ...agent, waveWorkers: workers };
}

/** Generic upsert of one field-set onto the wave member named by task_id. A call
 *  can arrive before that member's agent_start, so the row is seeded rather than
 *  the event dropped. */
function patchWorker(
  agent: AgentRunState,
  taskId: string,
  patch: (prior: WaveWorkerEntry) => WaveWorkerEntry,
): AgentRunState {
  const workers = agent.waveWorkers ? [...agent.waveWorkers] : [];
  const idx = workers.findIndex((w) => w.taskId === taskId);
  const prior = idx === -1
    ? ({ taskId, status: "running", startedAt: Date.now() } as WaveWorkerEntry)
    : workers[idx];
  const next = patch(prior);
  if (idx === -1) workers.push(next);
  else workers[idx] = next;
  return { ...agent, waveWorkers: workers };
}

/** Accumulate a member's own output text from its own chunks. */
function appendWorkerOutput(agent: AgentRunState, taskId: string, chunk: string): AgentRunState {
  return patchWorker(agent, taskId, (p) => ({ ...p, output: (p.output ?? "") + chunk }));
}

/** Record a member's own input prompt and context sources. */
function setWorkerInput(
  agent: AgentRunState,
  taskId: string,
  inputPrompt: string | undefined,
  contextSources: import("@/types/index").ContextSource[],
): AgentRunState {
  return patchWorker(agent, taskId, (p) => ({
    ...p,
    inputPrompt: inputPrompt ?? p.inputPrompt,
    contextSources: contextSources.length ? contextSources : p.contextSources,
  }));
}

/** Append a tool call to the wave member that made it, keyed by task_id. */
function appendWorkerToolCall(
  agent: AgentRunState,
  taskId: string,
  entry: import("@/types/index").ToolCallEntry,
): AgentRunState {
  const workers = agent.waveWorkers ? [...agent.waveWorkers] : [];
  const idx = workers.findIndex((w) => w.taskId === taskId);
  // A tool call can arrive before the worker's agent_start; seed a row rather
  // than dropping the call.
  const prior = idx === -1 ? { taskId, status: "running" as const } : workers[idx];
  const next = { ...prior, toolCalls: [...(prior.toolCalls ?? []), entry] };
  if (idx === -1) workers.push(next);
  else workers[idx] = next;
  return { ...agent, waveWorkers: workers };
}

/** Attach a result to that member's last unresolved call of the same tool. */
function resolveWorkerToolCall(
  agent: AgentRunState,
  taskId: string,
  toolName: string,
  result: string,
): AgentRunState {
  const workers = agent.waveWorkers ? [...agent.waveWorkers] : [];
  const idx = workers.findIndex((w) => w.taskId === taskId);
  if (idx === -1) return agent;
  const calls = [...(workers[idx].toolCalls ?? [])];
  for (let i = calls.length - 1; i >= 0; i--) {
    if (calls[i].tool === toolName && calls[i].result === null) {
      calls[i] = { ...calls[i], result };
      break;
    }
  }
  workers[idx] = { ...workers[idx], toolCalls: calls };
  return { ...agent, waveWorkers: workers };
}

/** Settle a wave step's child rows when the step itself reaches a terminal
 *  state. A worker still "running" at that point will never report again — its
 *  outcome was lost (a failed dispatch, a budget refusal, a repair pass that
 *  never completed). Leaving it spinning claims work is still in flight when
 *  the run is over, which is the opposite of the truth; marking it done would
 *  be worse. It becomes "stranded" — visibly ended, explicitly not successful. */
function settleWaveWorkers(agent: AgentRunState): AgentRunState {
  const workers = agent.waveWorkers;
  if (!workers || !workers.some((w) => w.status === "running")) return agent;
  return {
    ...agent,
    waveWorkers: workers.map((w) =>
      w.status === "running"
        ? { ...w, status: "stranded" as const,
            error: w.error ?? "the step ended before this worker reported a result" }
        : w,
    ),
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

  // Wall-clock accounting, folded in before the handler changes the state that defines
  // it. RAW setter on purpose — see `advanceTimeline`.
  if (TIMELINE_FRAME_TYPES.has(msg.type) && typeof msg.ts === "string") {
    setPipelineStateRaw((prev) => advanceTimeline(prev, msg.ts as string));
  }

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
          // ISS-317: an `error` carried from the PRE-resume attempt is stale
          // evidence the resume itself supersedes — the same treatment the
          // terminal cancelled/failed/degraded markers already get below. Spread
          // verbatim it kept every reader of this array (the Steps summary label,
          // its progress-bar segment and per-row style, RunChatLane's PipelineMini
          // pip, AgentDetailPanel's isError) showing a re-running agent as failed
          // until that agent's own agent_start finally fired. Reset it to the
          // fresh-roster rule instead.
          if (existing) {
            if (existing.status !== "error") return { ...existing, ...identity };
            return {
              ...existing,
              ...identity,
              status: idx < resumeOffset ? "done" : "idle",
              error: null,
            };
          }
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
          // ISS-108: preserve answered clarify rounds on a continuation; reset on a
          // genuinely fresh run so the prior Q&A never leaks into the new run.
          // Mirrors the protoCompletedTasks pattern on the same predicate.
          clarifications: isContinuation ? (prev.clarifications ?? []) : [],
          // ISS-110: preserve hookRuns on a continuation; reset on a fresh run so
          // the prior run's audit log never leaks. hookRuns is in
          // ACCUMULATING_FRAME_TYPES, so the dedup gate already covers it — only
          // the per-run boundary was missing.
          hookRuns: isContinuation ? (prev.hookRuns ?? []) : [],
          // KAN-120: clear terminal markers so a resumed run does not stay in
          // the "terminal" state (cancelled/failed) after pipeline_start fires.
          // Without this, pipeline_complete resolves isRunning→false but
          // cancelled/failed is still true → runLaneState falls back to "terminal"
          // and shows "Cancelled by you" / "Run Again" instead of the deliverable.
          cancelled: undefined,
          failed: undefined,
          degraded: undefined,
          // Gap fix: clear a stale `error` frame's message so a resumed/re-announced
          // run does not keep showing the previous attempt's failure reason.
          pipelineError: undefined,
          // Phase 39 (RUNUI-06): surface the run's created_at so the lane header can
          // render a relative age ("23h ago"). ADDITIVE optional.
          //
          // ISS-276: NO "now" fallback. This reducer is fed by BOTH the live SSE
          // stream and the durable REST replay (getRunEvents → handleWebSocketMessage),
          // and the two frames are identical on the wire — so stamping the receipt time
          // dated a day-old run to page-load time and froze the lane header on "just
          // now". A frame that carries no created_at now leaves the field unset, and
          // formatRelativeAge(undefined) renders "" (dropped by the header's
          // filter(Boolean)) — a blank instead of a wrong age. The engine stamps the
          // run's real created_at on pipeline_start (engine.py, same fix), so live runs
          // and every run recorded after it still render the real age.
          createdAt: (msg.created_at as string) || prev.createdAt,
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
      const taskId = msg.task_id as string | undefined;

      // A wave worker clone (per-task stamp) — every worker in a wave shares
      // the PARENT's agent_id, so this is a CHILD row nested under it, never
      // a re-render of the parent. Only the parent's own agent_start (no
      // task_id) runs the full reset/accumulator logic below. Guarded so a
      // backend that hasn't stamped `task_id` yet (today's events) falls
      // straight through to the existing parent-only path.
      if (taskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = upsertWaveWorker(updated[agentIdx], msg, "running");
          return { ...prev, agents: updated };
        });
        return true;
      }

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
          // RFN-001 — write the resolved model id from agent_start immediately so
          // the chip shows while the agent is running (the backend now emits model_id
          // on agent_start as well as agent_complete). If the event predates the
          // engine change and carries no model_id, the chip simply stays hidden until
          // agent_complete fires (graceful degrade, no chip flip).
          modelId: (msg.model_id as string) || undefined,
          inputPrompt: undefined,
          contextSources: undefined,
          // Which PASS this is. The engine omits the field on a first dispatch, so
          // `?? 0` keeps a normal run byte-identical to before (INV-3).
          visitCount: (msg.visit_count as number | undefined) ?? 0,
          // Which DISPATCH this is. Counts the spec-revision restarts `visitCount`
          // cannot see, and is what the "pass N" badge reads. `cumulativeDuration` is
          // deliberately NOT in this reset block: it survives the pass that is starting.
          passCount: (updated[agentIdx].passCount ?? 0) + 1,
        };

        // ── a CONDITIONAL ROUTE sent the pipeline backwards ─────────────────
        // Everything after a re-entered step belongs to the previous pass and is
        // about to run again, so its "done"/"skipped" badge is a lie until it does.
        // Observed in run fafea1bc: Coverage Check (index 8) routed back to the
        // Synthesizer (7), the Synthesizer went "running", and Coverage Check kept
        // the ✓ it earned on pass 1 — an earlier step in flight underneath a later
        // step marked done, which a sequential pipeline can never be. The progress
        // counter never came down either.
        //
        // Gated on visit_count, NOT on "the pointer moved backwards", and the
        // difference is load-bearing in two directions:
        //  - fan-out: the five readers all emit agent_start before any completes,
        //    so a bare index test would have each one reset its running siblings;
        //  - spec revisions: `prototype-specify` restarts at index 0 on every
        //    revision cycle, and ISS-075 deliberately pins plan/analyze as staying
        //    "done" across it (revisions count in `revision_attempt`, never in
        //    visit_count, so that path stays byte-identical here).
        //
        // NOT covered: an engine RESUME re-dispatches from step 0 with no
        // visit_count, and its `pipeline_start` is indistinguishable from a plain
        // re-announcement (same run id, resume_offset 0), so the ISS-075
        // carry-forward at :446 keeps the pre-restart rows. Fixing that needs the
        // engine to mark the frame as a resume; see the note in the run report.
        // BOTH conditions, and the second is not redundant. Gating on visit_count
        // alone protects fan-out only on pass 1: on any later pass every
        // concurrently dispatched sibling also carries visit_count > 0, so
        // whichever of them emits `agent_start` last would reset all
        // higher-indexed siblings — including ones already running or done in
        // that same pass. Requiring the pointer to have actually moved BACKWARDS
        // excludes them, because siblings dispatch in ascending index order and
        // each is therefore a forward move.
        const movedBackwards = agentIdx <= prev.currentAgentIndex;
        if ((msg.visit_count as number | undefined) && movedBackwards) {
          for (let i = agentIdx + 1; i < updated.length; i++) {
            // Every non-idle status, not just "done" — a step killed mid-write keeps
            // "running" forever otherwise, which is how the fafea1bc screenshot ended
            // up with Document Ingest AND the Synthesizer both showing "Writing…".
            if (updated[i].status !== "idle") {
              updated[i] = {
                ...updated[i],
                status: "idle",
                // Leave `output`/tokens in place: the Steps panel still lets you open
                // a step and read what the previous pass produced, and the next
                // `agent_start` for that step clears them itself (above).
              };
            }
          }
        }

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
          // A gate is over once work resumes. Needed as well as `review_gate_approved`
          // because a "request changes" re-dispatches the step with no approval event
          // (run faba87c9: gate_ready 18:31:04 -> agent_start 18:34:17, no approval).
          gateOpen: false,
          agentStartEventIds: { ...(prev.agentStartEventIds ?? {}), [agentId]: [...priorStarts, startIdentity] },
        };
      });
      return true;
    }

    case "agent_thinking": {
      const agentId = msg.agent_id as string;
      const thinking = (msg.thinking as string) || "";

      // A wave member's reasoning carries its task_id. Route it to that member,
      // or five readers' reasoning interleaves into one stream on the step.
      const thTaskId = msg.task_id as string | undefined;
      if (thTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = appendWorkerThinking(updated[agentIdx], thTaskId, thinking);
          return { ...prev, agents: updated };
        });
        return true;
      }

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

      // A step's output is ACCUMULATED from its chunks — agent_complete carries
      // no output text. A wave member is no different, and its chunks arrive on
      // the side channel stamped with its task_id.
      const chTaskId = msg.task_id as string | undefined;
      if (chTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = appendWorkerOutput(updated[agentIdx], chTaskId, chunk);
          return { ...prev, agents: updated };
        });
        return true;
      }

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
      const taskId = msg.task_id as string | undefined;

      // Same wave-worker branch as agent_start above — mark this worker's
      // child row done, never the parent's own accumulators/status.
      if (taskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = upsertWaveWorker(updated[agentIdx], msg, "done");
          return { ...prev, agents: updated };
        });
        return true;
      }

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
          ...settleWaveWorkers(updated[agentIdx]),
          status: "done",
          duration,
          thinking: "",
          inputTokens: (msg.input_tokens as number) || 0,
          outputTokens: (msg.output_tokens as number) || 0,
          totalTokens: (msg.total_tokens as number) || 0,
          estimatedCostUsd: (msg.estimated_cost_usd as number) || 0,
          // The engine mirrors visit_count on BOTH ends (engine.py :5754) so a client
          // can pair start/complete per pass; keep the pass the finished numbers
          // belong to rather than letting a stale value from the previous pass stand.
          visitCount: (msg.visit_count as number | undefined) ?? updated[agentIdx].visitCount ?? 0,
          // What every pass of this step has cost. `duration` above stays last-pass-only.
          cumulativeDuration: (updated[agentIdx].cumulativeDuration ?? 0) + (duration ?? 0),
          // RFN-001 — the engine already emits the resolved per-agent model id on
          // agent_complete (engine.py). Surface it here so the chip can render
          // immediately when the agent finishes, and persist through pipeline end.
          modelId: (msg.model_id as string) || undefined,
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

    // The two gate frames are handled for their TIMING only — the gate UI itself lives in
    // app/[...view]/page.tsx and is untouched. Both are plain overwrites of a boolean, so
    // they are idempotent and stay out of ACCUMULATING_FRAME_TYPES.
    case "review_gate_ready": {
      setPipelineState((prev) => (prev.gateOpen ? prev : { ...prev, gateOpen: true }));
      return false;
    }

    case "review_gate_approved": {
      setPipelineState((prev) => (prev.gateOpen ? { ...prev, gateOpen: false } : prev));
      return false;
    }

    case "agent_error": {
      const agentId = msg.agent_id as string;
      const error = (msg.error as string) || "Unknown error";

      // A wave worker shares the PARENT's agent_id, so an unguarded error here
      // would fail the whole step. A task_id means this is a child: fail that
      // row only. Mirrors the agent_start/agent_complete worker branches.
      const errTaskId = msg.task_id as string | undefined;
      if (errTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = upsertWaveWorker(updated[agentIdx], msg, "failed");
          return { ...prev, agents: updated };
        });
        return true;
      }

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...settleWaveWorkers(updated[agentIdx]),
          status: "error",
          error,
          thinking: "",
        };

        return { ...prev, agents: updated };
      });
      return true;
    }

    // Explicit skip signal (spec 014 follow-up): the engine emits this for
    // every conditional-gate route outcome NOT chosen, right when it resolves
    // the route — a definite "this step will never run, and here's why", not
    // an inference from the step never receiving agent_start.
    case "agent_skipped": {
      const agentId = msg.agent_id as string;

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = { ...updated[agentIdx], status: "skipped", thinking: "" };

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

      // A14 — a loop-cap message that did NOT flip the run to degraded (a
      // resolved deliverable stayed "completed" server-side). Presence-gated
      // per the backend's own convention: absent/empty → no warnings fired.
      const rawWarnings = msg.warnings;
      const warnings = Array.isArray(rawWarnings) && rawWarnings.length > 0
        ? (rawWarnings as string[])
        : undefined;

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
          warnings,
          completedCount: updated.filter((a) => a.status === "done").length,
          // ISS-304: prefer the totals accumulated from agent_complete, and fall
          // back to the event's own fields only when nothing accumulated (so a
          // run with no per-agent events never wipes the token card to zero).
          // The event's totals are NOT the same authority as the rest of the app:
          // `pipeline_complete.total_*` additionally folds in aux_token_usage
          // (planner/clarify/fix-loop, engine.py ISS-033), while the persisted
          // `workflow_runs.token_usage` every OTHER reader shows — the Run History
          // card, GET /api/runs/{id}, Analytics — is re-derived from agent_complete
          // alone. Taking the event field made this one header disagree with the
          // same run's own API (17.9K vs 10.4K). Accumulating from agent_complete
          // is the SAME set token_usage is built from, so the two now agree.
          totalInputTokens: prev.totalInputTokens || (msg.total_input_tokens as number) || 0,
          totalOutputTokens: prev.totalOutputTokens || (msg.total_output_tokens as number) || 0,
          totalTokens: prev.totalTokens || (msg.total_tokens as number) || 0,
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

    // Gap fix: the REST driver's generic run-failure frame (run_commands.py ~3420),
    // e.g. {type:"error", data:{error, code:"pipeline_error", recoverable}}. Distinct
    // from `pipeline_failed` (that one is the terminal per-run sweep with an
    // agents_failed list); this is the live, plain-text reason a user watching the
    // run SHOULD see immediately instead of only after history re-fetches it from
    // the DB on reopen. Stored on its own field — never overwrites a more specific
    // per-agent `error` already set by `agent_error`; a consumer picks whichever is
    // more specific.
    case "error": {
      const error = msg.error as string | undefined;
      if (!error) return false;
      setPipelineState((prev) => ({ ...prev, pipelineError: error }));
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
      //
      // Stale-status-chip fix: a RESUMED run (Resume/Reopen on a cancelled or
      // failed run) attaches via this event, not `pipeline_start` — a resume
      // does not re-announce the pipeline, so `pipeline_start`'s own
      // cancelled/failed/degraded clear (KAN-120, above) never runs. Without
      // clearing them here too, `pipelineState.cancelled` stood from the
      // earlier `pipeline_cancelled` frame while the run was actively
      // executing again, and the header chip read "Cancelled" until a full
      // reload re-fetched the run's REST status. Idempotent no-op on an
      // ordinary live reconnect (those fields are already unset).
      if (live !== false) {
        setPipelineState((prev) =>
          (prev.isRunning && !prev.cancelled && !prev.failed && !prev.degraded && !prev.pipelineError)
            ? prev
            : { ...prev, isRunning: true, cancelled: undefined, failed: undefined, degraded: undefined, pipelineError: undefined }
        );
        return true;
      }

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
      // Requirement 36: store system_prompt and context_message separately so
      // AgentDetailPanel can render them as distinct labelled sections.
      // inputPrompt keeps the targeted retry payload / step task (context_message)
      // for backward-compatible rendering on old SSE streams.
      const systemPrompt = (msg.system_prompt as string) || undefined;
      const contextMessage = (msg.context_message as string) || undefined;
      // inputPrompt = context_message when system_prompt is present (new streams),
      // or context_message alone when system_prompt is absent (old streams).
      // This keeps the RevisionInstructionCard logic working on inputPrompt.
      const inputPrompt = contextMessage;
      const contextSources = (msg.context_sources as import("@/types/index").ContextSource[]) || [];

      // A wave member's own input and context — otherwise its page shows the
      // step's, which is the same for all N members and says nothing about this one.
      const aiTaskId = msg.task_id as string | undefined;
      if (aiTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = setWorkerInput(updated[agentIdx], aiTaskId, inputPrompt, contextSources);
          return { ...prev, agents: updated };
        });
        return true;
      }

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = { ...updated[agentIdx], inputPrompt, systemPrompt, contextSources };
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

      // A wave member's own skills/hooks — the member page is the SAME page a
      // step gets, so every section it has must be filled from that member's
      // own events rather than the step's.
      const asTaskId = msg.task_id as string | undefined;
      if (asTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = patchWorker(updated[agentIdx], asTaskId, (p) => ({
            ...p, attachedSkills, attachedHooks,
          }));
          return { ...prev, agents: updated };
        });
        return true;
      }

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
      // A wave member's events carry task_id (stamped in fanout.py at push time).
      // Without this branch all N members' calls land on the parent step and the
      // wave becomes uninvestigable — "all is combined here".
      const tcTaskId = msg.task_id as string | undefined;
      if (tcTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = appendWorkerToolCall(updated[agentIdx], tcTaskId, entry);
          return { ...prev, agents: updated };
        });
        return true;
      }
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
      const trTaskId = msg.task_id as string | undefined;
      if (trTaskId) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = resolveWorkerToolCall(updated[agentIdx], trTaskId, toolName, result);
          return { ...prev, agents: updated };
        });
        return true;
      }
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
      // A wave member's own validation result, same reasoning as skills above.
      const vrTaskId = data.task_id as string | undefined;
      if (agentId && vrTaskId && issues.length > 0) {
        setPipelineState((prev) => {
          const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
          if (agentIdx === -1) return prev;
          const updated = [...prev.agents];
          updated[agentIdx] = patchWorker(updated[agentIdx], vrTaskId, (p) => ({
            ...p,
            validationIssues: [...(p.validationIssues || []), ...issues],
            validationPassed: false,
          }));
          return { ...prev, agents: updated };
        });
        return true;
      }
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

    // A wave ran but dispatched ZERO tasks, so it did nothing — the agent's own
    // agent_complete still fires normally, so without this flag a no-op wave is
    // indistinguishable from one that did the work. Flag-only; never overrides
    // the status transitions agent_start/agent_complete already own.
    case "wave_skipped": {
      const agentId = msg.agent_id as string;
      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          waveSkipped: {
            reason: (msg.reason as string) || "",
            sourceStep: msg.source_step as string | undefined,
          },
        };
        return { ...prev, agents: updated };
      });
      return true;
    }

    // The engine detected and re-dispatched tasks a prior wave pass dropped —
    // rendered as a warning row, not a failure.
    case "wave_repair": {
      const agentId = msg.agent_id as string;
      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;
        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          waveRepair: {
            waveIndex: (msg.wave_index as number) ?? 0,
            missingTaskIds: Array.isArray(msg.missing_task_ids) ? (msg.missing_task_ids as string[]) : [],
            count: (msg.count as number) ?? 0,
          },
        };
        return { ...prev, agents: updated };
      });
      return true;
    }

    // Task 9.2 (sandbox-git-versioning-v2, Req 20/19): chain_context_unavailable
    // Emitted when the chain payload is unavailable at install time (departure N3
    // / Requirement 6 AC 16). Payload carries one of five bounded reason codes —
    // no PII, secrets, file contents, internal paths, or another owner's run id.
    //
    // Task 11.8 (Req 21 AC 9): also fired synthetically by RunConnectionProvider
    // when a new frontend detects an older backend that does not support v2
    // chaining (reason: "incompatible_backend"), or for any other unrecognised
    // version combination (reason: "unsupported_version_combination").  Both
    // fall through to the existing generic-fallback path in RunEngineNotice, so
    // no structural change is needed here.
    case "chain_context_unavailable": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const reason = (data.reason as string) || "unknown";
      setPipelineState((prev) => ({ ...prev, chainContextUnavailableReason: reason }));
      return true;
    }

    // Task 9.2 (sandbox-git-versioning-v2, Req 20/19): run_finalization_failed
    // Emitted when finalize_terminal_run completes in a degraded state. Payload
    // carries a bounded degraded_reason from the finalization record — no PII,
    // secrets, file contents, internal paths, or another owner's run id.
    case "run_finalization_failed": {
      const data = (msg.data as Record<string, unknown>) || msg;
      const reason = (data.reason as string) || "unknown";
      setPipelineState((prev) => ({ ...prev, finalizationFailedReason: reason }));
      return true;
    }

    default:
      return false;
  }
}
