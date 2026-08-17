import { http } from "./http";

export interface WorkflowRun {
  id: string;
  title: string;
  type: string;
  status: string;
  input: string;
  output: string | null;
  agent_outputs: string | null;
  agent_count: number;
  duration: number | null;
  error: string | null;
  token_usage: string | null;
  model_id: string | null;
  deliverable_mimetype?: string | null;
  deliverable_filename?: string | null;
  parent_run_id?: string | null;
  root_run_id?: string;
  created_at: string;
  completed_at: string | null;
}

export interface FamilyMember {
  id: string;
  type: string;
  title: string;
  status: string;
  revision_index: number;
  parent_run_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RunFamily {
  root_id: string;
  members: FamilyMember[];
}

export interface ArtifactNode {
  id: string;
  kind: string;
  producer_step: string;
  producer_agent: string;
  task_id: string;
  content_hash: string;
  version: number;
  visibility: string;
  location: string;
  parents: string[];
  derived_from: string[];
  children: string[];
  content?: string;
}

export interface RunArtifactsResponse {
  workflow_id: string;
  artifacts: ArtifactNode[];
}

export interface ChainContext {
  workflow_id: string;
  pipeline_type: string;
  title: string;
  brief: string;
  structured_summary: string;
  agent_summaries: Array<{ agent: string; summary: string }>;
  context_block: string;
}

export interface RunEvent {
  id?: string;
  type: string;
  data?: unknown;
  [key: string]: unknown;
}

export interface RunEventsResponse {
  workflow_id: string;
  events: RunEvent[];
}

export interface HookRunsResponse {
  workflow_id: string;
  hook_runs: Array<{
    id: string;
    hook: string;
    event: string;
    outcome: string;
    detail: Record<string, unknown> | null;
    created_at: string | null;
  }>;
}

export const runsApi = {
  list: async (options?: {
    type?: string;
    limit?: number;
    offset?: number;
    status_filter?: string;
  }): Promise<WorkflowRun[]> => {
    const { data } = await http.get<WorkflowRun[]>("/api/runs", { params: options });
    return data;
  },

  get: async (workflowId: string): Promise<WorkflowRun> => {
    const { data } = await http.get<WorkflowRun>(`/api/runs/${workflowId}`);
    return data;
  },

  delete: async (workflowId: string): Promise<void> => {
    await http.delete(`/api/runs/${workflowId}`);
  },

  exportPptx: async (workflow_id: string, title: string): Promise<unknown> => {
    const { data } = await http.post("/api/runs/export-pptx", { workflow_id, title });
    return data;
  },

  chainContext: async (workflowId: string): Promise<ChainContext> => {
    const { data } = await http.get<ChainContext>(`/api/runs/${workflowId}/chain-context`);
    return data;
  },

  artifacts: async (
    workflowId: string,
    opts?: { kind?: string; includeContent?: boolean }
  ): Promise<RunArtifactsResponse> => {
    const { data } = await http.get<RunArtifactsResponse>(`/api/runs/${workflowId}/artifacts`, {
      params: {
        kind: opts?.kind,
        include: opts?.includeContent ? "content" : undefined,
      },
    });
    return data;
  },

  events: async (workflowId: string, after?: number): Promise<RunEventsResponse> => {
    const { data } = await http.get<RunEventsResponse>(`/api/runs/${workflowId}/events`, {
      params: { after },
    });
    return data;
  },

  family: async (workflowId: string): Promise<RunFamily> => {
    const { data } = await http.get<RunFamily>(`/api/runs/${workflowId}/family`);
    return data;
  },

  hookRuns: async (workflowId: string): Promise<HookRunsResponse> => {
    const { data } = await http.get<HookRunsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/hook-runs`
    );
    return data;
  },
};
