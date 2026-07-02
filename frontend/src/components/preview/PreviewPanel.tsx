"use client";

import { useEffect, useState, useMemo, useCallback, useRef, type ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, Brain, Shield, PanelRightClose, Copy, Check, Download, ExternalLink, Loader2, AlertTriangle } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { MarkdownPreview } from "./MarkdownPreview";
import { FilesTab } from "@/components/results/FilesTab";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { AuditTab } from "@/components/results/AuditTab";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";
import { LiveVersionChip, ReadOnlyVersionBanner } from "./LiveVersionChip";
import type { WorkflowType, GenericDeliverable, RunFamily } from "@/types/index";
import { getToken, getWorkflow } from "@/lib/api";
import { ENV } from "@/lib/env";
// ISS-024 — shared id→name resolution for the failed-agents list (no dual-impl).
import { buildAgentNameById, resolveAgentNames } from "@/lib/parseFailedAgents";

// ─── Agents whose output contains ```filename: ``` code blocks ────────────────
const CODE_PRODUCING_AGENT_IDS = new Set([
  "app-code-generator",
  "app-feature-implementation",
  "app-infra-generator",
  "app-test-implementation",
]);

// ─── Parse ```filename: path/to/file ``` blocks from any markdown string ──────
// Also handles the alternative ### path/to/file + fenced block format used
// by feature-implementation and test-implementation agents.
function parseAppBuilderFilesForIDE(markdown: string): ParsedFile[] {
  const files: ParsedFile[] = [];
  const seen = new Set<string>();

  const langMap: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", json: "json", md: "markdown", yml: "yaml", yaml: "yaml",
    css: "css", html: "html", sh: "bash", sql: "sql", dockerfile: "dockerfile",
    env: "bash", toml: "toml", prisma: "typescript", rs: "rust", go: "go",
    gitignore: "bash", lock: "plaintext", txt: "plaintext",
    java: "java", cs: "csharp", rb: "ruby", php: "php", kt: "kotlin",
    swift: "swift", xml: "xml", graphql: "graphql",
  };

  const addFile = (path: string, content: string) => {
    path = path.trim();
    if (!path || !content.trim() || seen.has(path)) return;
    // Skip paths that look like section headers, not file paths
    // (must contain a dot or be a known extensionless file like Dockerfile/Makefile)
    const name = path.split("/").pop() || path;
    const hasDot = name.includes(".");
    const isKnownExtensionless = /^(Dockerfile|Makefile|Procfile|Gemfile|Rakefile|Guardfile)$/i.test(name);
    if (!hasDot && !isKnownExtensionless) return;

    seen.add(path);
    const parts = path.split("/");
    const fileName = parts[parts.length - 1];
    const ext = fileName.includes(".") ? fileName.split(".").pop()!.toLowerCase() : "";
    files.push({
      path,
      name: fileName,
      ext,
      content,
      language: langMap[ext] || "plaintext",
    });
  };

  // Format 1: ```filename: path/to/file.ext\n[content]\n```
  const filenameRegex = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = filenameRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  // Format 2: ### path/to/file.ext\n```[lang]\n[content]\n```
  // Used by feature-implementation, test-implementation, api-design, devops agents
  const headerRegex = /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = headerRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  // Format 3: **`path/to/file.ext`** or **path/to/file.ext** followed by ```
  // Some agents bold the filename before the code block
  const boldRegex = /\*\*`?([\w./\-@][^\n`*]*\.\w+)`?\*\*\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = boldRegex.exec(markdown)) !== null) {
    addFile(m[1], m[2]);
  }

  return files;
}

// ─── App Builder IDE wrapper ───────────────────────────────────────────────────
// Merges files from ALL code-producing agents + the final output (last agent).
// The Preview tab receives userStoryContent = last agent's output only, so
// without scanning agentOutputs the IDE would only show docs/ files.
function AppBuilderIDEPreview({
  content,
  agentOutputs,
  onRevise,
}: {
  content: string;
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
  onRevise?: (s: string) => void;
}) {
  const files = useMemo(() => {
    const seen = new Set<string>();
    const merged: ParsedFile[] = [];

    const addFiles = (parsed: ParsedFile[]) => {
      for (const f of parsed) {
        if (!seen.has(f.path)) {
          seen.add(f.path);
          merged.push(f);
        }
      }
    };

    // 1. Scan all code-producing agents first (agents 8, 9, 10, 12)
    if (agentOutputs) {
      for (const agent of agentOutputs) {
        if (
          agent.agentId &&
          CODE_PRODUCING_AGENT_IDS.has(agent.agentId) &&
          agent.output?.trim()
        ) {
          addFiles(parseAppBuilderFilesForIDE(agent.output));
        }
      }
    }

    // 2. Also scan the final output (last agent — governance) for any
    //    filename: blocks it may contain (e.g. docs/RUNBOOK.md)
    if (content) {
      addFiles(parseAppBuilderFilesForIDE(content));
    }

    return merged;
  }, [content, agentOutputs]);

  const projectName = useMemo(() => {
    // Try to extract project name from architecture agent output first
    const archAgent = agentOutputs?.find(a => a.agentId === "material-analyzer");
    const source = archAgent?.output || content;
    const h = source.match(/^#\s+(.+)/m);
    return h ? h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().slice(0, 40) : "Generated App";
  }, [content, agentOutputs]);

  return <AppBuilderPreview files={files} onRevise={onRevise} projectName={projectName} />;
}

// ─── ISS-021 (18-03) — generic mimetype-dispatched deliverable renderer ───────
// Used as a FALLBACK for ANY pipeline_type that matched none of the four known
// render branches. Dispatch is on the DECLARED mimetype (SC-001 — never a
// workflow name):
//   • text/html         → a SANDBOXED iframe (sandbox="allow-scripts", NO
//                          allow-same-origin — reuses the PPTPreview non-od_ppt
//                          pattern). A custom workflow's HTML is semi-trusted →
//                          unsandboxed/same-origin would be stored-XSS-adjacent
//                          (T-18-05). This sandbox is a BLOCKING security
//                          mitigation, asserted in the component tests.
//   • text/markdown     → MarkdownPreview.
//   • application/zip…  → the AppBuilder file-bundle view (parsed from content).
//   • anything else     → a safe download affordance — never inline/execute an
//                          unknown type (T-18-06).
function GenericDeliverablePreview({
  deliverable,
  agentOutputs,
}: {
  deliverable: GenericDeliverable;
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
}) {
  const mimetype = (deliverable.mimetype || "").toLowerCase();
  const content = deliverable.content || "";

  // HTML → sandboxed iframe (NO allow-same-origin — see T-18-05 above).
  if (mimetype === "text/html" || mimetype.startsWith("text/html")) {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 overflow-hidden">
          <iframe
            srcDoc={content}
            className="w-full h-full border-0"
            title="Deliverable Preview"
            sandbox="allow-scripts"
          />
        </div>
      </div>
    );
  }

  // Markdown (or markdown-ish text) → MarkdownPreview.
  if (mimetype === "text/markdown" || mimetype === "text/x-markdown" || mimetype.startsWith("text/markdown")) {
    return <MarkdownPreview content={content} />;
  }

  // Zip / bundle → the AppBuilder file-bundle view (reuses the IDE parser).
  if (mimetype === "application/zip" || mimetype === "application/x-zip-compressed" || mimetype.includes("zip")) {
    return <AppBuilderIDEPreview content={content} agentOutputs={agentOutputs} />;
  }

  // Unknown / other → a safe download affordance (never inline/execute).
  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
          <FolderDown className="h-6 w-6 text-gray-500" />
        </div>
        <p className="text-sm font-semibold text-gray-900">Deliverable ready</p>
        <p className="text-xs text-gray-500">
          This deliverable ({deliverable.mimetype || "unknown type"}) can be downloaded from the Files tab.
        </p>
        <button
          onClick={() => {
            const blob = new Blob([content], { type: deliverable.mimetype || "application/octet-stream" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = deliverable.filename || "deliverable";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }}
          className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
        >
          <Download className="h-3.5 w-3.5" />
          Download {deliverable.filename || "deliverable"}
        </button>
      </div>
    </div>
  );
}

type PanelTab = "preview" | "files" | "thinking" | "audit";

interface PreviewPanelProps {
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  // ISS-021 (18-03) — generic deliverable channel for ANY pipeline_type that
  // matched none of the known render branches. The renderer (added below)
  // dispatches on `mimetype`: text/html → sandboxed iframe, text/markdown →
  // MarkdownPreview, application/zip → bundle view. SC-001: dispatch is on the
  // declared mimetype, never a workflow name.
  genericDeliverable?: GenericDeliverable;
  isStreaming?: boolean;
  onCollapse?: () => void;
  initialTab?: string;
  onTabSelect?: (tab: string) => void;
  workflowType?: WorkflowType;
  /** Raw pipeline type — not normalised. Used to distinguish od_ppt from ppt for download. */
  rawPipelineType?: string;
  pptxCode?: string;
  onRevisePpt?: (instruction: string) => void;
  onReviseUserStory?: (instruction: string) => void;
  onRevisePrototype?: (instruction: string) => void;
  onReviseAppBuilder?: (instruction: string) => void;
  // Per-agent outputs surfaced under the Files tab once the pipeline has
  // completed. Pass undefined / empty while running — the FilesTab filters
  // out empty outputs itself, but skipping the prop until completion keeps
  // the live "Final output" header from appearing prematurely.
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
  // Phase 3 (T045) — Thinking tab: live agent states with reasoning/tool data
  agents?: import("@/types/index").AgentRunState[];
  // Full pipeline state for the enhanced Thinking tab
  pipelineState?: import("@/types/index").PipelineRunState;
  // Phase 16 (ISS-017) — history-reopen server signal. When a persisted run is
  // reopened with status "failed"/"cancelled", the live pipelineState carries no
  // failed/degraded flag (it reflects the new/idle run), so the reopened run's
  // status is threaded here. PreviewPanel renders the terminal-empty
  // degraded/failed affordance when this is "failed"/"cancelled" — the
  // history-path counterpart of the live pipelineState.failed/.degraded signal.
  // Keyed on the SERVER-persisted status, never a client empty==failed guess.
  reopenedRunStatus?: import("@/types/index").WorkflowStatus;
  // Optional failed-agent names carried by the reopened run detail payload.
  reopenedFailedAgents?: string[];
  // ISS-024 (16 review IN-02) — id→name lookup for the reopened run's failed
  // agents. The live pipelineState reflects the new/idle run, so it cannot name
  // a reopened run's agents; the dashboard builds this from the reopened run
  // detail's persisted agentOutputs and threads it here. Unknown ids still fall
  // back to the raw id inside DegradedRunAffordance.
  reopenedAgentNameById?: Record<string, string>;
  // Revision Families (B3 / POR §5 D5) — the on-screen content's revision family
  // (root + ordered members) fetched by DashboardLayout keyed on
  // contentSourceRunId, and the id of the currently-live run. BOTH optional and
  // default undefined → the live version chip + read-only override are absent
  // unless explicitly wired by the live dashboard mount (zero regression for
  // history callers and existing test renders).
  runFamily?: RunFamily | null;
  liveRunId?: string | null;
}

const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "files", label: "Files", icon: FolderDown },
  { id: "thinking", label: "Thinking", icon: Brain },
  { id: "audit", label: "Audit", icon: Shield },
];

// ─── ISS-017 (16-04) — terminal-empty degraded/failed affordance ──────────────
// Rendered (instead of the neutral "Output will appear here") when a run is
// TERMINAL, has no content, AND carries a server-derived failure signal
// (pipelineState.failed/.degraded on live; the reopened run status on history).
// Surfaces the failed-agent names when present + a "view details"/retry hint.
//
// EXPORTED (no-dual-impl / INV-3): the history-reopen surface
// (components/history/WorkflowHistory.tsx) renders the SAME affordance for a
// terminal-empty failed/cancelled/degraded run, gated on the persisted
// `selectedRun.status`. Keeping ONE affordance component means the live path and
// the history-reopen path cannot drift. SC3 (CONTEXT A2): affordance on BOTH live
// and history-reopen.
export function DegradedRunAffordance({
  failedAgents,
  agentNameById,
  onRetry,
  cancelled,
}: {
  // Raw agent IDs (e.g. "prototype-build"). Resolved to human names below.
  failedAgents?: string[];
  // ISS-024 (16 review IN-02) — id→name lookup for the failed-agents list. The
  // LIVE path builds it from pipelineState.agents; the HISTORY-reopen path from
  // the persisted agentOutputs. Unknown ids fall back to the raw id (never
  // blank), so older runs keep working. When omitted, every id falls back —
  // identical to the pre-ISS-024 (raw-id) behaviour.
  agentNameById?: Record<string, string>;
  onRetry?: (instruction: string) => void;
  // IN-03 (16 review): true when the terminal state is a deliberate user cancel,
  // so the copy reads "cancelled" rather than "failed or degraded".
  cancelled?: boolean;
}) {
  const hasFailedAgents = !!(failedAgents && failedAgents.length > 0);
  // ISS-024: resolve ids → names once; fallback to the raw id keeps older runs
  // and unknown agents intact (never blank).
  const failedAgentEntries = (failedAgents || []).map((id) => ({
    id,
    label: resolveAgentNames([id], agentNameById)[0],
  }));
  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-50">
          <AlertTriangle className="h-6 w-6 text-amber-500" />
        </div>
        <p className="text-sm font-semibold text-gray-900">
          {cancelled
            ? "This run was cancelled"
            : "This run did not complete successfully"}
        </p>
        <p className="text-xs text-gray-500">
          {cancelled
            ? "The run was stopped before producing a deliverable."
            : "No deliverable was produced. The run ended in a failed or degraded state."}
        </p>
        {hasFailedAgents && (
          <div className="w-full rounded-md border border-amber-100 bg-amber-50/60 px-3 py-2 text-left">
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-amber-700">
              Failed agents
            </p>
            <ul className="space-y-0.5">
              {failedAgentEntries.map(({ id, label }) => (
                <li key={id} className="text-xs text-amber-800">
                  {label}
                </li>
              ))}
            </ul>
          </div>
        )}
        {onRetry ? (
          <button
            onClick={() => onRetry("Retry this run")}
            className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            View details / retry
          </button>
        ) : (
          <p className="mt-1 text-[11px] text-gray-400">
            Open the Thinking tab to view details.
          </p>
        )}
      </div>
    </div>
  );
}

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, genericDeliverable, isStreaming, onCollapse, initialTab, onTabSelect, workflowType, rawPipelineType, pptxCode, onRevisePpt, onReviseUserStory, onRevisePrototype, onReviseAppBuilder, agentOutputs, agents, pipelineState, reopenedRunStatus, reopenedFailedAgents, reopenedAgentNameById, runFamily, liveRunId }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  const [copied, setCopied] = useState(false);
  // ─── B3 (POR §5 D5) — live version chip state ───────────────────────────────
  // viewingVersion is the read-only older-version override ({ id, content }) or
  // null (live latest on screen); pulse is the one-shot tick shown when the
  // family grows on a revision-complete.
  const [viewingVersion, setViewingVersion] = useState<{ id: string; content?: string } | null>(null);
  const [pulse, setPulse] = useState(false);
  const prevMemberCount = useRef<number | null>(null);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  // ─── B3 — family/version derivation (UI-SPEC Surface 3) ──────────────────────
  // sortedMembers v1..vN by revision_index; latestId = last member (fallback
  // liveRunId); activeRunId = the read-only override id, else the live run, else
  // the latest member; activeIdx = its 0-based index; isViewingOlder = an
  // override is active AND it is not the latest.
  const sortedMembers = runFamily
    ? [...runFamily.members].sort((a, b) => a.revision_index - b.revision_index)
    : [];
  const latestId = sortedMembers.length > 0 ? sortedMembers[sortedMembers.length - 1].id : (liveRunId ?? null);
  const activeRunId = viewingVersion?.id ?? liveRunId ?? latestId;
  const activeIdx = sortedMembers.findIndex((m) => m.id === activeRunId);
  const isViewingOlder = viewingVersion != null && viewingVersion.id !== latestId;
  // The active member's parent (the immediately-prior version) — threaded to
  // FilesTab for the base-version "From v{n-1}" section (B3 / POR §5 D6). The
  // parent is v{activeIdx} (0-based index of the active member == the parent's
  // 1-based version number).
  const activeParentRunId = sortedMembers.find((m) => m.id === activeRunId)?.parent_run_id ?? null;

  const handleSelectVersion = useCallback(async (memberId: string) => {
    if (memberId === latestId) {
      setViewingVersion(null); // back to live
      return;
    }
    const token = getToken();
    try {
      const run = await getWorkflow(token || "", memberId);
      setViewingVersion({ id: memberId, content: run.output });
    } catch {
      // Read-only view is best-effort — never throw into the preview surface.
      setViewingVersion(null);
    }
  }, [latestId]);

  const handleBackToLatest = useCallback(() => setViewingVersion(null), []);

  // A revision completed → the threaded family grew: tick the chip label with a
  // one-shot animate-pulse (~1200ms), then clear.
  useEffect(() => {
    const count = runFamily?.members.length ?? 0;
    if (prevMemberCount.current != null && count > prevMemberCount.current) {
      setPulse(true);
      const t = setTimeout(() => setPulse(false), 1200);
      prevMemberCount.current = count;
      return () => clearTimeout(t);
    }
    prevMemberCount.current = count;
  }, [runFamily?.members.length]);

  // A new live run supersedes any active read-only view.
  useEffect(() => { setViewingVersion(null); }, [liveRunId]);

  const detectedType: WorkflowType = workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  // Normalize revision types to their base type for rendering
  const renderType = detectedType === "user_stories_revision" ? "user_stories"
    : detectedType === "ppt_revision" ? "ppt"
    : detectedType === "od_ppt" ? "ppt"
    : detectedType === "od_ppt_revision" ? "ppt"
    : detectedType === "prototype_revision" ? "prototype"
    : detectedType === "od_prototype" ? "prototype"
    : detectedType === "app_builder_revision" ? "app_builder"
    : detectedType;

  // ─── B3 (POR §5 D5) — read-only older-version override ───────────────────────
  // When an older version is being viewed read-only, route its fetched .output
  // into the slot matching renderType (user_stories/app_builder → userStory,
  // ppt → ppt, prototype → prototype); otherwise the live content flows through
  // unchanged. onRevise* are suppressed while viewing older (read-only).
  const overrideActive = viewingVersion != null;
  const overrideContent = viewingVersion?.content;
  const effUserStoryContent = overrideActive && (renderType === "user_stories" || renderType === "app_builder") ? overrideContent : userStoryContent;
  const effPptContent = overrideActive && renderType === "ppt" ? overrideContent : pptContent;
  const effPrototypeContent = overrideActive && renderType === "prototype" ? overrideContent : prototypeContent;

  const activeContent =
    renderType === "user_stories" || renderType === "app_builder"
      ? effUserStoryContent
      : renderType === "ppt"
      ? effPptContent
      : effPrototypeContent;

  // ─── ISS-021 (18-03) — generic deliverable fallback ─────────────────────────
  // The generic mimetype-dispatched renderer is taken ONLY when `renderType`
  // matches NONE of the known render branches AND a generic deliverable is
  // present. This is the structural "no known branch matched" fallback — never a
  // workflow-name check (SC-001). The four bespoke renderers below are untouched.
  // CR-01 (18 review fix): `custom` is NO LONGER a known render type — the live
  // agent-composer's `custom` deliverable now flows into the generic
  // mimetype-dispatched channel (text/html → sandboxed iframe), exactly mirroring
  // the reopen surface. Keeping `custom` here routed it to MarkdownPreview and
  // escaped HTML — the contradiction the phase was chartered to remove.
  const KNOWN_RENDER_TYPES = ["user_stories", "ppt", "prototype", "app_builder"] as const;
  const isKnownRenderType = (KNOWN_RENDER_TYPES as readonly string[]).includes(renderType);
  const hasGenericDeliverable = !isKnownRenderType && !!genericDeliverable?.content;

  const hasContent = !!(effUserStoryContent || effPptContent || effPrototypeContent || pptxCode || hasGenericDeliverable);

  // ─── ISS-017 (16-04) — terminal-empty degraded/failed affordance ────────────
  // A TERMINAL run (not streaming) with no content must show a failure
  // affordance, not the neutral "Output will appear here". The signal MUST come
  // from the server, never a client-side `terminal && !content` guess (the
  // REJECTED hack — re-creates the IN-03 FE-vs-DB disagreement and mislabels a
  // legitimately-empty completed run). The server-derived sources are:
  //   • live path  — pipelineState.failed (pipeline_failed) or .degraded
  //     (pipeline_complete status:"degraded"), set by useWorkflow.
  //   • history path — the reopened run's persisted status ("failed"/"cancelled").
  const isStillRunning = !!(isStreaming || pipelineState?.isRunning);
  const isTerminal = !isStillRunning;
  const liveFailureSignal = !!(pipelineState?.failed || pipelineState?.degraded);
  // WR-01 (16 review): "degraded" is a terminal failure-signal status ISS-016 now
  // persists. A degraded run reopened with NO partial deliverable must surface the
  // affordance (CONTEXT A2: on BOTH the live and history paths) — not the neutral
  // empty-state. Keyed on the SERVER status, never a client empty==failed guess.
  const reopenFailureSignal =
    reopenedRunStatus === "failed" ||
    reopenedRunStatus === "cancelled" ||
    reopenedRunStatus === "degraded";
  const terminalFailure = liveFailureSignal || reopenFailureSignal;
  const showFailureAffordance = !hasContent && isTerminal && terminalFailure;
  // IN-03 (16 review): a cancelled run is a deliberate user Stop, not a failure —
  // the affordance copy must say so rather than "failed or degraded". Live cancel
  // carries no failed/degraded flag (useWorkflow resets agents to idle), so the
  // cancelled signal is the reopened server status only.
  const isCancelledTerminal = reopenedRunStatus === "cancelled";
  // NOTE: these are agent IDs (failedAgents/degradedFailedAgents on live;
  // reopenedFailedAgents on history). They are resolved to human names inside
  // DegradedRunAffordance via the agentNameById map built below.
  const failedAgentNames =
    pipelineState?.failedAgents ||
    pipelineState?.degradedFailedAgents ||
    reopenedFailedAgents ||
    [];
  // ISS-024 (16 review IN-02) — id→name lookup for the failed-agents list.
  // LIVE source: pipelineState.agents carries {id,name} for the run's agents.
  // HISTORY-reopen source: reopenedAgentNameById (built by the dashboard from the
  // reopened run detail's persisted agentOutputs, since the live pipelineState
  // reflects the new/idle run and can't name a reopened run's agents).
  // Unknown ids fall back to the raw id inside DegradedRunAffordance.
  const failedAgentNameById = {
    ...(reopenedAgentNameById || {}),
    ...buildAgentNameById(pipelineState?.agents),
  };

  // ─── UXFIX-04 / D-21 (22-07) — generic-primary deliverable dispatch TABLE ────
  // The 4 first-party render types are REGISTERED ENTRIES in a dispatch table
  // keyed on the structural `renderType` (never a workflow name — SC-001). Each
  // entry returns its bespoke renderer ONLY when its content is present; an entry
  // that yields `null` (no first-party content) falls through to the PRIMARY
  // route — the generic mimetype-dispatched renderer (GenericDeliverablePreview).
  // This inverts the legacy "4 branches + generic fallback-last" into
  // "generic-primary + first-party routed entries" with NO visual regression:
  // a first-party type with content renders exactly as before; a custom/unknown
  // type (or a first-party type lacking first-party content) renders via the
  // generic path as the primary route. CR-01 stays intact (`custom` is NOT a
  // first-party entry → it routes generic), as does the P18 sandbox contract
  // (owned by GenericDeliverablePreview).
  // While viewing an older version read-only, suppress the revise affordances
  // (UI-SPEC Surface 3: "revise actions suppressed" for the read-only view).
  const FIRST_PARTY_RENDERERS: Record<string, () => ReactNode | null> = {
    user_stories: () =>
      effUserStoryContent
        ? <UserStoryPreview content={effUserStoryContent} onRevise={overrideActive ? undefined : onReviseUserStory} />
        : null,
    app_builder: () =>
      effUserStoryContent
        ? <AppBuilderIDEPreview content={effUserStoryContent} agentOutputs={agentOutputs} onRevise={overrideActive ? undefined : onReviseAppBuilder} />
        : null,
    ppt: () =>
      (effPptContent || pptxCode)
        ? <PPTPreview content={effPptContent} isStreaming={isStreaming} pptxCode={pptxCode} onRevise={overrideActive ? undefined : onRevisePpt} pipelineType={rawPipelineType || workflowType} />
        : null,
    prototype: () =>
      effPrototypeContent
        ? <PrototypePreview content={effPrototypeContent} isStreaming={isStreaming} onRevise={overrideActive ? undefined : onRevisePrototype} />
        : null,
  };

  const renderDeliverable = (): ReactNode => {
    // 1) First-party routed entry (if this renderType is registered AND its
    //    first-party content is present). A registered entry that yields null
    //    (no first-party content) deliberately falls through to the generic
    //    primary route below.
    const firstParty = FIRST_PARTY_RENDERERS[renderType]?.();
    if (firstParty) return firstParty;

    // 2) PRIMARY route — the generic mimetype-dispatched renderer. Taken for any
    //    custom/unknown deliverable, and for any first-party type that lacked
    //    first-party content but carries a generic deliverable.
    if (genericDeliverable?.content) {
      return <GenericDeliverablePreview deliverable={genericDeliverable} agentOutputs={agentOutputs} />;
    }

    return null;
  };

  const handleTabChange = (tabId: PanelTab) => { setActiveTab(tabId); onTabSelect?.(tabId); };
  const handleCopy = () => {
    if (activeContent) {
      navigator.clipboard.writeText(activeContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white border-l border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900">
          {isStreaming ? "Generating..." : hasContent ? "Results" : "Preview"}
        </h2>
        <div className="flex items-center gap-1">
          {/* B3 (POR §5 D5) — live version chip: first control in the cluster,
              before Copy (UI-SPEC Surface 3 "Where"). Renders nothing unless the
              on-screen content belongs to a ≥2-member revision family. */}
          <LiveVersionChip
            family={runFamily ?? null}
            activeRunId={activeRunId}
            isViewingOlder={isViewingOlder}
            pulse={pulse}
            onSelectVersion={handleSelectVersion}
            onBackToLatest={handleBackToLatest}
          />
          {hasContent && (
            <button
              onClick={handleCopy}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              title="Copy"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
          )}
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="p-1.5 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
              aria-label="Close preview"
            >
              <PanelRightClose className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* B3 (POR §5 D5) — read-only amber banner: shown as a slim strip directly
          under the header while an older version is on screen. */}
      {isViewingOlder && (
        <div className="px-4 py-2 border-b border-gray-200">
          <ReadOnlyVersionBanner versionNumber={activeIdx + 1} onBackToLatest={handleBackToLatest} />
        </div>
      )}

      {/* Tab Bar — tabs on left, PPT action buttons on right when PPT is active */}
      <div className="px-4 py-2 border-b border-gray-200 flex items-center justify-between gap-2">
        <div className="flex gap-0.5 bg-gray-100 rounded-md p-0.5 w-fit">
          {TAB_CONFIG.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-all ${
                  isActive ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <Icon className="h-3 w-3" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* PPT action buttons — shown only when PPT preview is active */}
        {activeTab === "preview" && renderType === "ppt" && (pptContent || pptxCode) && (
          <PPTTabActions
            content={pptContent}
            pptxCode={pptxCode}
            isOdPpt={
              rawPipelineType === "od_ppt" || rawPipelineType === "od_ppt_revision" ||
              detectedType === "od_ppt" || detectedType === "od_ppt_revision"
            }
          />
        )}
      </div>

      {/* Tab Content */}
      <div className="relative flex-1 min-h-0 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "preview" && (
            <motion.div
              key="preview"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 overflow-y-auto"
            >
              {showFailureAffordance ? (
                <DegradedRunAffordance
                  failedAgents={failedAgentNames}
                  agentNameById={failedAgentNameById}
                  onRetry={onRevisePrototype || onRevisePpt || onReviseUserStory || onReviseAppBuilder}
                  cancelled={isCancelledTerminal}
                />
              ) : !hasContent ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs text-gray-400">Output will appear here</p>
                </div>
              ) : (
                // ─── UXFIX-04 / D-21 (22-07) — generic-primary dispatch TABLE ──
                // The deliverable renderer is dispatched through a single table
                // where the generic mimetype-dispatched renderer is the PRIMARY
                // route and the 4 first-party types are registered routed entries
                // the dispatcher routes to (NOT 4 branches + a fallback-last
                // generic). Dispatch is keyed on `renderType` (a structural
                // render-shape), never a workflow NAME — a brand-new workflow
                // renders via the generic path with zero new branch (SC-001).
                // No visual regression: each first-party entry renders the exact
                // same bespoke renderer as before; the generic entry preserves
                // the CR-01 fix + the P18 sandboxed-iframe security contract.
                <>{renderDeliverable()}</>
              )}
            </motion.div>
          )}
          {activeTab === "files" && (
            <motion.div
              key="files"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <FilesTab workflowType={renderType} userStoryContent={userStoryContent} pptContent={pptContent} prototypeContent={prototypeContent} agentOutputs={agentOutputs} genericDeliverable={hasGenericDeliverable ? genericDeliverable : undefined} parentRunId={activeParentRunId} parentVersionNumber={activeIdx} />
            </motion.div>
          )}
          {activeTab === "thinking" && (
            <motion.div
              key="thinking"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <AgentThinkingTab agents={agents || []} pipelineState={pipelineState} />
            </motion.div>
          )}
          {activeTab === "audit" && (
            <motion.div
              key="audit"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <AuditTab
                hookRuns={pipelineState?.hookRuns}
                workflowRunId={pipelineState?.pipelineRunId}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── PPT action buttons shown in the tab bar ───────────────────────────────────

function PPTTabActions({
  content,
  pptxCode,
  isOdPpt,
}: {
  content?: string;
  pptxCode?: string;
  isOdPpt: boolean;
}) {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadHtml = useCallback(() => {
    if (!content) return;
    let html = content.trim();
    if (html.startsWith("```")) {
      html = html.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "presentation.html";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [content]);

  const handleDownloadPptx = useCallback(async () => {
    setIsDownloading(true);
    try {
      const token = getToken();
      let pptTitle = "Presentation";
      if (content) {
        const titleMatch = content.match(/<title>([^<]+)<\/title>/i);
        if (titleMatch && titleMatch[1] !== "Presentation") pptTitle = titleMatch[1].trim();
      }
      let workflowId = "";
      try {
        const res = await fetch(`${ENV.API_URL}/api/runs?type=ppt&limit=5`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const runs = await res.json();
          if (runs.length > 0) workflowId = runs[0].id;
        }
      } catch { /* ignore */ }
      const response = await fetch(`${ENV.API_URL}/api/runs/export-pptx`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ js_code: pptxCode || "", html: content || "", workflow_id: workflowId, title: pptTitle }),
      });
      if (!response.ok) throw new Error("Export failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${pptTitle.replace(/[^a-zA-Z0-9\s-]/g, "").trim().replace(/\s+/g, "_") || "Presentation"}.pptx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PPTX download failed:", err);
      alert("Download failed. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  }, [content, pptxCode]);

  const handleFullScreen = useCallback(() => {
    if (!content) return;
    let html = content.trim();
    if (html.startsWith("```")) {
      html = html.replace(/^```(?:html)?\s*\n?/, "").replace(/\n?```\s*$/, "");
    }
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [content]);

  return (
    <div className="flex items-center gap-1.5 flex-shrink-0">
      {isOdPpt ? (
        <button
          onClick={handleDownloadHtml}
          className="flex items-center gap-1.5 rounded-md bg-[#1B2A4A] px-2.5 py-1 text-[11px] font-medium text-white hover:bg-[#2a3d5e] transition-colors"
        >
          <Download className="h-3 w-3" />
          Download
        </button>
      ) : (
        <button
          onClick={handleDownloadPptx}
          disabled={isDownloading}
          className="flex items-center gap-1.5 rounded-md bg-[#1B2A4A] px-2.5 py-1 text-[11px] font-medium text-white hover:bg-[#2a3d5e] disabled:opacity-60 transition-colors"
        >
          {isDownloading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
          {isDownloading ? "Exporting…" : "Download"}
        </button>
      )}
      <button
        onClick={handleFullScreen}
        className="flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1 text-[11px] text-gray-500 hover:border-gray-300 hover:text-gray-800 transition-colors"
        title="Open in new tab"
      >
        <ExternalLink className="h-3 w-3" />
        Full Screen
      </button>
    </div>
  );
}
