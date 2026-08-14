import { http } from "./http";

// Mirrors backend GlobalHookEntry (backend/app/agents/hooks_catalog.py),
// scanned from hooks/global/{hook_id}/HOOK.md.
export interface GlobalHookEntry {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content: string;
  event: string;
  trigger: string;
  compatible_agents: string[];
  isBeta?: boolean;
  tags: string[];
}

// Frontend hook model (normalized from GlobalHookEntry for UI consumption)
export interface HookDef {
  id: string;
  name: string;
  description: string;
  event: "PreToolUse" | "PostToolUse" | "Stop" | "SessionStart" | "SessionEnd";
  trigger: string;
  compatible_agents: string[];
  tags: string[];
}

export interface HooksLibraryFilterOption {
  id: string;
  label: string;
  icon?: string;
}

export interface HooksLibraryResponse {
  hooks: GlobalHookEntry[];
  total_count: number;
  events: HooksLibraryFilterOption[];
}

export const hooksLibraryApi = {
  library: async (): Promise<HooksLibraryResponse> => {
    const { data } = await http.get<HooksLibraryResponse>("/api/hooks/library");
    return data;
  },
};
