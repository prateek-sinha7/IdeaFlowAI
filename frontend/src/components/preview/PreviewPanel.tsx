"use client";

import { useEffect, useState, useMemo, useCallback, useRef, type ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, Brain, Shield, Download, ExternalLink, Loader2, AlertTriangle } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { MarkdownPreview } from "./MarkdownPreview";
import { FilesTab, downloadBlob, deriveDeliverableFilename } from "@/components/results/FilesTab";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { AuditTab } from "@/components/results/AuditTab";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";
import { ReadOnlyVersionBanner } from "./ReadOnlyVersionBanner";
// Phase 39 (RUNUI-06/07) — the mock's browser-chrome frame that WRAPS the reused
// deliverable renderer (ND-G) with a real-filename URL bar (ND-D) + the "Renders
// as" segmented type switch. A passive frame — no content rendering here.
import { PreviewChrome, RendersAsSwitch } from "./PreviewChrome";
// Phase 39 (RUNUI-06/07) — the mock's right-column run header (Version menu /
// Share / Download / status badge) mounts above the tab row. It supersedes the
// old in-preview version pill (INV-3/INV-12 — one version affordance).
import { RunHeader } from "./RunHeader";
import type { RunLaneState } from "@/components/chat/RunChatLane";
// Phase 32 (plan 07) — shared run-screen underline-tab primitive (SC-1, D-15).
import { Tabs } from "@/components/ui/Tabs";
import type { WorkflowType, GenericDeliverable, RunFamily } from "@/types/index";
import type { TabDeepLinkTarget } from "@/hooks/useTabDeepLink";
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
    // presentation.html from a custom-composer PPT run → PPTPreview for the
    // styled deck viewer with navigation chrome. Keyed on filename (SC-001).
    if (deliverable.filename === "presentation.html") {
      return <PPTPreview content={content} isStreaming={false} pipelineType="od_ppt" onRevise={undefined} />;
    }
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

  // Markdown (or markdown-ish text) → check filename first for typed renderers,
  // then fall back to plain MarkdownPreview.
  if (mimetype === "text/markdown" || mimetype === "text/x-markdown" || mimetype.startsWith("text/markdown")) {
    // user_stories.md → UserStoryPreview (structured epic/story cards with
    // Given/When/Then blocks). Keyed on filename, not workflow name (SC-001).
    if (deliverable.filename === "user_stories.md") {
      return <UserStoryPreview content={content} />;
    }
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
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-warm">
          <FolderDown className="h-6 w-6 text-ink-500" />
        </div>
        <p className="text-sm font-semibold text-ink-900">Deliverable ready</p>
        <p className="text-xs text-ink-500">
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
          className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-line-border px-3 py-1.5 text-xs font-medium text-ink-700 transition-colors hover:bg-surface-warm"
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
  // Workstream C2 (POR §5 D3+D4+D7) — pass-throughs for the "Run input" surfaces.
  // The live path already carries clarify rounds via pipelineState.clarifications;
  // the explicit `clarifications` prop is the reopen override (?? keeps both
  // correct). BOTH optional/default-undefined → existing renders unchanged.
  runInput?: string;
  clarifications?: import("@/types/index").ClarifyRound[];
  // Phase 31 (CHATUI-02) — the nonce'd deep-link target a chat result-card mints
  // via useTabDeepLink.requestOpenTab (borrow #6). PreviewPanel is the CONSUMER:
  // an effect keyed on the nonce switches to the target tab for ALL panel tabs
  // (the legacy initialTab only honored preview/files). The monotonic nonce
  // makes a repeat deep-link to an already-open tab re-fire; a non-panel target
  // (e.g. "steps" = the left lane column) is ignored here. Optional/default-null
  // → existing renders unchanged (tsc-identity).
  deepLinkTarget?: TabDeepLinkTarget | null;
  // Phase 32 (plan 06 → 07/08) — additive optional passthrough of the run's
  // active gate + clarify quick-action context so a future Steps surface can
  // mount the same inline gate/clarify affordances the RunChatLane composer
  // uses. Pinned to the existing GateContext / ClarifyQuestion / ClarifyResponse
  // shapes (name-free, SC-001); default undefined → zero behavior change until
  // plan 07/08 consumes them (tsc-identity, no regression for history/test callers).
  laneGate?: import("@/components/chat/RunChatLane").GateContext;
  onApproveGate?: (gateKey: string, editedContent?: string) => void;
  onRejectGate?: (gateKey: string) => void;
  onRedoGate?: (gateKey: string, instructions: string) => void;
  onUpdateSpecsGate?: (gateKey: string, report: string) => void;
  clarifyQuestions?: import("@/types/index").ClarifyQuestion[];
  onSubmitClarify?: (
    responses: import("@/components/chat/InlineClarifyActions").ClarifyResponse[],
  ) => void;
  onSkipClarify?: () => void;
  /** Cancel the active pipeline from the inline Steps clarify (Phase 42-02 §A2 re-home). */
  onCancelWorkflow?: () => void;
  // Phase 32 (plan 08 / ISS-019) + Phase 39/42-04 — the live wave/subagent
  // groups, forwarded to the Steps drill-down where AgentDetailPanel's inline
  // construction/wave tree renders them (the separate WaveTreePanel was retired,
  // INV-12). Optional/default-empty (tsc-identity).
  waves?: import("@/types/index").WaveGroup[];
  // Phase 39 (RUNUI-06/07) — run-header action wiring. Both optional/default-
  // undefined so history + test renders are byte-unchanged (tsc-identity), and
  // both have sensible in-component defaults. onShare copies the run deep link
  // (ND-H, client-only — NO backend); onDownload downloads the primary deliverable.
  onShare?: () => void;
  onDownload?: () => void;
}

// Phase 39 (RUNUI-06 / D39 specifics #3) — tab order is Preview · Steps · Files ·
// Audit (was Preview · Files · Steps · Audit). The internal id stays "thinking"
// so the deep-link targets + tab testids (data-testid="tab-thinking") remain
// stable; the "Thinking"→"Steps" relabel (Phase 32 plan 07) is preserved. The
// mock's tab row is text-only, so the per-tab lucide icons are dropped here to
// match (a Steps review-dot is threaded in instead when the run is paused).
const TAB_CONFIG: { id: PanelTab; label: string; icon: typeof Eye }[] = [
  { id: "preview", label: "Preview", icon: Eye },
  { id: "thinking", label: "Steps", icon: Brain },
  { id: "files", label: "Files", icon: FolderDown },
  { id: "audit", label: "Audit", icon: Shield },
];

// The generic tab ids PreviewPanel owns. A deep-link to any of these switches the
// tab; other generic targets (e.g. "steps") belong to the left lane column.
const PANEL_TAB_IDS: readonly PanelTab[] = ["preview", "files", "thinking", "audit"];

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
        <p className="text-sm font-semibold text-ink-900">
          {cancelled
            ? "This run was cancelled"
            : "This run did not complete successfully"}
        </p>
        <p className="text-xs text-ink-500">
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
            className="mt-1 inline-flex items-center gap-1.5 rounded-md border border-line-border px-3 py-1.5 text-xs font-medium text-ink-700 transition-colors hover:bg-surface-warm"
          >
            View details / retry
          </button>
        ) : (
          <p className="mt-1 text-[11px] text-ink-400">
            Open the Thinking tab to view details.
          </p>
        )}
      </div>
    </div>
  );
}

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, genericDeliverable, isStreaming, initialTab, onTabSelect, workflowType, rawPipelineType, pptxCode, onRevisePpt, onReviseUserStory, onRevisePrototype, onReviseAppBuilder, agentOutputs, agents, pipelineState, reopenedRunStatus, reopenedFailedAgents, reopenedAgentNameById, runFamily, liveRunId, runInput, clarifications, deepLinkTarget, laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate, clarifyQuestions, onSubmitClarify, onSkipClarify, onCancelWorkflow, waves, onShare, onDownload }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  // ─── Plan 07 — manual typed-renderer switcher override ───────────────────────
  // null = follow the generic auto-dispatch (the PRIMARY route); a non-null value
  // is a renderType/mimetype token (SC-001, never a workflow name) that FORCES a
  // specific renderer for the current deliverable. Cleared back to auto on demand
  // (the "Auto" option) and whenever the deliverable's renderType changes.
  const [rendererOverride, setRendererOverride] = useState<string | null>(null);
  // ─── B3 (POR §5 D5) — read-only older-version state ─────────────────────────
  // viewingVersion is the read-only older-version override ({ id, content }) or
  // null (live latest on screen). The version affordance itself now lives in the
  // Phase-39 RunHeader Version menu (INV-12 — the old version-pill pulse tick is
  // retired with it).
  const [viewingVersion, setViewingVersion] = useState<{ id: string; content?: string } | null>(null);
  // Phase 42-02 (§B / RUNUI-06) — latch for the state-keyed default-tab effect: the
  // last generic run-state we auto-applied a tab for. Keyed on the state VALUE so the
  // auto-select fires once per state transition and never overrides a later manual
  // tab click within the same state (mirrors the initialTab effect idiom below).
  const autoTabbedForState = useRef<string | null>(null);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  // Phase 31 (CHATUI-02) — nonce'd deep-link consumer (borrow #6). A chat
  // result-card click mints a fresh {tab, nonce}; switch to the target tab for
  // ALL panel tabs (preview/files/thinking/audit) — one switch per click. The
  // effect is keyed on the monotonic nonce, so a repeat deep-link to the
  // already-active tab still re-fires, and a stale nonce cannot re-navigate. A
  // non-panel target (e.g. "steps", owned by the left lane column) is ignored.
  useEffect(() => {
    const tab = deepLinkTarget?.tab;
    if (tab && (PANEL_TAB_IDS as readonly string[]).includes(tab)) {
      setActiveTab(tab as PanelTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkTarget?.nonce]);

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
  // ─── C-FLAG-1 + C-FLAG-2 (260703-174) — live StartingPointCard revision wiring ─
  // revisionParentVersion = the 1-based family index of the active run's PARENT
  // (the "revision of v{n}" chip). For a linear chain this coincides with the
  // existing activeIdx note above; the parent_run_id lookup is robust for branched
  // families. originalBriefRootRunId is threaded ONLY when the active member IS a
  // revision (non-null parent) — matching the reopen mount's guard — so the live
  // "Original brief (v1)" expander appears (live/reopen symmetry).
  const activeParentIdx = activeParentRunId ? sortedMembers.findIndex((m) => m.id === activeParentRunId) : -1;
  const revisionParentVersion = activeParentIdx >= 0 ? activeParentIdx + 1 : undefined;
  const originalBriefRootRunId = activeParentRunId ? runFamily?.root_id : undefined;

  const handleSelectVersion = useCallback(async (memberId: string) => {
    if (memberId === latestId) {
      setViewingVersion(null); // back to live
      return;
    }
    const token = getToken();
    try {
      const run = await getWorkflow(token || "", memberId);
      setViewingVersion({ id: memberId, content: run.output });
    } catch (err) {
      // Read-only view is best-effort — never throw into the preview surface.
      // Dev-observability only: log the swallowed failure; fallback unchanged.
      console.warn("[revision-family] read-only version fetch failed", err);
      setViewingVersion(null);
    }
  }, [latestId]);

  const handleBackToLatest = useCallback(() => setViewingVersion(null), []);

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
  // BUG-008: on a terminal reopen the `isRunning`-gated workflowType binder never
  // fires, so `renderType` sits at the stale "user_stories" default →
  // `isKnownRenderType` is true and the old `!isKnownRenderType && …` gate starved
  // `hasGenericDeliverable` → the Preview short-circuited to "Output will appear
  // here". Decouple the signal from the stale gate: a present generic deliverable
  // counts whenever the typed renderer for the (possibly-stale) renderType has
  // nothing to show. Keys only on the generic typed-content slots + the structural
  // isKnownRenderType check — NO workflow-name literal (SC-001).
  const knownContentPresent = !!(effUserStoryContent || effPptContent || effPrototypeContent || pptxCode);
  const hasGenericDeliverable = !!genericDeliverable?.content && (!isKnownRenderType || !knownContentPresent);

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
  // ─── Phase 42-03 (§D / Group D) — terminal-FAILED run surface ────────────────
  // A terminal FAILED run (failed/degraded with NO deliverable, and NOT a
  // deliberate cancel) matches the Failed mock: tabs become [Steps, Audit, Files]
  // with NO Preview surface, the default tab is Audit, and the amber
  // DegradedRunAffordance is retired on the run screen (red, not amber, lives in
  // the lane + Steps + header — all §4 KEEP). Keyed on the generic terminal-
  // failure signal (SC-001 — never a workflow/agent-name literal). A failed run
  // that still carries content keeps its Preview tab (content wins), and a
  // cancelled run keeps its Preview affordance (§8 decision 4 — history untouched).
  const terminalFailureNoDeliverable = showFailureAffordance && !isCancelledTerminal;
  // Cancelled-terminal is the ONLY remaining consumer of the in-Preview
  // DegradedRunAffordance mount on the run screen (failed/degraded drop the tab).
  const showCancelledAffordance = showFailureAffordance && isCancelledTerminal;
  // Drop the Preview tab for a terminal-failed run; every other state keeps the
  // full four-tab set (Preview · Steps · Files · Audit).
  const visibleTabs = terminalFailureNoDeliverable
    ? TAB_CONFIG.filter((t) => t.id !== "preview")
    : TAB_CONFIG;
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

  // ─── Phase 39 (RUNUI-06/07) — run-header state derivation ────────────────────
  // The header keys off the SAME generic discriminator the lane uses (SC-001,
  // mirrors DashboardLayout.runLaneState): gate (an active review gate while
  // running) → clarify (open questions while running) → building (running) →
  // terminal (a server failure signal) → complete (a settled deliverable) → idle.
  // Never a workflow-name branch.
  const hasActiveGate = !!laneGate && isStillRunning;
  const hasOpenClarify = !!(clarifyQuestions && clarifyQuestions.length > 0) && isStillRunning;
  const headerFailed = terminalFailure && !isCancelledTerminal;
  const headerRunState: RunLaneState =
    hasActiveGate ? "gate" :
    hasOpenClarify ? "clarify" :
    isStillRunning ? "building" :
    headerFailed ? "terminal" :
    hasContent ? "complete" :
    "idle";
  // The Steps tab shows a pulsing review dot while the run is paused on the user
  // (an open gate or clarify round) — mirrors the mock's Live "review gate" dot.
  const stepsReviewDot = headerRunState === "gate" || headerRunState === "clarify";

  // ─── Phase 42-02 (§B / RUNUI-06) — state-keyed default tab ────────────────────
  // Auto-select the correct tab whenever the run transitions to a new generic state
  // (SC-001: keyed on headerRunState, NEVER a workflow/agent-name literal):
  //   gate | clarify | building (live, incl. planning) → Steps ("thinking")
  //   complete (settled deliverable)                    → Preview ("preview")
  //   terminal-failed (no deliverable)                  → Audit ("audit")
  //   terminal-failed WITH content | idle               → leave as-is
  // The autoTabbedForState latch makes this fire ONCE per state transition, so a
  // user's manual tab click within the same state is never clobbered on re-render.
  //
  // Phase 42-03 (§D / Group D): the Failed mock defaults to Audit (Hexaware Run -
  // Failed tab:'audit') and has NO Preview surface. A terminal FAILED run with no
  // deliverable now drops the Preview tab (visibleTabs) AND lands on Audit here.
  // The latch keys on a generic discriminator that folds the failed-no-deliverable
  // state into "failed" so the auto-select fires for it; a failed run that still
  // carries content keeps Preview (content wins) and is left as-is.
  const defaultTabDiscriminator = terminalFailureNoDeliverable ? "failed" : headerRunState;
  useEffect(() => {
    if (autoTabbedForState.current === defaultTabDiscriminator) return;
    autoTabbedForState.current = defaultTabDiscriminator;
    const target: PanelTab | null =
      defaultTabDiscriminator === "failed" ? "audit" :
      headerRunState === "complete" ? "preview" :
      (headerRunState === "gate" || headerRunState === "clarify" || headerRunState === "building") ? "thinking" :
      null;
    if (target) setActiveTab(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultTabDiscriminator]);
  // Live version label — derived from the live family (active member index) or the
  // pipeline's deliverableVersion; default v1. NEVER the mock's fixed "v1"/"v2".
  const familyVersionCount = runFamily?.members.length ?? 0;
  const derivedVersionNumber =
    activeIdx >= 0 ? activeIdx + 1
      : pipelineState?.deliverableVersion ?? (familyVersionCount > 0 ? familyVersionCount : 1);
  const headerVersionLabel = `v${derivedVersionNumber}`;
  // Live building-badge inputs (generic/live — the current running agent name +
  // step k of N from the live pipeline counts).
  const headerAgents = pipelineState?.agents ?? [];
  const currentAgentName = headerAgents.find((a) => a.status === "running")?.name;
  const buildStepTotal = headerAgents.length || undefined;
  const buildStepIndex = buildStepTotal
    ? Math.min((pipelineState?.completedCount ?? 0) + 1, buildStepTotal)
    : undefined;

  // Failed-badge reason (ND ruling 2026-07-11) — name WHERE the run stopped using
  // the SAME live signal the lane's failure card uses (resolveAgentNames on the
  // failed-agent ids, already in scope above). Generic + live (ND-D): the first
  // failed agent's human name (raw-id fallback), NEVER the mock's fixed "security
  // gate" text. Empty → the badge stays the bare "Run failed".
  const headerFailureReason = headerFailed
    ? resolveAgentNames(failedAgentNames, failedAgentNameById)[0]
    : undefined;

  // Client-only Share (ND-H) — copy the owner-auth-gated run deep link. Composed
  // from the live run id; NO backend call. Default provided here so the header is
  // functional even when the caller does not override it.
  const handleHeaderShare = useCallback(() => {
    if (onShare) return onShare();
    const runId = liveRunId ?? activeRunId ?? "";
    if (!runId || typeof window === "undefined") return;
    const link = `${window.location.origin}${window.location.pathname}?run=${encodeURIComponent(runId)}`;
    void navigator.clipboard?.writeText(link);
  }, [onShare, liveRunId, activeRunId]);

  // Primary deliverable download — reuses FilesTab.downloadBlob (INV-12). Default
  // downloads the on-screen deliverable content under its live filename.
  // KAN-128 (FIX-140): use deriveDeliverableFilename so the downloaded name
  // always matches what the Files tab shows (content-derived, word-boundary-safe).
  const canHeaderDownload = headerRunState === "complete" && !!activeContent;
  const handleHeaderDownload = useCallback(() => {
    if (onDownload) return onDownload();
    if (!activeContent) return;
    const name = deriveDeliverableFilename(
      rawPipelineType || workflowType || "user_stories",
      activeContent,
      pipelineState?.deliverableFilename || `deliverable-${headerVersionLabel}.md`,
    );
    // Derive the correct mimetype from the extension.
    const ext = name.split(".").pop()?.toLowerCase() || "md";
    const mimeMap: Record<string, string> = {
      html: "text/html",
      pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      md: "text/markdown",
      zip: "application/zip",
    };
    downloadBlob(activeContent, name, mimeMap[ext] || "text/markdown");
  }, [onDownload, activeContent, rawPipelineType, workflowType, pipelineState?.deliverableFilename, headerVersionLabel]);

  // ─── Phase 39 (RUNUI-06/07) — PreviewChrome URL bar + open affordance ────────
  // The REAL deliverable filename for the browser-chrome URL bar (ND-D live — the
  // live deliverable name, the generic deliverable's filename, else a derived name;
  // NEVER the mock's fixed "index.html").
  // KAN-128 (FIX-140): use deriveDeliverableFilename so the URL bar always agrees
  // with the Files tab (content-derived, word-boundary-safe truncation).
  const previewFilename = deriveDeliverableFilename(
    rawPipelineType || workflowType || "user_stories",
    activeContent,
    pipelineState?.deliverableFilename ||
      genericDeliverable?.filename ||
      `deliverable-${headerVersionLabel}`,
  );
  // The chrome's open-in-new affordance — opens the on-screen deliverable in a new
  // tab via a client-only blob URL (the same pattern PPTTabActions.handleFullScreen
  // uses; NO network, no new surface). The chrome itself stays a passive frame.
  const handlePreviewOpen = useCallback(() => {
    const content = genericDeliverable?.content ?? activeContent;
    if (!content || typeof window === "undefined") return;
    const mimetype =
      genericDeliverable?.mimetype ||
      (renderType === "ppt" || renderType === "prototype" ? "text/html" : "text/markdown");
    const blob = new Blob([content], { type: mimetype });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [genericDeliverable?.content, genericDeliverable?.mimetype, activeContent, renderType]);

  // ─── ND-V (Option B ruling 2026-07-11) — self-chromed renderers ──────────────
  // prototype (its own dots + prototype.preview URL + Tweaks/Source/Open) and
  // app_builder (AppBuilderIDEPreview — a full FileTree + editor IDE) bring their
  // OWN frame; wrapping them in our PreviewChrome browser frame doubled it. Skip
  // our chrome for those two EFFECTIVE types (a forced override matches what
  // actually renders), keeping the "Renders as" switch above the renderer.
  const effectiveRenderType = rendererOverride ?? renderType;
  const isSelfChromedRender =
    effectiveRenderType === "prototype" || effectiveRenderType === "app_builder";

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

  // ─── Plan 07 — typed-renderer switcher (manual override on top of dispatch) ──
  // A new deliverable (renderType change) drops any stale override so the generic
  // auto-dispatch resumes as the PRIMARY route.
  useEffect(() => { setRendererOverride(null); }, [renderType]);

  // Mimetype tokens the generic renderer can be forced into. These are DECLARED
  // mimetype/render shapes (SC-001 — never a workflow name).
  const MIMETYPE_OVERRIDES: Record<string, string> = {
    html: "text/html",
    markdown: "text/markdown",
    zip: "application/zip",
  };
  const FIRST_PARTY_LABELS: Record<string, string> = {
    user_stories: "User Stories",
    ppt: "Slides",
    prototype: "Prototype",
    app_builder: "Code",
  };
  const MIMETYPE_LABELS: Record<string, string> = {
    html: "HTML",
    markdown: "Markdown",
    zip: "Bundle",
  };

  // Switcher options — the set of typed renderers available for THIS deliverable,
  // derived from the generic renderType/mimetype set (never a workflow name).
  // Always leads with "Auto" (the generic auto-dispatch, i.e. no override).
  const rendererOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = [{ value: "auto", label: "Auto" }];
    // The current first-party renderType is an explicit typed option when it has
    // a registered renderer.
    if (renderType in FIRST_PARTY_RENDERERS && FIRST_PARTY_LABELS[renderType]) {
      opts.push({ value: renderType, label: FIRST_PARTY_LABELS[renderType] });
    }
    // A generic deliverable can be viewed through any of the mimetype renderers.
    if (genericDeliverable?.content) {
      for (const key of Object.keys(MIMETYPE_OVERRIDES)) {
        opts.push({ value: key, label: MIMETYPE_LABELS[key] });
      }
    }
    return opts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderType, genericDeliverable?.content]);

  // Resolve a manual override value → a concrete renderer. First-party tokens
  // route to their registered renderer; mimetype tokens re-run the generic
  // renderer with the forced mimetype (preserving the P18 sandboxed-iframe
  // contract owned by GenericDeliverablePreview). Returns null when the override
  // cannot render the current content, so the caller falls back to the primary
  // auto-dispatch.
  const renderRendererOverride = (value: string): ReactNode | null => {
    if (value in FIRST_PARTY_RENDERERS) {
      return FIRST_PARTY_RENDERERS[value]?.() ?? null;
    }
    const mimetype = MIMETYPE_OVERRIDES[value];
    if (!mimetype) return null;
    const content = genericDeliverable?.content ?? activeContent ?? "";
    if (!content) return null;
    const forced: GenericDeliverable = { ...(genericDeliverable ?? {}), content, mimetype };
    return <GenericDeliverablePreview deliverable={forced} agentOutputs={agentOutputs} />;
  };

  const renderDeliverable = (): ReactNode => {
    // 0) MANUAL OVERRIDE (plan 07) — the typed-renderer switcher. Layered ON TOP
    //    of the generic dispatch: when the user has picked a specific renderer it
    //    forces that one. When unset ("auto") the generic dispatch below runs
    //    UNCHANGED as the PRIMARY route (the switcher never replaces or reorders
    //    it). The override value is a renderType/mimetype token (SC-001).
    if (rendererOverride && rendererOverride !== "auto") {
      const forced = renderRendererOverride(rendererOverride);
      if (forced) return forced;
      // Override can't render this content → fall through to the primary route.
    }

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

  return (
    <div className="flex h-full flex-col bg-surface-paper">
      {/* Phase 39 (RUNUI-06/07) — the mock's right-column run header row (Version
          menu / Share / Download in the settled state; a status badge + version
          chip in the live/failed states). Supersedes the old title+Copy+Collapse
          header AND the old in-preview version pill (INV-3/INV-12: one version
          affordance). Styling routes through the Phase-32 token layer. */}
      <RunHeader
        runState={headerRunState}
        failed={headerFailed}
        failureReason={headerFailureReason}
        family={runFamily ?? null}
        activeRunId={activeRunId}
        versionLabel={headerVersionLabel}
        onSelectVersion={handleSelectVersion}
        onShare={handleHeaderShare}
        onDownload={handleHeaderDownload}
        canDownload={canHeaderDownload}
        currentAgentName={currentAgentName}
        buildStepIndex={buildStepIndex}
        buildStepTotal={buildStepTotal}
        clarifyCount={clarifyQuestions?.length}
      />

      {/* B3 (POR §5 D5) — read-only amber banner: shown as a slim strip directly
          under the header while an older version is on screen. */}
      {isViewingOlder && (
        <div className="px-[30px] pt-3">
          <ReadOnlyVersionBanner versionNumber={activeIdx + 1} onBackToLatest={handleBackToLatest} />
        </div>
      )}

      {/* Tab Bar — Phase 39: the mock's text-only tab row (Preview · Steps ·
          Files · Audit, 30px gutter, 2px brand underline via the Tabs primitive).
          The per-tab lucide icons are dropped to match the mock; the Steps tab
          carries a pulsing review dot while the run is paused on the user (an open
          gate / clarify round). PPT actions + the renderer switcher live in the
          right cluster. */}
      <div className="flex-none px-[30px] pt-4 flex items-center justify-between gap-2 border-b border-line-divider">
        <Tabs
          tabs={visibleTabs.map((tab) => ({
            id: tab.id,
            label: tab.label,
            icon:
              tab.id === "thinking" && stepsReviewDot ? (
                <span
                  aria-hidden
                  data-testid="steps-review-dot"
                  className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand"
                />
              ) : undefined,
          }))}
          active={activeTab}
          onChange={(id) => handleTabChange(id as PanelTab)}
        />

        <div className="flex items-center gap-2">
          {/* Phase 39 (RUNUI-07) — the renderer switcher was RESKINNED into the
              PreviewChrome's "Renders as" segmented row (below the browser top bar),
              replacing the old tab-bar <select>. It now surfaces for ANY deliverable
              with more than one genuinely-available typed renderer (segmented
              buttons, so no <option>-role collision with the Version menu). */}

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
              {showCancelledAffordance ? (
                // Phase 42-03 (§D / Group D): the FAILED run's amber
                // DegradedRunAffordance is RETIRED on the run screen — a terminal-
                // failed run now drops the Preview tab entirely (visibleTabs) and
                // defaults to Audit, so this branch is never reached for it. The
                // ONLY remaining consumer is a CANCELLED-terminal run (a deliberate
                // user Stop, §8 decision 4 keeps history/reopen behavior), which
                // keeps its Preview tab and its cancelled-specific affordance copy.
                // DegradedRunAffordance stays exported for RunDetailPage.tsx:296.
                <DegradedRunAffordance
                  failedAgents={failedAgentNames}
                  agentNameById={failedAgentNameById}
                  onRetry={onRevisePrototype || onRevisePpt || onReviseUserStory || onReviseAppBuilder}
                  cancelled={isCancelledTerminal}
                />
              ) : isStillRunning ? (
                // Streaming build — the mock's chrome with a "building …" URL + an
                // indeterminate progress bar (ND-F: no screenshot placeholder). The
                // live renderer streams inside; a calm building state fills until then.
                <PreviewChrome filename={previewFilename} versionLabel={headerVersionLabel} streaming>
                  {hasContent ? (
                    renderDeliverable()
                  ) : (
                    <div className="flex h-full items-center justify-center">
                      <p className="text-xs text-ink-400">Building your deliverable…</p>
                    </div>
                  )}
                </PreviewChrome>
              ) : !hasContent ? (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs text-ink-400">Output will appear here</p>
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
                //
                // Phase 39 (RUNUI-06/07): the settled deliverable is FRAMED in the
                // mock's browser chrome (ND-G — the renderer is WRAPPED, not rebuilt).
                // The "Renders as" switch reuses the existing rendererOptions/
                // rendererOverride dispatch (ND-D live typed set); renderDeliverable()
                // still applies the override, so the pills drive the SAME dispatch.
                //
                // ND-V (Option B ruling 2026-07-11): a SELF-CHROMED renderer
                // (prototype = its own dots/URL/Source/Tweaks/Open; app_builder = a
                // full IDE) brings its OWN frame, so wrapping it in our browser chrome
                // doubled it. For those two EFFECTIVE types we skip our chrome (the
                // renderer's frame is the single frame) but KEEP the "Renders as"
                // switch above. Keyed on the EFFECTIVE type so a forced override
                // matches what actually renders. Plain deliverables keep our chrome.
                isSelfChromedRender ? (
                  <div className="flex h-full flex-col">
                    {rendererOptions.length > 1 && (
                      <RendersAsSwitch
                        rendererOptions={rendererOptions}
                        rendererValue={rendererOverride ?? "auto"}
                        onRendererChange={setRendererOverride}
                      />
                    )}
                    <div className="min-h-0 flex-1">{renderDeliverable()}</div>
                  </div>
                ) : (
                  <PreviewChrome
                    filename={previewFilename}
                    versionLabel={headerVersionLabel}
                    rendererOptions={rendererOptions}
                    rendererValue={rendererOverride ?? "auto"}
                    onRendererChange={setRendererOverride}
                    onOpen={handlePreviewOpen}
                  >
                    {renderDeliverable()}
                  </PreviewChrome>
                )
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
              <FilesTab workflowType={renderType} userStoryContent={userStoryContent} pptContent={pptContent} prototypeContent={prototypeContent} agentOutputs={agentOutputs} genericDeliverable={hasGenericDeliverable ? genericDeliverable : undefined} parentRunId={activeParentRunId} parentVersionNumber={activeIdx} runInput={runInput} clarifications={clarifications ?? pipelineState?.clarifications} onOpenPreview={() => handleTabChange("preview")} runStatus={terminalFailure && !isCancelledTerminal ? "failed" : undefined} isRunning={isStillRunning} buildingTaskIndex={buildStepIndex} buildingTaskTotal={buildStepTotal} buildingFilename={pipelineState?.deliverableFilename} />
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
              <AgentThinkingTab
                agents={agents || []}
                pipelineState={pipelineState}
                waves={waves}
                runInput={runInput}
                clarifications={clarifications ?? pipelineState?.clarifications}
                revisionParentVersion={revisionParentVersion}
                originalBriefRootRunId={originalBriefRootRunId}
                /* Phase 32 (plan 07 → 08) — OPTIONAL gate/clarify passthrough.
                   These are the same GateContext / ClarifyQuestion / callback
                   shapes DashboardLayout (plan 06) now passes to PreviewPanel.
                   They are forwarded to the Steps body so plan 08 can render the
                   inline gate/clarify affordances here; dormant (declared but not
                   yet consumed by AgentThinkingTab) until then — zero behavior
                   change, name-free (SC-001). */
                laneGate={laneGate}
                onApproveGate={onApproveGate}
                onRejectGate={onRejectGate}
                onRedoGate={onRedoGate}
                onUpdateSpecsGate={onUpdateSpecsGate}
                clarifyQuestions={clarifyQuestions}
                onSubmitClarify={onSubmitClarify}
                onSkipClarify={onSkipClarify}
                onCancelWorkflow={onCancelWorkflow}
              />
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
                isRunning={isStillRunning}
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
          className="flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-2.5 py-1 text-[11px] font-medium text-white hover:bg-brand-pressed transition-colors"
        >
          <Download className="h-3 w-3" />
          Download
        </button>
      ) : (
        <button
          onClick={handleDownloadPptx}
          disabled={isDownloading}
          className="flex items-center gap-1.5 rounded-[var(--radius-button)] bg-brand px-2.5 py-1 text-[11px] font-medium text-white hover:bg-brand-pressed disabled:opacity-60 transition-colors"
        >
          {isDownloading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
          {isDownloading ? "Exporting…" : "Download"}
        </button>
      )}
      <button
        onClick={handleFullScreen}
        className="flex items-center gap-1 rounded-md border border-line-border bg-white px-2.5 py-1 text-[11px] text-ink-500 hover:border-line-control hover:text-ink-800 transition-colors"
        title="Open in new tab"
      >
        <ExternalLink className="h-3 w-3" />
        Full Screen
      </button>
    </div>
  );
}
