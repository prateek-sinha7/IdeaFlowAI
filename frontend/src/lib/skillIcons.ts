import {
  Users,
  Bug,
  Settings,
  Map,
  Lightbulb,
  Shield,
  Award,
  TestTube,
  GitBranch,
  type LucideIcon,
} from "lucide-react";

/**
 * Skill category icon lookup — maps skill SKILL.md `category` field to Lucide components.
 * Categories are defined by the backend and rendered throughout the UI.
 * Unrecognised categories fall back to Award (generic capability mark).
 */
const SKILL_CATEGORY_ICONS: Record<string, LucideIcon> = {
  collaboration: Users,
  debugging: Bug,
  meta: Settings,
  planning: Map,
  research: Lightbulb,
  security: Shield,
  specialist: Award,
  testing: TestTube,
  workflow: GitBranch,
};

export function getSkillCategoryIcon(
  category: string | null | undefined
): LucideIcon {
  if (!category) return Award;
  return SKILL_CATEGORY_ICONS[category] ?? Award;
}
