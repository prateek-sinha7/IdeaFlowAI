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
import { ArrowRight, Lock, AlertCircle, Plus } from "lucide-react";
import type { WorkflowType } from "@/types/index";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { CHAIN_OPTIONS } from "@/lib/workflowChaining";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import {
  getWorkflowDefinitions,
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
      router.push("/workflow/prototype/templates");
      return;
    }
    if (type === "ppt") {
      router.push("/workflow/ppt/templates");
      return;
    }
    onSelectFeature(type);
  };

  return (
    <div
      className="flex h-full flex-col overflow-y-auto"
      style={{ background: "#f5f5f0", scrollbarGutter: "stable" }}
    >
      <div className="flex-1 flex flex-col items-center px-6 py-12 max-w-2xl mx-auto w-full">

        {/* Header ⟵ CreationHub.tsx:47-66 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-12 w-full"
        >
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-5">
            VelocityAI
          </p>
          <h1
            className="text-[38px] sm:text-[44px] font-normal italic text-gray-900 leading-tight tracking-tight mb-4"
            style={{ fontFamily: "var(--font-fraunces)" }}
          >
            What would you like to build today?
          </h1>
          <p className="text-[14px] text-gray-500 leading-relaxed max-w-md mx-auto">
            Select a deliverable. The right specialist agents will be assembled — review and configure them before execution.
          </p>

          {/* "+ Create workflow" — SAVE-FROM-BOTH catalog entry: routes into the
              custom composer via the existing onSelectFeature prop. Quiet text
              button (no new visual language, UI-SPEC §4). */}
          <button
            onClick={() => onSelectFeature("custom" as WorkflowType)}
            className="mt-5 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold text-gray-500 hover:text-gray-900 hover:bg-white/60 border border-transparent hover:border-gray-200 transition-all"
          >
            <Plus className="h-3.5 w-3.5" /> Create workflow
          </button>
        </motion.div>

        {error && (
          <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {error}
          </div>
        )}

        {!loading && !error && workflows.length === 0 && (
          <p className="text-[11px] text-gray-400 py-2">
            No workflows available for your plan yet.
          </p>
        )}

        {/* Workflow list ⟵ CreationHub.tsx:69-123 (rows from the live fetch) */}
        {!loading && !error && workflows.length > 0 && (
          <div className="w-full divide-y divide-gray-200/70">
            {workflows.map((row, idx) => {
              const type = row.id as WorkflowType;
              // Friendly label, NEVER the raw API `name` (UI-SPEC §4).
              const label = row.display_name ?? getWorkflowLabel(row.id);
              const subtitle = row.description;
              const allowed = canRunPipeline(userTier, type); // gate 2
              const upgradeTo = getUpgradeTier(userTier, type);
              return (
                <motion.div
                  key={row.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.1 + idx * 0.06 }}
                >
                  <button
                    onClick={() => handleClick(type)}
                    disabled={!allowed}
                    className={`group w-full flex items-center justify-between gap-4 py-5 text-left rounded-lg px-3 -mx-3 transition-colors ${
                      allowed ? "hover:bg-white/60 cursor-pointer" : "cursor-not-allowed opacity-60"
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {!allowed && <Lock className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />}
                        <h2 className={`text-[15px] font-semibold italic leading-snug transition-colors ${
                          allowed ? "text-gray-900 group-hover:text-[#1B2A4A]" : "text-gray-400"
                        }`}>
                          {label}
                        </h2>
                      </div>
                      <p className={`text-[12px] italic leading-snug ${allowed ? "text-gray-500" : "text-gray-400"}`}>
                        {subtitle}
                      </p>
                      {!allowed && upgradeTo && (
                        <p className="text-[10px] font-semibold text-[#1B2A4A] mt-1">
                          Requires {TIER_LABELS[upgradeTo]} plan
                        </p>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {allowed ? (
                        <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
                      ) : (
                        <div className="h-6 w-6 rounded-full bg-gray-100 flex items-center justify-center">
                          <Lock className="h-3 w-3 text-gray-400" />
                        </div>
                      )}
                    </div>
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

      </div>
    </div>
  );
}
