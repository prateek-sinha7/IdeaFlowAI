/**
 * failure-messages.ts — Two-tier failure message lookup.
 *
 * Tier 1: getUserMessage — plain-English sentences shown to any user.
 * Tier 2: getDeveloperLabel — short technical label shown in the collapsed
 *         developer-detail panel.
 *
 * Keys are the normalized `failureCode` values stored on PipelineRunState.
 * Budget codes include both the raw dimension and the prefixed form so callers
 * never need to know which variant is stored.
 */

/** Tier 1 — user-facing plain-English sentences.
 *  Any code not in this map falls back to GENERIC_USER_MESSAGE. */
const USER_MESSAGES: Record<string, string> = {
  wall_clock_seconds: "This run took too long and was stopped.",
  budget_wall_clock_seconds: "This run took too long and was stopped.",
  max_subagents: "This run used too many agents and was stopped.",
  budget_max_subagents: "This run used too many agents and was stopped.",
  loop_iterations: "This run couldn't reach a result in time.",
  budget_loop_iterations: "This run couldn't reach a result in time.",
  max_depth: "This run reached its depth limit and was stopped.",
  budget_max_depth: "This run reached its depth limit and was stopped.",
  secret_detected: "The output couldn't be saved for security reasons.",
  pre_commit_hook_blocked: "The output was blocked before saving.",
  staging_failed: "The output couldn't be staged for saving.",
  placeholder_narration: "An agent couldn't complete its task.",
  dropped_sections: "The result is incomplete.",
  files_not_saved: "Some output files couldn't be saved.",
  snapshot_unrecoverable: "An internal error occurred while saving.",
  wip_commit_blocked: "Work in progress couldn't be saved.",
  tag_creation_failed: "An internal error occurred while tagging the run.",
  source_provenance_conflict: "A conflict occurred during finalization.",
  total_collapse: "The run stopped before completing. Reopen to resume.",
};

/** Tier 2 — developer-readable technical labels for failure codes. */
const DEVELOPER_LABELS: Record<string, string> = {
  wall_clock_seconds: "Wall-clock timeout exceeded",
  budget_wall_clock_seconds: "Wall-clock timeout exceeded",
  max_subagents: "Maximum agent count exceeded",
  budget_max_subagents: "Maximum agent count exceeded",
  loop_iterations: "Convergence loop limit reached",
  budget_loop_iterations: "Convergence loop limit reached",
  max_depth: "Maximum fan-out depth exceeded",
  budget_max_depth: "Maximum fan-out depth exceeded",
  secret_detected: "Secret detected in output",
  pre_commit_hook_blocked: "Pre-commit hook blocked the save",
  staging_failed: "Failed to stage output files",
  placeholder_narration: "Agent produced a placeholder response",
  dropped_sections: "Deliverable is missing required sections",
  files_not_saved: "Some files were excluded from the run",
  snapshot_unrecoverable: "Failed to persist run snapshot",
  wip_commit_blocked: "Could not save work-in-progress",
  tag_creation_failed: "Run tag could not be created",
  source_provenance_conflict: "Git ref conflict during finalization",
  total_collapse: "Total agent collapse",
};

const GENERIC_USER_MESSAGE = "Something went wrong and this run couldn't complete.";
const GENERIC_DEVELOPER_LABEL = "Unknown failure";

/**
 * Returns the Tier 1 user-facing plain-English sentence for a failure code.
 * Falls back to a generic sentence for unrecognised or empty codes
 * (never returns empty).
 *
 * @param code   Normalized failureCode from PipelineRunState (may be empty).
 * @param hasFailedAgents  When true and code is empty, returns the
 *   "all agents failed" message instead of the generic fallback.
 */
export function getUserMessage(code: string, hasFailedAgents?: boolean): string {
  if (code && USER_MESSAGES[code]) return USER_MESSAGES[code];
  if (!code && hasFailedAgents) return "All agents failed to complete their tasks.";
  return GENERIC_USER_MESSAGE;
}

/**
 * Returns the Tier 2 developer-readable technical label for a failure code.
 * Falls back to "Unknown failure" for unrecognised or empty codes.
 *
 * @param code  Normalized failureCode from PipelineRunState.
 */
export function getDeveloperLabel(code: string): string {
  if (!code) return GENERIC_DEVELOPER_LABEL;
  return DEVELOPER_LABELS[code] ?? GENERIC_DEVELOPER_LABEL;
}
