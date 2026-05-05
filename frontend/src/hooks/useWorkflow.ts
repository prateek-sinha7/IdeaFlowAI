"use client";

import { useCallback, useRef, useState } from "react";
import type { AgentRunState, PipelineRunState } from "@/types/index";

export interface UseWorkflowReturn {
  pipelineState: PipelineRunState;
  startPipeline: (type: string, message: string) => void;
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
export function useWorkflow(websocketSend: (msg: string) => void): UseWorkflowReturn {
  const [pipelineState, setPipelineState] = useState<PipelineRunState>(INITIAL_STATE);
  const startTimeRef = useRef<number | null>(null);
  const agentStartTimesRef = useRef<Record<string, number>>({});

  const startPipeline = useCallback(
    (type: string, message: string, agentIds?: string[]) => {
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

      // Include custom agent IDs if provided
      if (agentIds && agentIds.length > 0) {
        payload.agent_ids = agentIds;
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
      const agentId = msg.agent_id as string;
      const output = (msg.output as string) || "";
      const startTime = agentStartTimesRef.current[agentId];
      const duration = startTime ? (Date.now() - startTime) / 1000 : null;

      setPipelineState((prev) => {
        const agentIdx = prev.agents.findIndex((a) => a.id === agentId);
        if (agentIdx === -1) return prev;

        const updated = [...prev.agents];
        updated[agentIdx] = {
          ...updated[agentIdx],
          status: "done",
          output: output || updated[agentIdx].output,
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

    default:
      return false;
  }
}
