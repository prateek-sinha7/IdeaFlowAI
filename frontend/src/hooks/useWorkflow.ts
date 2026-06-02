"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState, AttachedSkill, AttachedHook } from "@/types/index";

export interface UseWorkflowReturn {
  pipelineState: PipelineRunState;
  startPipeline: (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>) => void;
  resetPipeline: () => void;
  isRunning: boolean;
  handleMessage: (msg: { type: string; [key: string]: unknown }) => boolean;
  submitQuestionnaire: (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>) => void;
}

const INITIAL_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
};

/**
 * Custom hook that manages workflow pipeline state and WebSocket communication.
 * Sends `run_pipeline` messages and handles incoming pipeline status updates.
 * Now includes `handleMessage` so the parent can route pipeline WebSocket messages here.
 */
export function useWorkflow(websocketSend: (msg: string) => boolean | void): UseWorkflowReturn {
  const [pipelineState, setPipelineState] = useState<PipelineRunState>(INITIAL_STATE);
  const startTimeRef = useRef<number | null>(null);
  const agentStartTimesRef = useRef<Record<string, number>>({});

  const startPipeline = useCallback(
    (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[], context?: Record<string, unknown>) => {
      startTimeRef.current = Date.now();
      agentStartTimesRef.current = {};

      setPipelineState({
        isRunning: true,
        pipeline_type: type,
        agents: [],
        currentAgentIndex: -1,
        totalDuration: null,
        completedCount: 0,
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
          // Build a rich description the backend can inject as a guideline
          description: `${h.name}: ${h.trigger}`,
        }));
      }

      // Extra context fields (e.g. template_id for od_prototype) are merged
      // at the top level so the backend can read them from message_data.
      if (context) {
        Object.assign(payload, context);
      }

      websocketSend(JSON.stringify(payload));
    },
    [websocketSend]
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
  const submitQuestionnaire = useCallback(
    (pipelineRunId: string, responses: Array<{ question_id: string; answer: string }>) => {
      websocketSend(JSON.stringify({
        type: "submit_questionnaire",
        pipeline_run_id: pipelineRunId,
        responses,
      }));
    },
    [websocketSend]
  );

  const isRunning = pipelineState.isRunning;

  return {
    pipelineState,
    startPipeline,
    resetPipeline,
    isRunning,
    handleMessage,
    submitQuestionnaire,
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

      const agentStates: AgentRunState[] = agents.map((a, idx) => ({
        id: a.id,
        name: a.name,
        role: a.role,
        icon: a.icon || "🤖",
        status: "idle",
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
        currentAgentIndex: 0,
        completedCount: 0,
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
        updated[agentIdx] = { ...updated[agentIdx], status: "running" };

        return { ...prev, agents: updated, currentAgentIndex: agentIdx };
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
      const duration = startTime ? (Date.now() - startTime) / 1000 : null;

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

      // Clear the persisted run ID — pipeline is done
      try {
        sessionStorage.removeItem("active_pipeline_run_id");
        sessionStorage.removeItem("active_pipeline_type");
      } catch { /* non-fatal */ }

      setPipelineState((prev) => {
        // Mark any agents still in running/thinking/idle state as done
        // (handles fast pipelines where agent_complete events were batched)
        const updated = prev.agents.map((a) =>
          (a.status === "running" || a.status === "thinking" || a.status === "idle")
            ? { ...a, status: "done" as const, thinking: "" }
            : a
        );
        return {
          ...prev,
          isRunning: false,
          totalDuration,
          agents: updated,
          completedCount: updated.filter((a) => a.status === "done").length,
          totalInputTokens: (msg.total_input_tokens as number) || 0,
          totalOutputTokens: (msg.total_output_tokens as number) || 0,
          totalTokens: (msg.total_tokens as number) || 0,
          estimatedCostUsd: (msg.estimated_cost_usd as number) || 0,
          modelId: (msg.model_id as string) || undefined,
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
        };
      });
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
      setPipelineState((prev) => ({
        ...prev,
        protoCompletedTasks: completedTasks,
        protoCompletedTaskCount: completedCount,
      }));
      return true;
    }

    case "task_loop_progress": {
      // Engine-level: build loop started a new task iteration
      const taskNumber = (msg.task_number as number) || 0;
      const completedFromLoop = Math.max(0, taskNumber - 1);
      setPipelineState((prev) => {
        const currentCount = prev.protoCompletedTaskCount ?? 0;
        return {
          ...prev,
          protoCompletedTaskCount: completedFromLoop > currentCount ? completedFromLoop : currentCount,
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

    default:
      return false;
  }
}
