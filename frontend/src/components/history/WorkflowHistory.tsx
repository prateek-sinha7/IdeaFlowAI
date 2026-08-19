"use client";

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  FileText, Presentation, Layout,
  Loader2, ArrowLeft, Trash2,
  Search, Sparkles, ArrowRight,
  Download, ExternalLink, RefreshCw, X, Send,
} from "lucide-react";
import { getToken, getWorkflows, getWorkflow, deleteWorkflow, getRunFamily, getRunArtifacts } from "@/lib/api";
import { parseClarificationArtifacts } from "@/lib/clarifications";
// KAN-116 (Bug 3): clean === markers from titles stored in DB (safety net for existing data).
import { parseRunInput } from "@/lib/runInput";
import { PPTPreview } from "@/components/preview/PPTPreview";
import { UserStoryPreview } from "@/components/preview/UserStoryPreview";
import { PrototypePreview } from "@/components/preview/PrototypePreview";
import { MarkdownPreview } from "@/components/preview/MarkdownPreview";
import { AppBuilderPreview, type ParsedFile } from "@/components/preview/AppBuilderPreview";
import { FilesTab } from "@/components/results/FilesTab";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { AuditTab } from "@/components/results/AuditTab";
import type { WorkflowRun, WorkflowType, AgentRunState, RunFamily, ClarifyRound } from "@/types/index";
import { resolveReopenMimetype } from "@/types/index";
import { useWorkflowChaining } from "@/hooks/useWorkflowMetadata";
// Revision Families (B2 / D3): client-side grouping by rootRunId + the family
// root card (REUSE-FIRST — WORKSTREAM-B-UI-SPEC.md Surface 1).
import { groupRunsByFamily, FamilyGroupCard, baseWorkflowType, bucketAndSortFamilies, type HistorySortKey } from "./RevisionFamilyView";
// SHELL-03: the terminal-run detail's summary surfaces (KPI / per-agent breakdown /
// version timeline / failure banner) render via the single-source RunDetailPage
// (fed by getRunSummary) — no dual implementation with the deliverable wrapper.
import { RunDetailPage } from "./RunDetailPage";

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
  // KAN-96: clicking a running run navigates to the live execution view instead
  // of opening the history detail. activeRunId is the current pipeline's run id;
  // onViewRunningPipeline switches the main view to "execution".
  activeRunId?: string | null;
  onViewRunningPipeline?: () => void;
  // BUG-002: route a row tap into the SHARED run screen (execution-chat-lane +
  // composer + DEF-44-12-4 durable seed + DEF-44-12-3 SSE attach) — the same
  // wiring the Home-recents path uses — instead of WorkflowHistory's divergent
  // internal RunDetailPage (one-shot summary, no SSE, no chat lane). When absent,
  // the legacy setSelectedRun internal-detail fallback is preserved.
  onOpenRun?: (run: WorkflowRun) => void;
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
  prototype: { icon: Layout, label: "Prototype" },
  prototype_revision: { icon: Layout, label: "Prototype (Revised)" },
  app_builder: { icon: Layout, label: "App Builder" },
  app_builder_revision: { icon: Layout, label: "App Builder (Revised)" },
  custom: { icon: FileText, label: "Custom" },
};

// Note: the run-detail KPI/duration/date formatting now lives in the single-source
// RunDetailPage (fed by `@/lib/runStats` formatDuration/formatTokenCount). The list
// rows format their own dates via RevisionFamilyView — so no local formatter here
// (INV-12: no dual implementation).

// KAN-116 (Bug 3) + FIX-130 + FIX-131: safety net for titles stored in the DB with === markers
// or with a "Title: " prefix from cascading context-block pollution.
// SC-001: generic, no workflow-name branches.
function cleanDisplayTitle(
  title: string | null | undefined,
  fallback = "",
  runInput?: string | null,
): string {
  // Strip "Title: " prefix — can appear when a polluted prior title cascades into
  // the next run's enrichedInput brief (the context block header line "Title: ..." 
  // leaks into the plain-brief portion of the next launch).
  const stripTitlePrefix = (s: string) =>
    s.startsWith("Title: ") ? s.slice("Title: ".length).trim() : s;

  const extractFromInput = (input: string): string => {
    const parsed = parseRunInput(input);
    const raw = (parsed.revisionInstruction ?? parsed.brief ?? "").split("\n")[0].trim();
    return stripTitlePrefix(raw);
  };
  if (!title) return runInput ? (extractFromInput(runInput) || fallback) : fallback;
  if (!title.includes("===")) return stripTitlePrefix(title);
  if (title.trimStart().startsWith("===")) {
    return runInput ? (extractFromInput(runInput) || fallback) : fallback;
  }
  const fromTitle = extractFromInput(title);
  if (fromTitle) return fromTitle;
  return runInput ? (extractFromInput(runInput) || fallback) : fallback;
}

export function WorkflowHistory({ onBack, onChainPipeline, onReviseUserStory, onRevisePpt, onRevisePrototype, onReviseAppBuilder, activeRunId, onViewRunningPipeline, onOpenRun }: WorkflowHistoryProps) {
  const chainInto = useWorkflowChaining();
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [totalRuns, setTotalRuns] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedRun, setSelectedRun] = useState<WorkflowRun | null>(null);
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  // Revision Families (B2 / D4): the open run's family (root + ordered members),
  // fetched on detail open and keyed on the STABLE rootRunId so switching
  // versions does NOT refetch the family.
  const [family, setFamily] = useState<RunFamily | null>(null);
  // Workstream C2 (POR §5 D4 / §6.6) — the open run's answered clarify rounds,
  // fetched on reopen from getRunArtifacts(kind="clarifications") and parsed via
  // parseClarificationArtifacts. Threaded to the Thinking + Files mounts.
  const [clarifyRounds, setClarifyRounds] = useState<ClarifyRound[]>([]);
  const [clarifyLoading, setClarifyLoading] = useState(false);
  const [filterType, setFilterType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  // SHELL-02: sort the (family-grouped, date-bucketed) list by recency / tokens /
  // duration — all derived from fields already on each row (no fetch).
  const [sortKey, setSortKey] = useState<HistorySortKey>("recent");
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
    getWorkflows(token, { limit: 50 })
      .then(({ runs: data, total }) => {
        setRuns(data);
        setTotalRuns(total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [filterType]);

  const handleLoadMore = useCallback(() => {
    const token = getToken();
    if (!token || loadingMore || runs.length >= totalRuns) return;
    setLoadingMore(true);
    getWorkflows(token, { limit: 50, offset: runs.length })
      .then(({ runs: moreRuns }) => {
        setRuns((prev) => [...prev, ...moreRuns]);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }, [runs.length, totalRuns, loadingMore]);

  const handleSelectRun = useCallback(async (run: WorkflowRun) => {
    // KAN-96: if this run is the currently-active pipeline, navigate to the
    // live execution view rather than opening the static history detail.
    if (activeRunId && run.id === activeRunId && onViewRunningPipeline) {
      onViewRunningPipeline();
      return;
    }
    // BUG-002: route the tap into the shared run screen (parity with Home-recents)
    // instead of the divergent internal RunDetailPage. Carry-over: cross-workflow
    // chaining (onChainPipeline) + the VersionTimeline version-switch stay reachable
    // via the History LIST rows; retiring the internal detail (INV-3) is a follow-up.
    if (onOpenRun) {
      onOpenRun(run);
      return;
    }
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
  }, [activeRunId, onViewRunningPipeline]);

  // Revision Families (B2 / D4): load a chosen version into the SAME detail surface
  // so BOTH the RunDetailPage summary column AND the deliverable/files/thinking/audit
  // right column re-sync to the picked version. Setting selectedRun re-keys the
  // RunDetailPage mount (runId=selectedRun.id) → it refetches that version's summary.
  // KAN-116 (Bug 1): when onOpenRun is present (shared run screen path), route the
  // version switch through it so page.tsx clears ALL content states (userStoryContent,
  // prototypeContent, etc.) and re-populates by the selected version's type — identical
  // to what handleSelectRun does. Without this the page.tsx content state retains the
  // last-rendered type (e.g. prototype HTML) for every version click.
  const handleSelectVersion = useCallback(async (memberId: string) => {
    const token = getToken();
    if (!token) return;
    setLoadingDetail(true);
    try {
      const full = await getWorkflow(token, memberId);
      if (onOpenRun) {
        // Shared run screen path: route through onOpenRun so page.tsx correctly
        // clears stale content state and re-populates by full.type (Bug 1 fix).
        onOpenRun(full);
      } else {
        setSelectedRun(full);
        setSelectedOutput(full.output || null);
      }
    } catch (err) {
      console.warn("[revision-family] version fetch failed", err);
    }
    finally { setLoadingDetail(false); }
  }, [onOpenRun]);

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

  // Workstream C2 (POR §5 D4 / §6.6): fetch the open run's clarify rounds on
  // reopen. Keyed on selectedRun?.id (each version has its own clarify history);
  // cancellable so a fast back-and-forth cannot land a stale result. A PROCEED
  // run resolves to empty artifacts → [] → ClarificationsCard renders nothing.
  useEffect(() => {
    if (!selectedRun) { setClarifyRounds([]); return; }
    const token = getToken();
    if (!token) { setClarifyRounds([]); return; }
    let cancelled = false;
    setClarifyLoading(true);
    getRunArtifacts(token, selectedRun.id, { kind: "clarifications", includeContent: true })
      .then((resp) => { if (!cancelled) setClarifyRounds(parseClarificationArtifacts(resp.artifacts)); })
      .catch(() => { if (!cancelled) setClarifyRounds([]); })
      .finally(() => { if (!cancelled) setClarifyLoading(false); });
    return () => { cancelled = true; };
  }, [selectedRun?.id]);

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
    const workflowType = selectedRun.type as WorkflowType;
    // ─── C-FLAG-1 (260703-174) — reopen StartingPointCard revision chip wiring ──
    // revisionParentVersion = 1-based family index of selectedRun's PARENT, derived
    // from the fetched `family` state (getRunFamily). family.members uses the same
    // revision_index-ASC ordering the RunDetailPage timeline derives, so the
    // chip's v-number matches the version timeline. Feeds the Thinking tab.
    const reopenSortedMembers = family ? [...family.members].sort((a, b) => a.revision_index - b.revision_index) : [];
    const reopenParentIdx = selectedRun.parentRunId ? reopenSortedMembers.findIndex((m) => m.id === selectedRun.parentRunId) : -1;
    const revisionParentVersion = reopenParentIdx >= 0 ? reopenParentIdx + 1 : undefined;
    const isUserStory = workflowType === "user_stories" || workflowType === "user_stories_revision";
    const isAppBuilder = detailIsAppBuilder;
    const isPpt = workflowType === "ppt" || workflowType === "ppt_revision";
    const isPrototype = workflowType === "prototype" || workflowType === "prototype_revision";
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
    // KAN-112 (FIX-060 follow-up): a custom-composer user stories run stores
    // deliverableFilename="user_stories.md" — route it to UserStoryPreview
    // for the same styled epic/story card layout as the dedicated pipeline.
    // Keyed on filename, not workflow name (SC-001).
    const isGenericUserStories = isGenericMarkdown && selectedRun.deliverableFilename === "user_stories.md";
    const isPlainMarkdown = isGenericMarkdown && !isGenericUserStories;
    // KAN-112: a custom-composer PPT run stores deliverableFilename="presentation.html"
    // and mimetype="text/html" — route it to PPTPreview for the styled deck viewer.
    // Keyed on filename (SC-001).
    const isGenericPpt = isGenericHtml && selectedRun.deliverableFilename === "presentation.html";
    const isGenericHtmlOnly = isGenericHtml && !isGenericPpt;
    const genericBundleFiles = isGenericBundle && selectedOutput ? parseFilesForIDE(selectedOutput) : [];
    const agentOutputs = detailAgentOutputs;

    // ─── SHELL-03 — summary surfaces via RunDetailPage (single source) ─────────
    // The KPI strip, per-agent breakdown, version/revision timeline AND the
    // terminal-failure banner render in the RunDetailPage summary column (fed by
    // getRunSummary) — no dual implementation. Here we only gate the deliverable
    // preview's neutral empty-state: a terminal-failure run is already explained by
    // the summary column, so we suppress the neutral "No preview available" for it.
    // STRICTLY server-status-gated on the PERSISTED status (never a client
    // empty==failed guess), SC-001 (generic status, no workflow-name branch).
    const reopenTerminalFailure =
      selectedRun.status === "failed" ||
      selectedRun.status === "cancelled" ||
      selectedRun.status === "degraded";

    return (
      <div className="h-full flex bg-surface-paper">
        {/* ── Left column — summary via the single-source RunDetailPage ──────────
            KAN-96: a terminal run opens the detail page here (a running run took the
            live-execution branch in handleSelectRun). RunDetailPage owns the KPI
            strip, per-agent breakdown, version/revision timeline + failure banner
            (fed by getRunSummary) — no dual implementation. Back returns to the
            list. The deliverable the summary does not cover renders on the right. */}
        <div className="w-[340px] flex-shrink-0 h-full border-r border-line-border flex flex-col bg-surface-white min-h-0">
          <div className="flex-1 min-h-0">
            <RunDetailPage
              runId={selectedRun.id}
              onBack={() => { setSelectedRun(null); setSelectedOutput(null); }}
              activeRunId={activeRunId}
              onViewRunningPipeline={onViewRunningPipeline ? () => onViewRunningPipeline() : undefined}
              onSelectVersion={handleSelectVersion}
            />
          </div>

          {/* Suggested next steps — always-visible footer for completed runs.
              Lets the user chain the historical output into another pipeline
              without having to re-run from the home page. Excludes the
              already-completed pipeline (incl. its `_revision` form) via
              the shared chainInto() rule (backend-owned via useWorkflowChaining,
              Plan 34-01). */}
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
             const chainOptions = onChainPipeline ? chainInto(baseWorkflowType(selectedRun.type)) : [];
             if (!reviseCallback && chainOptions.length === 0) return null;
             return (
               <div className="border-t border-line-divider px-3 py-3 bg-surface-warm flex-shrink-0">
                 <div className="flex items-center gap-1.5 mb-2 px-1">
                   <Sparkles className="h-3 w-3 text-brand" />
                   <p className="text-[9px] font-bold text-brand uppercase tracking-[0.12em]">
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
                         className="rounded-xl border border-brand/20 bg-surface-white overflow-hidden"
                       >
                         <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
                           <div className="flex items-center gap-1.5">
                             <RefreshCw className="h-3 w-3 text-brand" />
                             <p className="text-[11px] font-semibold text-brand">{reviseLabel}</p>
                           </div>
                           <button onClick={() => { setReviseOpen(false); setRevisionText(""); }} className="p-0.5 rounded text-ink-400 hover:text-ink-700 hover:bg-surface-warm transition-colors">
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
                             className="w-full text-[11px] text-ink-700 placeholder:text-ink-400 bg-surface-warm border border-line-border rounded-lg px-3 py-2 focus:outline-none focus:border-brand/40 transition-colors resize-y leading-relaxed min-h-[60px]"
                           />
                           <div className="flex items-center justify-between mt-2">
                             <span className="text-[9px] text-ink-400">⌘↵ to send</span>
                             <button
                               onClick={() => { if (revisionText.trim()) { reviseCallback(revisionText.trim()); setRevisionText(""); setReviseOpen(false); } }}
                               disabled={!revisionText.trim()}
                               className="flex items-center gap-1.5 text-[11px] font-medium text-white bg-brand hover:bg-brand-pressed disabled:opacity-40 rounded-lg px-3 py-1.5 transition-colors"
                             >
                               <Send className="h-3 w-3" /> Send
                             </button>
                           </div>
                         </div>
                       </motion.div>
                     ) : (
                       <button
                         onClick={() => setReviseOpen(true)}
                         className="group w-full flex items-center justify-between rounded-xl border border-brand/20 bg-surface-white hover:border-brand hover:bg-brand hover:shadow-md px-3 py-2 text-left transition-all"
                       >
                         <div className="min-w-0">
                           <p className="text-[11px] font-semibold text-ink-900 group-hover:text-white transition-colors">{reviseLabel}</p>
                           <p className="text-[9px] text-ink-500 group-hover:text-white/80 transition-colors leading-snug">Request changes to the output</p>
                         </div>
                         <RefreshCw className="h-3 w-3 text-brand group-hover:text-white group-hover:rotate-180 transition-all flex-shrink-0 ml-2" />
                       </button>
                     )
                   )}
                   {onChainPipeline && chainOptions.map((opt) => (
                     <button
                       key={opt.id}
                       onClick={() => { if (!opt.beta) onChainPipeline(selectedRun, opt.id as WorkflowType); }}
                       disabled={opt.beta}
                       className={`group w-full flex items-center justify-between rounded-xl border px-3 py-2 text-left transition-all ${
                         opt.beta
                           ? "cursor-not-allowed border-line-border bg-surface-white opacity-60"
                           : "border-brand/20 bg-surface-white hover:border-brand hover:bg-brand hover:shadow-md"
                       }`}
                     >
                       <div className="min-w-0">
                         <p className={`text-[11px] font-semibold transition-colors ${opt.beta ? "text-ink-400" : "text-ink-900 group-hover:text-white"}`}>{opt.label}</p>
                         <p className={`text-[9px] leading-snug transition-colors ${opt.beta ? "text-ink-400" : "text-ink-500 group-hover:text-white/80"}`}>
                           {opt.beta ? "Coming Soon" : `Chain this run into ${opt.label}`}
                         </p>
                       </div>
                       <ArrowRight className={`h-3 w-3 flex-shrink-0 ml-2 transition-all ${opt.beta ? "text-ink-300" : "text-brand group-hover:text-white group-hover:translate-x-0.5"}`} />
                     </button>
                   ))}
                 </div>
               </div>
             );
           })()}
        </div>

        {/* Main content — the deliverable the RunDetailPage summary does not cover
            (preview / files / thinking / audit). Version switching lives in the
            RunDetailPage timeline on the left (single source). */}
        <div className="flex-1 min-w-0 h-full flex flex-col bg-surface-white border-l border-line-border">
          {/* Title + tabs + PPT action buttons */}
          <div className="flex items-center justify-between gap-2 px-5 py-3 border-b border-line-divider bg-surface-white flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              {/* KAN-92: render the real async-generated run title (never a placeholder). */}
              <h2 className="min-w-0 max-w-[200px] truncate text-[13px] font-semibold text-ink-900">{cleanDisplayTitle(selectedRun.title, selectedRun.type, selectedRun.input)}</h2>
              <div className="flex items-center gap-1">
              {(["preview", "files", "thinking", "audit"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setDetailTab(tab)}
                  className={`px-3 py-1.5 rounded-md text-[11px] font-medium transition-all capitalize ${
                    detailTab === tab
                      ? "bg-surface-warm text-ink-900"
                      : "text-ink-400 hover:text-ink-700"
                  }`}
                >
                  {tab === "files" ? "Files" : tab === "thinking" ? "Thinking" : tab === "audit" ? "Audit" : "Preview"}
                </button>
              ))}
              </div>
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
                  className="flex items-center gap-1.5 rounded-md bg-brand px-2.5 py-1 text-[11px] font-medium text-white hover:bg-brand-pressed transition-colors"
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
                  className="flex items-center gap-1 rounded-md border border-line-border bg-surface-white px-2.5 py-1 text-[11px] text-ink-500 hover:border-line-control hover:text-ink-800 transition-colors"
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
                <Loader2 className="h-5 w-5 animate-spin text-ink-300" />
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
                // No deliverable to preview. A terminal-FAILED/cancelled/degraded run
                // is explained by the summary column (RunDetailPage renders the
                // failure banner + failed agents); the neutral empty state shows only
                // for a non-failure empty (server-status-gated, SC-001).
                reopenTerminalFailure ? null : (
                  <div className="flex flex-col items-center justify-center h-full gap-2">
                    <FileText className="h-8 w-8 text-ink-200" />
                    <p className="text-[12px] text-ink-400">No preview available</p>
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
                        // A terminal-failed app_builder reopen with no files/output:
                        // the summary column explains the failure; suppress neutral.
                        : reopenTerminalFailure
                          ? null
                          : <div className="flex flex-col items-center justify-center h-full gap-2"><FileText className="h-8 w-8 text-ink-200" /><p className="text-[12px] text-ink-400">No preview available</p></div>
                  )}
                  {/* ISS-021 (18-03) — generic reopen fallback: HTML → the SAME
                      sandboxed iframe as the live path (T-18-05: allow-scripts,
                      NO allow-same-origin); markdown/other → MarkdownPreview (this
                      preserves the prior `custom` markdown behavior).
                      KAN-112: presentation.html → PPTPreview for styled deck viewer. */}
                  {isGenericPpt && selectedOutput && (
                    <PPTPreview
                      content={selectedOutput}
                      pipelineType="ppt"
                      onRevise={undefined}
                    />
                  )}
                  {isGenericHtmlOnly && selectedOutput && (
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
                  {isGenericUserStories && selectedOutput && (
                    <UserStoryPreview content={selectedOutput} onRevise={undefined} />
                  )}
                  {isPlainMarkdown && selectedOutput && <MarkdownPreview content={selectedOutput} />}
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
              <AgentThinkingTab
                agents={thinkingAgents}
                runInput={selectedRun.input}
                clarifications={clarifyRounds}
                clarificationsLoading={clarifyLoading}
                originalBriefRootRunId={selectedRun.parentRunId ? selectedRun.rootRunId : undefined}
                revisionParentVersion={revisionParentVersion}
              />
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
                runInput={selectedRun.input}
                clarifications={clarifyRounds}
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
  // SHELL-02: layer the Today/Earlier/Older buckets + the chosen sort OVER the
  // family grouping (fields already on each row — no fetch, no backend change).
  const sections = bucketAndSortFamilies(visibleFamilies, sortKey);
  const typeGroups = ["all", "user_stories", "ppt", "prototype", "app_builder", "custom"];
  const typeCounts: Record<string, number> = { all: families.length };
  families.forEach((g) => {
    // Count the FAMILY once under its base type (normalized from the root).
    const base = baseWorkflowType(g.root.type);
    typeCounts[base] = (typeCounts[base] || 0) + 1;
  });

  return (
    <div className="h-full flex flex-col bg-surface-paper">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b border-line-divider">
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={onBack}
            className="flex items-center justify-center h-8 w-8 rounded-lg hover:bg-surface-warm transition-colors"
          >
            <ArrowLeft className="h-4 w-4 text-ink-500" />
          </button>
          <div>
            <h1 className="text-[18px] font-normal italic text-ink-900 leading-tight font-serif">Run History</h1>
            <p className="text-[11px] text-ink-400 mt-0.5">{runs.length} runs</p>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-400" />
          <input
            type="text"
            placeholder="Search workflows..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-[12px] bg-surface-warm border border-line-border rounded-lg focus:outline-none focus:border-line-control transition-colors placeholder:text-ink-400"
          />
        </div>

        {/* 40-06: type-filter chips + Sort tabs on ONE row (mock History: chips
            left flex-1, the Sort segmented control right) — over the live/seeded
            /api/runs family counts (ND-D). */}
        <div className="flex items-center gap-3.5 mt-3">
          {/* Type filter chips */}
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5 flex-1 min-w-0">
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
                      ? "bg-brand text-white"
                      : "text-ink-500 hover:bg-surface-warm hover:text-ink-700"
                  }`}
                >
                  {label}
                  <span className={`text-[9px] font-semibold px-1 rounded ${filterType === type ? "bg-white/20 text-white" : "bg-surface-warm text-ink-500"}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* SHELL-02: sort control — recency / tokens / duration, all off fields
              already on each row. Mock's segmented pill; the active option sits on
              a raised surface (no fetch, no backend change). */}
          <div
            role="group"
            aria-label="Sort runs"
            className="flex items-center gap-2 flex-none"
          >
            <span className="text-[10px] font-medium text-ink-400">Sort</span>
            <div className="inline-flex items-center gap-0.5 bg-surface-warm p-0.5 rounded-lg">
              {/* Display labels track the mock's Sort tabs (Newest / Longest /
                  Tokens); the sort KEYS + the "Sort by {key}" aria-labels stay
                  stable so behavior + the a11y contract (ts-t) don't shift. */}
              {([
                { key: "recent", label: "Newest" },
                { key: "duration", label: "Longest" },
                { key: "tokens", label: "Tokens" },
              ] as const).map((opt) => {
                const active = sortKey === opt.key;
                return (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setSortKey(opt.key)}
                    aria-pressed={active}
                    aria-label={`Sort by ${opt.key}`}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors ${
                      active
                        ? "bg-surface-white text-ink-900 shadow-sm"
                        : "text-ink-500 hover:text-ink-700"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
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
                <div className="h-8 w-8 rounded-full border-2 border-line-border border-t-brand animate-spin" />
              </div>
              <div>
                <p className="text-[13px] font-semibold text-ink-700">Loading workflows</p>
                <p className="text-[11px] text-ink-400">Fetching your pipeline history...</p>
              </div>
            </div>

            {/* Skeleton cards */}
            {Array.from({ length: 7 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-4 px-0 py-3.5 border-b border-line-divider"
                style={{ opacity: 1 - i * 0.1 }}
              >
                {/* Icon skeleton */}
                <div className="w-9 h-9 rounded-xl bg-surface-warm flex-shrink-0 animate-pulse" />

                {/* Text skeleton */}
                <div className="flex-1 min-w-0 space-y-2">
                  <div
                    className="h-3 rounded-full bg-surface-warm animate-pulse"
                    style={{ width: `${60 + (i % 4) * 10}%` }}
                  />
                  <div className="flex items-center gap-2">
                    <div className="h-2.5 w-20 rounded-full bg-surface-warm animate-pulse" />
                    <div className="h-2.5 w-2.5 rounded-full bg-surface-warm animate-pulse" />
                    <div className="h-2.5 w-14 rounded-full bg-surface-warm animate-pulse" />
                  </div>
                </div>

                {/* Badge skeleton */}
                <div className="h-5 w-14 rounded-full bg-surface-warm animate-pulse flex-shrink-0" />
                <div className="h-4 w-4 rounded bg-surface-warm animate-pulse flex-shrink-0" />
              </div>
            ))}
          </div>
        ) : visibleFamilies.length === 0 ? (
          runs.length === 0 ? (
            /* 40-06: ZERO state (mock histZero) — no runs at all. */
            <div className="flex flex-col items-center justify-center h-full min-h-[280px] gap-3 px-6 text-center">
              <FileText className="h-8 w-8 text-ink-200" />
              <div>
                <p className="text-[13px] font-medium text-ink-600">No runs yet</p>
                <p className="text-[11px] text-ink-400 mt-1">Your workflow runs will appear here.</p>
              </div>
              <button
                onClick={onBack}
                className="mt-1 rounded-lg bg-brand px-3.5 py-2 text-[12px] font-semibold text-white hover:bg-brand-pressed transition-colors"
              >
                Start a run
              </button>
            </div>
          ) : (
            /* 40-06: FILTER-EMPTY state (mock histFilterEmpty) — runs exist, none
               match the active type filter / search. "Show all runs" clears both. */
            <div className="flex flex-col items-center justify-center h-full min-h-[280px] gap-3 px-6 text-center">
              <Search className="h-7 w-7 text-ink-200" />
              <p className="text-[13px] font-medium text-ink-600">No runs match this filter</p>
              <button
                onClick={() => { setFilterType("all"); setSearchQuery(""); }}
                className="mt-1 rounded-lg border border-line-border bg-surface-white px-3.5 py-2 text-[12px] font-semibold text-ink-700 hover:border-brand hover:text-brand transition-colors"
              >
                Show all runs
              </button>
            </div>
          )
        ) : (
          <div>
            {sections.map((section) => (
              <section key={section.bucket} aria-label={section.bucket}>
                {/* 40-06: Today / Earlier / Older group header — mock composition:
                    uppercase label + a faded count + a hairline rule to the edge. */}
                <div className="flex items-center gap-2.5 px-6 pt-5 pb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                    {/* Mock bucket copy: "Earlier" reads "Earlier this week"
                        (uppercased by CSS → "EARLIER THIS WEEK"). The `bucket`
                        enum + the section aria-label stay Today/Earlier/Older. */}
                    {section.bucket === "Earlier" ? "Earlier this week" : section.bucket}
                  </span>
                  <span className="text-[10px] text-ink-300 tabular-nums">{section.groups.length}</span>
                  <span className="flex-1 h-px bg-line-divider" />
                </div>
                <div className="divide-y divide-line-divider">
                  {section.groups.map((group, idx) => (
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
              </section>
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
  const confirmRef = useRef<HTMLButtonElement>(null);
  // a11y: focus the primary action on open + Escape closes the dialog.
  useEffect(() => {
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] backdrop-blur-sm"
      onClick={onCancel}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-delete-title"
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.15 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-surface-white rounded-2xl border border-line-border shadow-[var(--elevation-modal)] p-6 max-w-[340px] w-full mx-4"
      >
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-xl bg-surface-warm flex items-center justify-center">
            <Trash2 className="h-5 w-5 text-ink-600" />
          </div>
          <div>
            <h3 id="history-delete-title" className="text-[13px] font-semibold text-ink-900">Delete workflow</h3>
            <p className="text-[11px] text-ink-400">This cannot be undone</p>
          </div>
        </div>
        <p className="text-[12px] text-ink-500 leading-relaxed mb-5">
          The workflow run and all its output will be permanently deleted.
        </p>
        {error && (
          <p className="text-[11px] text-status-failed mb-3 px-1">{error}</p>
        )}
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 rounded-xl border border-line-border px-4 py-2.5 text-[12px] font-medium text-ink-600 hover:bg-surface-warm transition-colors"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className="flex-1 rounded-xl bg-ink-900 px-4 py-2.5 text-[12px] font-medium text-white hover:bg-ink-800 transition-colors"
          >
            Delete
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
