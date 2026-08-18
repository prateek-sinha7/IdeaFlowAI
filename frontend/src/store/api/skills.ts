import { http } from "./http";

// Mirrors backend GlobalSkillEntry (backend/app/agents/skills_catalog.py),
// scanned from skills/global/{skill_id}/SKILL.md.
export interface GlobalSkillEntry {
  id: string;
  name: string;
  display_name: string;
  description: string;
  content: string;
  category: string;
  isBeta?: boolean;
  tags: string[];
  /** Spec 012 R-31/R-38: built-in agent ids this skill is a good fit for — a
   *  UI filter/sort hint only, never server-enforced (R-34). Absent/empty
   *  means compatible with everything (R-33 — a missed skill degrades to
   *  today's unfiltered behavior, never an invisible filter). */
  compatible_agents?: string[];
}

// Frontend skill model (normalized from GlobalSkillEntry for UI consumption)
export interface SkillDef {
  id: string;
  name: string;
  description: string;
  category: "testing" | "debugging" | "planning" | "collaboration" | "security" | "workflow" | "meta" | "research" | "specialist";
  content: string;
  isBeta?: boolean;
  tags: string[];
  /** Spec 012 R-31/R-38 (see `GlobalSkillEntry.compatible_agents`). */
  compatible_agents?: string[];
}

export interface SkillsLibraryFilterOption {
  id: string;
  label: string;
  icon?: string;
}

export interface SkillsLibraryResponse {
  skills: GlobalSkillEntry[];
  total_count: number;
  categories: SkillsLibraryFilterOption[];
  sources: SkillsLibraryFilterOption[];
}

export const skillsLibraryApi = {
  library: async (): Promise<SkillsLibraryResponse> => {
    const { data } = await http.get<SkillsLibraryResponse>("/api/skills/library");
    return data;
  },
};
