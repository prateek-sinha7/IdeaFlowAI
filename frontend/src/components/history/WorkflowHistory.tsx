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
  Trash2,
  Filter,
} from "lucide-react";
import { getToken, getWorkflows, getWorkflow, deleteWorkflow } from "@/lib/api";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { MarkdownPreview } from "@/components/preview/MarkdownPreview";
import { FilesTab } from "@/components/results/FilesTab";
import type { WorkflowRun, WorkflowType } from "@/types/index";

interface WorkflowHistoryProps {
  onBack: () => void;
}

const TYPE_META: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  user_stories: { icon: FileText, label: "User Stories", color: "text-gray-600 bg-gray-100" },
  ppt: { icon: Presentation, label: "Presentation", color: "text-gray-600 bg-gray-100" },
  prototype: { icon: Layout, label: "Prototype", color: "text-gray-600 bg-gray-100" },
  app_builder: { icon: Layout, label: "App Builder", color: "text-gray-600 bg-gray-100" },
  reverse_engineer: { icon: FileText, label: "Reverse Engineer", color: "text-gray-600 bg-gray-100" },
  custom: { icon: FileText, label: "Custom", color: "text-gray-600 bg-gray-100" },
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

    // If output already available from list, use it
    if (run.output && run.output.length > 0) {
      setSelectedOutput(run.output);
      return;
    }

    // Otherwise fetch full detail from API
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
    const isUserStory = workflowType === "user_stories";
    const isMarkdown = workflowType === "app_builder" || workflowType === "reverse_engineer" || workflowType === "custom";
    const isPpt = workflowType === "ppt";
    const isPrototype = workflowType === "prototype";

    // Parse agent outputs if available
    let agentOutputs: { agent_id: string; name: string; role: string; icon: string; output: string; duration: number | null }[] = [];
    if (selectedRun.agentOutputs) {
      try {
        agentOutputs = typeof selectedRun.agentOutputs === "string" ? JSON.parse(selectedRun.agentOutputs) : selectedRun.agentOutputs;
      } catch { /* ignore */ }
    }

    return (
      <div className="h-full flex bg-gray-50">
        {/* Left Panel — Back button + Agents */}
        <div className="w-full md:w-[280px] lg:w-[300px] flex-shrink-0 h-full border-r border-gray-200 overflow-y-auto bg-white flex flex-col">
          {/* Header with back + title */}
          <div className="px-3 py-2.5 border-b border-gray-200 flex-shrink-0">
            <div className="flex items-center gap-2">
              <button onClick={handleBack} className="flex items-center justify-center h-6 w-6 rounded-lg hover:bg-gray-100 transition-colors flex-shrink-0">
                <ArrowLeft className="h-3 w-3 text-gray-500" />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[7px] font-semibold ${meta.color}`}>
                    <Icon className="h-2 w-2" />{meta.label}
                  </span>
                  <span className="text-[8px] text-gray-400">{formatDuration(selectedRun.duration)}</span>
                </div>
                <p className="text-[10px] font-semibold text-gray-900 truncate mt-0.5">{selectedRun.title}</p>
              </div>
            </div>
          </div>

          {/* Agent list */}
          <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
            {agentOutputs.length > 0 ? agentOutputs.map((agent, idx) => (
              <details key={idx} className="rounded-lg border border-gray-200 bg-gray-50 overflow-hidden">
                <summary className="flex items-center gap-2 px-2.5 py-2 cursor-pointer hover:bg-gray-100 transition-colors">
                  <div className="flex h-5 w-5 items-center justify-center rounded bg-gray-200 flex-shrink-0">
                    <FileText className="h-3 w-3 text-gray-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] font-medium text-gray-900 truncate">{agent.name}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {agent.duration && <span className="text-[8px] text-gray-400">{agent.duration.toFixed(1)}s</span>}
                    <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                  </div>
                </summary>
                <div className="px-2.5 pb-2 border-t border-gray-200">
                  <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed mt-1.5 max-h-[120px] overflow-y-auto font-mono bg-white rounded p-2 border border-gray-200">
                    {agent.output?.slice(0, 1500) || "No output"}
                    {agent.output && agent.output.length > 1500 && "\n...[truncated]"}
                  </pre>
                </div>
              </details>
            )) : (
              <p className="text-[10px] text-gray-400 text-center py-4">No agent data available</p>
            )}
          </div>
        </div>

        {/* Right Panel — Preview + Files (full height, no top header) */}
        <div className="flex-1 min-w-0 h-full flex flex-col">
          {/* Tabs */}
          <div className="px-4 py-1.5 border-b border-gray-200 bg-white flex-shrink-0">
            <div className="flex gap-0.5 bg-gray-100 rounded-md p-0.5 w-fit">
              <button onClick={() => setDetailTab("preview")} className={`rounded px-3 py-1 text-[10px] font-medium transition-all ${detailTab === "preview" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}>
                Preview
              </button>
              <button onClick={() => setDetailTab("files")} className={`rounded px-3 py-1 text-[10px] font-medium transition-all ${detailTab === "files" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}>
                Files
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 min-h-0 overflow-auto">
            {loadingDetail ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
              </div>
            ) : !selectedOutput ? (
              <div className="flex flex-col items-center justify-center h-full gap-2">
                <FileText className="h-8 w-8 text-gray-300" />
                <p className="text-sm text-gray-400">No preview available</p>
                <p className="text-[10px] text-gray-300 text-center max-w-[200px]">Check agent outputs on the left panel.</p>
              </div>
            ) : detailTab === "preview" ? (
              <div className="h-full">
                {isUserStory && <UserStoryPreview content={selectedOutput} />}
                {isMarkdown && <MarkdownPreview content={selectedOutput} />}
                {isPpt && <PPTPreview content={selectedOutput} />}
                {isPrototype && <PrototypePreview content={selectedOutput} />}
              </div>
            ) : (
              <FilesTab
                workflowType={workflowType}
                userStoryContent={(isUserStory || isMarkdown) ? selectedOutput || undefined : undefined}
                pptContent={isPpt ? selectedOutput || undefined : undefined}
                prototypeContent={isPrototype ? selectedOutput || undefined : undefined}
              />
            )}
          </div>
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
                className="bg-white rounded-xl border border-gray-200 shadow-xl p-6 max-w-sm w-full mx-4"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                    <Trash2 className="h-5 w-5 text-gray-600" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Delete Workflow</h3>
                    <p className="text-[11px] text-gray-500">This action cannot be undone</p>
                  </div>
                </div>
                <p className="text-[12px] text-gray-600 mb-5">
                  Are you sure you want to delete this workflow run? The preview and all associated data will be permanently removed.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleDeleteCancel}
                    className="flex-1 rounded-lg border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDeleteConfirm}
                    className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors"
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
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100 transition-colors">
            <ArrowLeft className="h-4 w-4 text-gray-500" />
          </button>
          <div>
            <h1 className="text-base font-semibold text-gray-900 flex items-center gap-2">
              <History className="h-4 w-4 text-blue-600" />
              Workflow History
            </h1>
            <p className="text-[11px] text-gray-500 mt-0.5">{runs.length} total runs</p>
          </div>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-gray-400" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="text-[11px] rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-gray-900 focus:outline-none focus:border-blue-400 transition-colors"
          >
            <option value="all">All Types</option>
            <option value="user_stories">User Stories</option>
            <option value="ppt">Presentation</option>
            <option value="prototype">Prototype</option>
            <option value="app_builder">App Builder</option>
            <option value="reverse_engineer">Reverse Engineer</option>
          </select>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40">
            <History className="h-8 w-8 text-gray-300 mb-3" />
            <p className="text-sm text-gray-400">No workflow runs yet</p>
            <p className="text-[11px] text-gray-300 mt-1">Run a pipeline from the home page to see history here</p>
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
                  className="flex items-center gap-4 rounded-lg border border-gray-200 bg-white p-4 cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all"
                >
                  {/* Type icon */}
                  <div className={`flex h-10 w-10 items-center justify-center rounded-lg flex-shrink-0 ${meta.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[12px] font-semibold text-gray-900 truncate">{run.title}</h3>
                    <div className="flex items-center gap-3 mt-1">
                      <span className={`text-[9px] font-medium rounded-full px-2 py-0.5 ${meta.color}`}>{meta.label}</span>
                      <span className="text-[9px] text-gray-400 flex items-center gap-1">
                        <Clock className="h-2.5 w-2.5" />
                        {formatDate(run.createdAt)}
                      </span>
                      {run.duration && (
                        <span className="text-[9px] text-gray-400">{formatDuration(run.duration)}</span>
                      )}
                    </div>
                  </div>

                  {/* Status + Delete */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {run.status === "completed" ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                    ) : run.status === "failed" ? (
                      <XCircle className="h-5 w-5 text-gray-400" />
                    ) : (
                      <Loader2 className="h-5 w-5 text-gray-400 animate-spin" />
                    )}
                    <button
                      onClick={(e) => handleDeleteClick(run.id, e)}
                      className="flex items-center justify-center h-7 w-7 rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors"
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
              className="bg-white rounded-xl border border-gray-200 shadow-xl p-6 max-w-sm w-full mx-4"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-100">
                  <Trash2 className="h-5 w-5 text-gray-600" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Delete Workflow</h3>
                  <p className="text-[11px] text-gray-500">This action cannot be undone</p>
                </div>
              </div>
              <p className="text-[12px] text-gray-600 mb-5">
                Are you sure you want to delete this workflow run? The preview and all associated data will be permanently removed.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={handleDeleteCancel}
                  className="flex-1 rounded-lg border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteConfirm}
                  className="flex-1 rounded-lg bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors"
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
