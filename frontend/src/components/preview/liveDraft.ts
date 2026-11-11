/**
 * Live draft preview: while a run is still building, the Preview tab shows the
 * main output file from the run's workspace (prototype.html, slides.html, …)
 * instead of a "Building your deliverable…" placeholder.
 */
import type { SandboxFile } from "@/lib/api";

/** Main-output names, most specific first. Root-level files only. */
export const LIVE_DRAFT_CANDIDATES = [
  "prototype.html",
  "slides.html",
  "slide.html",
  "deck.html",
  "presentation.html",
  "index.html",
] as const;

/**
 * The workspace file to preview while the run builds, or null when none exists yet.
 * The workflow's declared deliverable name wins when it is already known and on disk.
 */
export function pickLiveDraftPath(
  files: readonly SandboxFile[],
  declared?: string | null,
): string | null {
  const root = new Set(files.filter((f) => !f.path.includes("/")).map((f) => f.path));
  if (declared && !declared.includes("/") && root.has(declared)) return declared;
  return LIVE_DRAFT_CANDIDATES.find((name) => root.has(name)) ?? null;
}

/** Banner text: "Build · 6/11 tasks done". */
export function liveDraftStage(
  stepName: string | undefined,
  completedTasks: number | undefined,
  totalTasks: number | undefined,
): string {
  const step = stepName?.trim() || "Building";
  return totalTasks && totalTasks > 0
    ? `${step} · ${Math.min(completedTasks ?? 0, totalTasks)}/${totalTasks} tasks done`
    : step;
}
