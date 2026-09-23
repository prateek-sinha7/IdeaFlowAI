/**
 * Frontend-only chaining plumbing (Plan 34-01).
 *
 * The ACTUAL chaining data (which workflows may chain into which, and
 * whether a specific edge is beta) is now backend-owned — every workflow
 * authors its own `chained_from` consent list on its manifest, exposed via
 * GET /api/workflows and consumed through `useWorkflowChaining()`
 * (hooks/useWorkflowMetadata.ts). The formerly frontend-hardcoded
 * CHAIN_OPTIONS/CHAINABLE_FROM_TYPES/canChainFrom/availableChainTargets have
 * been retired — do not resurrect them; a source workflow's eligibility to
 * offer "chain into X" now comes from X's own manifest, not a static list
 * here.
 *
 * What legitimately remains frontend-only, and stays in this file:
 *   - baseWorkflowType: normalizes a WorkflowType to its base pipeline id
 *     (strips _revision, maps od_prototype -> prototype). Used well beyond
 *     chaining (e.g. RevisionFamilyView's grouping), so it stays generic here.
 *   - The sessionStorage keys the wizard pages read to pre-fill from a chain
 *     action.
 */

import type { WorkflowType } from "@/types/index";

export function baseWorkflowType(t: WorkflowType | string): string {
  const base = t.replace(/_revision$/, "");
  return base;
}

/** sessionStorage key for the brief pre-filled from a chain action. */
export const CHAIN_BRIEF_KEY = "chain.brief";
/** sessionStorage key for the pipeline type that initiated the chain. */
export const CHAIN_FROM_KEY = "chain.from";
/** sessionStorage key for the source WorkflowRun ID when chaining (Phase 3 / T055).
 *  Wizard pages store this so the backend can retrieve the original planning_context. */
export const CHAIN_SOURCE_RUN_ID_KEY = "chain.source_run_id";

// ── v2 source-status keys ─────────────────────────────────────────────────────

/** sessionStorage key for the source run's published status when chaining from a
 *  non-success run. Set to a non-"completed" status string (e.g. "failed",
 *  "cancelled", "degraded") before navigating to the wizard so the wizard can
 *  surface the pre-launch warning. Absent / null when the source is "completed". */
export const CHAIN_SOURCE_STATUS_KEY = "chain.v2.source_status";

/** sessionStorage key for the source run's `nonChainableReason` when the source
 *  has `payloadChainable === false`. Written so the wizard can explain why the
 *  chain is unavailable in a compatible-FE fallback if needed. */
export const CHAIN_SOURCE_NON_CHAINABLE_REASON_KEY = "chain.v2.source_non_chainable_reason";

// ── v1 legacy keys (kept as constants so removal is a single-edit operation) ──

/** @deprecated v1 legacy: the raw text context block injected into the brief.
 *  v2 uses file-based chain context installed to `.context/` before agent 1.
 *  This constant exists so every cleanup site is a single find-by-name rather
 *  than a string literal hunt. */
export const CHAIN_CONTEXT_BLOCK_KEY = "chain.context_block";

// ── v2 namespace ──────────────────────────────────────────────────────────────

/** sessionStorage key recording that the v2 storage migration has been run.
 *  Presence (any value) means the migration already executed; do not re-run. */
export const CHAIN_V2_VERSION_KEY = "chain.v2.version";

/**
 * Idempotent one-time migration: drops the v1 `chain.context_block` key from
 * both `sessionStorage` and `localStorage` on first load under the v2 version
 * key.
 *
 * Safe to call at module load time or in an effect — it is idempotent, it
 * preserves `chain.brief`, `chain.from`, `chain.source_run_id`, and all
 * unrelated keys, and it never throws.
 *
 * In-memory launch state (the wizard's `chainContextBlock` state variable) is
 * implicitly cleared by this migration: the wizard reads `chain.context_block`
 * from `sessionStorage` into that state on mount — once the key is absent, the
 * state stays `null` and no context block is injected into the brief.
 */
export function migrateChainStorageV2(): void {
  try {
    // Already migrated — nothing to do.
    if (sessionStorage.getItem(CHAIN_V2_VERSION_KEY) !== null) return;

    // Drop the v1 text-block key from both storages.
    sessionStorage.removeItem(CHAIN_CONTEXT_BLOCK_KEY);
    try {
      localStorage.removeItem(CHAIN_CONTEXT_BLOCK_KEY);
    } catch {
      // localStorage may be unavailable (privacy mode, embedded context).
    }
    // Mark the migration as done so this function is a true no-op on every
    // subsequent call within this session.
    sessionStorage.setItem(CHAIN_V2_VERSION_KEY, "1");
  } catch {
    // sessionStorage unavailable — nothing to migrate, nothing to mark.
  }
}

// ── Mixed-deploy compatibility (Task 11.8, Req 21 AC 9) ──────────────────────
//
// These constants name every recognized mixed-deploy combination so that error
// surfaces never leave a combination "undefined" (Requirement 21 AC 9).
//
// The reason codes are bounded machine-readable strings that satisfy
// Requirement 20 AC 4 (distinct, actionable) and Requirement 20 AC 8
// (unknown-reason-code resilience — a frontend that doesn't recognise a code
// still falls back to the generic message rather than crashing).

/**
 * New frontend against an older backend that does not support v2 chaining.
 * The backend accepted the launch but ignored `source_workflow_run_id`, so
 * the run starts without chain context.  Surface via `chain_context_unavailable`
 * with this code so the user is told rather than silently getting no context.
 *
 * Correct next action: wait for a backend upgrade, or choose a workflow that
 * does not require chain context.
 */
export const CHAIN_REASON_INCOMPATIBLE_BACKEND = "incompatible_backend" as const;

/**
 * Older frontend against a new backend.
 * The backend strips the legacy `=== CONTEXT FROM PREVIOUS PIPELINE ===` block
 * when `source_workflow_run_id` is also present (task 9.3 / Req 13 AC 11), so
 * the two are never combined.  No frontend action is needed; this constant
 * exists so documentation, tests, and error surfaces can reference a named
 * identifier rather than an anonymous string literal.
 *
 * The backend records the strip as a `legacy_context_block_stripped` provenance
 * audit row (Requirement 21 AC 10).
 */
export const CHAIN_REASON_LEGACY_BLOCK_STRIPPED = "legacy_context_block_stripped" as const;

/**
 * Any combination not covered by the two named cases above.
 * Rendered as "Chain context unavailable: unsupported version combination" so
 * the user is never left with an undefined error (Requirement 21 AC 9).
 */
export const CHAIN_REASON_UNSUPPORTED_COMBINATION = "unsupported_version_combination" as const;

/**
 * All mixed-deploy reason codes in one typed union, so a `switch` statement
 * can be exhaustively checked.
 */
export type MixedDeployReason =
  | typeof CHAIN_REASON_INCOMPATIBLE_BACKEND
  | typeof CHAIN_REASON_LEGACY_BLOCK_STRIPPED
  | typeof CHAIN_REASON_UNSUPPORTED_COMBINATION;
