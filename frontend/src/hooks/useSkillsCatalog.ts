import { useAppSelector } from "@/store/hooks";
import type { SkillDef, SkillsLibraryFilterOption } from "@/store/api/skills";

export interface SkillsCatalogResult {
  skills: SkillDef[];
  categories: readonly SkillsLibraryFilterOption[];
}

/**
 * Returns the global Skills catalog from Redux state. Populated by
 * GET /api/skills/library when fetchSkills completes.
 */
export function useSkillsCatalog(): SkillsCatalogResult {
  const reduxSkills = useAppSelector((state) => state.skills.skills);
  const categories = useAppSelector((state) => state.skills.skillCategories);

  const skills: SkillDef[] = reduxSkills.map((s) => ({
    id: s.id,
    name: s.display_name || s.name,
    description: s.description,
    category: s.category as SkillDef["category"],
    content: s.content,
    isBeta: s.isBeta ? true : false,
    tags: s.tags,
    compatible_agents: s.compatible_agents,
  }));

  return {
    skills,
    categories,
  };
}
