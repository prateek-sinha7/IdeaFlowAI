"use client";

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  FileText, Presentation, Layout,
  Loader2, ArrowLeft, Trash2, ChevronRight,
  Search, Sparkles, ArrowRight,
  Download, ExternalLink, RefreshCw, X, Send,
} from "lucide-react";
import { getToken, getWorkflows, getWorkflow, deleteWorkflow, getRunFamily } from "@/lib/api";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { MarkdownPreview } from "@/components/preview/MarkdownPreview";
import { AppBuilderPreview, type ParsedFile } from "@/components/preview/AppBuilderPreview";
// ISS-017 (gap-fix) — the SAME terminal-failure affordance the live PreviewPanel
// path renders, reused here so the history-reopen detail view shows it too
// (instead of the neutral "No preview available") for a terminal-empty
// failed/cancelled/degraded run. ONE component → live + history cannot drift.
import { DegradedRunAffordance } from "@/components/preview/PreviewPanel";
import { FilesTab } from "@/components/results/FilesTab";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { AuditTab } from "@/components/results/AuditTab";
import type { WorkflowRun, WorkflowType, AgentRunState, RunFamily } from "@/types/index";
import { resolveReopenMimetype } from "@/types/index";
import { availableChainTargets } from "@/lib/workflowChaining";
// ISS-017 (gap-fix) — SHARED failed-agent-id parser (no dual-impl). The IDENTICAL
// parser app/dashboard/page.tsx uses for the live-reopen path; lists the real
// failed agents from the persisted run `error`.
// ISS-024 (16 review IN-02) — id→name resolution for the failed-agents list,
// SHARED with the live PreviewPanel path (no dual-impl). The history-reopen
// source for names is the persisted run detail's agentOutputs ({agent_id,name}).
import { parseFailedAgentIds, buildAgentNameById } from "@/lib/parseFailedAgents";
// Revision Families (B2 / D3): client-side grouping by rootRunId + the family
// root card (REUSE-FIRST — WORKSTREAM-B-UI-SPEC.md Surface 1).
import { groupRunsByFamily, FamilyGroupCard, VersionTimeline, baseWorkflowType } from "./RevisionFamilyView";

interface WorkflowHistoryProps {
  onBack: () => void;
  onChainPipeline?: (run: WorkflowRun, nextType: WorkflowType) => void;
  // Revision Families (B1): each revise callback gains a required sourceRunId
  // (selectedRun.id) so the launched revision links its parent run — history
  // revisions previously sent no parent and produced orphan runs.
  onReviseUserStory?: (instruction: string, content: string, sourceRunId: string) => void;
  onRevisePpt?: (instruction: string, content: string, sourceRunId: string) => void;
  onRevisePrototype?: (instruction: string, content: string, sourceRunId: string) => void;
  onReviseAppBuilder?: (instruction: string, content: string, sourceRunId: string) => void;
}

// ─── Parse all filename: blocks from agent outputs for the IDE preview ────────
const CODE_PRODUCING_AGENT_IDS = new Set([
  "app-code-generator", "app-feature-implementation",
  "app-infra-generator", "app-test-implementation",
]);

function parseFilesForIDE(markdown: string): ParsedFile[] {
  const files: ParsedFile[] = [];
  const seen = new Set<string>();
  const langMap: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", json: "json", md: "markdown", yml: "yaml", yaml: "yaml",
    css: "css", html: "html", sh: "bash", sql: "sql", dockerfile: "dockerfile",
    env: "bash", toml: "toml", prisma: "typescript", rs: "rust", go: "go",
    gitignore: "bash", lock: "plaintext", txt: "plaintext",
    java: "java", cs: "csharp", rb: "ruby", kt: "kotlin", xml: "xml",
  };
  const add = (path: string, content: string) => {
    path = path.trim();
    if (!path || !content.trim() || seen.has(path)) return;
    const name = path.split("/").pop() || path;
    if (!name.includes(".") && !/^(Dockerfile|Makefile|Procfile)$/i.test(name)) return;
    seen.add(path);
    const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
    files.push({ path, name, ext, content, language: langMap[ext] || "plaintext" });
  };
  // Format 1: ```filename: path\n[content]\n```
  const r1 = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = r1.exec(markdown)) !== null) add(m[1], m[2]);
  // Format 2: ### path/to/file.ext\n```lang\n[content]\n```
  const r2 = /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = r2.exec(markdown)) !== null) add(m[1], m[2]);
  // Format 3: **`path/to/file.ext`** followed by ```
  const r3 = /\*\*`?([\w./\-@][^\n`*]*\.\w+)`?\*\*\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = r3.exec(markdown)) !== null) add(m[1], m[2]);
  return files;
}

const TYPE_META: Record<string, { icon: typeof FileText; label: string }> = {
  user_stories: { icon: FileText, label: "User Stories" },
  user_stories_revision: { icon: FileText, label: "User Stories (Revised)" },
  ppt: { icon: Presentation, label: "Presentation" },
  ppt_revision: { icon: Presentation, label: "Presentation (Revised)" },
  od_ppt: { icon: Presentation, label: "Presentation" },
  od_ppt_revision: { icon: Presentation, label: "Presentation (Revised)" },
  prototype: { icon: Layout, label: "Prototype" },
  prototype_revision: { icon: Layout, label: "Prototype (Revised)" },
  od_prototype: { icon: Layout, label: "Prototype" },
  app_builder: { icon: Layout, label: "App Builder" },
  app_builder_revision: { icon: Layout, label: "App Builder (Revised)" },
  custom: { icon: FileText, label: "Custom" },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function WorkflowHistory({ onBack, onChainPipeline, onReviseUserStory, onRevisePpt, onRevisePrototype, onReviseAppBuilder }: WorkflowHistoryProps) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  // Revision Families (B2 / D4): the open run's family (root + ordered members),
  // fetched on detail open and keyed on the STABLE rootRunId so switching
  // versions does NOT refetch the family.
  const [family, setFamily] = useState<RunFamily | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [detailTab, setDetailTab] = useState<"preview" | "files" | "thinking" | "audit">("preview");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  // Revision Families (B2 / D3): which family roots are expanded in the list,
  // keyed by rootRunId (UI-SPEC Surface 1 — chevron toggles expansion).
  const [expandedFamilies, setExpandedFamilies] = useState<Set<string>>(new Set());
  // KAN-84: revision moved from thin right-panel bar to left-panel next-steps
  const [reviseOpen, setReviseOpen] = useState(false);
  const [revisionText, setRevisionText] = useState("");
  const revisionRef = useRef<HTMLTextAreaElement>(null);

  // Focus revision textarea when opened
  useEffect(() => {
    if (reviseOpen && revisionRef.current) revisionRef.current.focus();
  }, [reviseOpen]);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getWorkflows(token, { limit: 100 })
      .then((data) => setRuns(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSelectRun = useCallback(async (run: WorkflowRun) => {
    setSelectedRun(run);
    setSelectedOutput(null);
    setDetailTab("preview");
    if (run.output && run.output.length > 0) {
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
    } catch {}
    finally { setLoadingDetail(false); }
  }, []);

  // Revision Families (B2 / D4): fetch the open run's family. Keyed on the STABLE
  // rootRunId (same for every member) so switching versions does NOT refetch;
  // cancellable so a fast back-and-forth cannot land a stale family.
  useEffect(() => {
    if (!selectedRun) { setFamily(null); return; }
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    getRunFamily(token, selectedRun.rootRunId)
      .then((f) => { if (!cancelled) setFamily(f); })
      .catch((err) => {
        if (!cancelled) {
          // Dev-observability only: log the swallowed failure, then keep the
          // graceful degrade (the version affordance simply hides). No UI added.
          console.warn("[revision-family] family fetch failed", err);
          setFamily(null);
        }
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRun?.rootRunId]);

  // Revision Families (B2 / D4): load a chosen version into the SAME detail
  // surface (mirrors the fetch half of handleSelectRun, but keyed by id and
  // tab-preserving so a version switch feels like one workflow, not navigation).
  const handleSelectVersion = useCallback(async (memberId: string) => {
    const token = getToken();
    if (!token) return;
    setLoadingDetail(true);
    try {
      const full = await getWorkflow(token, memberId);
      setSelectedRun(full);
      setSelectedOutput(full.output || null);
    } catch (err) {
      // Dev-observability only: log the swallowed failure; behavior unchanged.
      console.warn("[revision-family] version fetch failed", err);
    }
    finally { setLoadingDetail(false); }
  }, []);

  const handleDeleteClick = useCallback((runId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setOpenMenuId(null);
    setDeleteConfirmId(runId);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteConfirmId) return;
    const token = getToken();
    if (!token) return;
    setDeleteError(null);
    try {
      await deleteWorkflow(token, deleteConfirmId);
      setRuns((prev) => prev.filter((r) => r.id !== deleteConfirmId));
      if (selectedRun?.id === deleteConfirmId) { setSelectedRun(null); setSelectedOutput(null); }
      setDeleteConfirmId(null);
    } catch {
      setDeleteError("Failed to delete run. Please try again.");
    }
  }, [deleteConfirmId, selectedRun]);

  // Revision Families (B2): the per-run filter predicate, extracted so the
  // grouped list can match a family if ANY member matches (UI-SPEC Surface 1).
  // Same normalize-then-match logic as before (od_prototype→prototype, od_ppt→
  // ppt, strip _revision; search on title) — via the SHARED baseWorkflowType.
  const matchesFilter = useCallback((r: WorkflowRun) => {
    const baseType = baseWorkflowType(r.type);
    const matchType = filterType === "all" || baseType === filterType || r.type === filterType;
    const matchSearch = !searchQuery || (r.title || "").toLowerCase().includes(searchQuery.toLowerCase());
    return matchType && matchSearch;
  }, [filterType, searchQuery]);

  const toggleFamily = useCallback((rootRunId: string) => {
    setExpandedFamilies((prev) => {
      const next = new Set(prev);
      if (next.has(rootRunId)) next.delete(rootRunId);
      else next.add(rootRunId);
      return next;
    });
  }, []);

  // ─── Derived values for detail view — must be computed unconditionally ────
  // (Rules of Hooks: useMemo cannot be inside an if block)
  const detailWorkflowType = (selectedRun?.type ?? "custom") as WorkflowType;
  const detailIsAppBuilder = detailWorkflowType === "app_builder" || detailWorkflowType === "app_builder_revision";

  const detailAgentOutputs = useMemo<{ agent_id: string; name: string; role: string; icon: string; output: string; duration: number | null; input_tokens?: number; output_tokens?: number; total_tokens?: number }[]>(() => {
    if (!selectedRun?.agentOutputs) return [];
    try {
      const raw = selectedRun.agentOutputs;
      const parsed = typeof raw === "string" ? JSON.parse(raw) : (raw as unknown as Record<string, unknown>[]);
      // Deduplicate by agent_id — for build agents that run multiple times,
      // keep the first unique entry and aggregate duration + tokens.
      const seen = new Map<string, number>(); // agent_id → index in result
      const deduped: typeof parsed = [];
      for (const a of parsed) {
        const aid = (a as Record<string, unknown>).agent_id as string | undefined;
        // Skip orphan entries with no agent_id (e.g. a trailing agent_complete
        // appended after the collector was reset). They have no name either, so
        // they render with key={undefined} and crash AgentTimelineCard at name.split().
        if (!aid) continue;
        if (seen.has(aid)) {
          // Aggregate duration and tokens for repeated agents
          const existing = deduped[seen.get(aid)!] as Record<string, unknown>;
          const existingDur = (existing.duration as number | null) ?? 0;
          const newDur = (a.duration as number | null) ?? 0;
          existing.duration = existingDur + newDur;
          existing.input_tokens = ((existing.input_tokens as number) || 0) + ((a.input_tokens as number) || 0);
          existing.output_tokens = ((existing.output_tokens as number) || 0) + ((a.output_tokens as number) || 0);
          existing.total_tokens = ((existing.total_tokens as number) || 0) + ((a.total_tokens as number) || 0);
          // Keep the last output (most recent/final result)
          if ((a.output as string)?.trim()) existing.output = a.output;
        } else {
          seen.set(aid, deduped.length);
          deduped.push({ ...a });
        }
      }
      return deduped as typeof parsed;
    } catch { return []; }
  }, [selectedRun]);

  const ideFiles = useMemo<ParsedFile[]>(() => {
    if (!detailIsAppBuilder) return [];
    const seen = new Set<string>();
    const merged: ParsedFile[] = [];
    const add = (parsed: ParsedFile[]) => {
      for (const f of parsed) { if (!seen.has(f.path)) { seen.add(f.path); merged.push(f); } }
    };
    for (const a of detailAgentOutputs) {
      if (CODE_PRODUCING_AGENT_IDS.has(a.agent_id) && a.output?.trim()) {
        add(parseFilesForIDE(a.output));
      }
    }
    if (selectedOutput) add(parseFilesForIDE(selectedOutput));
    return merged;
  }, [detailIsAppBuilder, detailAgentOutputs, selectedOutput]);

  const thinkingAgents = useMemo<AgentRunState[]>(() => {
    return detailAgentOutputs.map((a, idx) => ({
      id: a.agent_id,
      name: a.name,
      role: a.role,
      icon: a.icon || "",
      status: "done" as const,
      output: a.output || "",
      thinking: "",
      duration: a.duration,
      error: null,
      index: idx,
      // Thinking tab fields from persisted agent_outputs (Phase 3)
      inputPrompt: (a as Record<string, unknown>).input_prompt as string | undefined,
      contextSources: (a as Record<string, unknown>).context_sources as import("@/types/index").ContextSource[] | undefined,
      toolCalls: (a as Record<string, unknown>).tool_calls as import("@/types/index").ToolCallEntry[] | undefined,
      thinkingText: (a as Record<string, unknown>).thinking_text as string | undefined,
    }));
  }, [detailAgentOutputs]);

  const ideProjectName = useMemo(() => {
    const arch = detailAgentOutputs.find(a => a.agent_id === "material-analyzer");
    const src = arch?.output || selectedOutput || "";
    const h = src.match(/^#\s+(.+)/m);
    return h ? h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().slice(0, 40) : (selectedRun?.title || "Generated App");
  }, [detailAgentOutputs, selectedOutput, selectedRun?.title]);

  // ─── DETAIL VIEW ───────────────────────────────────────────────────────────
  if (selectedRun) {
    const meta = TYPE_META[selectedRun.type] || TYPE_META.custom;
    const Icon = meta.icon;
    const workflowType = selectedRun.type as WorkflowType;
    const isUserStory = workflowType === "user_stories" || workflowType === "user_stories_revision";
    const isAppBuilder = detailIsAppBuilder;
    const isPpt = workflowType === "ppt" || workflowType === "ppt_revision" || workflowType === "od_ppt" || workflowType === "od_ppt_revision";
    const isPrototype = workflowType === "prototype" || workflowType === "prototype_revision" || workflowType === "od_prototype";
    // ─── ISS-021 (18-03) — 2nd facet: the reopen generic fallback ─────────────
    // The OLD `isMarkdown = isCustom` swallowed HTML deliverables into
    // MarkdownPreview (escaped HTML). Replace it with a structural "no known
    // branch matched" flag so `custom` AND any unknown selectedRun.type fall
    // into a mimetype-dispatched generic path. UXFIX-02 (22-03): the deliverable
    // mimetype PREFERS the persisted `deliverableMimetype` on the run row (so a
    // binary deliverable, e.g. application/zip, re-renders faithfully), and falls
    // back to the deriveDeliverableMimetype text heuristic only for legacy NULL
    // rows — via the SHARED resolveReopenMimetype helper, the IDENTICAL rule
    // page.tsx's reopen block applies, so the two reopen surfaces cannot diverge.
    // SC-001: never a workflow-name check.
    const isGeneric = !isUserStory && !isAppBuilder && !isPpt && !isPrototype;
    const genericMimetype = isGeneric
      ? resolveReopenMimetype(selectedRun.deliverableMimetype, selectedOutput)
      : undefined;
    const isGenericHtml = isGeneric && genericMimetype === "text/html";
    // WR-02 (18 review fix): a serialized-sandbox bundle deliverable now derives
    // to application/zip (not text/markdown), so route it to the file-bundle view
    // — matching the live GenericDeliverablePreview dispatch — instead of a flat
    // MarkdownPreview / `.md` download. Markdown is the residual case.
    const isGenericBundle = isGeneric && genericMimetype === "application/zip";
    const isGenericMarkdown = isGeneric && !isGenericHtml && !isGenericBundle;
    const genericBundleFiles = isGenericBundle && selectedOutput ? parseFilesForIDE(selectedOutput) : [];
    const agentOutputs = detailAgentOutputs;

    // ─── ISS-017 (gap-fix) — history-reopen terminal-failure affordance ───────
    // A reopened run that ended failed/cancelled/degraded WITH no usable content
    // must show the SAME DegradedRunAffordance the live PreviewPanel path renders,
    // not the neutral "No preview available". This is the history-reopen half of
    // SC3 (CONTEXT A2: affordance on BOTH live and history-reopen) — the surface
    // users actually reach (WorkflowHistory at mainView="history").
    //
    // STRICTLY server-status-gated: keyed on the PERSISTED `selectedRun.status`,
    // never a client `empty==failed` guess (the REJECTED hack — it re-creates the
    // IN-03 FE-vs-DB disagreement and would mislabel a legitimately-empty
    // completed run). It fires only inside the existing `!selectedOutput` neutral
    // branch, so a terminal run WITH content always renders the content.
    const reopenTerminalFailure =
      selectedRun.status === "failed" ||
      selectedRun.status === "cancelled" ||
      selectedRun.status === "degraded";
    // IN-03 (16 review): a deliberate user cancel reads "cancelled", not "failed".
    const reopenCancelled = selectedRun.status === "cancelled";
    // IN-01 (16 review): list the real failed-agent ids parsed from the persisted
    // run error (shared parser); omitted when the marker is absent.
    const reopenFailedAgents = parseFailedAgentIds(selectedRun.error);
    // ISS-024 (16 review IN-02): resolve those ids → human names. The history
    // surface's name source is the persisted agentOutputs ({agent_id,name}); map
    // it into the {id,name} shape the SHARED resolver expects. Unknown ids fall
    // back to the raw id inside DegradedRunAffordance, so older runs whose error
    // names an agent absent from agentOutputs still render the id (never blank).
    const reopenAgentNameById = buildAgentNameById(
      detailAgentOutputs.map((a) => ({ id: a.agent_id, name: a.name })),
    );

    return (
      <div className="h-full flex" style={{ background: "#f5f5f0" }}>
        {/* Left sidebar — white panel */}
        <div className="w-[260px] flex-shrink-0 h-full border-r border-gray-200 flex flex-col bg-white min-h-0">
          {/* Back + run info */}
          <div className="px-5 pt-5 pb-4 border-b border-gray-100">
            <button
              onClick={() => { setSelectedRun(null); setSelectedOutput(null); }}
              className="flex items-center gap-1.5 text-[11px] text-gray-400 hover:text-gray-700 transition-colors mb-4"
            >
              <ArrowLeft className="h-3.5 w-3.5" /> Back to history
            </button>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center flex-shrink-0">
                <Icon className="h-4 w-4 text-gray-500" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-widest">{meta.label}</p>
              </div>
              {selectedRun.status === "completed" && (
                <span className="text-[9px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-100 px-1.5 py-0.5 rounded-full flex-shrink-0">Done</span>
              )}
            </div>
            <h2 className="text-[13px] font-semibold text-gray-900 leading-snug mb-1.5">{selectedRun.title}</h2>
            <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
              <span>{formatDate(selectedRun.createdAt)}</span>
              {selectedRun.duration && <><span>·</span><span>{formatDuration(selectedRun.duration)}</span></>}
            </div>
          </div>

          {/* Token usage — single compact line */}
          {selectedRun.tokenUsage && selectedRun.tokenUsage.total_tokens > 0 && (
            <div className="px-5 py-2 border-b border-gray-100 flex items-center gap-1.5 flex-wrap">
              {(() => {
                const t = selectedRun.tokenUsage!;
                const input = t.total_input_tokens;
                const output = t.total_output_tokens;
                const total = t.total_tokens;
                const fmt = (n: number) => n >= 1_000_000 ? `${(n/1_000_000).toFixed(1)}M` : n >= 1_000 ? `${(n/1_000).toFixed(1)}K` : String(n);
                return (
                  <>
                    <span className="text-[9px]">⚡</span>
                    <span className="text-[10px] font-bold text-gray-900">{fmt(total)} total</span>
                    <span className="text-[10px] text-gray-400">·</span>
                    <span className="text-[10px] text-gray-500">{fmt(input)} input</span>
                    <span className="text-[10px] text-gray-400">·</span>
                    <span className="text-[10px] text-gray-500">{fmt(output)} output</span>
                  </>
                );
              })()}
            </div>
          )}

          {/* Agents list */}
          <div className="flex-1 overflow-y-auto min-h-0 px-3 py-3 space-y-2">
            <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-widest px-2 mb-2">
              {agentOutputs.length} Agents
            </p>
            {agentOutputs.length > 0 ? agentOutputs.map((agent, idx) => {
              const iconStyles = [
                { bg: "#E8EDF5", text: "#1B2A4A" },
                { bg: "#F0EDE8", text: "#5C4A2A" },
                { bg: "#EAF0EA", text: "#2A5C2A" },
                { bg: "#F0E8EE", text: "#5C2A4A" },
                { bg: "#E8EEF0", text: "#2A4A5C" },
                { bg: "#F0EEE8", text: "#5C5A2A" },
              ];
              const iconStyle = iconStyles[idx % iconStyles.length];
              const initials = (agent.name || "Agent").split(" ").map((w: string) => w[0]).slice(0, 2).join("").toUpperCase();
              return (
                <details key={idx} className="group rounded-xl border border-gray-100 bg-white overflow-hidden">
                  <summary className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors list-none">
                    {/* Icon */}
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
                      style={{ background: iconStyle.bg, color: iconStyle.text }}
                    >
                      {initials}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-[12px] font-semibold text-gray-900 leading-tight">{agent.name}</p>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {agent.duration != null && (
                            <span className="text-[9px] text-gray-400">{agent.duration.toFixed(0)}s</span>
                          )}
                          {(agent as Record<string, unknown>).total_tokens ? (
                            <span className="text-[9px] text-gray-400">
                              {(((agent as Record<string, unknown>).total_tokens as number) / 1000).toFixed(1)}k tok
                            </span>
                          ) : null}
                          <span className="text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                            DONE
                          </span>
                        </div>
                      </div>
                      <p className="text-[10px] text-gray-400 mt-0.5">{agent.role}</p>
                    </div>
                    <ChevronRight className="h-3 w-3 text-gray-300 group-open:rotate-90 transition-transform flex-shrink-0" />
                  </summary>
                  <div className="border-t border-gray-100 overflow-hidden" style={{ background: "#f7f6f3" }}>
                    <pre className="text-[9px] text-gray-500 whitespace-pre-wrap leading-relaxed p-3 max-h-[300px] overflow-y-auto font-mono">
                      {agent.output || "No output"}
                    </pre>
                  </div>
                </details>
              );
            }) : (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <p className="text-[11px] text-gray-400">No agent data</p>
              </div>
            )}
          </div>

          {/* Suggested next steps — always-visible footer for completed runs.
              Lets the user chain the historical output into another pipeline
              without having to re-run from the home page. Excludes the
              already-completed pipeline (incl. its `_revision` form) via
              the shared availableChainTargets() rule. */}
          {selectedRun.status === "completed" &&
           (() => {
             // Determine which revise callback applies to this run type
             const reviseCallback = (() => {
               if (!selectedOutput) return undefined;
               if (isPrototype && onRevisePrototype) return (instruction: string) => onRevisePrototype(instruction, selectedOutput, selectedRun.id);
               if (isPpt && onRevisePpt) return (instruction: string) => onRevisePpt(instruction, selectedOutput, selectedRun.id);
               if (isUserStory && onReviseUserStory) return (instruction: string) => onReviseUserStory(instruction, selectedOutput, selectedRun.id);
               if (isAppBuilder && onReviseAppBuilder) return (instruction: string) => onReviseAppBuilder(instruction, selectedOutput || "", selectedRun.id);
               return undefined;
             })();
             const reviseLabel = isPrototype ? "Revise Prototype" : isPpt ? "Revise Presentation" : isUserStory ? "Revise User Stories" : isAppBuilder ? "Revise App Blueprint" : "Revise";
             const chainOptions = onChainPipeline ? availableChainTargets(selectedRun.type as WorkflowType) : [];
             if (!reviseCallback && chainOptions.length === 0) return null;
             return (
               <div className="border-t border-gray-100 px-3 py-3 bg-gradient-to-br from-[#FAFBFF] to-[#F1F4FB] flex-shrink-0">
                 <div className="flex items-center gap-1.5 mb-2 px-1">
                   <Sparkles className="h-3 w-3 text-[#1B2A4A]" />
                   <p className="text-[9px] font-bold text-[#1B2A4A] uppercase tracking-[0.12em]">
                     Suggested next steps
                   </p>
                 </div>
                 <div className="space-y-1.5">
                   {/* KAN-84: Revision button in left sidebar */}
                   {reviseCallback && (
                     reviseOpen ? (
                       <motion.div
                         initial={{ opacity: 0, y: -4 }}
                         animate={{ opacity: 1, y: 0 }}
                         className="rounded-xl border border-[#1B2A4A]/20 bg-white overflow-hidden"
                       >
                         <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
                           <div className="flex items-center gap-1.5">
                             <RefreshCw className="h-3 w-3 text-[#1B2A4A]" />
                             <p className="text-[11px] font-semibold text-[#1B2A4A]">{reviseLabel}</p>
                           </div>
                           <button onClick={() => { setReviseOpen(false); setRevisionText(""); }} className="p-0.5 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
                             <X className="h-3.5 w-3.5" />
                           </button>
                         </div>
                         <div className="px-3 pb-3">
                           <textarea
                             ref={revisionRef}
                             value={revisionText}
                             onChange={(e) => setRevisionText(e.target.value)}
                             onKeyDown={(e) => {
                               if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && revisionText.trim()) {
                                 reviseCallback(revisionText.trim());
                                 setRevisionText(""); setReviseOpen(false);
                               }
                             }}
                             placeholder="Describe what you'd like to change..."
                             rows={3}
                             className="w-full text-[11px] text-gray-700 placeholder-gray-400 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:border-[#1B2A4A]/40 transition-colors resize-y leading-relaxed min-h-[60px]"
                           />
                           <div className="flex items-center justify-between mt-2">
                             <span className="text-[9px] text-gray-400">⌘↵ to send</span>
                             <button
                               onClick={() => { if (revisionText.trim()) { reviseCallback(revisionText.trim()); setRevisionText(""); setReviseOpen(false); } }}
                               disabled={!revisionText.trim()}
                               className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-[#1B2A4A] hover:bg-[#2a3d5e] disabled:opacity-40 rounded-lg px-3 py-1.5 transition-colors"
                             >
                               <Send className="h-3 w-3" /> Send
                             </button>
                           </div>
                         </div>
                       </motion.div>
                     ) : (
                       <button
                         onClick={() => setReviseOpen(true)}
                         className="group w-full flex items-center justify-between rounded-xl border border-[#1B2A4A]/20 bg-white hover:border-[#1B2A4A] hover:bg-[#1B2A4A] hover:shadow-md px-3 py-2 text-left transition-all"
                       >
                         <div className="min-w-0">
                           <p className="text-[11px] font-semibold text-gray-900 group-hover:text-white transition-colors">{reviseLabel}</p>
                           <p className="text-[9px] text-gray-500 group-hover:text-white/80 transition-colors leading-snug">Request changes to the output</p>
                         </div>
                         <RefreshCw className="h-3 w-3 text-[#1B2A4A] group-hover:text-white group-hover:rotate-180 transition-all flex-shrink-0 ml-2" />
                       </button>
                     )
                   )}
                   {onChainPipeline && chainOptions.map((opt) => (
                     <button
                       key={opt.type}
                       onClick={() => onChainPipeline(selectedRun, opt.type)}
                       className="group w-full flex items-center justify-between rounded-xl border border-[#1B2A4A]/20 bg-white hover:border-[#1B2A4A] hover:bg-[#1B2A4A] hover:shadow-md px-3 py-2 text-left transition-all"
                     >
                       <div className="min-w-0">
                         <p className="text-[11px] font-semibold text-gray-900 group-hover:text-white transition-colors">{opt.label}</p>
                         <p className="text-[9px] text-gray-500 group-hover:text-white/80 transition-colors leading-snug">{opt.description}</p>
                       </div>
                       <ArrowRight className="h-3 w-3 text-[#1B2A4A] group-hover:text-white group-hover:translate-x-0.5 transition-all flex-shrink-0 ml-2" />
                     </button>
                   ))}
                 </div>
               </div>
             );
           })()}
        </div>

        {/* Main content — white panel */}
        <div className="flex-1 min-w-0 h-full flex flex-col bg-white border-l border-gray-200">
          {/* Revision Families (B2 / D4): version timeline — renders only when the
              family has >=2 members. Clicking a chip loads that version here. */}
          <VersionTimeline
            family={family}
            activeRunId={selectedRun.id}
            activeInput={selectedRun.input}
            onSelectVersion={handleSelectVersion}
          />
          {/* Tabs + PPT action buttons */}
          <div className="flex items-center justify-between gap-2 px-5 py-3 border-b border-gray-100 bg-white flex-shrink-0">
            <div className="flex items-center gap-1">
              {(["preview", "files", "thinking", "audit"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setDetailTab(tab)}
                  className={`px-3 py-1.5 rounded-md text-[11px] font-medium transition-all capitalize ${
                    detailTab === tab
                      ? "bg-gray-100 text-gray-900"
                      : "text-gray-400 hover:text-gray-700"
                  }`}
                >
                  {tab === "files" ? "Files" : tab === "thinking" ? "Thinking" : tab === "audit" ? "Audit" : "Preview"}
                </button>
              ))}
            </div>

            {/* Download + Full Screen for PPT/prototype previews */}
            {detailTab === "preview" && selectedOutput && isPpt && (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => {
                    let html = selectedOutput.trim();
                    if (html.startsWith("```")) html = html.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
                    const blob = new Blob([html], { type: "text/html" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url; a.download = "presentation.html";
                    document.body.appendChild(a); a.click();
                    document.body.removeChild(a); URL.revokeObjectURL(url);
                  }}
                  className="flex items-center gap-1.5 rounded-md bg-[#1B2A4A] px-2.5 py-1 text-[11px] font-medium text-white hover:bg-[#2a3d5e] transition-colors"
                >
                  <Download className="h-3 w-3" /> Download
                </button>
                <button
                  onClick={() => {
                    let html = selectedOutput.trim();
                    if (html.startsWith("```")) html = html.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
                    const blob = new Blob([html], { type: "text/html" });
                    const url = URL.createObjectURL(blob);
                    window.open(url, "_blank");
                    setTimeout(() => URL.revokeObjectURL(url), 5000);
                  }}
                  className="flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1 text-[11px] text-gray-500 hover:border-gray-300 hover:text-gray-800 transition-colors"
                >
                  <ExternalLink className="h-3 w-3" /> Full Screen
                </button>
              </div>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-h-0 overflow-hidden">
            {loadingDetail ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
              </div>
            ) : (
              /* Version-switch cross-fade (PreviewPanel.tsx:586-594 idiom): all
                 tabs re-render together keyed on selectedRun.id so a version
                 switch feels like one workflow, not navigation. */
              <AnimatePresence mode="wait">
                <motion.div
                  key={selectedRun.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="h-full"
                >
                  {detailTab === "preview" ? (
              !selectedOutput && !isAppBuilder ? (
                // ISS-017 (gap-fix): a reopened terminal-FAILED/cancelled/degraded
                // run with no content shows the SAME affordance the live path uses
                // (server-status-gated), not the neutral "No preview available".
                reopenTerminalFailure ? (
                  <DegradedRunAffordance
                    failedAgents={reopenFailedAgents}
                    agentNameById={reopenAgentNameById}
                    cancelled={reopenCancelled}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center h-full gap-2">
                    <FileText className="h-8 w-8 text-gray-200" />
                    <p className="text-[12px] text-gray-400">No preview available</p>
                  </div>
                )
              ) : (
                <div className="h-full overflow-auto">
                  {isUserStory && selectedOutput && (
                    <UserStoryPreview
                      content={selectedOutput}
                      onRevise={undefined}
                    />
                  )}
                  {isAppBuilder && (
                    ideFiles.length > 0
                      ? <AppBuilderPreview files={ideFiles} projectName={ideProjectName} onRevise={undefined} />
                      : selectedOutput
                        ? <MarkdownPreview content={selectedOutput} />
                        // ISS-017 (gap-fix): a terminal-failed app_builder reopen
                        // with no files and no output shows the affordance too
                        // (server-status-gated), mirroring the live path.
                        : reopenTerminalFailure
                          ? <DegradedRunAffordance failedAgents={reopenFailedAgents} agentNameById={reopenAgentNameById} cancelled={reopenCancelled} />
                          : <div className="flex flex-col items-center justify-center h-full gap-2"><FileText className="h-8 w-8 text-gray-200" /><p className="text-[12px] text-gray-400">No preview available</p></div>
                  )}
                  {/* ISS-021 (18-03) — generic reopen fallback: HTML → the SAME
                      sandboxed iframe as the live path (T-18-05: allow-scripts,
                      NO allow-same-origin); markdown/other → MarkdownPreview (this
                      preserves the prior `custom` markdown behavior). */}
                  {isGenericHtml && selectedOutput && (
                    <div className="h-full flex flex-col overflow-hidden">
                      <div className="flex-1 min-h-0 overflow-hidden">
                        <iframe
                          srcDoc={selectedOutput}
                          className="w-full h-full border-0"
                          title="Deliverable Preview"
                          sandbox="allow-scripts"
                        />
                      </div>
                    </div>
                  )}
                  {/* WR-02 (18 review fix): a serialized-sandbox / zip bundle →
                      the file-bundle view (matching the live path), not a flat
                      MarkdownPreview. Falls back to MarkdownPreview when the
                      bundle yields no parseable files. */}
                  {isGenericBundle && selectedOutput && (
                    genericBundleFiles.length > 0
                      ? <AppBuilderPreview files={genericBundleFiles} projectName={ideProjectName} />
                      : <MarkdownPreview content={selectedOutput} />
                  )}
                  {isGenericMarkdown && selectedOutput && <MarkdownPreview content={selectedOutput} />}
                  {isPpt && selectedOutput && (
                    <PPTPreview
                      content={selectedOutput}
                      pipelineType={workflowType}
                      onRevise={undefined}
                    />
                  )}
                  {isPrototype && selectedOutput && (
                    <PrototypePreview
                      content={selectedOutput}
                      onRevise={undefined}
                    />
                  )}
                </div>
              )
            ) : detailTab === "thinking" ? (
              /* Thinking tab — populated from persisted agent_outputs (Phase 3) */
              <AgentThinkingTab agents={thinkingAgents} />
            ) : detailTab === "audit" ? (
              /* Audit tab — persisted hook_runs fetched from GET /api/runs/{id}/hook-runs */
              <AuditTab workflowRunId={selectedRun.id} />
            ) : (
              /* Files tab */
              <FilesTab
                workflowType={workflowType}
                userStoryContent={(isUserStory || isAppBuilder) ? selectedOutput || undefined : undefined}
                pptContent={isPpt ? selectedOutput || undefined : undefined}
                prototypeContent={isPrototype ? selectedOutput || undefined : undefined}
                genericDeliverable={
                  isGeneric && selectedOutput
                    ? { mimetype: genericMimetype, filename: undefined, content: selectedOutput }
                    : undefined
                }
                agentOutputs={
                  agentOutputs.length > 0
                    ? agentOutputs
                        .filter((a) => a.output && a.output.trim().length > 0)
                        .map((a) => ({ name: a.name, role: a.role, output: a.output, agentId: a.agent_id }))
                    : undefined
                }
              />
            )}
                </motion.div>
              </AnimatePresence>
            )}
          </div>
        </div>

        {/* Delete modal */}
        <AnimatePresence>
          {deleteConfirmId && <DeleteModal onConfirm={handleDeleteConfirm} onCancel={() => { setDeleteConfirmId(null); setDeleteError(null); }} error={deleteError} />}
        </AnimatePresence>
      </div>
    );
  }

  // ─── LIST VIEW ─────────────────────────────────────────────────────────────
  // Revision Families (B2 / D3): group the flat run list by rootRunId. One card
  // per family root; the type-filter counts each family ONCE under its base type.
  const families = groupRunsByFamily(runs);
  const visibleFamilies = families.filter((g) => g.members.some(matchesFilter));
  const typeGroups = ["all", "user_stories", "ppt", "prototype", "app_builder", "custom"];
  const typeCounts: Record<string, number> = { all: families.length };
  families.forEach((g) => {
    // Count the FAMILY once under its base type (normalized from the root).
    const base = baseWorkflowType(g.root.type);
    typeCounts[base] = (typeCounts[base] || 0) + 1;
  });

  return (
    <div className="h-full flex flex-col bg-white" style={{ background: "#f5f5f0" }}>
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b border-gray-100">
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={onBack}
            className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="h-4 w-4 text-gray-500" />
          </button>
          <div>
            <h1 className="text-[18px] font-normal italic text-gray-900 leading-tight font-serif">Workflow History</h1>
            <p className="text-[11px] text-gray-400 mt-0.5">{runs.length} runs</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search workflows..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 transition-colors placeholder-gray-400"
          />
        </div>

        {/* Type filter tabs */}
        <div className="flex items-center gap-1 mt-3 overflow-x-auto pb-0.5">
          {typeGroups.map((type) => {
            const count = typeCounts[type] || 0;
            if (type !== "all" && count === 0) return null;
            const label = type === "all" ? "All" : (TYPE_META[type]?.label || type);
            return (
              <button
                key={type}
                onClick={() => setFilterType(type)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium whitespace-nowrap transition-all flex-shrink-0 ${
                  filterType === type
                    ? "bg-[#1B2A4A] text-white"
                    : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                }`}
              >
                {label}
                <span className={`text-[9px] font-semibold px-1 rounded ${filterType === type ? "bg-white/20 text-white" : "bg-gray-200 text-gray-500"}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          /* Professional skeleton loading state */
          <div className="px-6 py-4 space-y-1">
            {/* Loading header */}
            <div className="flex items-center gap-3 mb-5 pt-2">
              <div className="relative">
                <div className="h-8 w-8 rounded-full border-2 border-gray-200 border-t-[#1B2A4A] animate-spin" />
              </div>
              <div>
                <p className="text-[13px] font-semibold text-gray-700">Loading workflows</p>
                <p className="text-[11px] text-gray-400">Fetching your pipeline history...</p>
              </div>
            </div>

            {/* Skeleton cards */}
            {Array.from({ length: 7 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-0 py-3.5 border-b border-gray-100"
                style={{ opacity: 1 - i * 0.1 }}
              >
                {/* Icon skeleton */}
                <div className="w-9 h-9 rounded-xl bg-gray-100 flex-shrink-0 animate-pulse" />

                {/* Text skeleton */}
                <div className="flex-1 min-w-0 space-y-2">
                  <div
                    className="h-3 rounded-full bg-gray-100 animate-pulse"
                    style={{ width: `${60 + (i % 4) * 10}%` }}
                  />
                  <div className="flex items-center gap-2">
                    <div className="h-2.5 w-20 rounded-full bg-gray-100 animate-pulse" />
                    <div className="h-2.5 w-2.5 rounded-full bg-gray-100 animate-pulse" />
                    <div className="h-2.5 w-14 rounded-full bg-gray-100 animate-pulse" />
                  </div>
                </div>

                {/* Badge skeleton */}
                <div className="h-5 w-14 rounded-full bg-gray-100 animate-pulse flex-shrink-0" />
                <div className="h-4 w-4 rounded bg-gray-100 animate-pulse flex-shrink-0" />
              </div>
            ))}
          </div>
        ) : visibleFamilies.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 gap-2">
            <FileText className="h-8 w-8 text-gray-200" />
            <p className="text-[12px] text-gray-400">No workflows found</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {visibleFamilies.map((group, idx) => (
              <FamilyGroupCard
                key={group.rootRunId}
                group={group}
                index={idx}
                expanded={expandedFamilies.has(group.rootRunId)}
                onToggle={() => toggleFamily(group.rootRunId)}
                onSelectRun={handleSelectRun}
                openMenuId={openMenuId}
                onToggleMenu={(id, e) => { e?.stopPropagation(); setOpenMenuId(openMenuId === id ? null : id); }}
                onDeleteClick={handleDeleteClick}
              />
            ))}
          </div>
        )}
      </div>

      {/* Delete modal */}
      <AnimatePresence>
        {deleteConfirmId && <DeleteModal onConfirm={handleDeleteConfirm} onCancel={() => { setDeleteConfirmId(null); setDeleteError(null); }} error={deleteError} />}
      </AnimatePresence>

      {/* Close menu on outside click */}
      {openMenuId && (
        <div className="fixed inset-0 z-10" onClick={() => setOpenMenuId(null)} />
      )}
    </div>
  );
}

function DeleteModal({ onConfirm, onCancel, error }: { onConfirm: () => void; onCancel: () => void; error?: string | null }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm"
      onClick={onCancel}
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
          The workflow run and all its output will be permanently deleted.
        </p>
        {error && (
          <p className="text-[11px] text-red-500 mb-3 px-1">{error}</p>
        )}
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-[12px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 rounded-xl bg-gray-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-gray-800 transition-colors"
          >
            Delete
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
