import { http } from "./http";

export interface ModelOption {
  id: string;
  name: string;
  description: string;
  tier: "fast" | "balanced" | "powerful";
}

export interface UserPreferences {
  preferred_model: string | null;
  available_models: ModelOption[];
}

export interface ApiKey {
  id: string;
  name: string;
  created_at: string;
  [key: string]: unknown;
}

export const settingsApi = {
  // GitHub PAT
  getGithubPat: async (): Promise<{ pat: string | null }> => {
    const { data } = await http.get<{ pat: string | null }>("/api/settings/github-pat");
    return data;
  },
  setGithubPat: async (pat: string): Promise<{ pat: string }> => {
    const { data } = await http.put<{ pat: string }>("/api/settings/github-pat", { pat });
    return data;
  },
  deleteGithubPat: async (): Promise<void> => {
    await http.delete("/api/settings/github-pat");
  },

  // API keys
  listApiKeys: async (): Promise<ApiKey[]> => {
    const { data } = await http.get<ApiKey[]>("/api/settings/api-keys");
    return data;
  },
  createApiKey: async (name: string): Promise<ApiKey> => {
    const { data } = await http.post<ApiKey>("/api/settings/api-keys", { name });
    return data;
  },
  deleteApiKey: async (apiKeyId: string): Promise<void> => {
    await http.delete(`/api/settings/api-keys/${apiKeyId}`);
  },

  // Preferences
  getPreferences: async (): Promise<UserPreferences> => {
    const { data } = await http.get<UserPreferences>("/api/settings/preferences");
    return data;
  },
  updatePreferences: async (preferred_model: string | null): Promise<UserPreferences> => {
    const { data } = await http.put<UserPreferences>("/api/settings/preferences", {
      preferred_model,
    });
    return data;
  },

  // Constitution
  getConstitution: async (): Promise<{ content: string | null }> => {
    const { data } = await http.get<{ content: string | null }>("/api/settings/constitution");
    return data;
  },
  updateConstitution: async (content: string): Promise<{ content: string }> => {
    const { data } = await http.put<{ content: string }>("/api/settings/constitution", {
      content,
    });
    return data;
  },
  deleteConstitution: async (): Promise<void> => {
    await http.delete("/api/settings/constitution");
  },
};
