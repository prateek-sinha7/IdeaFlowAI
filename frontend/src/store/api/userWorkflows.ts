import { http } from "./http";

export interface UserWorkflowSummary {
  id: string;
  name: string;
  description?: string | null;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  selections?: Record<string, Record<string, unknown>> | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateUserWorkflowBody {
  name: string;
  description?: string;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string>;
  selections?: Record<string, Record<string, unknown>>;
}

export const userWorkflowsApi = {
  list: async (): Promise<UserWorkflowSummary[]> => {
    const { data } = await http.get<UserWorkflowSummary[]>("/api/user-workflows");
    return data;
  },
  get: async (userWorkflowId: string): Promise<UserWorkflowSummary> => {
    const { data } = await http.get<UserWorkflowSummary>(`/api/user-workflows/${userWorkflowId}`);
    return data;
  },
  create: async (body: CreateUserWorkflowBody): Promise<UserWorkflowSummary> => {
    const { data } = await http.post<UserWorkflowSummary>("/api/user-workflows", body);
    return data;
  },
  rename: async (
    userWorkflowId: string,
    body: { name?: string; description?: string }
  ): Promise<UserWorkflowSummary> => {
    const { data } = await http.patch<UserWorkflowSummary>(
      `/api/user-workflows/${userWorkflowId}`,
      body
    );
    return data;
  },
  delete: async (userWorkflowId: string): Promise<void> => {
    await http.delete(`/api/user-workflows/${userWorkflowId}`);
  },
};
