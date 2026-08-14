import { http } from "./http";
import type { AgentDef, PipelineConfig } from "@/types/index";

export interface AgentSkill {
  agent_id: string;
  content: string;
  [key: string]: unknown;
}

export interface AgentPromptData {
  agent_id: string;
  prompt_body: string;
  override: string | null;
  has_override: boolean;
}

export interface AgentLibraryResponse {
  agents: AgentDef[];
  total_count: number;
  pipelines: Record<string, number>;
}

export const agentsApi = {
  getPrototypePipeline: async (): Promise<PipelineConfig> => {
    const { data } = await http.get<PipelineConfig>("/api/agents/pipelines/prototype");
    return data;
  },

  library: async (): Promise<AgentLibraryResponse> => {
    const { data } = await http.get<AgentLibraryResponse>("/api/agents/library");
    return data;
  },

  listSkills: async (): Promise<AgentSkill[]> => {
    const { data } = await http.get<AgentSkill[]>("/api/agents/skills");
    return data;
  },
  getSkill: async (agentId: string): Promise<AgentSkill> => {
    const { data } = await http.get<AgentSkill>(`/api/agents/skills/${agentId}`);
    return data;
  },
  saveSkill: async (agent_id: string, content: string): Promise<AgentSkill> => {
    const { data } = await http.post<AgentSkill>("/api/agents/skills", { agent_id, content });
    return data;
  },
  deleteSkill: async (agentId: string): Promise<void> => {
    await http.delete(`/api/agents/skills/${agentId}`);
  },

  getPrompt: async (agentId: string): Promise<AgentPromptData> => {
    const { data } = await http.get<AgentPromptData>(
      `/api/agents/${encodeURIComponent(agentId)}/prompt`
    );
    return data;
  },
  savePromptOverride: async (
    agentId: string,
    content: string
  ): Promise<{ status: string; agent_id: string }> => {
    const { data } = await http.put<{ status: string; agent_id: string }>(
      `/api/agents/${encodeURIComponent(agentId)}/prompt`,
      { content }
    );
    return data;
  },
  deletePromptOverride: async (agentId: string): Promise<{ status: string; agent_id: string }> => {
    const { data } = await http.delete<{ status: string; agent_id: string }>(
      `/api/agents/${encodeURIComponent(agentId)}/prompt`
    );
    return data;
  },
};
