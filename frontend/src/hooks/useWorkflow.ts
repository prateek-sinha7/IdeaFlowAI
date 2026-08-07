"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState, AttachedSkill, AttachedHook, ClarifyRound } from "@/types/index";
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
  startPipeline: (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>) => Promise<string | null>;
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
    (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>): Promise<string | null> => {
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

      // Pass attached skills content — backend injects into agent system prompts
      if (attachedSkills && attachedSkills.length > 0) {
        payload.attached_skills = attachedSkills.map(s => ({
          id: s.id,
          name: s.name,
          content: s.content,
          source: s.sourceLabel,
          compatible_agents: [], // all agents get it unless filtered
        }));
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
  };
}

/**
 * Process an incoming pipeline WebSocket message and update state.
 * Call this from the parent component's onMessage handler.
 */
export function handlePipelineMessage(
  msg: { type: string; [key: string]: unknown },
  setPipelineState: React.Dispatch<React.SetStateAction<PipelineRunState>>,
  agentStartTimesRef: React.MutableRefObject<Record<string, number>>
): boolean {
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

      const agentStates: AgentRunState[] = agents.map((a, idx) => ({
        id: a.id,
        name: a.name,
        role: a.role,
        icon: a.icon || "🤖",
        // KAN-120 BUG-2: agents before the resume offset are already done.
        status: idx < resumeOffset ? "done" : "idle",
        output: "",
        thinking: "",
        duration: null,
        error: null,
        index: idx,
      }));

      setPipelineState((prev) => ({
        ...prev,
        isRunning: true,
        pipeline_type: (msg.pipeline_type as string) || prev.pipeline_type,
        pipelineRunId: pipelineRunIdFromStart ?? prev.pipelineRunId,
        agents: agentStates,
        currentAgentIndex: resumeOffset > 0 ? resumeOffset : 0,
        // KAN-120 BUG-2: on resume, seed completedCount from the offset so
        // the progress bar shows correct proportion immediately.
        completedCount: resumeOffset > 0 ? resumeOffset : 0,
        // KAN-120 BUG-3: on resume, carry over protoCompletedTasks from prev
        // so task data already recorded before the stop is not wiped. The
        // task_progress max-wins handler below will extend it as new tasks
        // complete. On a fresh run (resumeOffset==0) prev.protoCompletedTasks
        // is undefined/empty → same as before (byte-identical, INV-3).
        protoCompletedTasks: resumeOffset > 0 ? (prev.protoCompletedTasks ?? []) : [],
        protoCompletedTaskCount: resumeOffset > 0 ? (prev.protoCompletedTaskCount ?? 0) : 0,
        // KAN-153: reset the known total on a fresh run; preserve on resume so
        // the ConstructionBlock keeps showing the full task list while catching up.
        protoTotalTasks: resumeOffset > 0 ? (prev.protoTotalTasks ?? 0) : 0,
        protoPlannedTasks: resumeOffset > 0 ? prev.protoPlannedTasks : undefined,
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
      }));

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

        return {
          ...prev,
          agents: updated,
          currentAgentIndex: agentIdx,
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
          // Phase 3 (T043): accumulate into thinkingText for Thinking tab
          thinkingText: (updated[agentIdx].thinkingText || "") + (thinking ? thinking + "\n" : ""),
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
          isRunning: false,
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
          isRunning: false,
          totalDuration,
          completedCount: updated.filter((a) => a.status === "done").length,
          // ISS-017 (16-04): surface an additive server `failed` signal on the
          // run state (mirrors the degraded/degradedFailedAgents pattern in the
          // pipeline_complete handler). PreviewPanel keys its terminal-empty
          // degraded/failed affordance on this server-derived flag — NOT a
          // client-side empty==failed guess.
          failed: true,
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
          isRunning: false,
          totalDuration,
          completedCount: updated.filter((a) => a.status === "done").length,
          // ISS-035 (SC-4): stamp the terminal cancelled marker (symmetric with
          // pipeline_failed's `failed` flag above) so a downstream selector
          // derives the LIVE-STATE-CONTRACT §1 cancelled state ("Cancelled by
          // you") instead of falling through to idle. No chat message is pushed
          // from the reducer — RunChatLane renders the transcript line off this
          // marker + the generic RunLaneState (plan 06).
          cancelled: true,
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

      const TERMINAL_STATUSES = ["completed", "failed", "cancelled", "error"];
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
