import { http } from "./http";

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  step_count: number;
  steps: { agent_id: string; name: string; gate: string | null }[];
  user_launchable: boolean;
  display_name?: string | null;
  icon?: string | null;
  launch_surface?: string | null;
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
