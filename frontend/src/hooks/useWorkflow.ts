"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState, AttachedSkill, AttachedHook } from "@/types/index";

export interface UseWorkflowReturn {
  pipelineState: PipelineRunState;
  startPipeline: (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[]) => void;
  resetPipeline: () => void;
  isRunning: boolean;
  handleMessage: (msg: { type: string; [key: string]: unknown }) => boolean;
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
    (type: string, message: string, agentIds?: string[], attachedSkills?: AttachedSkill[], attachedHooks?: AttachedHook[]) => {
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
      if (attachedHooks && attachedHooks.length > 0) {
        payload.attached_hooks = attachedHooks.map(h => ({
          id: h.id,
          name: h.name,
          event: h.event,
          trigger: h.trigger,
          description: h.name + ": " + h.trigger,
        }));
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

  const isRunning = pipelineState.isRunning;

  return {
    pipelineState,
    startPipeline,
    resetPipeline,
    isRunning,
    handleMessage,
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
        agents: agentStates,
        currentAgentIndex: 0,
        completedCount: 0,
      }));
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
        updated[agentIdx] = { ...updated[agentIdx], status: "thinking", thinking };

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
      // Backend only emits `output_length` on agent_complete (see
      // orchestrator_v2.py emit site); the full output was streamed
      // chunk-by-chunk via `agent_chunk` and accumulated into
      // `updated[agentIdx].output` already. The previous code read a
      // non-existent `msg.output` and fell through to the accumulated
      // value by accident — keep the accumulated value explicitly so
      // the intent is obvious.
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
        };

        const completedCount = updated.filter((a) => a.status === "done").length;

        return { ...prev, agents: updated, completedCount };
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

      setPipelineState((prev) => ({
        ...prev,
        isRunning: false,
        totalDuration,
        completedCount: prev.agents.filter((a) => a.status === "done").length,
      }));
      return true;
    }

    case "pipeline_cancelled": {
      // Backend emits this on Stop / WebSocketDisconnect with an
      // `agents_completed` count and a partial `duration`. The previous
      // dispatcher omitted this case entirely so `isRunning` stayed true
      // forever after a cancel — UI showed a spinner that never resolved.
      // Reset any in-flight agent (status "thinking"/"running") back to
      // "idle" so the progress panel stops animating; completed agents
      // ("done") and already-errored agents are left untouched.
      const totalDuration = (msg.duration as number) || null;
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

    default:
      return false;
  }
}
