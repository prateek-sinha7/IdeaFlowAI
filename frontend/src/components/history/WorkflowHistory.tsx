"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  History,
  FileText,
  Presentation,
  Layout,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
  Download,
  Eye,
  Trash2,
  Filter,
} from "lucide-react";
import { getToken, getWorkflows, getWorkflow, deleteWorkflow } from "@/lib/api";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { FilesTab } from "@/components/results/FilesTab";
import type { WorkflowRun, WorkflowType } from "@/types/index";

interface WorkflowHistoryProps {
  onBack: () => void;
}

const TYPE_META: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  user_stories: { icon: FileText, label: "User Stories", color: "text-blue-600 bg-blue-50" },
  ppt: { icon: Presentation, label: "Presentation", color: "text-amber-600 bg-amber-50" },
  prototype: { icon: Layout, label: "Prototype", color: "text-emerald-600 bg-emerald-50" },
  validate_pitch: { icon: Presentation, label: "Pitch Deck", color: "text-violet-600 bg-violet-50" },
  app_builder: { icon: Layout, label: "App Builder", color: "text-orange-600 bg-orange-50" },
  reverse_engineer: { icon: FileText, label: "Reverse Engineer", color: "text-rose-600 bg-rose-50" },
  custom: { icon: FileText, label: "Custom", color: "text-slate-600 bg-slate-50" },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function WorkflowHistory({ onBack }: WorkflowHistoryProps) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [detailTab, setDetailTab] = useState<"preview" | "files">("preview");

  // Load workflow runs
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getWorkflows(token, { limit: 100 })
      .then((data) => setRuns(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load full workflow detail when selected
  const handleSelectRun = useCallback(async (run: WorkflowRun) => {
    setSelectedRun(run);
    setSelectedOutput(null);
    setDetailTab("preview");

    if (run.output) {
      setSelectedOutput(run.output);
      return;
    }

    const token = getToken();
    if (!token) return;
    setLoadingDetail(true);
    try {
      const full = await getWorkflow(token, run.id);
      setSelectedRun(full);
      setSelectedOutput(full.output || null);
    } catch {
      // silently fail
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const handleBack = () => {
    if (selectedRun) {
      setSelectedRun(null);
      setSelectedOutput(null);
    } else {
      onBack();
    }
  };

  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const handleDeleteClick = useCallback((runId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setDeleteConfirmId(runId);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirmId) return;
    const token = getToken();
    if (!token) return;
    try {
      await deleteWorkflow(token, deleteConfirmId);
      setRuns((prev) => prev.filter((r) => r.id !== deleteConfirmId));
      if (selectedRun?.id === deleteConfirmId) {
        setSelectedRun(null);
        setSelectedOutput(null);
      }
    } catch {
      // silently fail
    } finally {
      setDeleteConfirmId(null);
    }
  }, [deleteConfirmId, selectedRun]);

  const handleDeleteCancel = useCallback(() => {
    setDeleteConfirmId(null);
  }, []);

  const filteredRuns = filterType === "all" ? runs : runs.filter((r) => r.type === filterType);

  // Detail view for a selected run
  if (selectedRun) {
    const meta = TYPE_META[selectedRun.type] || TYPE_META.custom;
    const Icon = meta.icon;
    const workflowType = selectedRun.type as WorkflowType;

    // Determine content for preview
    const isUserStory = workflowType === "user_stories" || workflowType === "app_builder" || workflowType === "reverse_engineer" || workflowType === "custom";
    const isPpt = workflowType === "ppt" || workflowType === "validate_pitch";
    const isPrototype = workflowType === "prototype";

    return (
      <div className="h-full flex flex-col bg-[#f5f4ed]">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-[#e8e6dc] bg-white">
          <button onClick={handleBack} className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-[#f0eee6] transition-colors">
            <ArrowLeft className="h-4 w-4 text-[#5e5d59]" />
          </button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-semibold ${meta.color}`}>
                <Icon className="h-3 w-3" />
                {meta.label}
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-semibold ${selectedRun.status === "completed" ? "bg-emerald-50 text-emerald-700" : selectedRun.status === "failed" ? "bg-red-50 text-red-700" : "bg-yellow-50 text-yellow-700"}`}>
                {selectedRun.status === "completed" ? <CheckCircle2 className="h-2.5 w-2.5" /> : selectedRun.status === "failed" ? <XCircle className="h-2.5 w-2.5" /> : <Loader2 className="h-2.5 w-2.5 animate-spin" />}
                {selectedRun.status}
              </span>
            </div>
            <h1 className="text-sm font-bold text-[#141413] mt-1 truncate">{selectedRun.title}</h1>
            <p className="text-[10px] text-[#87867f] mt-0.5">
              {formatDate(selectedRun.createdAt)} • {formatDuration(selectedRun.duration)} • {selectedRun.agentCount} agents
            </p>
          </div>
          <button
            onClick={() => handleDeleteClick(selectedRun.id)}
            className="flex items-center justify-center h-8 w-8 rounded-lg text-[#87867f] hover:text-red-600 hover:bg-red-50 transition-colors"
            title="Delete this run"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="px-6 py-2 border-b border-[#e8e6dc] bg-white">
          <div className="flex gap-1 rounded-lg bg-[#f0eee6] p-0.5 w-fit border border-[#e8e6dc]">
            <button onClick={() => setDetailTab("preview")} className={`rounded-md px-4 py-1.5 text-[11px] font-medium transition-all ${detailTab === "preview" ? "bg-white text-[#141413] shadow-sm" : "text-[#87867f] hover:text-[#5e5d59]"}`}>
              <Eye className="h-3 w-3 inline mr-1" />Preview
            </button>
            <button onClick={() => setDetailTab("files")} className={`rounded-md px-4 py-1.5 text-[11px] font-medium transition-all ${detailTab === "files" ? "bg-white text-[#141413] shadow-sm" : "text-[#87867f] hover:text-[#5e5d59]"}`}>
              <Download className="h-3 w-3 inline mr-1" />Files
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 overflow-auto">
          {loadingDetail ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-[#87867f]" />
            </div>
          ) : !selectedOutput ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-[#87867f]">No output available for this run.</p>
            </div>
          ) : detailTab === "preview" ? (
            <div className="h-full">
              {isUserStory && <UserStoryPreview content={selectedOutput} />}
              {isPpt && <PPTPreview content={selectedOutput} />}
              {isPrototype && <PrototypePreview content={selectedOutput} />}
            </div>
          ) : (
            <FilesTab
              workflowType={workflowType}
              userStoryContent={isUserStory ? selectedOutput : undefined}
              pptContent={isPpt ? selectedOutput : undefined}
              prototypeContent={isPrototype ? selectedOutput : undefined}
            />
          )}
        </div>

        {/* Delete Confirmation Modal */}
        <AnimatePresence>
          {deleteConfirmId && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
              onClick={handleDeleteCancel}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 10 }}
                onClick={(e) => e.stopPropagation()}
                className="bg-white rounded-2xl border border-[#e8e6dc] shadow-xl p-6 max-w-sm w-full mx-4"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50">
                    <Trash2 className="h-5 w-5 text-red-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-[#141413]">Delete Workflow</h3>
                    <p className="text-[11px] text-[#87867f]">This action cannot be undone</p>
                  </div>
                </div>
                <p className="text-[12px] text-[#5e5d59] mb-5">
                  Are you sure you want to delete this workflow run? The preview and all associated data will be permanently removed.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteCancel}
                    className="flex-1 rounded-lg border border-[#e8e6dc] px-4 py-2.5 text-[12px] font-medium text-[#5e5d59] hover:bg-[#f0eee6] transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDeleteConfirm}
                    className="flex-1 rounded-lg bg-red-500 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-red-600 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  // List view
  return (
    <div className="h-full flex flex-col bg-[#f5f4ed]">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e6dc] bg-white">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-[#f0eee6] transition-colors">
            <ArrowLeft className="h-4 w-4 text-[#5e5d59]" />
          </button>
          <div>
            <h1 className="text-base font-bold text-[#141413] flex items-center gap-2">
              <History className="h-4 w-4 text-[#c96442]" />
              Workflow History
            </h1>
            <p className="text-[11px] text-[#87867f] mt-0.5">{runs.length} total runs</p>
          </div>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-[#87867f]" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="text-[11px] rounded-lg border border-[#e8e6dc] bg-white px-3 py-1.5 text-[#141413] focus:outline-none focus:border-[#c96442]/40"
          >
            <option value="all">All Types</option>
            <option value="user_stories">User Stories</option>
            <option value="ppt">Presentation</option>
            <option value="prototype">Prototype</option>
            <option value="validate_pitch">Pitch Deck</option>
            <option value="app_builder">App Builder</option>
            <option value="reverse_engineer">Reverse Engineer</option>
          </select>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="h-6 w-6 animate-spin text-[#87867f]" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40">
            <History className="h-8 w-8 text-[#c9c8c3] mb-3" />
            <p className="text-sm text-[#87867f]">No workflow runs yet</p>
            <p className="text-[11px] text-[#c9c8c3] mt-1">Run a pipeline from the home page to see history here</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredRuns.map((run, idx) => {
              const meta = TYPE_META[run.type] || TYPE_META.custom;
              const Icon = meta.icon;
              return (
                <motion.div
                  key={run.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: idx * 0.03 }}
                  onClick={() => handleSelectRun(run)}
                  className="flex items-center gap-4 rounded-xl border border-[#e8e6dc] bg-white p-4 cursor-pointer hover:border-[#c96442]/30 hover:shadow-md hover:shadow-black/5 transition-all"
                >
                  {/* Type icon */}
                  <div className={`flex h-10 w-10 items-center justify-center rounded-xl flex-shrink-0 ${meta.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[12px] font-semibold text-[#141413] truncate">{run.title}</h3>
                    <div className="flex items-center gap-3 mt-1">
                      <span className={`text-[9px] font-medium rounded-full px-2 py-0.5 ${meta.color}`}>{meta.label}</span>
                      <span className="text-[9px] text-[#87867f] flex items-center gap-1">
                        <Clock className="h-2.5 w-2.5" />
                        {formatDate(run.createdAt)}
                      </span>
                      {run.duration && (
                        <span className="text-[9px] text-[#87867f]">{formatDuration(run.duration)}</span>
                      )}
                    </div>
                  </div>

                  {/* Status + Delete */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {run.status === "completed" ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                    ) : run.status === "failed" ? (
                      <XCircle className="h-5 w-5 text-red-400" />
                    ) : (
                      <Loader2 className="h-5 w-5 text-amber-400 animate-spin" />
                    )}
                    <button
                      onClick={(e) => handleDeleteClick(run.id, e)}
                      className="flex items-center justify-center h-7 w-7 rounded-lg text-[#c9c8c3] hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      <AnimatePresence>
        {deleteConfirmId && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
            onClick={handleDeleteCancel}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white rounded-2xl border border-[#e8e6dc] shadow-xl p-6 max-w-sm w-full mx-4"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50">
                  <Trash2 className="h-5 w-5 text-red-500" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#141413]">Delete Workflow</h3>
                  <p className="text-[11px] text-[#87867f]">This action cannot be undone</p>
                </div>
              </div>
              <p className="text-[12px] text-[#5e5d59] mb-5">
                Are you sure you want to delete this workflow run? The preview and all associated data will be permanently removed.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleDeleteCancel}
                  className="flex-1 rounded-lg border border-[#e8e6dc] px-4 py-2.5 text-[12px] font-medium text-[#5e5d59] hover:bg-[#f0eee6] transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteConfirm}
                  className="flex-1 rounded-lg bg-red-500 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-red-600 transition-colors"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
