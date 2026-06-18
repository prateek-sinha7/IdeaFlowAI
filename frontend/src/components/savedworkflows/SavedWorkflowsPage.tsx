"use client";

/**
 * SavedWorkflowsPage — standalone page for managing the user's saved (custom)
 * workflows. Extracted from WorkflowCatalog so the list lives at its own route
 * (accessible from the profile dropdown) rather than being buried at the bottom
 * of the home screen.
 *
 * Logic mirrors WorkflowCatalog's "Your workflows" section verbatim:
 * same fetch, same CRUD (Rename / Duplicate / Delete), same launch wiring.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  AlertCircle,
  MoreHorizontal,
  Pencil,
  Copy,
  Trash2,
  ArrowRight,
  Workflow,
} from "lucide-react";
import {
  getUserWorkflows,
  createUserWorkflow,
  renameUserWorkflow,
  deleteUserWorkflow,
  getToken,
  type UserWorkflowSummary,
} from "@/lib/api";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";

interface SavedWorkflowsPageProps {
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
}

export function SavedWorkflowsPage({ onLaunchSaved }: SavedWorkflowsPageProps) {
  const [userWorkflows, setUserWorkflows] = useState<UserWorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [savedError, setSavedError] = useState<string | null>(null);

  // Per-row kebab state
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [renameRow, setRenameRow] = useState<UserWorkflowSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) {
      setSavedError("Not authenticated.");
      setLoading(false);
      return;
    }
    setLoading(true);
    getUserWorkflows(jwt)
      .then((rows) => {
        if (cancelled) return;
        setUserWorkflows(rows);
        setSavedError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        setSavedError(e?.message ?? "Failed to load saved workflows.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── CRUD handlers ──────────────────────────────────────────────────────────

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

  const handleDeleteConfirm = async () => {
    const id = deleteConfirmId;
    if (!id) return;
    setDeleteConfirmId(null);
    const jwt = getToken();
    if (!jwt) return;
    try {
      await deleteUserWorkflow(jwt, id);
      setUserWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch (e) {
      setSavedError((e as Error)?.message ?? "Delete failed.");
    }
  };

  return (
    <div
      className="flex h-full flex-col overflow-y-auto"
      style={{ background: "#f5f5f0" }}
    >
      <div className="flex-1 flex flex-col items-center px-6 py-12 max-w-2xl mx-auto w-full">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full mb-10"
        >
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-5">
            VelocityAI
          </p>
          <h1
            className="text-[32px] sm:text-[38px] font-normal italic text-gray-900 leading-tight tracking-tight mb-2"
            style={{ fontFamily: "var(--font-fraunces)" }}
          >
            Saved Workflows
          </h1>
          <p className="text-[14px] text-gray-500 leading-relaxed">
            Your custom-built workflows — launch, rename, duplicate or delete them here.
          </p>
        </motion.div>

        {/* Loading */}
        {loading && (
          <p className="text-[11px] text-gray-400 py-2">Loading…</p>
        )}

        {/* Error */}
        {savedError && (
          <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-2.5 py-1.5 mb-4 w-full">
            <AlertCircle className="h-3 w-3 flex-shrink-0" />
            {savedError}
          </div>
        )}

        {/* Empty state */}
        {!loading && !savedError && userWorkflows.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="flex flex-col items-center gap-3 py-16 text-center"
          >
            <div className="w-12 h-12 rounded-2xl bg-gray-100 flex items-center justify-center">
              <Workflow className="h-5 w-5 text-gray-400" />
            </div>
            <p className="text-[13px] font-medium text-gray-500">No saved workflows yet</p>
            <p className="text-[12px] text-gray-400 max-w-xs leading-relaxed">
              Build a custom workflow from the home screen using "Create workflow" — it will appear here once saved.
            </p>
          </motion.div>
        )}

        {/* Workflow list */}
        {!loading && userWorkflows.length > 0 && (
          <div className="w-full divide-y divide-gray-200/70">
            {userWorkflows.map((row, idx) => (
              <motion.div
                key={row.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.05 + idx * 0.05 }}
                className="group flex items-center justify-between gap-4 py-5 rounded-lg px-3 -mx-3 hover:bg-white/60 transition-colors"
              >
                {/* Launch button area */}
                <button
                  onClick={() => onLaunchSaved?.(row)}
                  className="flex-1 min-w-0 text-left cursor-pointer"
                >
                  <h2 className="text-[15px] font-semibold italic leading-snug text-gray-900 group-hover:text-[#1B2A4A] transition-colors truncate">
                    {row.name}
                  </h2>
                  {row.description && (
                    <p className="text-[12px] italic leading-snug text-gray-500 truncate mt-0.5">
                      {row.description}
                    </p>
                  )}
                  <p className="text-[10px] text-gray-400 mt-1">
                    {row.agent_ids?.length ?? 0} agents · {row.base_pipeline_type}
                  </p>
                </button>

                {/* Right slot: kebab + launch arrow */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* Kebab menu */}
                  <div className="relative">
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

                  {/* Launch arrow */}
                  <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Rename modal */}
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

      {/* Delete confirm modal */}
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

      {/* Close kebab on outside click */}
      {openMenuId && (
        <div className="fixed inset-0 z-10" onClick={() => setOpenMenuId(null)} />
      )}
    </div>
  );
}
