"use client";

/**
 * WorkflowCatalog — the data-driven Creation Hub (Plan 20-02, WF-DB-01 /
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
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useRouter } from "next/navigation";
import {
  ArrowRight, Lock, AlertCircle, Plus, MoreHorizontal,
  Pencil, Copy, Trash2,
} from "lucide-react";
import type { WorkflowType } from "@/types/index";
import type { Tier } from "@/lib/entitlements";
import { canRunPipeline, TIER_LABELS, getUpgradeTier } from "@/lib/entitlements";
import { CHAIN_OPTIONS } from "@/lib/workflowChaining";
import { getWorkflowLabel } from "@/hooks/useNotifications";
import {
  getWorkflowDefinitions,
  getUserWorkflows,
  createUserWorkflow,
  renameUserWorkflow,
  deleteUserWorkflow,
  getToken,
  type WorkflowSummary,
  type UserWorkflowSummary,
} from "@/lib/api";
import { NameWorkflowModal } from "./NameWorkflowModal";

interface WorkflowCatalogProps {
  onSelectFeature: (type: WorkflowType) => void;
  // NEW (Phase 21) — launch a SAVED workflow (carries the composer triple),
  // which `onSelectFeature` (a bare WorkflowType) cannot express. Optional here
  // so the existing DashboardLayout caller keeps compiling; the load-bearing
  // wiring (handleLaunchSaved → IdeaInputPage preload) lands in 21-03.
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
  userTier?: Tier;
}

export function WorkflowCatalog({
  onSelectFeature,
  onLaunchSaved,
  userTier = "basic",
}: WorkflowCatalogProps) {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Phase 21 — the SECOND list: the caller's saved workflows. No
  // `user_launchable` filter (every owned `source="user"` row always shows).
  const [userWorkflows, setUserWorkflows] = useState<UserWorkflowSummary[]>([]);
  const [savedError, setSavedError] = useState<string | null>(null);
  // Per-row kebab state — analog WorkflowHistory.tsx:127-128.
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [renameRow, setRenameRow] = useState<UserWorkflowSummary | null>(null);

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

  // Phase 21 — second fetch (copy of the mount effect above), swapping
  // `getWorkflowDefinitions` for `getUserWorkflows` and dropping the
  // `user_launchable` filter (user rows are always shown). A failed saved-list
  // fetch is non-fatal: the built-in catalog still renders (SC-001 no regression).
  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) return;
    getUserWorkflows(jwt)
      .then((rows) => {
        if (cancelled) return;
        setUserWorkflows(rows);
        setSavedError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setSavedError(e?.message ?? "Failed to load saved workflows.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Saved-row kebab actions (CRUD-OWNER-SCOPED) ──────────────────────────
  // Rename → NameWorkflowModal prefilled → renameUserWorkflow → optimistic
  // label update.
  const handleRenameSave = async (name: string, description: string) => {
    if (!renameRow) return;
    const id = renameRow.id;
    setRenameRow(null);
    const jwt = getToken();
    if (!jwt) return;
    try {
      const updated = await renameUserWorkflow(jwt, id, { name, description });
      setUserWorkflows((prev) => prev.map((w) => (w.id === id ? updated : w)));
    } catch (e) {
      setSavedError((e as Error)?.message ?? "Rename failed.");
    }
  };

  // Duplicate → createUserWorkflow with the copied composer payload + a "(copy)"
  // name → prepend to the list.
  const handleDuplicate = async (row: UserWorkflowSummary) => {
    setOpenMenuId(null);
    const jwt = getToken();
    if (!jwt) return;
    try {
      const created = await createUserWorkflow(jwt, {
        name: `${row.name} (copy)`,
        description: row.description ?? undefined,
        base_pipeline_type: row.base_pipeline_type,
        agent_ids: row.agent_ids,
        model_overrides: row.model_overrides ?? undefined,
      });
      setUserWorkflows((prev) => [created, ...prev]);
    } catch (e) {
      setSavedError((e as Error)?.message ?? "Duplicate failed.");
    }
  };

  // Delete → DeleteModal confirm → deleteUserWorkflow → optimistic removal
  // (analog WorkflowHistory.tsx:159-175).
  const handleDeleteConfirm = async () => {
    const id = deleteConfirmId;
    if (!id) return;
    setDeleteConfirmId(null);
    const jwt = getToken();
    if (!jwt) return;
    try {
      await deleteUserWorkflow(jwt, id);
    } catch (e) {
      setSavedError((e as Error)?.message ?? "Delete failed.");
    }
    setUserWorkflows((prev) => prev.filter((w) => w.id !== id));
  };

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
      style={{ background: "#f5f5f0" }}
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

        {/* Loading/error/empty triad ⟵ AgentModelPicker.tsx:99-114 */}
        {loading && (
          <p className="text-[11px] text-gray-400 py-2">Loading workflows…</p>
        )}

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

        {/* ── "Your workflows" — the SECOND list (saved rows). Row markup is a
            copy of the built-in list above; `label = row.name` (user rows render
            their OWN name — the never-raw-API-name rule is MANIFEST-only). Each
            row launches via onLaunchSaved(row); the right slot is the per-row
            kebab (Rename/Duplicate/Delete) instead of the ArrowRight. Built-in
            rows stay read-only — only these source="user" rows get the kebab. ── */}
        {userWorkflows.length > 0 && (
          <section className="w-full mt-12">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-3">
              Your workflows
            </p>
            {savedError && (
              <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5 mb-2">
                <AlertCircle className="h-3 w-3 flex-shrink-0" />
                {savedError}
              </div>
            )}
            <div className="w-full divide-y divide-gray-200/70">
              {userWorkflows.map((row, idx) => (
                <motion.div
                  key={row.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.05 + idx * 0.05 }}
                  className="group flex items-center justify-between gap-4 py-5 rounded-lg px-3 -mx-3 hover:bg-white/60 transition-colors"
                >
                  <button
                    onClick={() => onLaunchSaved?.(row)}
                    className="flex-1 min-w-0 text-left cursor-pointer"
                  >
                    <h2 className="text-[15px] font-semibold italic leading-snug text-gray-900 group-hover:text-[#1B2A4A] transition-colors truncate">
                      {row.name}
                    </h2>
                    {row.description && (
                      <p className="text-[12px] italic leading-snug text-gray-500 truncate">
                        {row.description}
                      </p>
                    )}
                  </button>
                  {/* Per-row kebab ⟵ WorkflowHistory.tsx:872-899 (Rename/Duplicate/Delete). */}
                  <div className="relative flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId(openMenuId === row.id ? null : row.id);
                      }}
                      className="flex items-center justify-center h-7 w-7 rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                    <AnimatePresence>
                      {openMenuId === row.id && (
                        <motion.div
                          initial={{ opacity: 0, scale: 0.95, y: -4 }}
                          animate={{ opacity: 1, scale: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.95, y: -4 }}
                          transition={{ duration: 0.1 }}
                          className="absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            onClick={() => { setOpenMenuId(null); setRenameRow(row); }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-gray-700 hover:bg-gray-50 transition-colors"
                          >
                            <Pencil className="h-3.5 w-3.5" /> Rename
                          </button>
                          <button
                            onClick={() => handleDuplicate(row)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-gray-700 hover:bg-gray-50 transition-colors"
                          >
                            <Copy className="h-3.5 w-3.5" /> Duplicate
                          </button>
                          <button
                            onClick={() => { setOpenMenuId(null); setDeleteConfirmId(row.id); }}
                            className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-red-600 hover:bg-red-50 transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" /> Delete
                          </button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              ))}
            </div>
          </section>
        )}

      </div>

      {/* Rename modal — reuses NameWorkflowModal (Save + Rename share it). */}
      <AnimatePresence>
        {renameRow && (
          <NameWorkflowModal
            title="Rename workflow"
            initialName={renameRow.name}
            initialDescription={renameRow.description ?? ""}
            onSave={handleRenameSave}
            onCancel={() => setRenameRow(null)}
          />
        )}
      </AnimatePresence>

      {/* Delete confirm — DeleteModal shell (analog WorkflowHistory.tsx:923-969). */}
      <AnimatePresence>
        {deleteConfirmId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-black/20 backdrop-blur-sm"
            onClick={() => setDeleteConfirmId(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }}
              transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-2xl border border-gray-200 shadow-2xl p-6 max-w-[340px] w-full mx-4"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
                  <Trash2 className="h-5 w-5 text-gray-600" />
                </div>
                <div>
                  <h3 className="text-[13px] font-semibold text-gray-900">Delete workflow</h3>
                  <p className="text-[11px] text-gray-400">This cannot be undone</p>
                </div>
              </div>
              <p className="text-[12px] text-gray-500 leading-relaxed mb-5">
                The saved workflow will be permanently removed from your list.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setDeleteConfirmId(null)}
                  className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteConfirm}
                  className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Close kebab on outside click — analog WorkflowHistory.tsx:916-918. */}
      {openMenuId && (
        <div className="fixed inset-0 z-10" onClick={() => setOpenMenuId(null)} />
      )}
    </div>
  );
}
