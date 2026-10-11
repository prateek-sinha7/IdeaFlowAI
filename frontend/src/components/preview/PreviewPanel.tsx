"use client";

import { useEffect, useState, useMemo, useCallback, useRef, type ReactNode } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Eye, FolderDown, FolderTree, Brain, Shield, Download, ExternalLink, Loader2, AlertTriangle } from "lucide-react";
import { UserStoryPreview } from "./UserStoryPreview";
import { PPTPreview } from "./PPTPreview";
import { PrototypePreview } from "./PrototypePreview";
import { MarkdownPreview } from "./MarkdownPreview";
import { FilesTab, downloadBlob, deriveDeliverableFilename, type AgentOutputItem } from "@/components/results/FilesTab";
import { SandboxTab } from "@/components/results/SandboxTab";
import { AgentThinkingTab } from "@/components/results/AgentThinkingTab";
import { AuditTab } from "@/components/results/AuditTab";
import { AppBuilderPreview, type ParsedFile } from "./AppBuilderPreview";
import { ReadOnlyVersionBanner } from "./ReadOnlyVersionBanner";
// Phase 39 (RUNUI-06/07) — the mock's browser-chrome frame that WRAPS the reused
// deliverable renderer (ND-G) with a real-filename URL bar (ND-D) + the "Renders
// as" segmented type switch. A passive frame — no content rendering here.
import { PreviewChrome, RendersAsSwitch } from "./PreviewChrome";
import { useTheme } from "@/hooks/useTheme";
// Phase 39 (RUNUI-06/07) — the mock's right-column run header (Version menu /
// Share / Download / status badge) mounts above the tab row. It supersedes the
// old in-preview version pill (INV-3/INV-12 — one version affordance).
import { RunHeader } from "./RunHeader";
import type { RunLaneState } from "@/components/chat/RunChatLane";
// Phase 32 (plan 07) — shared run-screen underline-tab primitive (SC-1, D-15).
import { Tabs } from "@/components/ui/Tabs";
import type { WorkflowType, GenericDeliverable, RunFamily, WorkflowRun, AgentThinkingEntry, AgentRunState, PipelineRunState } from "@/types/index";
import type { TabDeepLinkTarget } from "@/hooks/useTabDeepLink";
import { authedFetch, getToken, getWorkflow, getRunSandbox, getRunSandboxFile, getRunSandboxFileBlob, getRunSandboxZip, resolveRunDeliverable } from "@/lib/api";
import { useClipboardCopy } from "@/hooks/useClipboardCopy";
import { isPlausibleFilePath } from "@/lib/parsers/filePath";
import { parseRunInput } from "@/lib/runInput";
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
    // ISS-323: a prose heading ("### Via Node.js") matches the heading/bold
    // regexes as well as a real path does — a real file path has no whitespace.
    if (!isPlausibleFilePath(path)) return;
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
// A raw HTML deliverable that sets no background of its own renders on the
// browser's UA-default white canvas — a jarring white hole when our viewer
// chrome is in dark theme. We don't touch the deliverable's own bytes if it
// DOES style itself: this only supplies a fallback default, inserted right
// after <head> (or prepended if there's no <head>) so any of the page's own
// <style>/<link> rules — which come later in source order — still win on an
// equal-specificity `html,body{background:...}` tie.
const DARK_IFRAME_DEFAULT_STYLE =
  "<style>:root{color-scheme:dark}html,body{background:#0D0D0D;color:#F5F5F5}</style>";

function withDarkIframeDefault(html: string, dark: boolean): string {
  if (!dark) return html;
  const headMatch = html.match(/<head[^>]*>/i);
  if (headMatch) {
    const idx = html.indexOf(headMatch[0]) + headMatch[0].length;
    return html.slice(0, idx) + DARK_IFRAME_DEFAULT_STYLE + html.slice(idx);
  }
  return DARK_IFRAME_DEFAULT_STYLE + html;
}

function GenericDeliverablePreview({
  deliverable,
  agentOutputs,
}: {
  deliverable: GenericDeliverable;
  agentOutputs?: import("@/components/results/FilesTab").AgentOutputItem[];
}) {
  const { theme } = useTheme();
  const mimetype = (deliverable.mimetype || "").toLowerCase();
  const content = deliverable.content || "";

  // HTML → sandboxed iframe (NO allow-same-origin — see T-18-05 above).
  if (mimetype === "text/html" || mimetype.startsWith("text/html")) {
    // presentation.html from a custom-composer PPT run → PPTPreview for the
    // styled deck viewer with navigation chrome. Keyed on filename (SC-001).
    if (deliverable.filename === "presentation.html") {
      return <PPTPreview content={content} isStreaming={false} pipelineType="ppt" onRevise={undefined} />;
    }
    return (
      <div className="h-full flex flex-col overflow-hidden">
        <div className="flex-1 min-h-0 overflow-hidden">
          <iframe
            // REMOUNT on a theme change; never MUTATE srcDoc in place.
            //
            // `useTheme` renders "light" once before its effect reads the real
            // `data-theme` (hooks/useTheme.ts:18 — deliberate, it avoids an SSR
            // hydration mismatch). In dark mode that makes this iframe mount carrying
            // the LIGHT document and then have its `srcdoc` attribute rewritten ~40ms
            // later with the dark one. Chrome leaves the frame BLANK: measured live on
            // run b0642e0f — iframe added srcdoc=72,792 → attr:srcdoc 72,874 → one load
            // event → nothing painted, while a fresh element with byte-identical
            // attributes appended beside it rendered the deliverable perfectly.
            //
            // That is also why clicking Markdown and back "fixed" it: switching
            // renderers unmounts this component, and the remount creates the iframe with
            // the final srcDoc already in place — one value, one load. This key makes
            // the normal path do what the workaround did.
            //
            // Scope: `theme` here only ever changes once, at mount. A theme TOGGLE does
            // not reach this component at all (useTheme is per-component state, not a
            // context — verified live: toggling produced zero srcdoc mutations and zero
            // load events here), so this adds exactly one remount, before the frame
            // could hold any state worth losing.
            key={theme}
            srcDoc={withDarkIframeDefault(content, theme === "dark")}
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

// ─── U1 — browsing a git tag renders that tag's deliverable, read-only ────────
// Extension → mimetype, so the reused GenericDeliverablePreview dispatches the
// same way it does for the live path (html → sandboxed iframe, md → markdown,
// zip → bundle view). Falls back to the caller's best guess when the path is
// unknown (still loading).
function mimetypeForPath(path: string | null | undefined, fallback: string): string {
  const ext = path?.split(".").pop()?.toLowerCase();
  if (ext === "html" || ext === "htm") return "text/html";
  if (ext === "md" || ext === "markdown") return "text/markdown";
  if (ext === "zip") return "application/zip";
  return fallback;
}

// ponytail: reuses GenericDeliverablePreview for every workflow's ref-view
// rather than each workflow's bespoke chrome (PrototypePreview/PPTPreview/
// UserStoryPreview) — the read-only tag browse only needs the content to
// render, not the live tools those bring; upgrade if per-workflow chrome
// matters for an old tag too.
function RefVersionPreview({
  tag,
  content,
  mimetype,
  filename,
  agentOutputs,
  onBackToLatest,
}: {
  tag: string;
  content: string | null;
  mimetype: string;
  filename?: string;
  agentOutputs?: AgentOutputItem[];
  onBackToLatest: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div
        role="status"
        className="flex flex-none items-center gap-2 rounded-lg mx-4 mt-3 bg-amber-50 border border-amber-200 px-3 py-2 text-[11px] text-amber-700"
      >
        <span>
          Viewing {tag} · read-only
        </span>
        <button
          type="button"
          onClick={onBackToLatest}
          className="ml-auto font-medium hover:underline"
        >
          Back to latest
        </button>
      </div>
      <div className="min-h-0 flex-1">
        {content === null ? (
          <div className="flex h-full items-center justify-center text-xs text-ink-400">
            Loading {tag}…
          </div>
        ) : (
          <GenericDeliverablePreview
            deliverable={{ content, mimetype, filename }}
            agentOutputs={agentOutputs}
          />
        )}
      </div>
    </div>
  );
}

type PanelTab = "preview" | "files" | "thinking" | "audit" | "workspace";

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
  // ISS-296: the optional second argument is an explicit version override —
  // a version number pins, `null` clears the pin, omitted keeps whatever the
  // URL already carries. The Version menu writes the URL through this same
  // chokepoint so a pin is shareable and survives a later tab switch.
  onTabSelect?: (tab: string, version?: string | null) => void;
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
  // ISS-739 (QA-PS-014) — true while the dashboard's reopen fetch for this run is
  // in flight. The ONLY signal that separates "still fetching" from "confirmed
  // empty terminal run": on a reopened terminal run `isStillRunning` is false for
  // the whole fetch window (no stream is attached, and resetPipeline() clears
  // isRunning at fetch start) and `hasContent` is false because the content has
  // not arrived yet, so without this the neutral empty-state fires for both.
  // Per ISS-739's locked_constraints this is an EXPLICIT fetch-in-flight boolean
  // from the fetcher — never a client-side `terminal && !content` inference
  // (the hack ISS-017 already rejected for the failure signal below).
  isLoadingRunData?: boolean;
  // Revision Families (B3 / POR §5 D5) — the on-screen content's revision family
  // (root + ordered members) fetched by DashboardLayout keyed on
  // contentSourceRunId, and the id of the currently-live run. BOTH optional and
  // default undefined → the live version chip + read-only override are absent
  // unless explicitly wired by the live dashboard mount (zero regression for
  // history callers and existing test renders).
  runFamily?: RunFamily | null;
  liveRunId?: string | null;
  // ISS-230 — the 1-based version number the URL pins (`/runs/{id}/versions/{v}`,
  // and its per-tab form). Optional/default-undefined: an un-pinned URL leaves
  // the version state exactly as it was, so every existing caller and test
  // render is unchanged.
  pinnedVersion?: string;
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
  // KAN-101 — spec revision cycle counter for the Steps "Spec Revision Cycle N"
  // banner. Optional + defaulted to 0 → history/test renders unchanged.
  specRevisionCount?: number;
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
  // Files is HIDDEN from the strip. Workspace supersedes it: Files shows the
  // curated deliverable list, Workspace shows the run's actual sandbox — every
  // file, in its real tree, with the same downloads — so two tabs answered one
  // question and disagreed whenever a run wrote more than one artifact.
  //
  // The tab is hidden, not deleted: `files` stays in PANEL_TAB_IDS and keeps its
  // panel below, so an existing /files deep link still opens something rather
  // than a blank pane. Nothing links there any more.
  { id: "workspace", label: "Workspace", icon: FolderTree },
  { id: "audit", label: "Audit", icon: Shield },
];

// The generic tab ids PreviewPanel owns. A deep-link to any of these switches the
// tab; other generic targets (e.g. "steps") belong to the left lane column.
const PANEL_TAB_IDS: readonly PanelTab[] = ["preview", "files", "thinking", "workspace", "audit"];

// ─── ISS-606/608/609 — a pinned version's OWN pipeline data ───────────────────
// The `/versions/{v}` override used to carry the fetched run's `.output` alone,
// so only the deliverable CONTENT became version-aware (ISS-300/FIX-334). Every
// pipeline surface — the Steps tab's summary + agent list, the Files tab's
// "Agent outputs", the app_builder/generic previews, the Workspace tab's
// agent-name labels, the Audit tab's own fetches — kept reading the raw live/root
// props, so a pinned URL rendered the ROOT run's pipeline whichever version it
// named. Project the SAME fetched record into the shapes those surfaces consume,
// once, here: the eff* override pattern extended from content to pipeline data.
//
// A persisted `agent_outputs` row is one agent RUN, so a task-loop agent repeats
// (this bug's root run: 17 rows, `agent_count` 5). Collapse to the LAST row per
// agent id — what the live reducer holds after a durable replay — which keeps
// first-appearance order and restores the run's own agent count.
type PersistedAgentRow = AgentThinkingEntry & Partial<{
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_prompt: string;
  thinking_text: string;
  tool_calls: AgentRunState["toolCalls"];
  context_sources: AgentRunState["contextSources"];
}>;

type VersionView = {
  id: string;
  content?: string;
  // QA-PS-057 — the pinned version's OWN brief. Every other field here followed
  // the version already; this one did not exist, so Steps' "Starting point" (and
  // the Files tab's prompt.md row) kept rendering whichever run the page was
  // opened at while the agent list obeyed the dropdown.
  //
  // SHAPE: the SAME already-parsed, first-line, trimmed brief the live `runInput`
  // prop carries (page.tsx's submittedBrief, FIX-130) — NOT run.input raw. The
  // two values flow into one prop via effRunInput below, so a pinned view and the
  // live view of the same run must render identical text; feeding one raw and the
  // other parsed would make a pinned revision read "Revision request" + the full
  // marker-laden instruction while the live view of that same run reads
  // "Starting point" + one line.
  runInput?: string;
  agents: AgentRunState[];
  pipelineState: PipelineRunState;
  agentOutputs: AgentOutputItem[];
  // ISS-300 — the pinned version's OWN deliverable. `content` above only reaches
  // the first-party renderers (user_stories/ppt/prototype); a custom or unknown
  // renderType routes through the generic channel instead, which read the
  // un-pinned `genericDeliverable` prop and so rendered the ROOT's bytes under a
  // v2 pin. That produced a view mixing two runs: this version's agent outputs
  // beside the root's "Final output".
  genericDeliverable?: GenericDeliverable;
};

function versionViewFrom(run: WorkflowRun): VersionView {
  const lastRowPerAgent = new Map<string, PersistedAgentRow>();
  for (const row of (run.agentOutputs ?? []) as PersistedAgentRow[]) {
    if (row?.agent_id) lastRowPerAgent.set(row.agent_id, row);
  }
  const agents: AgentRunState[] = [...lastRowPerAgent.values()].map((row, index) => ({
    id: row.agent_id,
    name: row.name ?? row.agent_id,
    role: row.role ?? "",
    icon: row.icon ?? "",
    // A persisted row IS a completed agent output. A run-level failure comes from
    // the server's own status below — never a per-agent client guess (ISS-017).
    status: "done",
    output: row.output ?? "",
    thinking: row.thinking ?? "",
    duration: row.duration ?? null,
    error: null,
    index,
    inputTokens: row.input_tokens,
    outputTokens: row.output_tokens,
    totalTokens: row.total_tokens,
    inputPrompt: row.input_prompt,
    thinkingText: row.thinking_text,
    toolCalls: row.tool_calls,
    contextSources: row.context_sources,
  }));
  const usage = run.tokenUsage;
  // QA-PS-057 — mirrors page.tsx's own submittedBrief derivation exactly
  // (handleSwitchToLiveRun :2728-2730, handleSelectWorkflowRun :2941-2942) so the
  // pinned and live shapes cannot drift apart.
  const parsedInput = parseRunInput(run.input ?? "");
  const brief = (parsedInput.revisionInstruction ?? parsedInput.brief ?? "").split("\n")[0].trim();
  return {
    id: run.id,
    content: run.output,
    runInput: brief || run.title,
    agents,
    pipelineState: {
      isRunning: false,
      pipeline_type: run.type,
      agents,
      currentAgentIndex: agents.length - 1,
      totalDuration: run.duration ?? null,
      completedCount: agents.length,
      totalInputTokens: usage?.total_input_tokens,
      totalOutputTokens: usage?.total_output_tokens,
      totalTokens: usage?.total_tokens,
      estimatedCostUsd: usage?.estimated_cost_usd,
      cacheReadTokens: usage?.total_cache_read_tokens,
      cacheWriteTokens: usage?.total_cache_write_tokens,
      modelId: run.modelId,
      // ISS-609 — AuditTab keys its gate/validation/exec/hook-run fetches on this
      // id, so the pinned run's id has to travel with the override.
      pipelineRunId: run.id,
      failed: run.status === "failed",
    },
    agentOutputs: agents
      .filter((a) => a.output.trim().length > 0)
      .map((a) => ({ name: a.name, role: a.role, output: a.output, agentId: a.id })),
    // ISS-300 — built whenever this run HAS output, so a pinned version never
    // falls back to the un-pinned prop and silently shows the root's bytes.
    // filename/mimetype are the run's own declared values; the Files tab still
    // derives the DISPLAY name from the content itself (deriveDeliverableFilename),
    // which is why two runs both declaring "prototype.html" render distinct names.
    genericDeliverable: run.output
      ? {
          content: run.output,
          filename: run.deliverableFilename,
          mimetype: run.deliverableMimetype,
        }
      : undefined,
  };
}

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
  diverted,
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
  // ISS-390: true when the terminal state is a divert (a `trigger: workflow` route
  // outcome handed off to a newly-minted run). Terminal and non-resumable like the
  // others, but NOT a failure — only the detail line changes, so the run still
  // reads as "did not complete" without claiming its agents failed.
  diverted?: boolean;
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
            : diverted
              ? "The run was diverted to another workflow and will not resume. No deliverable was produced here."
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

// ─── ISS-739 (QA-PS-014) — reopen-fetch-in-flight skeleton ───────────────────
// Rendered (instead of the neutral "Output will appear here") while the viewed
// run's own fetch is still running, so the wait reads as "content is on the way"
// rather than an empty or failed run. Mirrors the in-repo skeleton idiom
// (shimmer-effect + bg-surface-warm blocks) already used by LibraryPage /
// HomeLaunchGrid.
function RunDataSkeleton() {
  return (
    <div className="h-full w-full p-6 shimmer-effect" aria-busy="true" aria-label="Loading run">
      <div className="h-5 w-1/3 rounded bg-surface-warm" />
      <div className="mt-4 space-y-2.5">
        <div className="h-3 w-full rounded bg-surface-warm" />
        <div className="h-3 w-5/6 rounded bg-surface-warm" />
        <div className="h-3 w-4/6 rounded bg-surface-warm" />
      </div>
      <div className="mt-6 h-40 w-full rounded-lg bg-surface-warm" />
    </div>
  );
}

export function PreviewPanel({ userStoryContent, pptContent, prototypeContent, genericDeliverable, isStreaming, initialTab, onTabSelect, workflowType, rawPipelineType, pptxCode, onRevisePpt, onReviseUserStory, onRevisePrototype, onReviseAppBuilder, agentOutputs, agents, pipelineState, reopenedRunStatus, reopenedFailedAgents, reopenedAgentNameById, isLoadingRunData, runFamily, liveRunId, pinnedVersion, runInput, clarifications, deepLinkTarget, laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate, clarifyQuestions, onSubmitClarify, onSkipClarify, onCancelWorkflow, waves, onShare, onDownload, specRevisionCount = 0 }: PreviewPanelProps) {
  const [activeTab, setActiveTab] = useState<PanelTab>("preview");
  // ─── Plan 07 — manual typed-renderer switcher override ───────────────────────
  // null = follow the generic auto-dispatch (the PRIMARY route); a non-null value
  // is a renderType/mimetype token (SC-001, never a workflow name) that FORCES a
  // specific renderer for the current deliverable. Cleared back to auto on demand
  // (the "Auto" option) and whenever the deliverable's renderType changes.
  const [rendererOverride, setRendererOverride] = useState<string | null>(null);
  // ─── B3 (POR §5 D5) — read-only older-version state ─────────────────────────
  // viewingVersion is the read-only older-version override (the pinned member's
  // own run record, projected by versionViewFrom) or null (live latest on
  // screen). The version affordance itself now lives in the Phase-39 RunHeader
  // Version menu (INV-12 — the old version-pill pulse tick is retired with it).
  const [viewingVersion, setViewingVersion] = useState<VersionView | null>(null);

  // ── task 11.6: sandbox ref state, lifted so VersionMenu and SandboxTab share it ──
  // The VersionMenu (in RunHeader) calls onSelectVersion(tagName: string).
  // Previously that was wired to handleSelectVersion which expects a run UUID —
  // the defect.  Instead it sets sandboxSelectedRef, which is passed down to
  // SandboxTab as a controlled selectedRef prop.
  const [sandboxSelectedRef, setSandboxSelectedRef] = useState<string | null>(null);
  // B22 fix: carries the intended git tag through the activeRunId-change reset so
  // the Workspace ref is not cleared when handleVersionMenuSelect triggers
  // handleSelectVersion (which changes viewingVersion → activeRunId, firing the
  // reset effect below). This avoids threading git_tag through VersionView or
  // changing handleSelectVersion's signature.
  const intendedSandboxRef = useRef<string | null>(null);
  // Phase 42-02 (§B / RUNUI-06) — latch for the state-keyed default-tab effect: the
  // last generic run-state we auto-applied a tab for. Keyed on the state VALUE so the
  // auto-select fires once per state transition and never overrides a later manual
  // tab click within the same state (mirrors the initialTab effect idiom below).
  const autoTabbedForState = useRef<string | null>(null);

  useEffect(() => { if (initialTab === "preview" || initialTab === "files") setActiveTab(initialTab); }, [initialTab]);

  // Phase 31 (CHATUI-02) — nonce'd deep-link consumer (borrow #6). A chat
  // result-card click (or T7's cold-mount reopen) mints a fresh {tab, nonce};
  // switch to the target tab for ALL panel tabs (preview/files/thinking/audit).
  // T7 retry (015-frontend-routing, FR-003/SC-001): this used to be its OWN
  // effect, independently calling setActiveTab and racing the state-keyed
  // default-tab effect below for the same setter — see that effect's comment
  // for why the two are now merged into one so precedence is explicit.

  // ─── B3 — family/version derivation (UI-SPEC Surface 3) ──────────────────────
  // sortedMembers v1..vN by revision_index; latestId = last member (fallback
  // liveRunId); activeRunId = the read-only override id, else the live run, else
  // the latest member; activeIdx = its 0-based index; isViewingOlder = an
  // override is active AND it is not the latest.
  const sortedMembers = runFamily
    ? [...runFamily.members].sort((a, b) => a.revision_index - b.revision_index)
    : [];
  const latestId = sortedMembers.length > 0 ? sortedMembers[sortedMembers.length - 1].id : (liveRunId ?? null);
  // ISS-607/ISS-610/ISS-611 — the member the UN-pinned route renders: liveRunId
  // when the shell has one (a base `/runs/{rootId}/...` URL pins it to the ROOT),
  // else the family's newest. This is a DIFFERENT value from latestId whenever
  // the route names the root of a >=2-member family, so the two are not
  // interchangeable: "dropping the pin" lands on THIS, never necessarily on the
  // latest member.
  const unpinnedRunId = liveRunId ?? latestId;
  const activeRunId = viewingVersion?.id ?? unpinnedRunId;
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

  // task 11.6: Reset the sandbox ref picker whenever the active run changes so
  // navigating to a different family member never leaves a stale tag selected.
  // B22 fix: if a version-menu selection staged an intendedSandboxRef, restore it
  // instead of clearing — handleSelectVersion changes activeRunId as a side effect
  // and the plain setSandboxSelectedRef(null) would wipe the tag.
  useEffect(() => {
    if (intendedSandboxRef.current !== null) {
      setSandboxSelectedRef(intendedSandboxRef.current);
      intendedSandboxRef.current = null;
    } else {
      setSandboxSelectedRef(null);
    }
  }, [activeRunId]);

  // ISS-607/ISS-612 — `tab` defaults to the tab already on screen (picking a
  // version never also changes which tab is showing), and is passed explicitly
  // by the chat deep-link consumer, which switches BOTH at once.
  const handleSelectVersion = useCallback(async (memberId: string, tab: PanelTab = activeTab) => {
    // ISS-296 — the menu is the primary way a version gets pinned, so it must
    // WRITE the pin into the URL, not only into local state: the
    // `/versions/{v}` segment is what makes a pin shareable, refreshable and
    // (via `pinnedVersion`) survivable across the tab switches ISS-230 fixed.
    // Routed through the tab-select chokepoint carrying the CURRENT tab, so
    // picking a version never also changes which tab is on screen.
    //
    // ISS-607/ISS-610/ISS-611 — the "no pin needed, this member is already what
    // the un-pinned route shows" shortcut keys on `unpinnedRunId`, NOT on
    // `latestId`. On a base `/runs/{rootId}/...` route those differ (root vs
    // newest member), and keying on latestId dropped the pin for the newest
    // member: the target route then equalled the current pathname and
    // DashboardLayout's pushState guard swallowed the click entirely.
    const memberIdx = sortedMembers.findIndex((m) => m.id === memberId);
    onTabSelect?.(tab, memberId === unpinnedRunId || memberIdx < 0 ? null : String(memberIdx + 1));
    if (memberId === unpinnedRunId) {
      setViewingVersion(null); // back to live
      return;
    }
    const token = getToken();
    try {
      const run = await getWorkflow(token || "", memberId);
      setViewingVersion(versionViewFrom(run));
    } catch (err) {
      // Read-only view is best-effort — never throw into the preview surface.
      // Dev-observability only: log the swallowed failure; fallback unchanged.
      console.warn("[revision-family] read-only version fetch failed", err);
      setViewingVersion(null);
    }
  }, [unpinnedRunId, sortedMembers, onTabSelect, activeTab]);

  // B22 fix: resolve the tag to its family member and route through the
  // handleSelectVersion chokepoint so Steps/agents/outputs follow the version.
  // intendedSandboxRef carries the git tag through the activeRunId-change reset
  // that would otherwise clear sandboxSelectedRef when handleSelectVersion sets
  // viewingVersion → changes activeRunId → fires the reset effect.
  //
  // Fallback (no member found for tag): only setSandboxSelectedRef fires, keeping
  // the Workspace tab ref-scoped while Steps stays live — same as the pre-fix
  // behaviour, acceptable when a tag has no associated member record yet.
  const handleVersionMenuSelect = useCallback((tag: string | null) => {
    if (tag === null) {
      // "Latest (live)" — drop both the version pin and the sandbox ref.
      intendedSandboxRef.current = null;
      setSandboxSelectedRef(null);
      if (latestId) void handleSelectVersion(latestId);
      return;
    }
    // Resolve tag → family member UUID and pin the full version view.
    const member = sortedMembers.find((m) => m.git_tag === tag);
    if (member) {
      // Stage the tag so the reset effect restores it after activeRunId changes.
      intendedSandboxRef.current = tag;
      setSandboxSelectedRef(tag);
      void handleSelectVersion(member.id);
    } else {
      // Tag not yet on any member (in-progress run, pre-tagging).
      // Flip the Workspace tab only; Steps stays on the live run.
      intendedSandboxRef.current = null;
      setSandboxSelectedRef(tag);
    }
  }, [latestId, sortedMembers, handleSelectVersion]);

  // ISS-296 — dropping the pin drops the URL segment too, so the address bar
  // never claims a version that is no longer on screen.
  // ISS-611 — "latest" is the family's NEWEST member, which is only the same
  // thing as dropping the pin when the un-pinned route already names it. Routed
  // through the one chokepoint above so the button pins exactly what its own
  // label promises instead of falling back to the family root.
  const handleBackToLatest = useCallback(() => {
    if (latestId) void handleSelectVersion(latestId);
  }, [latestId, handleSelectVersion]);

  // The read-only view is dropped when the URL stops naming a pinned version.
  //
  // This used to key on `liveRunId` — "a new live run supersedes any active
  // read-only view" — which is true of a NAVIGATION but not of what actually
  // moves that prop most often. QA-PS-055 / ISS-744: a tracked `*_revision`
  // completing advances liveRunId with no navigation at all (page.tsx:1521 fires
  // setContentSourceRunId for ANY tracked revision — FIX-088's deliberate
  // foreign-run bypass, which MUST stay: it is what makes the chip and family
  // advance instead of sticking at v1). Clearing on that prop threw away an
  // explicit pin mid-review, and — via activeRunId — the sandboxSelectedRef reset
  // above went with it, collapsing Steps/agents/Preview/Workspace at once.
  //
  // `pinnedVersion` (the `/versions/{n}` segment) is the pin's real source of
  // truth: ISS-296 made handleSelectVersion WRITE it on every selection, dropping
  // the pin drops the segment, and navigating to another run drops it too — so
  // this still supersedes in every case the old comment meant, and in none of the
  // ones it did not. With nothing pinned the effect is a no-op, so FIX-088's
  // "revision completes → follow to latest" path is untouched.
  useEffect(() => { if (!pinnedVersion) setViewingVersion(null); }, [pinnedVersion]);

  // ─── ISS-230 — the URL's `/versions/{v}` pin, applied ────────────────────────
  // A pinned deep link opens the family ROOT in the shell (contentSourceRunId →
  // liveRunId), and liveRunId wins over latestId in activeRunId above — so
  // without this the pin never reached the panel at all and every tab fetched
  // and rendered v1. Set as the read-only override directly rather than through
  // handleSelectVersion, which treats "the latest member" as the Version menu's
  // back-to-live shortcut and would null the pin out for exactly the family
  // whose newest member is the one pinned.
  // Keyed on the RESOLVED member id alone: a tab switch changes neither it nor
  // the family, so switching tabs no longer refetches or re-pins, and clicking
  // Back to latest is not immediately undone.
  const pinnedMember = pinnedVersion ? sortedMembers[Number(pinnedVersion) - 1] : undefined;
  const pinnedMemberId = pinnedMember?.id;
  const pinnedMemberTag = pinnedMember?.git_tag ?? null;
  useEffect(() => {
    if (!pinnedMemberId) return;
    // QA-PS-056 — the URL pin has to carry its git TAG as well as its run id.
    // SandboxTab already threads `selectedRef` through every one of its reads
    // (SandboxTab.tsx:1046/1085/1106/1119) and the version MENU already stages the
    // tag (handleVersionMenuSelect, FIX-516) — but this path set viewingVersion
    // alone, so the activeRunId reset above found nothing staged, nulled
    // sandboxSelectedRef, and the Workspace tab read the LIVE working tree under
    // the "Viewing v{n} (read-only)" banner. Reached by a /versions/{n} deep link,
    // a reload while pinned, and any remount after the menu wrote that segment.
    if (pinnedMemberTag) {
      intendedSandboxRef.current = pinnedMemberTag;
      setSandboxSelectedRef(pinnedMemberTag);
    }
    let cancelled = false;
    void (async () => {
      try {
        const run = await getWorkflow(getToken() || "", pinnedMemberId);
        if (!cancelled) setViewingVersion(versionViewFrom(run));
      } catch (err) {
        // Same contract as handleSelectVersion: best-effort, never throw into
        // the preview surface — an unresolvable pin leaves the live view up.
        console.warn("[revision-family] pinned version fetch failed", err);
      }
    })();
    return () => { cancelled = true; };
  }, [pinnedMemberId, pinnedMemberTag]);

  // ISS-300 — a PINNED version renders as ITSELF, so its own pipeline type wins.
  // `workflowType` is the SHELL's type, and a pinned deep link mounts the family
  // ROOT in the shell — so a `prototype_revision` pinned under a `custom` root
  // was typed `custom`, fell through to the generic channel, and presented the
  // version differently from its own /runs/{id} page (different renderer, and so
  // a different derived deliverable name) even once its bytes were correct.
  // Null when nothing is pinned, so the live path below is untouched.
  const pinnedType = viewingVersion?.pipelineState?.pipeline_type as WorkflowType | undefined;
  const detectedType: WorkflowType = pinnedType || workflowType || (userStoryContent ? "user_stories" : pptContent ? "ppt" : prototypeContent ? "prototype" : "user_stories");
  // Normalize revision types to their base type for rendering
  const renderType = detectedType === "user_stories_revision" ? "user_stories"
    : detectedType === "ppt_revision" ? "ppt"
    // spec 017 — ppt_v2 renders the same HTML deck as ppt; it differs only in
    // ALSO producing a .pptx. Without this it falls through to the default and
    // the deck renders as raw text.
    : detectedType === "ppt_v2" ? "ppt"
    : detectedType === "prototype_revision" ? "prototype"
    : detectedType === "prototype_large_revision" ? "prototype"
    : detectedType === "prototype_feature_revision" ? "prototype"
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
  // ISS-606/608/609 — the pipeline-data counterparts of the eff* content above.
  // Unlike the content slots these are renderType-independent: a pinned version's
  // agents/outputs/run id belong to that version whatever it rendered.
  const effAgents = viewingVersion?.agents ?? agents;
  const effPipelineState = viewingVersion?.pipelineState ?? pipelineState;
  const effAgentOutputs = viewingVersion?.agentOutputs ?? agentOutputs;
  // QA-PS-057 — the same axis: each revision is its own run with its own brief,
  // so a pinned version's "Starting point" is its own, not the shell's.
  const effRunInput = viewingVersion?.runInput ?? runInput;
  // ISS-300 — the generic deliverable belongs to the SAME axis as the three
  // above, not to the renderType-keyed eff*Content slots: whatever a pinned
  // version rendered, its deliverable is its own. Every read below goes through
  // this one value; reading the raw prop anywhere is what let the Files tab and
  // the Preview tab disagree with the pin while the agent list obeyed it.
  const effGenericDeliverable = overrideActive
    ? viewingVersion?.genericDeliverable
    : genericDeliverable;

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
  const hasGenericDeliverable = !!effGenericDeliverable?.content && (!isKnownRenderType || !knownContentPresent);

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
  // ISS-390: a diverted run is terminal and non-resumable with no deliverable, but
  // it is a hand-off, not a failure — so it gets its OWN affordance branch instead
  // of joining reopenFailureSignal, which would mislabel the header as failed
  // (headerFailed below) and drop the Preview tab entirely
  // (terminalFailureNoDeliverable). Same carve-out shape as isCancelledTerminal.
  const isDivertedTerminal = reopenedRunStatus === "diverted";
  const showDivertedAffordance = !hasContent && isTerminal && isDivertedTerminal;
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
  // Drop the Preview tab for a terminal-failed run; every other state keeps the
  // full four-tab set (Preview · Steps · Files · Audit).
  // The run whose DISK the Workspace tab browses — deliberately NOT activeRunId.
  //
  // `liveRunId` is misnamed for this purpose: DashboardLayout passes
  // `contentSourceRunId`, which page.tsx only sets once a run COMPLETES or is
  // reopened from history. During a live run it is null, so `activeRunId` falls
  // through to the family's latest member — which resolves and re-resolves as
  // the family fetch lands, making the tab appear and vanish mid-run.
  // `pipelineState.pipelineRunId` is the id the engine actually minted, and it
  // is available from the first frame.
  //
  // Order: an explicitly-selected version wins (browse THAT version's files),
  // then the live run, then whatever activeRunId resolved to for a settled run.
  const workspaceRunId = viewingVersion?.id ?? pipelineState?.pipelineRunId ?? activeRunId ?? null;
  // Dropped rather than rendered as a dead tab before a run has an id at all.
  const tabsForRun = workspaceRunId ? TAB_CONFIG : TAB_CONFIG.filter((t) => t.id !== "workspace");
  const visibleTabs = terminalFailureNoDeliverable
    ? tabsForRun.filter((t) => t.id !== "preview")
    : tabsForRun;
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
  const agentNameById = {
    ...(reopenedAgentNameById || {}),
    ...buildAgentNameById(effPipelineState?.agents),
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
  //
  // T7 retry (015-frontend-routing, FR-003/SC-001): this effect and the Phase-31
  // (CHATUI-02) deep-link consumer used to be TWO SEPARATE effects, each calling
  // setActiveTab on its own — ordered only by declaration position when both fired
  // in the same commit. That broke cold-opening /runs/{id}/steps|files|audit for a
  // COMPLETED run: the page's T7 cold-mount effect fetches the run AND requests
  // the deep-link tab from the same promise-chain flush, so headerRunState's flip
  // to "complete" and the deep-link's nonce bump landed in the SAME React commit —
  // both effects fired, and this one (declared later) always won, silently
  // stomping the deep link back to "preview" (confirmed live). Moving the deep-
  // link request into page.tsx's `.finally()` only changes WHEN the nonce updates
  // relative to the fetch's own state updates, not WHICH effect wins once they
  // land together, so that alone could never fix it. The two are merged into this
  // ONE effect so precedence is explicit and independent of commit/scheduling
  // timing: a freshly-arrived deep-link nonce always wins over the generic
  // per-state default, whether it lands in its own commit or the same one as a
  // state transition.
  const defaultTabDiscriminator = terminalFailureNoDeliverable ? "failed" : headerRunState;
  const lastAppliedDeepLinkNonceRef = useRef<number | undefined>(undefined);
  useEffect(() => {
    const nonce = deepLinkTarget?.nonce;
    const freshDeepLink = nonce !== undefined && nonce !== lastAppliedDeepLinkNonceRef.current;
    lastAppliedDeepLinkNonceRef.current = nonce;

    if (freshDeepLink) {
      const tab = deepLinkTarget!.tab;
      const isPanelTab = (PANEL_TAB_IDS as readonly string[]).includes(tab);
      if (isPanelTab) setActiveTab(tab as PanelTab);
      // ISS-607/ISS-612 — a narrator card minted by a DIFFERENT family member
      // (a revision's "Revision started"/"Delivered" card, stitched into the
      // shared family transcript) has to switch the RUN, not only the tab.
      // Routed through handleSelectVersion — the same pin-and-navigate
      // chokepoint the version menu uses — so there is one route-building path,
      // not a second one here. Unknown/absent ids and the member already on
      // screen fall through to the plain tab switch above.
      const targetRunId = deepLinkTarget!.runId;
      if (targetRunId && targetRunId !== activeRunId && sortedMembers.some((m) => m.id === targetRunId)) {
        void handleSelectVersion(targetRunId, isPanelTab ? (tab as PanelTab) : activeTab);
      }
      // The deep link owns the tab for this state too, so a same-commit state
      // transition doesn't immediately re-fire the default branch below for it.
      autoTabbedForState.current = defaultTabDiscriminator;
      return;
    }

    if (autoTabbedForState.current === defaultTabDiscriminator) return;
    autoTabbedForState.current = defaultTabDiscriminator;
    const target: PanelTab | null =
      defaultTabDiscriminator === "failed" ? "audit" :
      headerRunState === "complete" ? "preview" :
      (headerRunState === "gate" || headerRunState === "clarify" || headerRunState === "building") ? "thinking" :
      null;
    if (target) setActiveTab(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultTabDiscriminator, deepLinkTarget?.nonce]);
  // Live version label — derived from the live family (active member index) or the
  // pipeline's deliverableVersion; default v1. NEVER the mock's fixed "v1"/"v2".
  const familyVersionCount = runFamily?.members.length ?? 0;
  // QA-PS-058 — what "Latest (live)" should mean for THIS family, read off the
  // same family rows the chip already uses (no new fetch): the newest member's
  // tag — `null` when it finished without one, which is a real, permanent state
  // (ISS-697: tagging is best-effort) and the one case where the live tree is
  // the only route to that content — and whether that member is still running.
  // `undefined` when there is no family data at all: the menu keeps the live
  // entry rather than guessing.
  const latestMember = sortedMembers.length > 0 ? sortedMembers[sortedMembers.length - 1] : undefined;
  const latestVersionTag = latestMember ? (latestMember.git_tag ?? null) : undefined;
  const latestVersionInFlight = !!latestMember && !latestMember.completed_at;
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
    ? resolveAgentNames(failedAgentNames, agentNameById)[0]
    : undefined;

  // Client-only Share (ND-H) — copy the owner-auth-gated run deep link. Composed
  // from the live run id; NO backend call. Default provided here so the header is
  // functional even when the caller does not override it.
  // ISS-599: use the shared useClipboardCopy hook so a clipboard-permission denial
  // or a missing navigator.clipboard lands in `shareFailed` rather than silently
  // swallowed (the `void optional?.writeText()` fire-and-forget it replaces gave
  // no feedback whatsoever to the user or devtools).
  const { copy: copyToClipboard } = useClipboardCopy();
  const handleHeaderShare = useCallback(() => {
    if (onShare) return onShare();
    const runId = liveRunId ?? activeRunId ?? "";
    if (!runId || typeof window === "undefined") return;
    const link = `${window.location.origin}${window.location.pathname}?run=${encodeURIComponent(runId)}`;
    void copyToClipboard(link);
  }, [onShare, liveRunId, activeRunId, copyToClipboard]);

  // ─── Primary deliverable download — the WORKSPACE FILE, not a reconstruction ─
  //
  // Every workflow DECLARES what it delivers, in its own workflow.yaml:
  //
  //     prototype  → prototype.html      ppt_v2   → presentation.html
  //     ppt        → presentation.pptx   user_stories → user_stories.md
  //
  // The engine emits that literal name on `pipeline_complete` and persists it to
  // `WorkflowRun.deliverable_filename`, so it is available on the live path and
  // on reopen. This button now serves THAT FILE, read from the run's workspace.
  //
  // It used to rebuild a file from `activeContent` and name it from the content
  // itself — a prototype's `<title>` became `bespoke-facebook-sprint-8-board.html`
  // — with the declared name demoted to a fallback that only applied when there
  // was no content at all. So the workflow's own declaration lost to a guess, and
  // the bytes came from what the panel happened to be holding rather than from
  // what the run actually wrote.
  //
  // Presence is now the gate. Disabled until the declared file EXISTS in the
  // workspace listing, enabled once it does. That is strictly stronger than the
  // old `!!activeContent`, which could offer a download of something never
  // written to disk. It also settles the ppt `.pptx` question on its own: a run
  // that declares a file it does not write simply leaves the button disabled,
  // rather than handing over a mislabelled one.
  const [deliverableFile, setDeliverableFile] = useState<string | null>(null);
  // ISS-313: a workflow may declare a deliverable STRATEGY and no name at all.
  // `serialized_sandbox` delivers the WHOLE workspace, so there is no single file
  // to name — the manifest declares none, the engine emits `deliverable_filename:
  // null`, and the run row keeps it. That left this button permanently disabled on
  // a run whose deliverable is fully rendered and already downloadable from the
  // file panel's own "Download ZIP". The bundle IS the deliverable there, so it is
  // served as that same archive. Presence is still the gate — the workspace has to
  // actually hold a deliverable-flagged file — and this applies ONLY when nothing
  // was declared: a run that declares a file it does not write still stays
  // disabled rather than handing over a mislabelled one.
  const [deliverableBundle, setDeliverableBundle] = useState(false);

  useEffect(() => {
    setDeliverableFile(null);
    setDeliverableBundle(false);
    // ONE fetch, when the run settles — no polling. A build writes its
    // deliverable at an unpredictable point and a timer would spend a request
    // every few seconds on every open run to notice a few seconds earlier.
    // U1: also resolve while a tag is pinned (sandboxSelectedRef), even if the
    // CURRENT/live run isn't complete yet — browsing an older tag has to keep
    // working while a later revision is still running.
    if (!activeRunId || (headerRunState !== "complete" && !sandboxSelectedRef)) return;
    let cancelled = false;
    void (async () => {
      const token = getToken();
      if (!token) return;
      try {
        // ISS-251: the sibling-preference rule (declared .html → prefer
        // <stem>.pptx, declared .pptx → prefer <stem>.html, else the declared
        // file) was duplicated inline here and in resolveRunDeliverable
        // (frontend/src/lib/api.ts). Collapse to the shared function so a
        // future change to the preference applied in api.ts is automatically
        // reflected here too — the original drift was how ISS-214/215 happened.
        //
        // The ISS-313 bundle path (!declared → no single file, serve the whole
        // workspace archive) is NOT inside resolveRunDeliverable (it returns
        // null for no-declared and lets callers decide), so it stays here.
        //
        // T7 — `pipelineState` reflects the NEW/idle run whenever this isn't
        // the pipeline actively streaming in THIS browser session (a reopened
        // run, or a family member that never streamed here — the same gap
        // ISS-017/ISS-609's reopenedRunStatus/reopenedAgentNameById props
        // exist to cover elsewhere). Before this fell straight to the bundle
        // branch whenever pipelineState lacked it, so `deliverableFile` never
        // resolved for such a run — and the U1 ref-scoped fetch below (gated
        // on `deliverableFile`) never fired, leaving "Loading {tag}…" forever
        // with no request ever issued. Fall back to the run's OWN persisted
        // declaration (resolveRunDeliverable's documented `declared` contract)
        // before assuming the workflow declares no deliverable at all.
        let declared = pipelineState?.deliverableFilename ?? null;
        if (!declared) {
          const run = await getWorkflow(token, activeRunId);
          if (cancelled) return;
          declared = run.deliverableFilename ?? null;
        }
        if (!declared) {
          // Nothing declared → whole-workspace bundle (ISS-313).
          const listing = await getRunSandbox(token, activeRunId);
          if (cancelled) return;
          setDeliverableBundle(listing.files.some((f) => f.deliverable));
          return;
        }
        if (cancelled) return;
        const hit = await resolveRunDeliverable(token, activeRunId, declared);
        if (cancelled) return;
        if (hit) setDeliverableFile(hit.path);
      } catch {
        // A workspace that cannot be listed leaves the button disabled —
        // the honest state; we cannot promise a file we have not seen.
      }
    })();
    return () => { cancelled = true; };
  }, [activeRunId, headerRunState, sandboxSelectedRef, pipelineState?.deliverableFilename]);

  // ── U1: browsing a tag fetches that tag's deliverable bytes, read-only ────
  // Reuses the SAME resolved path the header Download button already found —
  // just read at the pinned ref instead of the live tree — via the existing
  // getRunSandboxFile(token, runId, deliverableFile, ref).
  const [refDeliverableContent, setRefDeliverableContent] = useState<string | null>(null);
  useEffect(() => {
    setRefDeliverableContent(null);
    if (!sandboxSelectedRef || !activeRunId || !deliverableFile) return;
    let cancelled = false;
    const token = getToken();
    if (!token) return;
    getRunSandboxFile(token, activeRunId, deliverableFile, sandboxSelectedRef)
      .then((text) => { if (!cancelled) setRefDeliverableContent(text); })
      .catch((err: Error) => {
        // Best-effort, mirrors handleSelectVersion's swallow below — the
        // banner still renders and "Back to latest" always works.
        console.warn("[version-menu] ref deliverable fetch failed", err);
      });
    return () => { cancelled = true; };
  }, [sandboxSelectedRef, activeRunId, deliverableFile]);

  const canHeaderDownload = !!deliverableFile || deliverableBundle;
  const handleHeaderDownload = useCallback(() => {
    if (onDownload) return onDownload();
    if (!activeRunId || (!deliverableFile && !deliverableBundle)) return;
    void (async () => {
      const token = getToken();
      if (!token) return;
      // The server's own Content-Type rides on the blob, so no extension→mime
      // table is needed here (and cannot drift from the one the API applies).
      // ISS-313: no declared file → the workspace archive, the same bytes the
      // file panel's "Download ZIP" serves, under the same name it gives them.
      // QA-PS-054 / ISS-706: read at the PINNED ref, exactly as the sibling
      // preview effect above and every SandboxTab call already do. Without it the
      // request carries no `?ref=`, the API falls through to a live working-tree
      // read (run_files.py), and the button hands back the newest bytes under the
      // "Viewing v{n} (read-only)" banner.
      const blob = deliverableFile
        ? await getRunSandboxFileBlob(token, activeRunId, deliverableFile, sandboxSelectedRef ?? undefined)
        : await getRunSandboxZip(token, activeRunId, sandboxSelectedRef ?? undefined);
      const url = URL.createObjectURL(blob);
      // downloadBlob passes a `blob:` string straight through to the anchor.
      const name = deliverableFile
        ? deliverableFile.split("/").pop() || deliverableFile
        : `workspace-${activeRunId.slice(0, 8)}.zip`;
      downloadBlob(url, name, blob.type);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    })();
    // sandboxSelectedRef is load-bearing here, not decorative: deliverableFile is
    // usually the same string across versions, so without it this callback is not
    // rebuilt when only the pinned ref changes and the closure serves a stale ref.
  }, [onDownload, deliverableFile, deliverableBundle, activeRunId, sandboxSelectedRef]);

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
      effGenericDeliverable?.filename ||
      `deliverable-${headerVersionLabel}`,
    effGenericDeliverable?.mimetype,
  );
  // The chrome's open-in-new affordance — opens the on-screen deliverable in a new
  // tab via a client-only blob URL (the same pattern PPTTabActions.handleFullScreen
  // uses; NO network, no new surface). The chrome itself stays a passive frame.
  const handlePreviewOpen = useCallback(() => {
    const content = effGenericDeliverable?.content ?? activeContent;
    if (!content || typeof window === "undefined") return;
    const mimetype =
      effGenericDeliverable?.mimetype ||
      (renderType === "ppt" || renderType === "prototype" ? "text/html" : "text/markdown");
    const blob = new Blob([content], { type: mimetype });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [effGenericDeliverable?.content, effGenericDeliverable?.mimetype, activeContent, renderType]);

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
        ? <AppBuilderIDEPreview content={effUserStoryContent} agentOutputs={effAgentOutputs} onRevise={overrideActive ? undefined : onReviseAppBuilder} />
        : null,
    ppt: () =>
      (effPptContent || pptxCode)
        ? <PPTPreview content={effPptContent} isStreaming={isStreaming} pptxCode={pptxCode} runId={activeRunId} onRevise={overrideActive ? undefined : onRevisePpt} pipelineType={rawPipelineType || workflowType} />
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
    // Deliberately gated on the GENERIC slot alone (ND-D: the switch offers only
    // the deliverable's live typed renderers). A first-party deliverable already
    // has its own typed pill — a ppt_v2 deck showing HTML/Markdown/Bundle was the
    // SYMPTOM of it being mis-routed into the generic channel, not a feature.
    if (effGenericDeliverable?.content) {
      for (const key of Object.keys(MIMETYPE_OVERRIDES)) {
        opts.push({ value: key, label: MIMETYPE_LABELS[key] });
      }
    }
    return opts;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderType, effGenericDeliverable?.content]);

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
    const content = effGenericDeliverable?.content ?? activeContent ?? "";
    if (!content) return null;
    const forced: GenericDeliverable = { ...(effGenericDeliverable ?? {}), content, mimetype };
    return <GenericDeliverablePreview deliverable={forced} agentOutputs={effAgentOutputs} />;
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
    if (effGenericDeliverable?.content) {
      return <GenericDeliverablePreview deliverable={effGenericDeliverable} agentOutputs={effAgentOutputs} />;
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
        activeRunId={activeRunId}
        versionLabel={headerVersionLabel}
        selectedRef={sandboxSelectedRef}
        onSelectVersion={handleVersionMenuSelect}
        latestVersionTag={latestVersionTag}
        latestVersionInFlight={latestVersionInFlight}
        runId={liveRunId ?? activeRunId ?? undefined}
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
      <div className="flex-none px-[30px] pt-4 flex flex-wrap items-center justify-between gap-2 border-b border-line-divider">
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
              runId={activeRunId}
              // Every ppt run is now the HTML-deck pipeline (the legacy
              // PptxGenJS pipeline is retired) — always the HTML-download path.
              isOdPpt={true}
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
              {sandboxSelectedRef ? (
                // U1 — a tag is pinned via the RunHeader VersionMenu: render
                // THAT tag's deliverable, read-only, regardless of the live
                // run's own state (a later revision may still be running).
                // Steps/Files/Thinking/Audit stay on the live run; only this
                // tab and the Workspace tab (ref= already wired) are affected.
                <RefVersionPreview
                  tag={sandboxSelectedRef}
                  content={refDeliverableContent}
                  mimetype={mimetypeForPath(
                    deliverableFile,
                    effGenericDeliverable?.mimetype ||
                      (renderType === "ppt" || renderType === "prototype" ? "text/html" : "text/markdown"),
                  )}
                  filename={deliverableFile ? deliverableFile.split("/").pop() : undefined}
                  agentOutputs={effAgentOutputs}
                  onBackToLatest={() => setSandboxSelectedRef(null)}
                />
              ) : showFailureAffordance || showDivertedAffordance ? (
                // Phase 42-03 (§D / Group D): the FAILED run's amber
                // DegradedRunAffordance is RETIRED on the run screen — a terminal-
                // failed run drops the Preview tab entirely (visibleTabs) and
                // defaults to Audit, so the generic run screen never reaches this
                // branch for it. The other consumers are a CANCELLED-terminal run (a
                // deliberate user Stop, §8 decision 4 keeps history/reopen behavior)
                // and — per ISS-390 — a DIVERTED-terminal run, both of which keep
                // their Preview tab and get status-specific affordance copy instead
                // of the neutral "Output will appear here" live-streaming placeholder.
                // DegradedRunAffordance stays exported for RunDetailPage.tsx:296.
                //
                // ISS-285: the one route that DOES reach this branch for a FAILED
                // run is `/runs/{id}/preview/full`, whose deep link (reopenTabFor,
                // now a real case) forces activeTab="preview" even though
                // visibleTabs dropped the tab. Gating on showFailureAffordance
                // rather than on the cancelled-only case is what makes that forced
                // Preview state its own honest "no deliverable was produced"
                // instead of the generic per-state default silently substituting
                // the Audit trail — the failed counterpart to the cancelled copy
                // this same route already renders correctly. `cancelled`/`diverted`
                // still pick WHICH copy renders.
                <DegradedRunAffordance
                  failedAgents={failedAgentNames}
                  agentNameById={agentNameById}
                  onRetry={onRevisePrototype || onRevisePpt || onReviseUserStory || onReviseAppBuilder}
                  cancelled={isCancelledTerminal}
                  diverted={isDivertedTerminal}
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
              ) : isLoadingRunData ? (
                // ISS-739/ISS-740 (QA-PS-014): the viewed run's own fetch is
                // still in flight. Nothing above can fire yet — no stream is
                // attached for a terminal reopen (isStillRunning false) and
                // reopenedRunStatus is undefined until the fetch resolves, so
                // the failure/diverted affordances are false BY CONSTRUCTION —
                // and the neutral branch below would render the same
                // "Output will appear here" copy it shows for a genuinely empty
                // run. Sits ahead of it so the wait reads as loading, and so a
                // run about to resolve failed/cancelled/diverted never shows the
                // success-shaped placeholder first (ISS-740).
                <RunDataSkeleton />
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
              {/* ISS-300 — the eff* (version-aware) content, NOT the raw props.
                  With a pin active these carry the pinned member's own output,
                  so the Files tab's "Final output" name/size/content match the
                  Preview tab instead of always showing the live/root run's. */}
              <FilesTab workflowType={renderType} userStoryContent={effUserStoryContent} pptContent={effPptContent} prototypeContent={effPrototypeContent} agentOutputs={effAgentOutputs} genericDeliverable={hasGenericDeliverable ? effGenericDeliverable : undefined} runId={activeRunId} parentRunId={activeParentRunId} parentVersionNumber={activeIdx} runInput={effRunInput} clarifications={clarifications ?? pipelineState?.clarifications} onOpenPreview={() => handleTabChange("preview")} runStatus={terminalFailure && !isCancelledTerminal ? "failed" : undefined} isRunning={isStillRunning} buildingTaskIndex={buildStepIndex} buildingTaskTotal={buildStepTotal} buildingFilename={pipelineState?.deliverableFilename} />
            </motion.div>
          )}
          {activeTab === "workspace" && (
            <motion.div
              key="workspace"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0"
            >
              <SandboxTab
                runId={workspaceRunId}
                agentNameById={agentNameById}
                hasDeliverable={hasContent}
                selectedRef={sandboxSelectedRef}
              />
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
                agents={effAgents || []}
                /* ISS-277 — the agent the URL named (`/runs/{id}/steps/{agentId}`),
                   arriving on the same nonce'd deep-link target that selected this
                   tab. Opaque id, matched against the run's own agent ids inside the
                   Steps tab; undefined for every deep link that names no agent. */
                initialAgentId={deepLinkTarget?.agentId}
                pipelineState={effPipelineState}
                /* ISS-752 (QA-PS-014) — same fetch-in-flight signal, one tab over:
                   the Steps trace is empty for the whole reopen fetch too, and its
                   EmptyState tells the user to "start a pipeline" for a run that
                   already ran. */
                isLoadingRunData={isLoadingRunData}
                waves={waves}
                runInput={effRunInput}
                clarifications={clarifications ?? pipelineState?.clarifications}
                revisionParentVersion={revisionParentVersion}
                originalBriefRootRunId={originalBriefRootRunId}
                /* ISS-853 (QA-PS-048) — the family this panel already holds, so the
                   Steps divert-link row reads it instead of re-downloading the run. */
                runFamily={runFamily}
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
                specRevisionCount={specRevisionCount}
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
                workflowRunId={activeRunId ?? undefined}
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
  runId,
  isOdPpt,
}: {
  content?: string;
  pptxCode?: string;
  /** The run actually on screen. Spec 017: the fallback below asks for the most
   *  recent `type=ppt` run, which is the WRONG run whenever the user reopened an
   *  older one — and no run at all for a `ppt_v2` deck, which that filter never
   *  returns. Passing the id the panel already resolved removes the guess. */
  runId?: string | null;
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
      let workflowId = runId ?? "";
      if (!workflowId) {
        try {
          const res = await authedFetch(`${ENV.API_URL}/api/runs?type=ppt&limit=5`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const runs = await res.json();
            if (runs.length > 0) workflowId = runs[0].id;
          }
        } catch { /* ignore */ }
      }
      // FR-015: authedFetch, not bare fetch — this reads a Blob so it can't go
      // through request(); a 401 previously surfaced as a generic
      // "Download failed" alert with no session-expiry redirect.
      const response = await authedFetch(`${ENV.API_URL}/api/runs/export-pptx`, {
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
  }, [content, pptxCode, runId]);

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
