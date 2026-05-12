"use client";

import { useCallback, useMemo, useReducer } from "react";

import {
  INITIAL_AGENTS,
  type HandoffAgentId,
  type HandoffAgentState,
  type HandoffPipelineState,
  type HandoffStreamMessage,
} from "./types";

/**
 * Reducer that consumes the same ``StreamMessage`` envelope the rest of
 * Flowin uses and projects it into the handoff-specific pipeline state.
 *
 * Kept private to the handoff folder so it cannot accidentally be reused
 * by other workflows (the agent set and reports are handoff-shaped).
 */

const INITIAL_STATE: HandoffPipelineState = {
  pipelineStatus: "pending",
  phases: [],
  agents: { ...INITIAL_AGENTS },
  editResults: [],
  done: false,
};

type Action =
  | { type: "reset" }
  | { type: "setPipelineStatus"; status: HandoffPipelineState["pipelineStatus"] }
  | { type: "ws"; msg: HandoffStreamMessage };

function applyAgent(
  state: HandoffPipelineState,
  agentId: string,
  patch: Partial<HandoffAgentState>
): HandoffPipelineState {
  if (!(agentId in state.agents)) return state;
  const id = agentId as HandoffAgentId;
  return {
    ...state,
    agents: {
      ...state.agents,
      [id]: { ...state.agents[id], ...patch },
    },
  };
}

function reducer(state: HandoffPipelineState, action: Action): HandoffPipelineState {
  if (action.type === "reset") return { ...INITIAL_STATE, agents: { ...INITIAL_AGENTS } };
  if (action.type === "setPipelineStatus") {
    return { ...state, pipelineStatus: action.status };
  }
  const { msg } = action;
  const data = (msg.data ?? {}) as Record<string, unknown>;
  const t = msg.type as string;

  switch (t) {
    case "phase_start":
    case "phase_end":
      return {
        ...state,
        phases: [
          ...state.phases,
          {
            section: (msg.section ?? "unknown") as string,
            status: t === "phase_start" ? "start" : "end",
            data,
            at: Date.now(),
          },
        ],
        editResults:
          t === "phase_end" && msg.section === "apply_edits" && Array.isArray(data.results)
            ? (data.results as HandoffPipelineState["editResults"])
            : state.editResults,
      };
    case "agent_thinking": {
      const id = (data.agent_id as string) ?? "";
      return applyAgent(state, id, {
        status: "thinking",
        thinking: (data.thinking as string) ?? undefined,
        started_at: Date.now(),
      });
    }
    case "agent_complete": {
      const id = (data.agent_id as string) ?? "";
      const patch: Partial<HandoffAgentState> = {
        status: "complete",
        completed_at: Date.now(),
      };
      if (id === "coding_agent") {
        patch.summary = (data.summary as string) ?? "";
        patch.rationale = (data.rationale as string) ?? "";
        patch.edits = (data.edits as HandoffAgentState["edits"]) ?? [];
        patch.edit_count = (data.edit_count as number) ?? 0;
        patch.tests_added = (data.tests_added as string[]) ?? [];
        patch.follow_ups = (data.follow_ups as string[]) ?? [];
      } else if (id === "test_agent") {
        patch.test_report = (data.report as HandoffAgentState["test_report"]) ?? undefined;
      } else if (id === "compliance_agent") {
        patch.compliance_report =
          (data.report as HandoffAgentState["compliance_report"]) ?? undefined;
      }
      return applyAgent(state, id, patch);
    }
    case "agent_error": {
      const id = (data.agent_id as string) ?? "";
      return applyAgent(state, id, {
        status: "error",
        error: (data.error as string) ?? "Agent failed.",
      });
    }
    case "pr_created":
      return {
        ...state,
        prUrl: (data.url as string) ?? undefined,
        prNumber: (data.number as number) ?? undefined,
      };
    case "pipeline_complete":
      return {
        ...state,
        done: true,
        pipelineStatus: "completed",
        resolvedMode: (data.resolved_mode as "coding" | "test") ?? state.resolvedMode,
        branchName: (data.branch_name as string) ?? state.branchName,
        prUrl: (data.pr_url as string) ?? state.prUrl,
        prNumber: (data.pr_number as number) ?? state.prNumber,
      };
    case "handoff_error":
      return {
        ...state,
        done: true,
        pipelineStatus: "failed",
        error: (data.message as string) ?? "Pipeline failed.",
      };
    default:
      return state;
  }
}

export function useHandoffPipelineState() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const handleMessage = useCallback((msg: HandoffStreamMessage) => {
    dispatch({ type: "ws", msg });
  }, []);

  const setPipelineStatus = useCallback(
    (status: HandoffPipelineState["pipelineStatus"]) => {
      dispatch({ type: "setPipelineStatus", status });
    },
    []
  );

  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  const activeAgent = useMemo(() => {
    if (state.agents.coding_agent.status === "thinking") return "coding_agent" as const;
    if (state.agents.test_agent.status === "thinking") return "test_agent" as const;
    if (state.agents.compliance_agent.status === "thinking")
      return "compliance_agent" as const;
    return null;
  }, [state.agents]);

  return { state, handleMessage, setPipelineStatus, reset, activeAgent };
}
