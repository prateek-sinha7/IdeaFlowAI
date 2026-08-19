import {
  FileText,
  GitBranch,
  GitPullRequest,
  Layout,
  MessageSquare,
  Network,
  Presentation,
  Puzzle,
  Rocket,
  Search,
  Sparkles,
  Waves,
  type LucideIcon,
} from "lucide-react";

/**
 * Workflow catalog icon lookup — a workflow's manifest authors `icon` as a
 * Lucide component NAME (string, e.g. "Presentation"), never a JS reference:
 * the manifest is pure inert data (agents/workflows/manifest.py — never read
 * by the compiler/kernel, INV-3/INV-5) and can only carry strings. This map
 * is the single place that binds those authored names to the actual Lucide
 * components, matching the existing per-workflow icon convention
 * (WorkflowView.tsx's FEATURE_CARDS: user_stories→FileText, ppt→Presentation,
 * prototype→Layout) rather than introducing a second icon vocabulary (no
 * emoji — this app's icon language is Lucide everywhere else, 90+ call sites).
 *
 * Extend this map when a manifest authors a new icon name; an unrecognised or
 * absent name falls back to Sparkles (getWorkflowIcon below), the same
 * generic mark HomeLaunchGrid already used before any workflow authored one.
 */
const WORKFLOW_ICONS: Record<string, LucideIcon> = {
  FileText,
  Presentation,
  Layout,
  Rocket,
  Puzzle,
  GitBranch,
  MessageSquare,
  Search,
  GitPullRequest,
  Network,
  Waves,
};

// Map workflow type (pipeline_type) to icon name
const WORKFLOW_TYPE_ICONS: Record<string, string> = {
  user_stories: "FileText",
  user_stories_revision: "FileText",
  ppt: "Presentation",
  ppt_revision: "Presentation",
  prototype: "Layout",
  prototype_revision: "Layout",
  app_builder: "Rocket",
  app_builder_revision: "Rocket",
  custom: "Puzzle",
  chat: "MessageSquare",
  mulesoft_to_springboot: "GitBranch",
  dotnet_to_azure: "GitBranch",
  reverse_engineer: "Search",
  migration: "GitBranch",
  sample_brownfield: "GitPullRequest",
  sample_fanout: "Network",
  sample_wave: "Waves",
};

/** Resolve a manifest's authored `icon` string to its Lucide component,
 * falling back to Sparkles when absent/unrecognised (never a blank icon). */
export function getWorkflowIcon(iconName: string | null | undefined): LucideIcon {
  if (!iconName) return Sparkles;
  return WORKFLOW_ICONS[iconName] ?? Sparkles;
}

/** Resolve a workflow type (pipeline_type) to its Lucide icon component. */
export function getWorkflowTypeIcon(workflowType: string | null | undefined): LucideIcon {
  if (!workflowType) return Sparkles;
  const iconName = WORKFLOW_TYPE_ICONS[workflowType];
  return iconName ? WORKFLOW_ICONS[iconName] : Sparkles;
}
