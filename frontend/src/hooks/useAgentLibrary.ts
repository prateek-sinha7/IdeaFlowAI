import { useMemo } from "react";
import { useAppSelector } from "@/store/hooks";
import { agentMatchesPipelineType } from "@/lib/workflowIcons";
import type { AgentDef } from "@/types/index";

export interface AgentLibraryResult {
  /** Every non-"custom" pipeline agent from the API registry. */
  libraryAgents: AgentDef[];
  /** pipeline_type === "custom" agents from the API registry. */
  customAgents: AgentDef[];
  /** libraryAgents ∪ customAgents — all agents from the API. */
  allAgents: AgentDef[];
}

/**
 * Returns the agent library from Redux state, populated by GET /api/agents/library
 * via the listenerMiddleware on app boot (signedIn action).
 *
 * The Redux store initializes with empty arrays and is populated when the API
 * fetch completes. Returns the API-driven data only; no static fallback.
 */
export function useAgentLibrary(): AgentLibraryResult {
  const reduxAgents = useAppSelector((state) => state.agents.agents);

  // Memoized on reduxAgents' own reference (Redux keeps it stable unless the
  // slice actually changes) — without this, every render produced two fresh
  // .filter() arrays, and a consumer effect keyed on libraryAgents would loop
  // forever (setState -> re-render -> new array -> effect fires -> setState...).
  const customAgents = useMemo(
    () => reduxAgents.filter((a) => agentMatchesPipelineType(a.pipeline_type, "custom")),
    [reduxAgents],
  );
  const libraryAgents = useMemo(
    () => reduxAgents.filter((a) => !agentMatchesPipelineType(a.pipeline_type, "custom")),
    [reduxAgents],
  );

  return { libraryAgents, customAgents, allAgents: reduxAgents };
}
