import { http } from "./http";

export interface ChainSource {
  id: string;
  beta: boolean;
  text: string;
  /** Additional fields that may be sent by the backend for richer chain UI */
  [key: string]: unknown;
}

export interface WorkflowSummary {
  id: string;
  display_name?: string | null;
  name: string;
  short_name?: string | null;
  description: string;
  step_count: number;
  steps: { agent_id: string; name: string; gate: string | null }[];
  user_launchable: boolean;
  icon?: string | null;
  launch_surface?: string | null;
  /** Beta/coming-soon workflows: shown after the fully-available rows, greyed
   * out and non-interactive (mirrors the skills-catalog isBeta treatment).
   * Optional/undefined on backends that don't send it yet — treated as false.
   * snake_case to match the raw /api/workflows JSON contract (user_launchable,
   * display_name, launch_surface are all unconverted snake_case too). */
  is_beta?: boolean;
  /** This workflow's own "chain into me" consent list (backend-owned —
   * REPLACES the formerly frontend-hardcoded CHAIN_OPTIONS/CHAINABLE_FROM_TYPES
   * in lib/workflowChaining.ts). A source workflow may only offer "chain into
   * X" if X's OWN manifest lists it here. `beta` is an EDGE-level override:
   * True marks that ONE source->target relationship as "Coming Soon" even
   * when the target's own `is_beta` is false. Optional/undefined on backends
   * that don't send it yet — treated as []. */
  chained_from?: ChainSource[];
}

export interface WorkflowStepDetail {
  agent_id: string;
  name: string;
  role: string;
  order: number;
  strategy: string;
  gates: string[];
  validators: string[];
  compaction?: string | null;
  task_source?: { kind: string; parser?: string | null; target?: string | null } | null;
  declared_gate?: string | null;
}

export interface WorkflowDeliverable {
  strategy?: string | null;
  name?: string | null;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  description: string;
  planner: string;
  clarify_mode: string;
  clarify_defaults: string[];
  context_providers: string[];
  deliverable: WorkflowDeliverable;
  steps: WorkflowStepDetail[];
}

export const workflowsApi = {
  list: async (): Promise<WorkflowSummary[]> => {
    const { data } = await http.get<WorkflowSummary[]>("/api/workflows");
    return data;
  },
  get: async (workflowId: string): Promise<WorkflowDetail> => {
    const { data } = await http.get<WorkflowDetail>(
      `/api/workflows/${encodeURIComponent(workflowId)}`
    );
    return data;
  },
};
