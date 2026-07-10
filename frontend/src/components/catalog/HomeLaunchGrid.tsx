"use client";

/**
 * HomeLaunchGrid — the data-driven Creation Hub (Plan 20-02, WF-DB-01 /
 * ISS-015). It is a TWO-ANALOG GRAFT:
 *
 *   - Fetch/state shell  ⟵ AgentModelPicker.tsx (:48-74,:99-114): the mount
 *     `useEffect` with the `cancelled` guard + `getToken()` fallback, and the
 *     loading/error/empty triad. `.filter(m => m.user_allowed)` becomes
 *     `.filter(w => w.user_launchable)` — GATE 1 (the declared product flag).
 *   - Row JSX + launch + tier gating ⟵ CreationHub.tsx (:27-38,:69-123): the
 *     row `<button>` (all Tailwind classes verbatim — net-new styling is a
 *     defect, UI-SPEC §0), the per-row `allowed`/`upgradeTo` lock decoration —
 *     GATE 2 (`canRunPipeline`), and the `handleClick` launch fork.
 *
 * SC-001: the rows come from the live `GET /api/workflows` list (never a
 * hardcoded workflow-name array — the CreationHub `WORKFLOWS` module-const is
 * intentionally GONE here). A brand-new manifest setting `user_launchable:
 * true` appears in this catalog with zero FE edit.
 *
 * The raw API `name` is NEVER rendered (UI-SPEC §4) — only the friendly label
 * `display_name ?? getWorkflowLabel(id)` (WORKFLOW_LABELS, useNotifications).
 *
 * NOTE: "Your Workflows" (saved/custom workflows) was moved to SavedWorkflowsPage,
 * accessible from the profile dropdown in AppHeader.
 */

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { ArrowRight, Lock, AlertCircle, Plus, Info } from "lucide-react";
import type { WorkflowType } from "@/types/index";
import { WorkflowDialog } from "@/components/workflow/WorkflowDialog";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { CHAIN_OPTIONS } from "@/lib/workflowChaining";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import {
  getWorkflowDefinitions,
  getAnalyticsSummary,
  getToken,
  type WorkflowSummary,
  type UserWorkflowSummary,
} from "@/lib/api";

interface HomeLaunchGridProps {
  onSelectFeature: (type: WorkflowType) => void;
  // Optional — kept for API compatibility; launch wiring lives in
  // SavedWorkflowsPage (profile dropdown) now.
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
  userTier?: Tier;
}

export function HomeLaunchGrid({
  onSelectFeature,
  userTier = "basic",
}: HomeLaunchGridProps) {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // SC-2: owner-scoped per-type history-average duration (seconds), keyed by
  // the generic workflow id, from GET /api/analytics/summary (38-01). Feeds the
  // "~Xm" half of each card's real estimate. Empty until fetched / on failure —
  // the estimate then degrades to agents-only (no fabricated time).
  const [avgDurationSec, setAvgDurationSec] = useState<Record<string, number>>({});
  // SURF-03: the compiled workflow the read-only WorkflowDialog is inspecting
  // (null = closed). Set by any catalog row's inspect affordance.
  const [inspectId, setInspectId] = useState<string | null>(null);

  // Fetch shell ⟵ AgentModelPicker.tsx:48-74 (cancelled guard, getToken
  // fallback, loading/error/finally). `.filter(w => w.user_launchable)` is
  // GATE 1 — the declared product-visibility flag.
  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getWorkflowDefinitions(jwt)
      .then((rows) => {
        if (cancelled) return;
        setWorkflows(rows.filter((w) => w.user_launchable)); // gate 1
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message ?? "Failed to load workflows.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // SC-2: owner-scoped per-type history average for the "~Xm" estimate half.
    // The endpoint enforces WHERE user_id server-side (no cross-owner leak); we
    // ask for the full window ("all"). Tolerant .catch → empty map so the grid
    // still renders (agents-only) if analytics is unavailable — never crashes.
    getAnalyticsSummary(jwt, "all")
      .then((summary) => {
        if (cancelled) return;
        setAvgDurationSec(summary.type_avg_duration_sec ?? {});
      })
      .catch(() => {
        if (!cancelled) setAvgDurationSec({});
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Launch fork ⟵ CreationHub.tsx:27-38, but wizard routing is read from
  // CHAIN_OPTIONS (workflowChaining) instead of the two hardcoded router.push
  // strings, with the prototype/ppt template-wizard fallback preserved.
  const handleClick = (type: WorkflowType) => {
    if (!canRunPipeline(userTier, type)) return; // gate 2: tier-blocked → no-op
    const opt = CHAIN_OPTIONS.find((o) => o.type === type);
    if (opt?.requiresWizard && opt.wizardPath) {
      router.push(opt.wizardPath);
      return;
    }
    if (type === "prototype") {
      router.push("/workflow/create?mode=prototype");
      return;
    }
    if (type === "ppt") {
      router.push("/workflow/create?mode=ppt");
      return;
    }
    onSelectFeature(type);
  };

  return (
    <div
      className="flex h-full flex-col overflow-y-auto bg-surface-paper"
      style={{ scrollbarGutter: "stable" }}
    >
      <div className="flex-1 flex flex-col items-center px-6 py-12 max-w-2xl mx-auto w-full">

        {/* Header ⟵ CreationHub.tsx:47-66 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-12 w-full"
        >
          <p className="text-[10px] font-semibold text-ink-400 uppercase tracking-[0.18em] mb-5">
            VelocityAI
          </p>
          <h1
            className="text-[38px] sm:text-[44px] font-normal italic text-ink-900 leading-tight tracking-tight mb-4 font-serif"
          >
            What would you like to build today?
          </h1>
          <p className="text-[14px] text-ink-500 leading-relaxed max-w-md mx-auto">
            Select a deliverable. The right specialist agents will be assembled — review and configure them before execution.
          </p>

          {/* "+ Create workflow" — SAVE-FROM-BOTH catalog entry: routes into the
              custom composer via the existing onSelectFeature prop. Quiet text
              button (no new visual language, UI-SPEC §4). */}
          <button
            onClick={() => onSelectFeature("custom" as WorkflowType)}
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold text-ink-500 hover:text-ink-900 hover:bg-surface-card border border-transparent hover:border-line-border transition-all"
          >
            <Plus className="h-3.5 w-3.5" /> Create workflow
          </button>
        </motion.div>

        {error && (
          <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-[var(--status-failed-fill)] rounded-lg px-2.5 py-1.5">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {error}
          </div>
        )}

        {!loading && !error && workflows.length === 0 && (
          <p className="text-[11px] text-ink-400 py-2">
            No workflows available for your plan yet.
          </p>
        )}

        {/* Workflow list ⟵ CreationHub.tsx:69-123 (rows from the live fetch) */}
        {!loading && !error && workflows.length > 0 && (
          <div className="w-full divide-y divide-line-divider">
            {workflows.map((row, idx) => {
              const type = row.id as WorkflowType;
              // Friendly label, NEVER the raw API `name` (UI-SPEC §4).
              const label = row.display_name ?? getWorkflowLabel(row.id);
              const subtitle = row.description;
              // SC-2 real estimate — generic, keyed on the row id (NEVER a
              // workflow-name branch; SC-001/INV-1). Agents come from the
              // step_count already on the wire (agent_count tolerated as a
              // fallback if a future manifest exposes it). Minutes come from
              // the owner-scoped history average, rendered ONLY when an entry
              // for this row exists — otherwise the time clause is omitted (no
              // fabricated/hardcoded time).
              const agents =
                row.step_count ??
                (row as WorkflowSummary & { agent_count?: number }).agent_count;
              const avgSec = avgDurationSec[row.id];
              const minutes =
                avgSec != null ? Math.round(avgSec / 60) : null;
              const estimate = `~${agents} agents${
                minutes != null ? ` · ~${minutes}m` : ""
              }`;
              const allowed = canRunPipeline(userTier, type); // gate 2
              const upgradeTo = getUpgradeTier(userTier, type);
              return (
                <motion.div
                  key={row.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.1 + idx * 0.06 }}
                  className="flex items-stretch"
                >
                  <button
                    onClick={() => handleClick(type)}
                    disabled={!allowed}
                    className={`group flex-1 flex items-center justify-between gap-4 py-5 text-left rounded-lg px-3 -mx-3 transition-colors ${
                      allowed ? "hover:bg-surface-card cursor-pointer" : "cursor-not-allowed opacity-60"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {!allowed && <Lock className="h-3.5 w-3.5 text-ink-400 flex-shrink-0" />}
                        <h2 className={`text-[15px] font-semibold italic leading-snug transition-colors ${
                          allowed ? "text-ink-900 group-hover:text-brand" : "text-ink-400"
                        }`}>
                          {label}
                        </h2>
                      </div>
                      <p className={`text-[12px] italic leading-snug ${allowed ? "text-ink-500" : "text-ink-400"}`}>
                        {subtitle}
                      </p>
                      {/* SC-2 — real per-deliverable estimate: agents always,
                          time only when the owner-scoped history has an entry. */}
                      <p className="text-[11px] not-italic text-ink-400 mt-1">
                        {estimate}
                      </p>
                      {!allowed && upgradeTo && (
                        <p className="text-[10px] font-semibold text-brand mt-1">
                          Requires {TIER_LABELS[upgradeTo]} plan
                        </p>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {allowed ? (
                        <ArrowRight className="h-4 w-4 text-ink-300 group-hover:text-ink-600 group-hover:translate-x-0.5 transition-all" />
                      ) : (
                        <div className="h-6 w-6 rounded-full bg-surface-warm flex items-center justify-center">
                          <Lock className="h-3 w-3 text-ink-400" />
                        </div>
                      )}
                    </div>
                  </button>
                  {/* SURF-03 — inspect this compiled workflow's declared
                      capabilities / context / compaction. A SIBLING of the launch
                      button (never nested) so both stay valid focusable controls;
                      opens the read-only WorkflowDialog without launching. Stays
                      enabled even on a tier-locked row (looking ≠ launching). */}
                  <button
                    type="button"
                    onClick={() => setInspectId(row.id)}
                    aria-label={`Inspect ${label} details`}
                    className="flex w-9 flex-shrink-0 items-center justify-center self-center rounded-lg text-ink-300 transition-colors hover:bg-surface-card hover:text-ink-700"
                  >
                    <Info className="h-3.5 w-3.5" />
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

      </div>

      {/* SURF-03 detail viewer — mounted here so the inspect affordance on any
          catalog row is reachable. Read-only; surfaces declared data only (INV-5). */}
      {inspectId && (
        <WorkflowDialog workflowId={inspectId} onClose={() => setInspectId(null)} />
      )}
    </div>
  );
}
