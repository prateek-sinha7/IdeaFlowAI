"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  AlertCircle, MoreHorizontal, Pencil, Copy, Trash2,
  Play, Workflow, Clock, Cpu,
  Search, Calendar,
} from "lucide-react";
import {
  getUserWorkflows, createUserWorkflow, renameUserWorkflow,
  deleteUserWorkflow, getToken, type UserWorkflowSummary,
} from "@/lib/api";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";

// ── Helpers ───────────────────────────────────────────────────────────────────

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

// Matches ICON_STYLES used across Library / AgentsPopup — neutral palette only
const ICON_STYLES = [
  { bg: "#E8EDF5", text: "#1B2A4A" },
  { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" },
  { bg: "#F0E8EE", text: "#5C2A4A" },
  { bg: "#E8EEF0", text: "#2A4A5C" },
  { bg: "#F0EEE8", text: "#5C5A2A" },
];

function getInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function formatRelativeDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (isNaN(date.getTime())) return "—";
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatFullDate(iso?: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}


interface SavedWorkflowsPageProps {
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
}

export function SavedWorkflowsPage({ onLaunchSaved }: SavedWorkflowsPageProps) {
  const [userWorkflows, setUserWorkflows] = useState<UserWorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [savedError, setSavedError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [renameRow, setRenameRow] = useState<UserWorkflowSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const jwt = getToken();
    if (!jwt) { setSavedError("Not authenticated."); setLoading(false); return; }
    setLoading(true);
    getUserWorkflows(jwt)
      .then((rows) => { if (!cancelled) { setUserWorkflows(rows); setSavedError(null); } })
      .catch((e) => { if (!cancelled) setSavedError(e?.message ?? "Failed to load."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered = userWorkflows.filter((w) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return w.name.toLowerCase().includes(q)
      || (w.description ?? "").toLowerCase().includes(q)
      || (PIPELINE_LABEL[w.base_pipeline_type] ?? w.base_pipeline_type).toLowerCase().includes(q);
  });

  const handleRenameSave = async (name: string, description: string) => {
    if (!renameRow) return;
    const id = renameRow.id; setRenameRow(null);
    const jwt = getToken(); if (!jwt) return;
    try {
      const updated = await renameUserWorkflow(jwt, id, { name, description });
      setUserWorkflows((prev) => prev.map((w) => (w.id === id ? updated : w)));
    } catch (e) { setSavedError((e as Error)?.message ?? "Rename failed."); }
  };

  const handleDuplicate = async (row: UserWorkflowSummary) => {
    setOpenMenuId(null);
    const jwt = getToken(); if (!jwt) return;
    try {
      const created = await createUserWorkflow(jwt, {
        name: `${row.name} (copy)`, description: row.description ?? undefined,
        base_pipeline_type: row.base_pipeline_type, agent_ids: row.agent_ids,
        model_overrides: row.model_overrides ?? undefined,
      });
      setUserWorkflows((prev) => [created, ...prev]);
    } catch (e) { setSavedError((e as Error)?.message ?? "Duplicate failed."); }
  };

  const handleDeleteConfirm = async () => {
    const id = deleteConfirmId; if (!id) return; setDeleteConfirmId(null);
    const jwt = getToken(); if (!jwt) return;
    try {
      await deleteUserWorkflow(jwt, id);
      setUserWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch (e) { setSavedError((e as Error)?.message ?? "Delete failed."); }
  };

  // ── Kebab dropdown (shared between list + grid) ───────────────────────────
  const KebabMenu = ({ row }: { row: UserWorkflowSummary }) => (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpenMenuId(openMenuId === row.id ? null : row.id)}
        className="h-7 w-7 flex items-center justify-center rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors"
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
            className="absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[130px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button onClick={() => { setOpenMenuId(null); setRenameRow(row); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-gray-700 hover:bg-gray-50 transition-colors">
              <Pencil className="h-3.5 w-3.5" /> Rename
            </button>
            <button onClick={() => handleDuplicate(row)}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-gray-700 hover:bg-gray-50 transition-colors">
              <Copy className="h-3.5 w-3.5" /> Duplicate
            </button>
            <div className="border-t border-gray-100 my-0.5" />
            <button onClick={() => { setOpenMenuId(null); setDeleteConfirmId(row.id); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-red-600 hover:bg-red-50 transition-colors">
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );

  return (
    <div className="flex flex-col h-full overflow-y-auto" style={{ background: "#f5f5f0" }}>
      <div className="flex-1 flex flex-col max-w-5xl mx-auto w-full px-6 py-10">

        {/* ── Page header — matches WorkflowCatalog style ─────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }} className="mb-8">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-4">
            VelocityAI
          </p>
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-[32px] sm:text-[38px] font-normal italic text-gray-900 leading-tight tracking-tight"
                style={{ fontFamily: "var(--font-fraunces)" }}>
                Workflow Catalogue
              </h1>
              <p className="text-[14px] text-gray-500 leading-relaxed mt-1">
                Your saved custom workflows — launch, manage and reuse them.
              </p>
            </div>
            {!loading && userWorkflows.length > 0 && (
              <div className="flex items-center gap-5 flex-shrink-0">
                <div className="text-right">
                  <p className="text-[22px] font-semibold text-gray-900 leading-none">{userWorkflows.length}</p>
                  <p className="text-[11px] text-gray-400 mt-0.5">workflow{userWorkflows.length !== 1 ? "s" : ""}</p>
                </div>
                <div className="w-px h-8 bg-gray-200" />
                <div className="text-right">
                  <p className="text-[22px] font-semibold text-gray-900 leading-none">
                    {userWorkflows.reduce((s, w) => s + (w.agent_ids?.length ?? 0), 0)}
                  </p>
                  <p className="text-[11px] text-gray-400 mt-0.5">total agents</p>
                </div>
              </div>
            )}
          </div>
        </motion.div>

        {/* ── Toolbar ─────────────────────────────────────────────────────── */}
        {!loading && userWorkflows.length > 0 && (
          <div className="flex items-center gap-3 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Search workflows…"
                className="w-full pl-9 pr-4 py-2 text-[12px] bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 placeholder-gray-400 transition-colors" />
            </div>
            {search && filtered.length < userWorkflows.length && (
              <p className="text-[11px] text-gray-400">{filtered.length} of {userWorkflows.length}</p>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && <p className="text-[11px] text-gray-400 py-4">Loading…</p>}

        {/* Error */}
        {savedError && (
          <div className="flex items-center gap-1.5 text-[11px] text-red-600 bg-red-50 rounded-lg px-3 py-2 mb-4">
            <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />{savedError}
          </div>
        )}

        {/* Empty state */}
        {!loading && !savedError && userWorkflows.length === 0 && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center gap-3 py-20 text-center">
            <div className="w-14 h-14 rounded-2xl bg-white border border-gray-200 flex items-center justify-center">
              <Workflow className="h-6 w-6 text-gray-400" />
            </div>
            <p className="text-[14px] font-medium text-gray-600">No workflows saved yet</p>
            <p className="text-[12px] text-gray-400 max-w-xs leading-relaxed">
              Build a custom workflow from the home screen using "Create workflow" — it will appear here once saved.
            </p>
          </motion.div>
        )}

        {/* No search results */}
        {!loading && userWorkflows.length > 0 && filtered.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center gap-2 py-12 text-center">
            <Search className="h-7 w-7 text-gray-300" />
            <p className="text-[13px] font-medium text-gray-500">No workflows match "{search}"</p>
            <button onClick={() => setSearch("")} className="text-[12px] text-[#1B2A4A] hover:underline">Clear search</button>
          </motion.div>
        )}

        {/* ── CARD VIEW ─────────────────────────────────────────────────── */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filtered.map((row, idx) => {
              const iconStyle = ICON_STYLES[idx % ICON_STYLES.length];
              const pipelineLabel = PIPELINE_LABEL[row.base_pipeline_type] ?? row.base_pipeline_type;
              const agentCount = row.agent_ids?.length ?? 0;
              return (
                <motion.div key={row.id}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: Math.min(idx * 0.05, 0.3) }}
                  className="group flex flex-col bg-white rounded-xl border border-gray-200 p-4 hover:border-gray-300 hover:shadow-md transition-all">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 text-[11px] font-bold group-hover:scale-105 transition-transform"
                      style={{ background: iconStyle.bg, color: iconStyle.text }}>
                      {getInitials(row.name)}
                    </div>
                    <KebabMenu row={row} />
                  </div>
                  {/* Type badge */}
                  <span className="self-start text-[10px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200 mb-1.5">
                    {pipelineLabel}
                  </span>
                  {/* Name */}
                  <p className="text-[14px] font-semibold italic text-gray-900 group-hover:text-[#1B2A4A] transition-colors line-clamp-1">
                    {row.name}
                  </p>
                  {/* Description */}
                  {row.description
                    ? <p className="text-[11px] text-gray-500 mt-1 leading-relaxed line-clamp-2 flex-1">{row.description}</p>
                    : <div className="flex-1" />}
                  {/* Metadata */}
                  <div className="flex items-center gap-3 mt-3 pt-3 border-t border-gray-100">
                    <span className="flex items-center gap-1 text-[10px] text-gray-400">
                      <Cpu className="h-3 w-3" />{agentCount} agent{agentCount !== 1 ? "s" : ""}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-gray-400 ml-auto">
                      <Clock className="h-3 w-3" />{formatRelativeDate(row.updated_at)}
                    </span>
                  </div>
                  {/* Run button */}
                  <button onClick={() => onLaunchSaved?.(row)}
                    className="mt-3 w-full flex items-center justify-center gap-1.5 rounded-lg bg-[#1B2A4A] px-3 py-2.5 text-[12px] font-semibold text-white hover:bg-[#243761] transition-colors">
                    <Play className="h-3.5 w-3.5" />Run workflow
                  </button>
                </motion.div>
              );
            })}
          </div>
        )}

      </div>

      {/* ── Rename modal ── */}
      <AnimatePresence>
        {renameRow && (
          <NameWorkflowModal title="Rename workflow" initialName={renameRow.name}
            initialDescription={renameRow.description ?? ""}
            onSave={handleRenameSave} onCancel={() => setRenameRow(null)} />
        )}
      </AnimatePresence>

      {/* ── Delete confirm ── */}
      <AnimatePresence>
        {deleteConfirmId && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-black/20 backdrop-blur-sm"
            onClick={() => setDeleteConfirmId(null)}>
            <motion.div initial={{ opacity: 0, scale: 0.96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }} transition={{ duration: 0.15 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-2xl border border-gray-200 shadow-2xl p-6 max-w-[340px] w-full mx-4">
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
                The saved workflow will be permanently removed from your catalogue.
              </p>
              <div className="flex gap-2">
                <button onClick={() => setDeleteConfirmId(null)}
                  className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button onClick={handleDeleteConfirm}
                  className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors">
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {openMenuId && <div className="fixed inset-0 z-10" onClick={() => setOpenMenuId(null)} />}
    </div>
  );
}
