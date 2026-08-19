"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import {
  Download, FileText, Presentation, Layout, Code, Package,
  BookOpen, Settings, Shield, Palette, Database, TestTube,
  GitBranch, Server, FileCode, ChevronDown, Clock,
} from "lucide-react";
import { exportUserStories } from "@/lib/exporters/storyExporter";
import { ENV } from "@/lib/env";
import { parseRunInput } from "@/lib/runInput";
import { renderClarificationsMarkdown } from "@/lib/clarifications";
import type { WorkflowType, GenericDeliverable, ClarifyRound } from "@/types/index";

interface FilesTabProps {
  workflowType: WorkflowType;
  userStoryContent?: string;
  pptContent?: string;
  prototypeContent?: string;
  // Per-agent outputs: each agent's full text becomes a downloadable .md.
  // For live runs the parent derives this from pipelineState.agents (only
  // entries with non-empty output should be passed). For history runs the
  // parent passes WorkflowRun.agentOutputs which the API already returns.
  agentOutputs?: AgentOutputItem[];
  // ISS-021 (18-03) — generic deliverable for any pipeline_type that matched no
  // known FE render branch. When present it yields ONE generic deliverable row
  // (using the resolved mimetype + filename), keeping the per-agent .md outputs
  // grouped as "Agent outputs". Dispatch on mimetype, never a workflow name.
  genericDeliverable?: GenericDeliverable;
  // Revision Families (B3 / POR §5 D6) — the immediately-prior version's run id
  // (the active member's parent_run_id) and its 1-based version number. When
  // parentRunId is non-null a collapsed "From v{n-1}" base-version section
  // renders and lazily fetches the parent's files on first expand. BOTH optional
  // and default undefined → a non-revision run shows NO such section (zero
  // regression for existing renders that pass neither).
  parentRunId?: string | null;
  parentVersionNumber?: number;
  // Workstream C2 (POR §5 D7) — "Run input" section. The raw run input (parsed
  // via C1 parseRunInput → prompt.md) and the answered clarify rounds (rendered
  // via renderClarificationsMarkdown → clarifications.md). BOTH optional and
  // default-undefined → a call site that threads neither shows NO "Run input"
  // section (zero regression). Type-agnostic (SC-001 — no workflowType branch).
  runInput?: string;
  clarifications?: ClarifyRound[];
  // Phase 39-03 (RUNUI-06) — the hero "Preview" action. When provided the dark
  // Final-output hero renders a "Preview" button that calls this (the caller
  // switches to the Preview tab). Optional + default-undefined → the button is
  // omitted (zero regression for callers that don't wire it).
  onOpenPreview?: () => void;
  // Phase 39-03 (RUNUI-06, W6) — the run's terminal status. When "failed" or
  // "degraded" the mock's amber "Build incomplete" banner renders above the file
  // list. Optional + default-undefined → NO banner (zero regression for
  // completed runs). The file list itself already reflects the reduced live
  // outputs (ND-D — never a fabricated planning-only list).
  runStatus?: "failed" | "degraded";
  // Phase 42-07 (RUNUI-06, Group H) — LIVE building signal. While the run is in
  // flight the dark "Final output" hero swaps to a BUILDING variant (spinner +
  // indeterminate top bar + "task N of M · not yet validated") and the Download /
  // Download-All actions are suppressed (nothing to download yet). Bound to the
  // live pipelineState.isRunning (generic — SC-001), NOT a workflow name. Default
  // undefined/false → the settled hero renders unchanged (zero regression). The
  // task counts + in-progress filename are the SAME live values the run header
  // uses (INV-12 — never the mock's fixed literal); each is elided when absent (ND-D).
  isRunning?: boolean;
  buildingTaskIndex?: number;
  buildingTaskTotal?: number;
  buildingFilename?: string;
}

// ─── Workstream C2 (POR §5 D7) — "Run input" file rows (module-level pure) ─────
// Derives prompt.md (the parsed revision instruction OR the brief — whichever the
// input parses to; present whenever non-empty) + clarifications.md (rendered Q&A
// markdown, present ONLY when rounds exist). parseRunInput is called ONCE and the
// primary row dispatches purely on parsed shape (revisionInstruction wins for
// revision runs, brief for originals — mirrors StartingPointCard.isRevision), so
// the filename stays prompt.md for BOTH original and revision runs. Both are plain
// text/markdown FileItems that fall into the default downloadBlob branch — no new
// download code, no special-cased id. Type-agnostic: no workflowType branch.
function runInputFileRows(runInput?: string, clarifications?: ClarifyRound[]): FileItem[] {
  const rows: FileItem[] = [];
  const parsed = parseRunInput(runInput ?? "");
  const primary = parsed.revisionInstruction || parsed.brief;
  if (primary) {
    rows.push({
      id: "run-input-prompt",
      name: "prompt.md",
      type: "Run input",
      icon: FileText,
      format: "Markdown (.md)",
      content: primary,
      mimeType: "text/markdown",
      size: formatSize(primary.length),
    });
  }
  if (clarifications?.length) {
    const md = renderClarificationsMarkdown(clarifications);
    rows.push({
      id: "run-input-clarifications",
      name: "clarifications.md",
      type: "Run input",
      icon: FileText,
      format: "Markdown (.md)",
      content: md,
      mimeType: "text/markdown",
      size: formatSize(md.length),
    });
  }
  return rows;
}

// ─── ISS-021 (18-03) — mimetype → file metadata for the generic deliverable row ──
function genericDeliverableExtension(mimetype?: string): { ext: string; format: string; icon: typeof FileText } {
  const m = (mimetype || "").toLowerCase();
  if (m.includes("html")) return { ext: "html", format: "HTML (.html)", icon: Layout };
  if (m.includes("markdown")) return { ext: "md", format: "Markdown (.md)", icon: FileText };
  if (m.includes("zip")) return { ext: "zip", format: "ZIP Archive", icon: Package };
  if (m.includes("json")) return { ext: "json", format: "JSON (.json)", icon: FileText };
  return { ext: "bin", format: mimetype || "Binary", icon: Package };
}

export interface AgentOutputItem {
  name: string;
  role?: string;
  output: string;
  agentId?: string;
}

interface FileItem {
  id: string;
  name: string;
  type: string;
  icon: typeof FileText;
  size: string;
  format: string;
  content: string;
  mimeType: string;
  // Phase 39-03 — 1–2 letter agent initials for the agent-outputs timeline
  // avatar node (derived from the source agent name). Present only on per-agent
  // rows; undefined for deliverable / run-input / code rows.
  code?: string;
}

// ─── Phase 39-03 — agent initials for the timeline avatar node ────────────────
// "Spec Writer" → "SW", "Task Planner" → "TP", single word → first two letters.
function agentInitials(name?: string): string {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "··";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// ─── Agent ID → documentation metadata ───────────────────────────────────────
// Maps each app_builder agent to a human-readable doc name and icon.
// Agents that produce code files (code-generator, infra-generator, feature-impl,
// test-impl) are handled separately — their ```filename: ... ``` blocks are
// parsed into individual code files.
const APP_BUILDER_DOC_META: Record<string, { label: string; filename: string; icon: typeof FileText }> = {
  "material-analyzer":        { label: "Architecture Overview",      filename: "01-architecture.md",          icon: BookOpen },
  "app-user-stories":         { label: "User Stories & Epics",       filename: "02-user-stories.md",          icon: FileText },
  "app-system-design":        { label: "System Design & ADRs",       filename: "03-system-design.md",         icon: Settings },
  "app-security-architecture":{ label: "Security Architecture",      filename: "04-security-architecture.md", icon: Shield },
  "app-ux-design":            { label: "UX & UI Design",             filename: "05-ux-design.md",             icon: Palette },
  "app-api-design":           { label: "API Contracts (OpenAPI)",    filename: "06-api-contracts.md",         icon: FileCode },
  "app-database-design":      { label: "Data Model & Migrations",    filename: "07-database-design.md",       icon: Database },
  "app-code-compliance":      { label: "Code Compliance & SAST",     filename: "11-code-compliance.md",       icon: Shield },
  "app-test-compliance":      { label: "Test Strategy & Coverage",   filename: "13-test-compliance.md",       icon: TestTube },
  "app-devops":               { label: "DevOps & CI/CD Pipeline",    filename: "14-devops.md",                icon: GitBranch },
  "app-sdlc-governance":      { label: "SDLC Governance & Runbooks", filename: "15-governance.md",            icon: BookOpen },
};

// Agents whose output contains ```filename: ... ``` code blocks to parse
const CODE_PRODUCING_AGENTS = new Set([
  "app-code-generator",
  "app-feature-implementation",
  "app-infra-generator",
  "app-test-implementation",
]);

// ─── Parse ```filename: path ``` blocks from markdown ────────────────────────
// Also handles ### path/to/file + fenced block format used by some agents.
function parseCodeFiles(markdown: string): FileItem[] {
  const files: FileItem[] = [];
  const seen = new Set<string>();

  const mimeMap: Record<string, string> = {
    ts: "text/typescript", tsx: "text/typescript", js: "text/javascript",
    jsx: "text/javascript", py: "text/x-python", json: "application/json",
    md: "text/markdown", yml: "text/yaml", yaml: "text/yaml",
    env: "text/plain", txt: "text/plain", sh: "text/x-sh",
    dockerfile: "text/plain", css: "text/css", html: "text/html",
    sql: "text/x-sql", prisma: "text/plain", toml: "text/plain",
    java: "text/x-java", cs: "text/x-csharp", rb: "text/x-ruby",
    go: "text/x-go", rs: "text/x-rust", kt: "text/x-kotlin",
  };
  const iconMap: Record<string, typeof FileText> = {
    ts: Code, tsx: Code, js: Code, jsx: Code, py: Code,
    json: FileText, md: FileText, yml: Settings, yaml: Settings,
    dockerfile: Server, sh: Code, css: Code, html: Layout,
    sql: Database, java: Code, cs: Code, rb: Code, go: Code,
    rs: Code, kt: Code,
  };

  const addFile = (filePath: string, content: string) => {
    filePath = filePath.trim();
    if (!filePath || !content.trim() || seen.has(filePath)) return;
    const name = filePath.split("/").pop() || filePath;
    const hasDot = name.includes(".");
    const isKnownExtensionless = /^(Dockerfile|Makefile|Procfile|Gemfile|Rakefile)$/i.test(name);
    if (!hasDot && !isKnownExtensionless) return;
    seen.add(filePath);
    const ext = name.includes(".") ? name.split(".").pop()?.toLowerCase() || "txt" : "txt";
    files.push({
      id: `file-${files.length}-${filePath.replace(/[^a-z0-9]/gi, "-")}`,
      name,
      type: filePath,
      icon: iconMap[ext] || FileText,
      size: formatSize(content.length),
      format: ext.toUpperCase(),
      content,
      mimeType: mimeMap[ext] || "text/plain",
    });
  };

  // Format 1: ```filename: path/to/file.ext\n[content]\n```
  const filenameRegex = /```(?:filename:\s*([^\n]+)\n)([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = filenameRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  // Format 2: ### path/to/file.ext\n```[lang]\n[content]\n```
  const headerRegex = /###\s+([\w./\-@][^\n]*\.\w+)\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = headerRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  // Format 3: **`path/to/file.ext`** followed by ```
  const boldRegex = /\*\*`?([\w./\-@][^\n`*]*\.\w+)`?\*\*\s*\n```[^\n]*\n([\s\S]*?)```/g;
  while ((m = boldRegex.exec(markdown)) !== null) addFile(m[1], m[2]);

  return files;
}

// ─── Same parser used by AppBuilderPreview (alias) ───────────────────────────
function parseAppBuilderFiles(markdown: string): FileItem[] {
  return parseCodeFiles(markdown);
}

// ─── SectionHeader — defined outside FilesTab to avoid "component created during render" lint error ──
function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between mb-2 mt-5 first:mt-0">
      <p className="text-[10px] uppercase tracking-wider text-ink-300 font-semibold">{label}</p>
      <span className="text-[9px] text-ink-300 bg-surface-paper px-1.5 py-0.5 rounded font-medium">{count}</span>
    </div>
  );
}

// ─── slugify — shared name normaliser ────────────────────────────────────────
// Converts a raw title / heading string into a URL-safe, word-boundary-safe
// filename stem:
//   1. Strip non-alphanumeric characters except spaces.
//   2. Trim.
//   3. Collapse whitespace runs to a single hyphen.
//   4. Lower-case.
//   5. Truncate to `maxWords` WHOLE WORDS (default 8) so the filename never
//      ends mid-syllable (the old `.slice(0, 40)` bug).
//
// The result is suitable for use as a filename stem — callers append the
// appropriate extension.
function slugify(raw: string, maxWords = 8): string {
  const clean = raw.replace(/[^a-zA-Z0-9\s]/g, "").trim();
  const words = clean.split(/\s+/).filter(Boolean).slice(0, maxWords);
  return words.join("-").toLowerCase();
}

// ─── deriveDeliverableFilename — exported pure helper (KAN-128 / FIX-140) ────
// Returns the content-derived filename (with extension) for the primary
// deliverable of a workflow run. Uses the SAME extraction logic as
// deriveDeliverableFiles so the Files tab and the Preview tab (URL bar +
// header download) always agree.
//
// Parameters
//   workflowType  — the normalised pipeline type (may include _revision suffix)
//   content       — the relevant deliverable content string (or undefined while
//                   still streaming)
//   fallback      — optional static fallback (e.g. pipelineState.deliverableFilename)
//                   used before content is available or for unknown types
//
// SC-001: dispatches on the STRUCTURAL workflowType string exactly as
// deriveDeliverableFiles does — no new pipeline_type branch added to any engine
// surface.
export function deriveDeliverableFilename(
  workflowType: string,
  content: string | undefined,
  fallback?: string,
): string {
  // ── User Stories ──────────────────────────────────────────────────────────
  if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
    if (content) {
      const h = content.match(/^#\s+(.+)/m);
      const stem = h ? slugify(h[1]) : "user-stories";
      return `${stem || "user-stories"}.md`;
    }
    return fallback || "user-stories.md";
  }

  // ── Custom ────────────────────────────────────────────────────────────────
  if (workflowType === "custom") {
    if (content) {
      const h = content.match(/^#\s+(.+)/m);
      const stem = h ? slugify(h[1]) : "custom-output";
      return `${stem || "custom-output"}.md`;
    }
    return fallback || "custom-output.md";
  }

  // ── PPT ────────────────────────────────────────────────────────────────────
  // Every ppt run is the HTML-deck pipeline (formerly od_ppt/od_ppt_revision —
  // see backend/agents/registry.py). All produce HTML.
  if (workflowType === "ppt" || workflowType === "ppt_revision") {
    const ext = "html"; // always HTML — PptxGenJS (.pptx) path is not used
    if (content) {
      const t = content.match(/<title>([^<]+)<\/title>/i);
      const h1 = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
      let stem = "presentation";
      if (t && t[1] !== "Presentation") stem = slugify(t[1]) || "presentation";
      else if (h1) stem = slugify(h1[1]) || "presentation";
      return `${stem}.${ext}`;
    }
    return fallback || `presentation.${ext}`;
  }

  // ── Prototype ─────────────────────────────────────────────────────────────
  if (
    workflowType === "prototype" || workflowType === "prototype_revision"
  ) {
    if (content) {
      const t = content.match(/<title>(.+?)<\/title>/i);
      const stem = t ? slugify(t[1]) : "prototype";
      return `${stem || "prototype"}.html`;
    }
    return fallback || "prototype.html";
  }

  // ── App Builder ───────────────────────────────────────────────────────────
  if (workflowType === "app_builder" || workflowType === "app_builder_revision") {
    return "project.zip";
  }

  // ── Generic fallback ──────────────────────────────────────────────────────
  return fallback || "deliverable";
}

// ─── deriveDeliverableFiles — module-level pure helper (B3 / POR §5 D6) ───────
// The per-type single-deliverable file rows (user_stories, custom, ppt,
// prototype) extracted VERBATIM from the FilesTab body so the base-version
// section can reuse the SAME derivation for the parent run (INV-12 net-negative:
// these branches are DELETED from the body, not copied). The app_builder ZIP
// special-case + the generic-deliverable row stay in the body (they need
// agentOutputs/JSZip and are out of scope for the base-version reference).
// `content` routes into the slot the workflowType self-selects; behaviour is
// byte-identical to the pre-extraction body for any single run (the branches are
// mutually exclusive by workflowType).
function deriveDeliverableFiles(
  workflowType: string,
  content: { userStoryContent?: string; pptContent?: string; prototypeContent?: string },
): FileItem[] {
  const files: FileItem[] = [];
  const { userStoryContent, pptContent, prototypeContent } = content;

  // ── User Stories ──────────────────────────────────────────────────────────
  if ((workflowType === "user_stories" || workflowType === "user_stories_revision") && userStoryContent) {
    let name = "user-stories";
    const h = userStoryContent.match(/^#\s+(.+)/m);
    if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "user-stories-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
  }

  // ── Custom ────────────────────────────────────────────────────────────────
  if (workflowType === "custom" && userStoryContent) {
    let name = "custom-output";
    const h = userStoryContent.match(/^#\s+(.+)/m);
    if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "custom-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
  }

  // ── PPT ───────────────────────────────────────────────────────────────────
  // Every ppt run produces an HTML deck — never a .pptx binary.
  if ((workflowType === "ppt" || workflowType === "ppt_revision") && pptContent) {
    let name = "presentation";
    const t = pptContent.match(/<title>([^<]+)<\/title>/i);
    const h1 = pptContent.match(/<h1[^>]*>([^<]+)<\/h1>/i);
    if (t && t[1] !== "Presentation") name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    else if (h1) name = h1[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    // All variants produce an HTML deck — one HTML download only.
    files.push({ id: "presentation-html", name: `${name}.html`, type: "HTML Presentation", icon: Presentation, size: formatSize(pptContent.length), format: "HTML (.html) — open in browser", content: pptContent, mimeType: "text/html" });
  }

  // ── Prototype ─────────────────────────────────────────────────────────────
  if ((workflowType === "prototype" || workflowType === "prototype_revision") && prototypeContent) {
    let name = "prototype";
    const t = prototypeContent.match(/<title>(.+?)<\/title>/i);
    if (t) name = t[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
    files.push({ id: "prototype-html", name: `${name}.html`, type: "HTML Prototype", icon: Layout, size: formatSize(prototypeContent.length), format: "HTML (.html)", content: prototypeContent, mimeType: "text/html" });
  }

  return files;
}

export function FilesTab({ workflowType, userStoryContent, pptContent, prototypeContent, agentOutputs, genericDeliverable, parentRunId, parentVersionNumber, runInput, clarifications, onOpenPreview, runStatus, isRunning, buildingTaskIndex, buildingTaskTotal, buildingFilename }: FilesTabProps) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  // ─── B3 (POR §5 D6) — base-version "From v{n-1}" section state ────────────────
  // Collapsed by default; the parent run's files are fetched LAZILY on first
  // expand (never while collapsed) and cached. baseFetched guards the fetch to
  // run at most once.
  const [baseOpen, setBaseOpen] = useState(false);
  const [baseLoading, setBaseLoading] = useState(false);
  const [baseFiles, setBaseFiles] = useState<FileItem[] | null>(null);
  const baseFetched = useRef(false);

  const handleToggleBase = useCallback(async () => {
    const next = !baseOpen;
    setBaseOpen(next);
    if (next && !baseFetched.current && parentRunId) {
      baseFetched.current = true;
      setBaseLoading(true);
      try {
        // Reuse the existing dynamic-import idiom (FilesTab.tsx handleDownload).
        const { getWorkflow, getToken } = await import("@/lib/api");
        const parentRun = await getWorkflow(getToken() || "", parentRunId);
        // Route the parent .output into every slot — deriveDeliverableFiles
        // self-selects by parentRun.type.
        const rows = deriveDeliverableFiles(parentRun.type, {
          userStoryContent: parentRun.output,
          pptContent: parentRun.output,
          prototypeContent: parentRun.output,
        });
        setBaseFiles(rows);
      } catch {
        setBaseFiles([]);
      } finally {
        setBaseLoading(false);
      }
    }
  }, [baseOpen, parentRunId]);

  // ── App Builder: split agent outputs into docs + code files (memoized) ───
  const { appBuilderDocFiles, appBuilderCodeFiles } = useMemo(() => {
    const docFiles: FileItem[] = [];
    const codeFiles: FileItem[] = [];
    if ((workflowType === "app_builder" || workflowType === "app_builder_revision") && agentOutputs) {
      for (const agent of agentOutputs) {
        if (!agent.output?.trim()) continue;
        const agentId = agent.agentId || "";
        if (CODE_PRODUCING_AGENTS.has(agentId)) {
          codeFiles.push(...parseCodeFiles(agent.output));
        } else {
          const meta = agentId ? APP_BUILDER_DOC_META[agentId] : undefined;
          const slug = (agent.name || "agent").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50);
          const idx = String((agentOutputs.indexOf(agent) + 1)).padStart(2, "0");
          docFiles.push({
            id: `doc-${agentId || slug}`,
            name: meta?.filename || `${idx}-${slug}.md`,
            type: agent.role || agent.name,
            icon: meta?.icon || FileText,
            size: formatSize(agent.output.length),
            format: "Markdown (.md)",
            content: agent.output,
            mimeType: "text/markdown",
          });
        }
      }
    }
    return { appBuilderDocFiles: docFiles, appBuilderCodeFiles: codeFiles };
  }, [workflowType, agentOutputs]);

  // ── Generic agent files for non-app-builder pipelines (memoized) ─────────
  const genericAgentFiles = useMemo<FileItem[]>(() => {
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") return [];
    return (agentOutputs ?? [])
      .filter(a => a.output?.trim())
      .map((a, i) => {
        const slug = (a.name || "agent").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
        const idx = String(i + 1).padStart(2, "0");
        return {
          // Include index to ensure uniqueness — build agent runs multiple times
          // with the same agentId (e.g. "prototype-build" × 6 tasks)
          id: `agent-${a.agentId || slug}-${i}`,
          name: `${idx}-${slug}.md`,
          type: a.role || "Agent output",
          icon: FileText,
          size: formatSize(a.output.length),
          format: "Markdown (.md)",
          content: a.output,
          mimeType: "text/markdown",
          code: agentInitials(a.name),
        };
      });
  }, [workflowType, agentOutputs]);

  const files: FileItem[] = [];

  // ── App Builder final output: ZIP of all code files ───────────────────────
  // Stays in the body — needs appBuilderCodeFiles + JSZip. Runs FIRST on the
  // empty files array; mutually exclusive with the helper-derived single
  // deliverables below (byte-identical to the pre-extraction ordering).
  if ((workflowType === "app_builder" || workflowType === "app_builder_revision") && userStoryContent) {
    // Also parse the final compiled output for any code files not caught by agent outputs
    const finalCodeFiles = parseAppBuilderFiles(userStoryContent);
    // Merge with agent-parsed code files (deduplicate by path)
    const allCodePaths = new Set(appBuilderCodeFiles.map(f => f.type));
    for (const f of finalCodeFiles) {
      if (!allCodePaths.has(f.type)) {
        appBuilderCodeFiles.push(f);
        allCodePaths.add(f.type);
      }
    }

    if (appBuilderCodeFiles.length > 0) {
      // ZIP download at top
      files.unshift({
        id: "project-zip",
        name: "project.zip",
        type: `All ${appBuilderCodeFiles.length} code files (ZIP)`,
        icon: Package,
        size: `${appBuilderCodeFiles.length} files`,
        format: "ZIP Archive",
        content: userStoryContent,
        mimeType: "application/zip",
      });
    } else {
      // Fallback: single markdown download
      let name = "app-blueprint";
      const h = userStoryContent.match(/^#\s+(.+)/m);
      if (h) name = h[1].replace(/[^a-zA-Z0-9\s]/g, "").trim().replace(/\s+/g, "-").toLowerCase().slice(0, 40);
      files.push({ id: "project-md", name: `${name}.md`, type: "Markdown", icon: FileText, size: formatSize(userStoryContent.length), format: "Markdown (.md)", content: userStoryContent, mimeType: "text/markdown" });
    }
  }

  // ── Single-deliverable current-run rows (user_stories/custom/ppt/prototype) ─
  // Extracted to the module-level deriveDeliverableFiles helper (INV-12
  // net-negative). Mutually exclusive with the app_builder branch above, so the
  // resulting files array is byte-identical to the pre-extraction body.
  files.push(...deriveDeliverableFiles(workflowType, { userStoryContent, pptContent, prototypeContent }));

  // ── ISS-021 (18-03) — generic deliverable row ─────────────────────────────
  // ONE row for any pipeline_type that matched no known branch above. Reuses
  // FileItem.mimeType + the existing downloadBlob path. Filename from the
  // resolved deliverable_filename when present, else derived from the mimetype.
  // Only when no known-branch file was already produced for this content (the
  // generic channel is mutually exclusive with the four known types).
  if (genericDeliverable?.content && files.length === 0) {
    const { ext, format, icon } = genericDeliverableExtension(genericDeliverable.mimetype);
    const name = genericDeliverable.filename || `deliverable.${ext}`;
    files.push({
      id: "generic-deliverable",
      name,
      type: "Deliverable",
      icon,
      size: formatSize(genericDeliverable.content.length),
      format,
      content: genericDeliverable.content,
      mimeType: genericDeliverable.mimetype || "application/octet-stream",
    });
  }

  const handleDownload = useCallback(async (file: FileItem) => {
    if (file.id === "user-stories-md" && userStoryContent) {
      exportUserStories(userStoryContent, file.name.replace(".md", ""));
    } else if (file.id === "project-zip" && userStoryContent) {
      setDownloadingId(file.id);
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if (!(window as any).JSZip) {
          await new Promise<void>((resolve, reject) => {
            const s = document.createElement("script");
            s.src = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js";
            s.onload = () => resolve();
            s.onerror = reject;
            document.head.appendChild(s);
          });
        }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const JSZip = (window as any).JSZip;
        const zip = new JSZip();
        // Include all code files from agent outputs
        const allCode = parseAppBuilderFiles(userStoryContent);
        const seen = new Set<string>();
        for (const f of [...appBuilderCodeFiles, ...allCode]) {
          if (!seen.has(f.type)) { zip.file(f.type, f.content); seen.add(f.type); }
        }
        // Also include doc files as docs/ folder
        for (const d of appBuilderDocFiles) {
          zip.file(`docs/${d.name}`, d.content);
        }
        const blob = await zip.generateAsync({ type: "blob" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "project.zip";
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        alert("Failed to generate ZIP.");
      } finally {
        setDownloadingId(null);
      }
    } else if (file.id === "presentation-pptx" && pptContent) {
      setDownloadingId(file.id);
      try {
        const { getToken } = await import("@/lib/api");
        const token = getToken();
        const title = file.name.replace(".pptx", "").replace(/-/g, " ");
        let workflowId = "";
        try {
          const res = await fetch(`${ENV.API_URL}/api/runs?type=ppt&limit=20`, {
            headers: { "Authorization": `Bearer ${token}` },
          });
          if (res.ok) {
            const runs = await res.json();
            const h1 = pptContent.match(/<h1[^>]*>([^<]+)<\/h1>/i);
            if (h1) {
              const match = runs.find((r: { output?: string }) => r.output?.includes(h1[1]));
              if (match) workflowId = match.id;
            }
            if (!workflowId && runs.length > 0) workflowId = runs[0].id;
          }
        } catch {}
        const response = await fetch(`${ENV.API_URL}/api/runs/export-pptx`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
          body: JSON.stringify({ html: pptContent, workflow_id: workflowId, title }),
        });
        if (response.ok) {
          const blob = await response.blob();
          downloadBlob(URL.createObjectURL(blob), file.name, "");
        } else {
          alert("PPTX export failed. Try the Download PPTX button in the preview.");
        }
      } catch {
        alert("PPTX export failed.");
      } finally {
        setDownloadingId(null);
      }
    } else {
      downloadBlob(file.content, file.name, file.mimeType);
    }
  }, [userStoryContent, pptContent, appBuilderCodeFiles, appBuilderDocFiles]);

  const isAppBuilder = workflowType === "app_builder" || workflowType === "app_builder_revision";
  // Workstream C2 (POR §5 D7) — the "Run input" rows; counted in totalCount so the
  // "{N} files available" header stays truthful, and included in "Download All".
  const runInputRows = runInputFileRows(runInput, clarifications);
  const totalCount = files.length + appBuilderDocFiles.length + appBuilderCodeFiles.length + genericAgentFiles.length + runInputRows.length;

  // While the run is live the building hero renders even before any deliverable /
  // agent output has landed, so the empty-state only shows for a settled run with
  // genuinely nothing (KEEP — zero regression when not running).
  if (totalCount === 0 && !isRunning) {
    return (
      <div className="flex items-center justify-center h-full px-6 bg-surface-paper">
        <div className="text-center">
          <p className="text-sm text-ink-400">No files available</p>
          <p className="text-[11px] text-ink-300 mt-1">Run a workflow to generate downloadable files</p>
        </div>
      </div>
    );
  }

  const renderFileRow = (file: FileItem, idx: number) => {
    const Icon = file.icon;
    return (
      <motion.div
        key={file.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.03 }}
        className="flex items-center gap-3 rounded-[var(--radius-list-row)] border border-line-faint-row bg-surface-card px-4 py-3 hover:border-line-control hover:shadow-sm transition-all"
      >
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-paper border border-line-border flex-shrink-0">
          <Icon className="h-4 w-4 text-ink-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13.5px] font-medium text-ink-800 truncate">{file.name}</p>
          <p className="text-[11.5px] text-ink-300 mt-0.5 truncate">
            {file.type !== file.name ? `${file.type} · ` : ""}{file.size}
          </p>
        </div>
        <button
          onClick={() => handleDownload(file)}
          disabled={downloadingId === file.id}
          className="flex h-[34px] w-[34px] items-center justify-center rounded-lg text-ink-500 hover:text-brand hover:border-brand bg-surface-white border border-line-border transition-all flex-shrink-0 disabled:opacity-50"
          title={`Download ${file.name}`}
        >
          {downloadingId === file.id
            ? <span className="h-3.5 w-3.5 border-2 border-ink-300 border-t-transparent rounded-full animate-spin" />
            : <Download className="h-4 w-4" strokeWidth={1.7} />
          }
        </button>
      </motion.div>
    );
  };

  // ─── B3 (POR §5 D6) — base-version "From v{n-1}" collapsed section ───────────
  // Rendered at the END of both layout branches when parentRunId is truthy.
  // Header clones the plain uppercase SectionHeader label variant (FilesTab.tsx
  // :506,514 — UI-SPEC Surface 4 accepts it); the collapse affordance is a
  // controlled button with a controlled chevron rotate (NOT group-open, which
  // only fires inside a native <details> — the B2 W2 lesson). aria-busy marks
  // the section while the lazy fetch is in flight.
  const baseLabel = `From v${parentVersionNumber ?? "previous"}`;
  const baseAriaLabel = `From version ${parentVersionNumber ?? "previous"}`;
  const baseVersionSection = parentRunId ? (
    <div className="mt-5" aria-busy={baseLoading}>
      <button
        onClick={handleToggleBase}
        aria-expanded={baseOpen}
        aria-label={baseAriaLabel}
        className="w-full flex items-center justify-between mb-2 hover:bg-surface-card rounded transition-colors"
      >
        <span className="text-[10px] uppercase tracking-wider text-ink-300 font-semibold">{baseLabel}</span>
        <ChevronDown aria-hidden className={`h-3.5 w-3.5 text-ink-300 transition-transform ${baseOpen ? "rotate-180" : ""}`} />
      </button>
      {baseOpen && (
        <div className="space-y-2">
          {baseLoading ? (
            <div className="flex items-center gap-2 px-1 py-2">
              <span className="h-3.5 w-3.5 border-2 border-ink-300 border-t-transparent rounded-full animate-spin" />
              <span className="text-[10px] text-ink-300">Loading base version…</span>
            </div>
          ) : baseFiles && baseFiles.length > 0 ? (
            <>
              {baseFiles.map((f, i) => renderFileRow(f, i))}
              <p className="text-[10px] text-ink-300">Files from the previous version this revision was based on.</p>
            </>
          ) : (
            <p className="text-[10px] text-ink-300">No files in the base version.</p>
          )}
        </div>
      )}
    </div>
  ) : null;

  // ── Phase 39-03 — the run's final deliverable (the hero) is files[0] on the
  // non-app-builder path; deliverableCount drives the "· N deliverable" subline.
  const deliverableCount = files.length;
  const finalFile = files[0];

  const downloadAll = () => {
    const all = [...files, ...(isAppBuilder ? appBuilderDocFiles : genericAgentFiles), ...(isAppBuilder ? appBuilderCodeFiles : []), ...runInputRows];
    all.forEach((file, i) => setTimeout(() => handleDownload(file), i * 150));
  };

  // ── Phase 39-03 — dark "Final output" hero (mock Hexaware Run.dc.html:624-638).
  // Names the LIVE final deliverable (finalFile). "validated" is the mock's static
  // deliverable-passed affirmation (ND-Q) — the run reached Files after its
  // validation gate; not a fabricated per-run value (name/format/size are live).
  const HeroIcon = finalFile?.icon ?? FileText;
  const finalOutputHero = finalFile ? (
    <div className="relative overflow-hidden rounded-2xl bg-surface-ink-black px-6 py-[22px]">
      <div aria-hidden className="pointer-events-none absolute -top-10 -right-8 h-[220px] w-[220px] rounded-full" style={{ background: "radial-gradient(circle, rgba(60,44,218,.55), transparent 70%)" }} />
      <div className="relative flex items-center gap-[18px]">
        <div className="grid h-[52px] w-[52px] flex-none place-items-center rounded-xl border border-white/[0.12] bg-white/[0.08]">
          <HeroIcon className="h-6 w-6 text-white" strokeWidth={1.6} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="m-0 font-sans text-[9.5px] font-semibold uppercase tracking-[0.14em] text-brand-on-dark">Final output</p>
          <p className="m-0 mt-1 truncate font-sans text-[17px] font-medium leading-[1.25] text-white">{finalFile.name}</p>
          <p className="m-0 mt-[5px] font-serif text-[12px] text-[#9FA0AE]">{finalFile.format} · {finalFile.size} · validated</p>
        </div>
        <div className="flex flex-none gap-2">
          {onOpenPreview && (
            <button onClick={onOpenPreview} className="inline-flex items-center gap-[7px] rounded-[9px] border border-white/[0.16] bg-transparent px-[13px] py-[9px] font-sans text-[12.5px] font-medium text-[#E7E7EE] transition-colors hover:bg-white/[0.08]">
              Preview
            </button>
          )}
          <button
            onClick={() => handleDownload(finalFile)}
            disabled={downloadingId === finalFile.id}
            className="inline-flex items-center gap-[7px] rounded-[9px] bg-brand px-[14px] py-[9px] font-sans text-[12.5px] font-semibold text-white transition-colors hover:bg-brand-pressed disabled:opacity-50"
          >
            {downloadingId === finalFile.id
              ? <span className="h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              : <Download className="h-3.5 w-3.5" strokeWidth={1.9} />}
            Download
          </button>
        </div>
      </div>
    </div>
  ) : null;

  // ── Phase 42-07 (RUNUI-06, Group H) — BUILDING hero (mock Hexaware Run -
  // Live.dc.html:568-578). Renders in place of the settled `finalOutputHero`
  // while the run is live: an indeterminate top progress bar + a spinner + the
  // "Final output · building" eyebrow + the in-progress filename (finalFile when
  // the streamed deliverable already exists, else the live buildingFilename;
  // elided when neither is known — never fabricated) + a live "task N of M · not
  // yet validated" subline (counts elided when absent — ND-D). NO Download /
  // Preview actions (nothing to download yet). Component-scoped keyframe (uniquely
  // named to avoid a global collision — globals.css is out of scope), mirroring
  // the PreviewChrome indeterminate-bar idiom (INV-12).
  const BUILDING_BAR_KEYFRAMES =
    "@keyframes files-hero-bar{0%{transform:translateX(-100%)}100%{transform:translateX(320%)}}";
  const buildingName = finalFile?.name ?? buildingFilename;
  const buildingSubline = [
    finalFile?.format,
    buildingTaskTotal && buildingTaskTotal > 0
      ? `task ${Math.min(buildingTaskIndex ?? 1, buildingTaskTotal)} of ${buildingTaskTotal}`
      : null,
    "not yet validated",
  ].filter(Boolean).join(" · ");
  const buildingHero = (
    <div data-testid="files-building-hero" className="relative overflow-hidden rounded-2xl bg-surface-ink-black px-6 py-[22px]">
      <style>{BUILDING_BAR_KEYFRAMES}</style>
      <div aria-hidden className="absolute inset-x-0 top-0 h-[3px] overflow-hidden bg-brand-border">
        <div className="h-full w-[30%] bg-brand-on-dark" style={{ animation: "files-hero-bar 1.6s ease-in-out infinite" }} />
      </div>
      <div className="relative flex items-center gap-[18px]">
        <div className="grid h-[52px] w-[52px] flex-none place-items-center rounded-xl border border-white/[0.12] bg-white/[0.08]">
          <span aria-hidden className="h-6 w-6 rounded-full border-2 border-brand-on-dark border-t-transparent animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="m-0 font-sans text-[9.5px] font-semibold uppercase tracking-[0.14em] text-brand-on-dark">Final output · building</p>
          {buildingName && (
            <p className="m-0 mt-1 truncate font-sans text-[17px] font-medium leading-[1.25] text-white">{buildingName}</p>
          )}
          <p className="m-0 mt-[5px] font-serif text-[12px] text-[#9FA0AE]">{buildingSubline}</p>
        </div>
      </div>
    </div>
  );

  // ── Phase 39-03 — "Run input" bordered card pair (mock :658-669). The same
  // live runInputRows (prompt.md / clarifications.md), one compact card each;
  // clicking a card downloads it (reuses handleDownload). Type-agnostic.
  const runInputCards = runInputRows.length > 0 ? (
    <div className="mt-7">
      <p className="m-0 mb-3 font-sans text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-300">Run input</p>
      <div className="flex gap-2.5">
        {runInputRows.map((f) => {
          const Icon = f.icon;
          return (
            <button
              key={f.id}
              onClick={() => handleDownload(f)}
              aria-label={`download ${f.name}`}
              className="flex flex-1 items-center gap-[11px] rounded-[var(--radius-list-row)] border border-line-divider bg-transparent px-[13px] py-[11px] text-left transition-colors hover:border-line-control hover:bg-surface-card"
            >
              <Icon className="h-[17px] w-[17px] flex-none text-ink-300" strokeWidth={1.6} />
              <div className="min-w-0 flex-1">
                <p className="m-0 truncate font-sans text-[12.5px] font-medium text-ink-700">{f.name}</p>
                <p className="m-0 mt-0.5 font-serif text-[11px] text-ink-200">{f.size}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  ) : null;

  // ── Phase 39-03 (W6) — failed-run "Build incomplete" banner (mock Hexaware
  // Run - Failed.dc.html:175). Renders ONLY for a failed/degraded run; the file
  // list below already reflects the reduced live outputs (ND-D — no fabricated
  // planning-only rows). Default runStatus undefined → no banner (zero regression).
  const isFailedRun = runStatus === "failed" || runStatus === "degraded";
  const buildIncompleteBanner = isFailedRun ? (
    <div className="mb-4 flex items-center gap-[9px] rounded-xl border border-status-amber-border bg-status-amber-fill px-[15px] py-[13px]">
      <Clock className="h-[17px] w-[17px] flex-none text-status-amber" strokeWidth={1.8} />
      <span className="font-serif text-[12.5px] leading-[1.4] text-status-amber">
        Build incomplete — only the planning artifacts were produced before the run stopped. No application code was written.
      </span>
    </div>
  ) : null;

  return (
    <div className="h-full overflow-y-auto bg-surface-paper">
      <div className="mx-auto max-w-[860px] px-8 pt-6 pb-16">
        {/* Header — title + subline + Download All (mock :616-622) */}
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="m-0 font-sans text-[22px] font-light leading-[1.2] text-ink-900">Files</p>
            <p className="m-0 mt-1.5 font-serif text-[13px] text-ink-400">
              {totalCount} file{totalCount !== 1 ? "s" : ""} available
              {deliverableCount > 0 ? ` · ${deliverableCount} deliverable${deliverableCount !== 1 ? "s" : ""}` : ""}
            </p>
          </div>
          {/* Download All is suppressed while the run is building (nothing to
              download yet) — Phase 42-07 Group H. */}
          {!isRunning && (
            <button
              onClick={downloadAll}
              className="inline-flex flex-none items-center gap-2 rounded-[var(--radius-button)] border border-line-control bg-surface-card px-[15px] py-[9px] font-sans text-[13px] font-medium text-ink-700 transition-colors hover:border-line-faint hover:bg-surface-white"
            >
              <Download className="h-[15px] w-[15px]" strokeWidth={1.7} />
              Download All
            </button>
          )}
        </div>

        {buildIncompleteBanner}

        {/* Phase 42-07 Group H — while running the BUILDING hero replaces the
            settled deliverable hero (shown here so it precedes both layouts). */}
        {isRunning && buildingHero}

        {/* ── App Builder layout (multi-section; token-reskinned) ─────────────── */}
        {isAppBuilder ? (
          <>
            {files.length > 0 && (
              <>
                <SectionHeader label="Project Download" count={files.length} />
                <div className="space-y-2">{files.map((f, i) => renderFileRow(f, i))}</div>
              </>
            )}

            {appBuilderCodeFiles.length > 0 && (
              <>
                <SectionHeader label="Source Code Files" count={appBuilderCodeFiles.length} />
                <p className="text-[10px] text-ink-300 mb-2">
                  Generated code files — frontend, backend, tests, config, and infrastructure.
                </p>
                <div className="space-y-2">
                  {appBuilderCodeFiles.map((f, i) => renderFileRow(f, files.length + i))}
                </div>
              </>
            )}

            {appBuilderDocFiles.length > 0 && (
              <>
                <SectionHeader label={`Agent Outputs (${appBuilderDocFiles.length})`} count={appBuilderDocFiles.length} />
                <p className="text-[10px] text-ink-300 mb-2">
                  Intermediate output from each agent in the pipeline. Each file contains the full output of one agent.
                </p>
                <div className="space-y-2">
                  {appBuilderDocFiles.map((f, i) => renderFileRow(f, files.length + appBuilderCodeFiles.length + i))}
                </div>
              </>
            )}

            {runInputCards}
            {baseVersionSection}
          </>
        ) : (
          /* ── Non-app-builder layout — hero + agent-outputs + run input ─────── */
          <>
            {/* The settled deliverable hero is replaced by the building hero
                (rendered above) while the run is live — Phase 42-07 Group H. */}
            {!isRunning && finalOutputHero}

            {genericAgentFiles.length > 0 && (
              <div className="mt-7">
                <p className="m-0 mb-1 font-sans text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-300">
                  Agent outputs ({genericAgentFiles.length})
                </p>
                <p className="m-0 mb-3 font-serif text-[12.5px] leading-[1.4] text-ink-300">
                  Intermediate work-in-progress from each agent in the pipeline.
                </p>
                {/* Timeline spine (mock :642-656): a vertical rail behind a
                    per-agent 38px avatar node + the downloadable file-row card. */}
                <div className="relative">
                  <div aria-hidden className="absolute left-[19px] top-3 bottom-[26px] w-0.5 bg-line-divider" />
                  {genericAgentFiles.map((f) => {
                    const Icon = f.icon;
                    return (
                      <motion.div
                        key={f.id}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="relative flex items-center gap-[14px] py-2"
                      >
                        <div className="relative z-[1] grid h-[38px] w-[38px] flex-none place-items-center rounded-full border border-line-control bg-surface-card font-sans text-[11px] font-semibold text-ink-900">
                          {f.code || <Icon className="h-4 w-4 text-ink-500" strokeWidth={1.7} />}
                        </div>
                        <div className="flex min-w-0 flex-1 items-center gap-[14px] rounded-[var(--radius-list-row)] border border-line-faint-row bg-surface-card px-[14px] py-[11px]">
                          <div className="min-w-0 flex-1">
                            <p className="m-0 truncate font-sans text-[13.5px] font-medium text-ink-800">{f.name}</p>
                            <p className="m-0 mt-[3px] font-serif text-[11.5px] text-ink-300">
                              {f.type !== f.name ? `${f.type} · ` : ""}{f.size}
                            </p>
                          </div>
                          <button
                            onClick={() => handleDownload(f)}
                            disabled={downloadingId === f.id}
                            className="grid h-[34px] w-[34px] flex-none place-items-center rounded-lg border border-line-border bg-surface-white text-ink-500 transition-all hover:border-brand hover:text-brand disabled:opacity-50"
                            title={`Download ${f.name}`}
                          >
                            {downloadingId === f.id
                              ? <span className="h-3.5 w-3.5 border-2 border-ink-300 border-t-transparent rounded-full animate-spin" />
                              : <Download className="h-4 w-4" strokeWidth={1.7} />}
                          </button>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </div>
            )}

            {runInputCards}
            {baseVersionSection}
          </>
        )}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

// Exported (INV-12) so the run header's primary Download button reuses the SAME
// blob-download path rather than rolling a second implementation.
export function downloadBlob(content: string, filename: string, mimeType: string) {
  let url: string;
  if (content.startsWith("blob:")) {
    url = content;
  } else {
    const blob = new Blob([content], { type: mimeType });
    url = URL.createObjectURL(blob);
  }
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  if (!content.startsWith("blob:")) URL.revokeObjectURL(url);
}
