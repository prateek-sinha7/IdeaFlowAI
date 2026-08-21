"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import {
  AlertCircle, MoreVertical, Pencil, Copy, Trash2, Edit,
  Play, Workflow, Clock, Cpu,
  Search, Plus,
} from "lucide-react";
import {
  getUserWorkflows, createUserWorkflow, renameUserWorkflow,
  deleteUserWorkflow, getToken, type UserWorkflowSummary,
} from "@/lib/api";
import { NameWorkflowModal } from "@/components/catalog/NameWorkflowModal";
import { routes } from "@/lib/routes";

// ── Helpers ───────────────────────────────────────────────────────────────────

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories", ppt: "Presentation", prototype: "Prototype",
  app_builder: "App Builder", custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot", dotnet_to_azure: ".NET → Azure",
};

// Neutral avatar tints — Phase-32 @theme tokens only (no raw hex / stock palette).
const ICON_STYLES = [
  "bg-brand-fill text-brand",
  "bg-surface-warm text-ink-700",
  "bg-[var(--status-done-fill)] text-status-done",
  "bg-[var(--status-amber-fill)] text-status-amber",
  "bg-[var(--status-running-fill)] text-status-running",
  "bg-surface-paper text-ink-600",
];

function getInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function formatRelativeDate(iso?: string | null): string {
  if (!iso) return "—";
  // Ensure UTC — backend timestamps have no timezone suffix
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z";
  const date = new Date(normalized);
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

/** Strip === Attached: filename === ... === End: filename === blocks, then trim.
 *  Returns the user's own text, or if ALL content was attachments,
 *  returns a summary of the attached filenames instead. */
function cleanBrief(raw: string): string {
  // Collect filenames before stripping
  const fileMatches = [...raw.matchAll(/===\s*Attached:\s*([^=\n]+?)\s*===/g)];
  const stripped = raw
    .replace(/===\s*Attached:[^=]+===[\s\S]*?===\s*End:[^=]+===/g, "")
    .replace(/\[Attached:[^\]]*\]/g, "")
    .trim();
  if (stripped) return stripped;
  // All content was file attachments — show filenames as a fallback
  if (fileMatches.length > 0) {
    const names = fileMatches.map(m => m[1].trim());
    return `📎 ${names.join(", ")}`;
  }
  return "";
}

interface SavedWorkflowsPageProps {
  onLaunchSaved?: (saved: UserWorkflowSummary) => void;
  /** Opens a fresh Composer canvas to build a new workflow — mirrors the
   *  Dashboard's "Compose a custom workflow" card (HomeLaunchGrid → the
   *  `custom` catalog card → handleSelectFeature). */
  onCreateNew?: () => void;
}

// ── Kebab dropdown (module-level for a STABLE element identity) ──────────────
// Defined outside the page so a parent state change re-renders (never remounts)
// the trigger button — keeping aria-expanded live in place and the Escape-focus
// ref stable. a11y: trigger exposes aria-haspopup/expanded; the panel is
// role=menu with role=menuitem rows; Escape closes + refocuses the trigger.
function KebabMenu({
  row, isOpen, onToggle, onClose, onEdit, onRename, onDuplicate, onDelete,
}: {
  row: UserWorkflowSummary;
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  onEdit: () => void;
  onRename: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape" && isOpen) {
      e.stopPropagation();
      onClose();
      triggerRef.current?.focus();
    }
  };
  return (
    <div className="relative" onClick={(e) => e.stopPropagation()} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Workflow actions"
        onClick={onToggle}
        className="h-7 w-7 flex items-center justify-center rounded-lg text-ink-300 hover:text-ink-600 hover:bg-surface-warm transition-colors"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.1 }}
            className="absolute right-0 top-8 z-20 bg-surface-white border border-line-border rounded-[var(--radius-menu)] shadow-[var(--elevation-menu)] py-1 min-w-[130px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button role="menuitem" onClick={onEdit}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-ink-700 hover:bg-surface-warm transition-colors">
              <Edit className="h-3.5 w-3.5" /> Edit
            </button>
            <button role="menuitem" onClick={onRename}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-ink-700 hover:bg-surface-warm transition-colors">
              <Pencil className="h-3.5 w-3.5" /> Rename
            </button>
            <button role="menuitem" onClick={onDuplicate}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-ink-700 hover:bg-surface-warm transition-colors">
              <Copy className="h-3.5 w-3.5" /> Duplicate
            </button>
            <div className="border-t border-line-divider my-0.5" />
            <button role="menuitem" onClick={onDelete}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-status-failed hover:bg-[var(--status-failed-fill)] transition-colors">
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function SavedWorkflowsPage({ onLaunchSaved, onCreateNew }: SavedWorkflowsPageProps) {
  const router = useRouter();
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

  const handleEdit = (row: UserWorkflowSummary) => {
    setOpenMenuId(null);
    router.push(routes.workflowEdit(row.id));
  };

  const handleDeleteConfirm = async () => {
    const id = deleteConfirmId; if (!id) return; setDeleteConfirmId(null);
    const jwt = getToken(); if (!jwt) return;
    try {
      await deleteUserWorkflow(jwt, id);
      setUserWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch (e) { setSavedError((e as Error)?.message ?? "Delete failed."); }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-surface-paper">
      <div className="flex-1 flex flex-col max-w-5xl mx-auto w-full px-6 py-10">

        {/* ── Page header — matches HomeLaunchGrid style ─────────────────── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }} className="mb-8">
          <p className="text-[11px] font-semibold text-ink-400 uppercase tracking-[0.24em] mb-2">
            VelocityAI
          </p>
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-[32px] sm:text-[38px] font-normal italic text-ink-900 leading-tight tracking-tight font-serif">
                My Workflows
              </h1>
              <p className="text-[14px] text-ink-500 leading-relaxed mt-1">
                Your saved custom workflows — launch, manage and reuse them.
              </p>
            </div>
            <div className="flex items-center gap-5 flex-shrink-0">
              {!loading && userWorkflows.length > 0 && (
                <>
                  <div className="text-right">
                    <p className="text-[22px] font-semibold text-ink-900 leading-none">{userWorkflows.length}</p>
                    <p className="text-[11px] text-ink-400 mt-0.5">workflow{userWorkflows.length !== 1 ? "s" : ""}</p>
                  </div>
                  <div className="w-px h-8 bg-line-divider" />
                  <div className="text-right">
                    <p className="text-[22px] font-semibold text-ink-900 leading-none">
                      {userWorkflows.reduce((s, w) => s + (w.agent_ids?.length ?? 0), 0)}
                    </p>
                    <p className="text-[11px] text-ink-400 mt-0.5">total agents</p>
                  </div>
                  <div className="w-px h-8 bg-line-divider" />
                </>
              )}
              {onCreateNew && (
                <button onClick={onCreateNew}
                  className="flex items-center gap-1.5 rounded-[10px] bg-brand px-3.5 py-2.5 text-[12px] font-semibold text-white hover:bg-brand-pressed transition-colors">
                  <Plus className="h-3.5 w-3.5" />New workflow
                </button>
              )}
            </div>
          </div>
        </motion.div>

        {/* ── Toolbar ─────────────────────────────────────────────────────── */}
        {!loading && userWorkflows.length > 0 && (
          <div className="flex items-center gap-3 mt-[22px] mb-[18px]">
            <div className="relative w-full max-w-[340px]">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-[15px] w-[15px] text-ink-400" />
              <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                aria-label="Search workflows"
                name="saved-workflows-search"
                placeholder="Search workflows…"
                className="w-full pl-10 pr-4 py-[9px] text-[13px] bg-surface-card border border-line-control rounded-[10px] focus:outline-none focus:border-line-faint placeholder-ink-400 transition-colors" />
            </div>
            {search && filtered.length < userWorkflows.length && (
              <p className="text-[11px] text-ink-400">{filtered.length} of {userWorkflows.length}</p>
            )}
          </div>
        )}

        {/* Loading */}
        {loading && <p className="text-[11px] text-ink-400 py-4">Loading…</p>}

        {/* Error */}
        {savedError && (
          <div className="flex items-center gap-1.5 text-[11px] text-status-failed bg-[var(--status-failed-fill)] rounded-lg px-3 py-2 mb-4">
            <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />{savedError}
          </div>
        )}

        {/* Empty state */}
        {!loading && !savedError && userWorkflows.length === 0 && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="flex flex-col items-center gap-3 py-20 text-center">
            <div className="w-14 h-14 rounded-2xl bg-surface-white border border-line-border flex items-center justify-center">
              <Workflow className="h-6 w-6 text-ink-400" />
            </div>
            <p className="text-[14px] font-medium text-ink-600">No workflows saved yet</p>
            <p className="text-[12px] text-ink-400 max-w-xs leading-relaxed">
              Build a custom workflow from the home screen using &quot;Create workflow&quot; — it will appear here once saved.
            </p>
          </motion.div>
        )}

        {/* No search results */}
        {!loading && userWorkflows.length > 0 && filtered.length === 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center gap-2 py-12 text-center">
            <Search className="h-7 w-7 text-ink-300" />
            <p className="text-[13px] font-medium text-ink-500">No workflows match &quot;{search}&quot;</p>
            <button onClick={() => setSearch("")} className="text-[12px] text-brand hover:underline">Clear search</button>
          </motion.div>
        )}

        {/* ── CARD VIEW ─────────────────────────────────────────────────── */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {filtered.map((row, idx) => {
              const iconStyle = ICON_STYLES[idx % ICON_STYLES.length];
              const pipelineLabel = PIPELINE_LABEL[row.base_pipeline_type] ?? row.base_pipeline_type;
              const agentCount = row.agent_ids?.length ?? 0;
              return (
                <motion.div key={row.id}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, delay: Math.min(idx * 0.05, 0.3) }}
                  className="group flex flex-col min-h-[200px] bg-surface-card rounded-[14px] border border-line-border p-[17px] hover:border-line-faint hover:shadow-md transition-all">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className={`w-10 h-10 rounded-[11px] flex items-center justify-center flex-shrink-0 text-[13px] font-semibold group-hover:scale-105 transition-transform ${iconStyle}`}>
                      {getInitials(row.name)}
                    </div>
                    <KebabMenu
                      row={row}
                      isOpen={openMenuId === row.id}
                      onToggle={() => setOpenMenuId(openMenuId === row.id ? null : row.id)}
                      onClose={() => setOpenMenuId(null)}
                      onEdit={() => handleEdit(row)}
                      onRename={() => { setOpenMenuId(null); setRenameRow(row); }}
                      onDuplicate={() => handleDuplicate(row)}
                      onDelete={() => { setOpenMenuId(null); setDeleteConfirmId(row.id); }}
                    />
                  </div>
                  {/* Type badge */}
                  <span className="self-start text-[9px] font-semibold uppercase tracking-[0.06em] px-2 py-1 rounded-[5px] bg-surface-warm text-ink-500 border border-line-control mb-1.5">
                    {pipelineLabel}
                  </span>
                  {/* Name */}
                  <p className="text-[15px] font-semibold italic text-ink-900 group-hover:text-brand transition-colors line-clamp-1">
                    {row.name}
                  </p>
                  {/* Description */}
                  {row.description
                    ? <p className="text-[12px] text-ink-500 mt-1 leading-relaxed line-clamp-2 flex-1">{row.description}</p>
                    : null}
                  {/* Brief preview — from _wizard for all workflow types.
                      Strips === Attached: === file blocks so only the user's own
                      words appear. Falls back to spacer when nothing to show. */}
                  {(() => {
                    const wizard = (row.selections?._wizard ?? null) as Record<string, unknown> | null;
                    const rawBrief = typeof wizard?.brief === "string" ? wizard.brief : null;
                    const brief = rawBrief ? cleanBrief(rawBrief) : null;
                    if (!brief) return row.description ? null : <div className="flex-1" />;
                    return (
                      <p className="text-[11px] text-ink-400 mt-1 leading-relaxed line-clamp-2 flex-1 italic">
                        {brief}
                      </p>
                    );
                  })()}
                  {/* Metadata */}
                  <div className="flex items-center gap-3 mt-3 pt-3 border-t border-line-divider">
                    <span className="flex items-center gap-1 text-[10px] text-ink-400">
                      <Cpu className="h-3 w-3" />{agentCount} agent{agentCount !== 1 ? "s" : ""}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-ink-400 ml-auto">
                      <Clock className="h-3 w-3" />{formatRelativeDate(row.updated_at)}
                    </span>
                  </div>
                  {/* Run button */}
                  <button onClick={() => onLaunchSaved?.(row)}
                    className="mt-3 w-full flex items-center justify-center gap-1.5 rounded-[10px] bg-brand px-3 py-2.5 text-[12px] font-semibold text-white hover:bg-brand-pressed transition-colors">
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
            className="fixed inset-0 z-[80] flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm"
            onClick={() => setDeleteConfirmId(null)}
            onKeyDown={(e) => { if (e.key === "Escape") setDeleteConfirmId(null); }}>
            <motion.div initial={{ opacity: 0, scale: 0.96, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 8 }} transition={{ duration: 0.15 }}
              role="dialog" aria-modal="true" aria-labelledby="delete-workflow-title"
              onClick={(e) => e.stopPropagation()}
              className="bg-surface-white rounded-2xl border border-line-border shadow-[var(--elevation-modal)] p-6 max-w-[340px] w-full mx-4">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-surface-warm flex items-center justify-center">
                  <Trash2 className="h-5 w-5 text-ink-600" />
                </div>
                <div>
                  <h3 id="delete-workflow-title" className="text-[13px] font-semibold text-ink-900">Delete workflow</h3>
                  <p className="text-[11px] text-ink-400">This cannot be undone</p>
                </div>
              </div>
              <p className="text-[12px] text-ink-500 leading-relaxed mb-5">
                The saved workflow will be permanently removed from your saved workflows.
              </p>
              <div className="flex gap-2">
                <button onClick={() => setDeleteConfirmId(null)}
                  className="flex-1 rounded-xl border border-line-border px-4 py-2.5 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors">
                  Cancel
                </button>
                <button onClick={handleDeleteConfirm}
                  className="flex-1 rounded-xl bg-ink-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-ink-800 transition-colors">
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
