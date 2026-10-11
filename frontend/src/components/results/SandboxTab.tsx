"use client";

/**
 * SandboxTab — the run workspace, browsed as a real file tree (spec 017 phase 2).
 *
 * `ppt_v2` is the first workflow whose run leaves TWO artifacts on disk —
 * `presentation.html` and `presentation.pptx` — and only one of them can be the
 * deliverable. The alternative was bolting a second `.pptx` row onto FilesTab,
 * which would have to be extended again for the next workflow that writes a
 * second file. This shows whatever the run actually wrote.
 *
 * LAZY BY DESIGN. The listing is one request; a file's bytes are fetched only
 * when it is opened. A sandbox can hold a multi-megabyte binary, so pulling
 * every file up front (the way FilesTab receives its content) is not an option.
 *
 * Download goes through `fetch`, not an `<a href>` to the endpoint. Auth is a
 * bearer token held in JS, so a browser navigation there arrives anonymous and
 * renders `{"detail":"Not authenticated"}` instead of saving the file (BUG-031).
 *
 * TWO PANES, and the split is workflow-agnostic by construction:
 *
 *   Artifacts — root-level files the server marked `deliverable`, then `.agents/`
 *               on a timeline spine. Curated order, never re-sorted: the agents
 *               are in pipeline order and that ordering IS the information.
 *   All files — every group, sortable, with bulk expand/collapse.
 *
 * Nothing here knows what a workflow is. `deliverable` comes from the backend's
 * `is_deliverable_relpath`, the same predicate the deliverable walk applies, so
 * the fact that `PLANNER.md` is not one lives in `_DELIVERABLE_EXCLUDE` and
 * nowhere else. `.agents/` is written by the ENGINE for every agent of every
 * run, so the spine appears for a deck run and an app build alike — and not at
 * all for a run that wrote no agent output, because the group is then empty.
 *
 * A group's expansion is the USER's, and only the user's. Opening a file never
 * folds anything away — a list that rearranges itself under the click that was
 * meant to open something is a list you cannot navigate twice the same way.
 */

import { createElement, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUpDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Code2,
  Download,
  Eye,
  File,
  FolderDown,
  FileCode,
  FileJson,
  FileText,
  Folder,
  Globe,
  Image as ImageIcon,
  Loader2,
  Lock,
  Package,
  Settings,
} from "lucide-react";

import {
  getRunSandbox,
  getRunSandboxFile,
  getRunSandboxFileBlob,
  getRunSandboxZip,
  getToken,
  type SandboxFile,
} from "@/lib/api";
import { stripStaticPreviewFallback } from "@/lib/deckHtml";
import { downloadBlob } from "./FilesTab";
import { MermaidBlock, isMermaidFence } from "./MermaidBlock";

// ─── Grouping ─────────────────────────────────────────────────────────────────

/** Written by the engine for every agent of every run — see `agent_output_relpath`. */
const AGENTS_PREFIX = ".agents/";

/** Structured chain payload written by the engine on post_run — see Requirement 20.
 *  Listed in the Workspace tab so operators can inspect what a chained workflow
 *  will receive, but EXCLUDED from the deliverable zip (backend's
 *  `is_deliverable_relpath` already marks these `deliverable: false`). */
const CHAIN_PREFIX = ".chain/";

/** Context directory written at sandbox open before step 1 — see Requirement 23.
 *  Contains the OpenDesign material (design-system, craft, template SKILL.md,
 *  seed files) and selections.json.  Listed in the Workspace tab for debugging
 *  but EXCLUDED from the deliverable zip.  Gitignored by design. */
const CONTEXT_PREFIX = ".context/";

/** Legacy chain payloads relocated by the v2 migration (task 6.7).
 *  Excluded from all listing surfaces per Requirement 18 / task 11.6. */
const CHAIN_LEGACY_PREFIX = ".chain-legacy/";

export interface FileGroup {
  id: string;
  label: string;
  desc?: string;
  files: SandboxFile[];
  /** Render each row against a timeline spine with the agent's initials. */
  spine?: boolean;
  /** The label is a real directory name: print it as it is on disk, never
   *  upper-cased into a section heading. `.verify` is a path, not a shout. */
  literal?: boolean;
}

/** `.agents/02-ppt-composer-t3-p2.md` → `ppt-composer`.
 *
 *  The engine's own name shape: a one-based index, the agent id, then optional
 *  `-t<task>` / `-p<pass>` loop identity when a step ran more than once. */
export function agentIdFromPath(path: string): string {
  return path
    .slice(AGENTS_PREFIX.length)
    .replace(/\.md$/i, "")
    .replace(/^\d+-/, "")
    .replace(/-t[^-]*$/, "")
    .replace(/-p\d+$/, "");
}

/** "Deck Composer" → "DC", one word → its first two letters. Mirrors FilesTab. */
export function agentInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "··";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** `ppt-brief-analyst` → `Ppt Brief Analyst`. Only reached when the run's agent
 *  name map has no entry — a reopened run whose agents are no longer in state. */
function prettifyAgentId(id: string): string {
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

const isRoot = (f: SandboxFile) => !f.path.includes("/");
/** Absent on a listing that predates the field: a root file is a deliverable. */
const isDeliverable = (f: SandboxFile) => f.deliverable !== false;

export type SortKey = "name" | "size" | "type";

function sortFiles(files: SandboxFile[], key: SortKey): SandboxFile[] {
  const out = [...files];
  const name = (f: SandboxFile) => f.path.split("/").pop() || f.path;
  if (key === "name") out.sort((a, b) => name(a).localeCompare(name(b)));
  if (key === "size") out.sort((a, b) => b.size - a.size);
  if (key === "type")
    out.sort(
      (a, b) => extOf(name(a)).localeCompare(extOf(name(b))) || name(a).localeCompare(name(b)),
    );
  return out;
}

/** The Artifacts pane: what the run delivered, and who wrote what along the way.
 *
 *  Deliberately NOT sorted. The agents are in pipeline order and the deliverables
 *  in the order the server listed them; re-ordering either destroys the only
 *  thing this pane offers over the flat listing. */
export function artifactGroups(
  files: SandboxFile[],
  agentNameById?: Record<string, string>,
): FileGroup[] {
  const deliverables = files.filter((f) => isRoot(f) && isDeliverable(f));
  const notes = files.filter((f) => isRoot(f) && !isDeliverable(f));
  const agents = files.filter((f) => f.path.startsWith(AGENTS_PREFIX));
  // Chain payload written by the engine on post_run.  Listed here so operators
  // can inspect what a chained workflow will receive — but these files are NOT
  // deliverables and are NOT included in the zip download.  The backend marks
  // them `deliverable: false` via `is_deliverable_relpath`; the group label and
  // description make the same fact visible to the user.
  const chain = files.filter((f) => f.path.startsWith(CHAIN_PREFIX));
  // Context directory written at sandbox open before step 1 (Requirement 23).
  // Contains the OpenDesign material seeded for agents to read from disk rather
  // than receiving it injected into the system prompt.  Listed but not delivered.
  const context = files.filter((f) => f.path.startsWith(CONTEXT_PREFIX));

  const groups: FileGroup[] = [];
  if (deliverables.length)
    groups.push({
      id: "deliverables",
      label: "Deliverables",
      desc: "What the client receives.",
      files: deliverables,
    });
  if (agents.length)
    groups.push({
      id: "agents",
      label: "Agent outputs",
      desc: "Intermediate work-in-progress from each agent in the pipeline.",
      files: agents,
      spine: true,
    });
  if (chain.length)
    groups.push({
      id: "chain",
      label: "Chain payload",
      desc: "Structured run history available to chained workflows. Not included in the deliverable zip.",
      files: chain,
    });
  if (context.length)
    groups.push({
      id: "context",
      label: "Run context",
      desc: "OpenDesign material written at sandbox open (design system, template, craft rules). Not included in the deliverable zip.",
      files: context,
    });
  if (notes.length) groups.push({ id: "notes", label: "Run notes", files: notes });
  // Everything nested that is not .agents/ or .chain/ — reachable only from
  // All files, but named here so the counts in the segment stay honest.
  void agentNameById;
  return groups;
}

/** The All files pane: one group per top-level directory, root files first. */
export function allFileGroups(files: SandboxFile[]): FileGroup[] {
  const root = files.filter(isRoot);
  const byDir = new Map<string, SandboxFile[]>();
  for (const f of files) {
    if (isRoot(f)) continue;
    const dir = f.path.slice(0, f.path.indexOf("/"));
    const list = byDir.get(dir);
    if (list) list.push(f);
    else byDir.set(dir, [f]);
  }
  const groups: FileGroup[] = [];
  if (root.length) groups.push({ id: "root", label: "Root", files: root });
  for (const [dir, list] of [...byDir].sort((a, b) => a[0].localeCompare(b[0])))
    groups.push({ id: `dir:${dir}`, label: dir, files: list, literal: true });
  return groups;
}

function extOf(name: string): string {
  return name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
}

/** Which of the three text views a text file gets.
 *
 *  `plain` is a <pre>. `markdown` renders, `html` gets a Code/Preview toggle —
 *  a run's `PLANNER.md` and `presentation.html` are the two files anyone opens
 *  this tab for, and reading either as escaped source is not looking at it. */
function textFlavour(path: string): "markdown" | "html" | "code" | "plain" {
  const e = extOf(path);
  if (e === "md" || e === "markdown") return "markdown";
  if (e === "html" || e === "htm") return "html";
  if (CODE_EXTS.has(e)) return "code";
  return "plain";
}

const CODE_EXTS = new Set([
  "js", "jsx", "ts", "tsx", "mjs", "cjs", "py", "rb", "go", "rs", "java", "kt",
  "c", "h", "cpp", "cs", "php", "swift", "sh", "bash", "zsh", "sql", "json",
  "jsonl", "css", "scss", "xml", "svg", "yml", "yaml", "toml", "ini",
]);

/** Fence the payloads an agent wraps in a protocol tag, before markdown sees them.
 *
 *  An agent output is markdown with a machine payload pasted inside it:
 *
 *      <spec> {"title": …, "slides": [ … ] } </spec>          (brief analyst)
 *      <artifact type="text/html"> <!DOCTYPE html> … </artifact>  (composer)
 *      <!DOCTYPE html> … </html>                             (deck QA, codegen)
 *
 *  Those markers ARE the statement "this part is code", so they become fenced
 *  blocks and render in the editor. That fixes three things at once:
 *
 *   - readability — react-markdown runs without `rehype-raw` (a security
 *     invariant, not an oversight), so an unfenced document is escaped tag by
 *     tag and reflowed into one unreadable paragraph;
 *   - the payload is now code, in a code view, which is where it belongs;
 *   - speed. These payloads arrive as SINGLE LINES of 29–32k characters, and
 *     micromark's inline tokeniser costs ~300ms on each one — five of them are
 *     most of the 4.3s this file used to take. Inside a fence there is no
 *     inline pass at all.
 *
 *  Anything already fenced is left alone, so a file that got this right itself
 *  is untouched. */
export function fenceAgentPayloads(md: string): string {
  // DEFECT 1 FIX: Normalize fence markers glued to narration before processing.
  // CommonMark would not treat a glued fence as valid either, so we're
  // deliberately forgiving of agent output that puts markers on the same line
  // as prose. Only split when we have a clear code fence pattern:
  // text immediately followed by ``` and a language identifier (no whitespace between).
  // This avoids false positives from prose mentioning fence syntax.
  const normalized = md
    .replace(/([^\s`])(`{3,}|~{3,})([a-z])/gi, '$1\n$2\n$3');

  const lines = normalized.split("\n");
  const out: string[] = [];
  let plain: string[] = [];
  let fence: string | null = null;

  // DEFECT 2 FIX: Track wrapper tags to avoid treating internal fences as boundaries.
  // When inside a <spec>, <tasks>, <analysis>, or <artifact> tag, internal
  // fence markers (```) should not be treated as fence boundaries — the entire
  // wrapper should be passed to fenceOne as plain text.
  let wrapperTag: string | null = null;

  const flush = () => {
    if (!plain.length) return;
    out.push(fenceOne(plain.join("\n")));
    plain = [];
  };

  // An open fence's opening line, its info string, and the lines inside it. The
  // block is BUFFERED rather than written straight out, because whether it is
  // really code cannot be known until its closing line arrives — see the
  // unwrap check below.
  let fenceOpen = "";
  let fenceInfo = "";
  let fenced: string[] = [];

  for (const line of lines) {
    // Check if we're starting or inside an existing fence.
    const m = /^\s{0,3}(`{3,}|~{3,})/.exec(line);
    if (m) {
      const ch = m[1][0];
      if (fence === null) {
        flush();
        fence = ch;
        fenceOpen = line;
        fenceInfo = line.slice(line.indexOf(m[1]) + m[1].length).trim();
        fenced = [];
        continue;
      }
      if (ch === fence) {
        fence = null;
        // ── An agent that fenced its OWN prose ────────────────────────────────
        // The task planner writes `# Task Planner Agent`, then opens a bare ```
        // fence and puts <tasks>…</tasks> inside it — so its markdown arrived as
        // a code block with `<tasks>` on line 1. "Never reach inside an existing
        // fence" is the right default and stays: a ```js block is a deliberate
        // claim and must survive untouched. But a fence whose ENTIRE body is a
        // prose wrapper is that same wrapper, wearing one more layer; the agent
        // fenced a document, not code.
        //
        // Narrow on purpose. It requires BOTH an empty info string — ```js or
        // ```html names a language and is left alone — and a body that is
        // exactly one wrapper, opening on its first line and closing on its
        // last. Anything else falls through and is emitted verbatim.
        const body = fenced.join("\n").trim();
        const w = /^<(spec|tasks|analysis)\b[^>]*>([\s\S]*)<\/\1\s*>$/i.exec(body);
        if (!fenceInfo && w) {
          out.push("", w[2].trim(), "");
        } else {
          out.push(fenceOpen, ...fenced, line);
        }
        fenced = [];
        continue;
      }
    }
    if (fence !== null) {
      fenced.push(line);
      continue;
    }
    
    // Only check for wrapper tags when NOT inside a fence.
    // Check if we're inside a wrapper tag and track its boundaries.
    if (wrapperTag) {
      // Inside a wrapper: accumulate and check for closing tag.
      if (new RegExp(`</${wrapperTag}\\s*>`, 'i').test(line)) {
        wrapperTag = null;
      }
      plain.push(line);
      continue;
    } else {
      // Not inside a wrapper: check if one opens.
      const openMatch = /^<(spec|tasks|analysis|artifact)\b/i.exec(line);
      if (openMatch) {
        wrapperTag = openMatch[1].toLowerCase();
        plain.push(line);
        continue;
      }
    }
    
    // A line this long is not prose. Nothing a person writes reaches 4000
    // characters on one line; what does is source pasted mid-sentence, and
    // `conversation_history` is full of it — 29–32k-character lines that cost
    // micromark ~300ms EACH to tokenise inline, which is most of the 4s that
    // file used to take. Unmarked, so `fenceOne` cannot see it: the only signal
    // is the length itself.
    if (line.length >= LONG_LINE_IS_CODE) {
      flush();
      out.push("```", line, "```");
      continue;
    }
    plain.push(line);
  }
  // A fence that never closed: emit it verbatim rather than dropping the lines
  // the buffer is holding.
  if (fence !== null) out.push(fenceOpen, ...fenced);
  // An unclosed wrapper tag: add a synthetic closing tag so fenceOne can process it.
  if (wrapperTag) {
    plain.push(`</${wrapperTag}>`);
  }
  flush();
  return out.join("\n");
}

const LONG_LINE_IS_CODE = 4000;

/** Strip the agent protocol wrappers; fence what is actually a document.
 *
 *  `<spec>`, `<tasks>` and `<analysis>` are TRANSPORT MARKERS. They say which
 *  step produced the payload, not what the payload is — every one of the three
 *  carries a markdown document written for a person to read. So all three are
 *  unwrapped and handed to the markdown renderer, with no test on the body.
 *
 *  This used to fence `<spec>` on the strength of the tag alone, which is why
 *  `01-prototype-specify.md` rendered as raw source — headings and table pipes
 *  as literal characters — while `02-…-plan.md` and `03-…-analyze.md` rendered
 *  correctly, purely because their tags were absent from the list.
 *
 *  `<artifact>` and a bare `<!DOCTYPE html>` are the other thing: a whole
 *  document, pasted in. react-markdown runs without `rehype-raw` (a security
 *  invariant, not an oversight), so unfenced they are escaped tag by tag into
 *  one unreadable paragraph. They get the fence.
 *
 *  Nothing here inspects the body. Pasted source that carries no marker at all
 *  is caught by LONG_LINE_IS_CODE in the caller, on line length — which is also
 *  what keeps a large JSON payload out of the inline tokeniser regardless of
 *  which tag delivered it. */
function fenceOne(text: string): string {
  return text.replace(
    // Branch order matters: a whole document wins over the last branch, which
    // is the orphan case — a bare `<!DOCTYPE html>` whose `</html>` was already
    // consumed by an earlier match. Left alone it renders as escaped prose in
    // the middle of a paragraph.
    //
    // The document branch is GREEDY on purpose. A composer deck nests a second
    // document inside its presenter-window template (`<!DOCTYPE` at 6 and 911,
    // `</html>` at 960 and 970), so stopping at the first `</html>` cuts the
    // deck in half and spills its tail into the page as prose. The last one is
    // the real end.
    //
    // The LAST branch is the orphaned OPENER: `<artifact …>` whose `</artifact>`
    // never arrived because the agent's output was cut off mid-payload (one real
    // run ends `</parameter></invoke>` with the deck still open). The closed
    // branch above cannot match it, so the tag used to escape into the prose
    // paragraph it was glued onto — `…self-contained HTML file.<artifact
    // identifier="…">`. It requires WHITESPACE AND ATTRIBUTES on purpose: every
    // real opener in the corpus carries `identifier=`, while all 39 bare
    // `<artifact>` occurrences are prose describing the format ("Emit between
    // `<artifact>` tags:") and must be left exactly as written. Everything after
    // an orphaned opener IS the payload — there is no closer to end it — so it
    // runs to the end of the input.
    /<(spec|tasks|analysis)\b[^>]*>([\s\S]*?)<\/\1\s*>|<artifact\b[^>]*>([\s\S]*?)<\/artifact\s*>|<!DOCTYPE\s+html[\s\S]*<\/html\s*>|<!DOCTYPE\s+html[^\n]*|<artifact\s+[^>]*>([\s\S]*)/gi,
    (match, proseTag, proseBody, artifactBody, orphanBody) => {
      // Prose wrapper — unwrap, full stop.
      if (proseTag) return `\n\n${proseBody.trim()}\n\n`;

      const t = (artifactBody ?? orphanBody ?? match).trim();
      // A payload that already fenced itself needs unwrapping, not a second
      // fence around the first.
      if (/^(`{3,}|~{3,})/.test(t)) return `\n\n${t}\n\n`;
      return `\n\n\`\`\`html\n${t}\n\`\`\`\n\n`;
    },
  );
}

// Rendered markdown, styled to match MarkdownPreview. NO `rehype-raw` and no
// rehypePlugins at all — react-markdown's default escapes raw HTML to literal
// text, and these bytes are agent-authored. Adding rehype-raw here would render
// a sandbox file's `<script>` in the app's own origin; the HTML flavour above
// exists precisely so live markup goes through a sandboxed iframe instead.
// Prose is capped at a readable measure. Code is NOT: a block is read by
// scanning lines, and wrapping it to 72ch would put a horizontal scrollbar on
// something that had room to breathe.
const MEASURE = "max-w-[72ch]";

const MD_COMPONENTS = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className={`mb-2 mt-4 text-[15px] font-bold text-ink-900  ${MEASURE}`}>{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className={`mb-2 mt-5 border-b border-line-divider pb-1 text-[14px] font-bold text-ink-900  ${MEASURE}`}>
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className={`mb-1 mt-4 text-[13px] font-semibold text-ink-900  ${MEASURE}`}>{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className={`mb-2 text-[12.5px] leading-[1.6] text-ink-700  ${MEASURE}`}>{children}</p>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className={`my-1 space-y-0.5 pl-4 ${MEASURE}`}>{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className={`my-1 list-decimal space-y-0.5 pl-4 ${MEASURE}`}>{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="text-[12.5px] leading-[1.6] text-ink-700 marker:text-brand">{children}</li>
  ),
  // A fenced block arrives as <pre><code class="language-x">. Only the fenced
  // case gets the full code view; inline `code` stays inline.
  code: ({ className, children }: { className?: string; children?: React.ReactNode }) => {
    const text = String(children ?? "");
    // A ```mermaid fence is a picture, not source. Drawn here exactly as the
    // agent panel draws it (JudgedContent) — a design document's transition
    // diagram is the page worth reading, and CodeView would show `flowchart TD`
    // and a list of arrows instead. MermaidBlock falls back to the source in a
    // code block when the chart does not parse, so a typo stays visible.
    if (isMermaidFence(className)) return <MermaidBlock chart={text.replace(/\n$/, "")} />;
    const lang = /language-(\w+)/.exec(className || "")?.[1];
    if (lang || text.includes("\n"))
      return (
        <span className="block min-w-0 max-w-full">
          <CodeView code={text.replace(/\n$/, "")} lang={lang} />
        </span>
      );
    return (
      <code className="rounded border border-brand-border bg-brand-fill px-1.5 py-0.5 font-mono text-[12px] text-brand">
        {children}
      </code>
    );
  },
  // The block above is already a container; a <pre> wrapper would nest one
  // scroller inside another.
  pre: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-line-divider">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border-b border-line-divider bg-surface-warm px-3 py-2 text-left font-semibold text-ink-900">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border-b border-line-faint-row px-3 py-2 text-ink-700">{children}</td>
  ),
  hr: () => <hr className="my-4 border-line-divider" />,
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-ink-900">{children}</strong>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className={`my-2 border-l-[3px] border-brand pl-3 italic text-ink-600 ${MEASURE}`}>
      {children}
    </blockquote>
  ),
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand underline">
      {children}
    </a>
  ),
};

/** How to present a file. `kind` is served by the API; `text` is the older
 *  field and the fallback for a listing that predates it. */
function kindOf(file: SandboxFile): "text" | "image" | "pdf" | "binary" {
  return file.kind ?? (file.text ? "text" : "binary");
}

function iconFor(name: string): typeof File {
  const map: Record<string, typeof File> = {
    ts: FileCode, tsx: FileCode, js: FileCode, jsx: FileCode,
    py: FileCode, json: FileJson, md: FileText, txt: FileText,
    yml: Settings, yaml: Settings, css: FileCode, html: Globe,
    sh: FileCode, sql: FileCode, pptx: Package, zip: Package,
    png: ImageIcon, jpg: ImageIcon, jpeg: ImageIcon, gif: ImageIcon,
    webp: ImageIcon, svg: ImageIcon, pdf: FileText,
  };
  return map[extOf(name)] || File;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Source, in a real editor. ONE component, both surfaces: the full-file view
 *  and every fenced block inside a rendered markdown file.
 *
 *  CodeMirror 6, LAZILY imported — a run workspace is not on the critical
 *  path, so the editor must never enter the main bundle. Until it resolves the
 *  same bytes render in a <pre>, which is also what a test or a no-JS render
 *  sees.
 *
 *  NOT read-only, and it says so on the strip below the editor. ⌘F opens
 *  Replace and Replace has to be able to write, so the doc takes keystrokes —
 *  but there is no save path for a run artifact, and opening another file
 *  re-fetches the server's bytes. A pane that swallows typing and drops it
 *  without a word is the defect (ISS-383); the strip is the answer, and it
 *  lives in here so BOTH surfaces carry it (ISS-597).
 *
 *  Deliberately NOT `AppBuilderPreview`'s approach: that injects highlight.js
 *  from a CDN at runtime — a third-party script in the app's own origin, and
 *  dead offline.
 *
 *  Seven direct packages, no meta-package and no `basicSetup`: state, view,
 *  language, search, two grammars and the highlight tags. Autocomplete and
 *  linting — the parts that only pay off in a file you are going to save — are
 *  not pulled in. `history` and the edit keymaps ARE, for the reason on the
 *  extensions list below. */
function CodeView({
  code,
  lang,
  fill,
}: {
  code: string;
  lang?: string;
  /** Full-file view: fill the pane and drop the outer frame. */
  fill?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let view: { destroy: () => void } | null = null;
    let cancelled = false;

    (async () => {
      const [state, viewMod, language, search, commands, js, htmlLang, cssLang, mdLang, hl] =
        await Promise.all([
          import("@codemirror/state"),
          import("@codemirror/view"),
          import("@codemirror/language"),
          import("@codemirror/search"),
          import("@codemirror/commands"),
          import("@codemirror/lang-javascript"),
          import("@codemirror/lang-html"),
          import("@codemirror/lang-css"),
          import("@codemirror/lang-markdown"),
          import("@lezer/highlight"),
        ]);
      if (cancelled) return;

      const t = hl.tags;
      // The palette is the app's, not a stock editor theme — a foreign colour
      // scheme in the middle of a warm-paper surface reads as an embed.
      //
      // Every colour resolves through a token. It used to take its BACKGROUND
      // from var(--surface-white) while carrying its text as literal hexes, so
      // the dark theme flipped the surface to #222 and left the ink near-black:
      // a markdown file opened to a code block showing line numbers and nothing
      // else, and an HTML block whose property names vanished while its strings
      // survived. One style, both themes — see --code-* in globals.css.
      const highlight = language.HighlightStyle.define([
        { tag: [t.keyword, t.moduleKeyword], color: "var(--code-keyword)" },
        { tag: [t.string, t.special(t.string)], color: "var(--code-string)" },
        { tag: [t.number, t.bool, t.null], color: "var(--code-number)" },
        { tag: [t.comment, t.lineComment, t.blockComment], color: "var(--code-comment)", fontStyle: "italic" },
        { tag: [t.propertyName, t.attributeName], color: "var(--code-property)" },
        { tag: [t.function(t.variableName), t.function(t.propertyName)], color: "var(--code-function)" },
        { tag: [t.typeName, t.className, t.tagName], color: "var(--code-type)" },
        { tag: [t.operator, t.punctuation, t.separator], color: "var(--code-punctuation)" },
        { tag: t.invalid, color: "var(--code-invalid)" },
        // Markdown's own tags. Without these the grammar parses and nothing
        // colours, which reads as "highlighting is broken" rather than
        // "this theme forgot markdown".
        { tag: t.heading, color: "var(--ink-900)", fontWeight: "700" },
        { tag: t.strong, fontWeight: "700" },
        { tag: t.emphasis, fontStyle: "italic" },
        { tag: [t.link, t.url], color: "var(--code-function)", textDecoration: "underline" },
        { tag: t.monospace, color: "var(--code-string)" },
        { tag: t.quote, color: "var(--code-punctuation)", fontStyle: "italic" },
        { tag: t.list, color: "var(--code-keyword)" },
        { tag: t.contentSeparator, color: "var(--code-gutter)" },
      ]);

      const theme = viewMod.EditorView.theme({
        "&": {
          // Code sits on white, not on the warm page. Paper is for prose; a
          // listing wants the flat ground its colours were picked against.
          backgroundColor: "var(--surface-white)",
          color: "var(--code-fg)",
          // Full-file fills the pane; a fenced block is capped and scrolls
          // INSIDE itself — clipping it with overflow:hidden made the rest of
          // the file unreachable, and letting it grow pushed the whole pane
          // sideways.
          // Viewport-relative: a flat 420px left acres of white under a short
          // document on a tall screen, and was most of the screen on a short one.
          ...(fill ? { height: "100%" } : { maxHeight: "min(70vh, 760px)" }),
        },
        "&.cm-focused": { outline: "none" },
        ".cm-scroller": {
          fontFamily: "var(--font-mono)",
          fontSize: "11.5px",
          lineHeight: "1.65",
          overflow: "auto",
        },
        ".cm-content": { padding: "12px 0" },
        ".cm-gutters": {
          backgroundColor: "var(--surface-warm)",
          color: "var(--code-gutter)",
          border: "none",
          borderRight: "1px solid var(--line-divider)",
        },
        ".cm-lineNumbers .cm-gutterElement": { padding: "0 10px 0 12px", minWidth: "2.2em" },
        ".cm-foldGutter .cm-gutterElement": { padding: "0 4px", cursor: "pointer" },
        ".cm-activeLine": { backgroundColor: "var(--code-active-line)" },
        ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--code-gutter-active)" },
        ".cm-selectionBackground, ::selection": { backgroundColor: "var(--code-selection)" },
        ".cm-cursor": { borderLeftColor: "var(--brand)" },
        ".cm-panels": {
          backgroundColor: "var(--surface-card)",
          color: "var(--ink-700)",
          fontFamily: "var(--font-sans)",
          fontSize: "11.5px",
        },
        ".cm-panels.cm-panels-top": { borderBottom: "1px solid var(--line-divider)" },
        ".cm-panel.cm-search": {
          padding: "8px 10px",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "6px",
        },
        ".cm-panel.cm-search input, .cm-panel.cm-search button, .cm-panel.cm-search label": {
          fontFamily: "var(--font-sans)",
          fontSize: "11.5px",
        },
        ".cm-panel.cm-search input[type=text]": {
          padding: "4px 8px",
          borderRadius: "7px",
          border: "1px solid var(--line-control)",
          backgroundColor: "var(--surface-white)",
          color: "var(--code-fg)",
          outline: "none",
        },
        ".cm-panel.cm-search input[type=text]:focus": { borderColor: "var(--brand)" },
        ".cm-panel.cm-search button:not([name=close])": {
          padding: "4px 9px",
          borderRadius: "7px",
          border: "1px solid var(--line-control)",
          backgroundColor: "var(--surface-white)",
          color: "var(--ink-700)",
          backgroundImage: "none",
          cursor: "pointer",
        },
        ".cm-panel.cm-search button:not([name=close]):hover": {
          borderColor: "var(--line-faint)",
          backgroundColor: "var(--surface-warm)",
        },
        ".cm-panel.cm-search [name=close]": {
          color: "var(--code-comment)",
          fontSize: "15px",
          cursor: "pointer",
          padding: "0 4px",
        },
        // The panel ships native checkboxes and bare text nodes; left alone they
        // are the one part of this surface that looks like a browser default.
        ".cm-panel.cm-search label": {
          display: "inline-flex",
          alignItems: "center",
          gap: "5px",
          color: "var(--code-punctuation)",
          cursor: "pointer",
          whiteSpace: "nowrap",
        },
        ".cm-panel.cm-search input[type=checkbox]": {
          accentColor: "var(--brand)",
          width: "13px",
          height: "13px",
          margin: 0,
          cursor: "pointer",
        },
        ".cm-searchMatch": { backgroundColor: "var(--code-search-match)" },
        ".cm-searchMatch-selected": { backgroundColor: "var(--code-search-selected)" },
      });

      const e = (lang || "").toLowerCase();
      const grammar =
        e === "ts" || e === "tsx"
          ? js.javascript({ typescript: true, jsx: e === "tsx" })
          : ["js", "jsx", "mjs", "cjs", "json", "jsonl"].includes(e)
            ? js.javascript({ jsx: e === "jsx" })
            : ["html", "htm", "svg", "xml"].includes(e)
              ? htmlLang.html()
              : ["css", "scss", "less"].includes(e)
                ? cssLang.css()
                : ["md", "markdown"].includes(e)
                  ? mdLang.markdown()
                  : null;

      view = new viewMod.EditorView({
        parent: el,
        state: state.EditorState.create({
          doc: code,
          extensions: [
            viewMod.lineNumbers(),
            language.foldGutter(),
            language.codeFolding(),
            viewMod.highlightActiveLine(),
            viewMod.highlightActiveLineGutter(),
            search.highlightSelectionMatches(),
            language.syntaxHighlighting(highlight),
            // ⌘F opens Find AND Replace. Replace has to be able to write, so
            // the doc is editable — but it is a SCRATCHPAD: there is no save
            // path for a run artifact, and Download always re-fetches the
            // server's bytes, so nothing you do here can alter what shipped.
            search.search({ top: true }),
            commands.history(),
            viewMod.keymap.of([
              ...search.searchKeymap,
              ...language.foldKeymap,
              ...commands.historyKeymap,
              ...commands.defaultKeymap,
            ]),
            theme,
            ...(grammar ? [grammar] : []),
          ],
        }),
      });
      setReady(true);
    })();

    return () => {
      cancelled = true;
      view?.destroy();
      setReady(false);
    };
  }, [code, lang]);

  return (
    <div
      className={
        fill
          ? "flex h-full min-h-0 flex-col bg-surface-white"
          : "my-2 min-w-0 max-w-full overflow-hidden rounded-[6px] border border-line-border bg-surface-white"
      }
    >
      {/* Only a fenced block needs to name its language — the full-file view
          already has the filename in the header above it. */}
      {!fill && lang && (
        <span className="block border-b border-line-border bg-surface-warm px-3 py-1 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-500">
          {lang}
        </span>
      )}
      <div ref={host} className={fill ? "min-h-0 flex-1" : ""} />
      {!ready && (
        <pre className="overflow-x-auto bg-surface-white px-3.5 py-3 font-mono text-[11.5px] leading-[1.65] text-ink-800">
          {code}
        </pre>
      )}
      {/* The one thing the pane never said: it takes keystrokes and throws
          them away. Here rather than at either call site — the full-file view
          and every fenced block in a rendered markdown file are the same
          function, so one strip covers both. */}
      <span className="flex flex-none items-center gap-1 border-t border-line-border bg-surface-warm px-3 py-1 text-[9.5px] text-ink-400">
        <Lock className="h-2.5 w-2.5 flex-none" />
        Read-only scratchpad — edits are not saved
      </span>
    </div>
  );
}

// ─── Rows ─────────────────────────────────────────────────────────────────────

function FileRow({
  file,
  label,
  sub,
  node,
  active,
  onSelect,
}: {
  file: SandboxFile;
  label: string;
  sub?: string;
  /** 1–2 letter agent initials — renders the spine avatar instead of an icon. */
  node?: string;
  active: boolean;
  onSelect: (f: SandboxFile) => void;
}) {
  // iconFor returns one of a fixed set of module-level lucide components, so
  // this is not a component "created during render"; createElement makes that
  // explicit to react-hooks/static-components instead of a capitalised local.
  const fileIcon = iconFor(file.path.split("/").pop() || file.path);
  return (
    <div className={node ? "relative flex items-center gap-3 py-1" : ""}>
      {node && (
        <span className="relative z-[1] grid h-[38px] w-[38px] flex-none place-items-center rounded-full border border-line-control bg-surface-card text-[11px] font-semibold text-ink-900">
          {node}
        </span>
      )}
      <button
        type="button"
        onClick={() => onSelect(file)}
        aria-current={active}
        className={`flex w-full min-w-0 items-center gap-[11px] rounded-[11px] border px-[11px] py-[9px] text-left transition-colors ${
          active
            ? "border-brand-border bg-brand-violet-tint"
            : "border-line-faint-row bg-surface-card hover:border-line-control hover:bg-surface-white"
        }`}
      >
        {!node &&
          createElement(fileIcon, {
            className: `h-4 w-4 flex-none ${active ? "text-brand" : "text-ink-400"}`,
            strokeWidth: 1.7,
          })}
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-[12.5px] font-medium ${
              active ? "text-brand-pressed" : "text-ink-800"
            }`}
          >
            {label}
          </span>
          {sub && <span className="mt-0.5 block truncate font-serif text-[11px] text-ink-500">{sub}</span>}
        </span>
        <span className="flex-none text-[10.5px] tabular-nums text-ink-500">
          {formatBytes(file.size)}
        </span>
      </button>
    </div>
  );
}

/** Split `files` under `prefix` into the files directly in it and its sub-folders. */
export function folderLevel(
  files: SandboxFile[],
  prefix: string,
): { here: SandboxFile[]; dirs: [string, SandboxFile[]][] } {
  const here: SandboxFile[] = [];
  const dirs = new Map<string, SandboxFile[]>();
  for (const f of files) {
    const rel = f.path.slice(prefix.length);
    const slash = rel.indexOf("/");
    if (slash < 0) {
      here.push(f);
      continue;
    }
    const name = rel.slice(0, slash);
    const list = dirs.get(name);
    if (list) list.push(f);
    else dirs.set(name, [f]);
  }
  return { here, dirs: [...dirs].sort((a, b) => a[0].localeCompare(b[0])) };
}

/** Every sub-folder path below a top-level directory — what Expand all opens. */
export function allSubDirs(files: SandboxFile[]): Set<string> {
  const out = new Set<string>();
  for (const f of files) {
    const parts = f.path.split("/");
    for (let i = 2; i < parts.length; i++) out.add(parts.slice(0, i).join("/"));
  }
  return out;
}

/** A directory group's files as a real tree: sub-folders (collapsed until
 *  clicked) first, then the files directly inside, named by basename. */
function FolderTree({
  files,
  prefix,
  sort,
  openDirs,
  onToggleDir,
  activePath,
  onSelect,
}: {
  files: SandboxFile[];
  prefix: string;
  sort: SortKey;
  openDirs: Set<string>;
  onToggleDir: (path: string) => void;
  activePath?: string;
  onSelect: (f: SandboxFile) => void;
}) {
  const { here, dirs } = folderLevel(files, prefix);
  return (
    <>
      {dirs.map(([name, list]) => {
        const path = `${prefix}${name}`;
        const open = openDirs.has(path);
        return (
          <div key={path}>
            <button
              type="button"
              onClick={() => onToggleDir(path)}
              aria-expanded={open}
              className="flex w-full items-center gap-1.5 rounded-[9px] px-1.5 py-1.5 text-left text-[12px] font-medium text-ink-700 transition-colors hover:bg-surface-card"
            >
              <ChevronRight
                className={`h-3 w-3 flex-none text-ink-400 transition-transform ${open ? "rotate-90" : ""}`}
              />
              <Folder className="h-3.5 w-3.5 flex-none text-ink-400" strokeWidth={1.7} />
              <span className="min-w-0 flex-1 truncate">{name}</span>
              <span className="flex-none text-[10px] tabular-nums text-ink-400">{list.length}</span>
            </button>
            {open && (
              <div className="ml-[11px] space-y-1.5 border-l border-line-divider pl-2.5 pt-1">
                <FolderTree
                  files={list}
                  prefix={`${path}/`}
                  sort={sort}
                  openDirs={openDirs}
                  onToggleDir={onToggleDir}
                  activePath={activePath}
                  onSelect={onSelect}
                />
              </div>
            )}
          </div>
        );
      })}
      {sortFiles(here, sort).map((f) => (
        <FileRow
          key={f.path}
          file={f}
          label={f.path.slice(prefix.length)}
          active={activePath === f.path}
          onSelect={onSelect}
        />
      ))}
    </>
  );
}

function GroupBlock({
  group,
  open,
  onToggle,
  children,
}: {
  group: FileGroup;
  open: boolean;
  onToggle: (id: string) => void;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5 last:mb-0">
      <button
        type="button"
        onClick={() => onToggle(group.id)}
        aria-expanded={open}
        className={`flex w-full items-center gap-1.5 px-1 py-1 text-left font-semibold text-ink-500 transition-colors hover:text-ink-800 ${
          group.literal
            ? "text-[11.5px] tracking-normal"
            : "text-[10.5px] uppercase tracking-[0.12em]"
        }`}
      >
        <ChevronRight
          className={`h-3 w-3 flex-none text-ink-400 transition-transform ${open ? "rotate-90" : ""}`}
        />
        {group.label}
        <span className="ml-auto text-[10px] font-medium normal-case tracking-normal tabular-nums text-ink-400">
          {group.files.length}
        </span>
      </button>
      {open && group.desc && (
        <p className="mb-2 ml-1 font-serif text-[11.5px] leading-[1.45] text-ink-500">
          {group.desc}
        </p>
      )}
      {open && <div className="space-y-1.5 pt-1">{children}</div>}
    </div>
  );
}

// ─── The tab ──────────────────────────────────────────────────────────────────

export interface SandboxTabProps {
  /** The run whose workspace to browse. Absent → nothing to show. */
  runId?: string | null;
  /** Agent id → display name, for the spine. The same map PreviewPanel already
   *  builds from `pipelineState.agents` (live) or the reopened run's outputs.
   *  An id it does not carry falls back to a prettified form of the id. */
  agentNameById?: Record<string, string>;
  /** Whether this run actually produced a deliverable. ISS-356/ISS-586: the
   *  expired empty state may only point at the Preview and Files tabs when the
   *  caller CONFIRMS one exists — `expired` is a directory-existence flag
   *  (`run_files.py`, `not sandbox.root.is_dir()`) and cannot tell a completed
   *  run from a diverted/failed/cancelled one that never produced anything.
   *  Absent → say nothing about a deliverable rather than assert a false one. */
  hasDeliverable?: boolean;
  /** Controlled ref (version tag) selection — the RunHeader VersionMenu is the
   *  ONLY selector (task U1); this tab just reflects it read-only. */
  selectedRef?: string | null;
}

export function SandboxTab({ runId, agentNameById, hasDeliverable, selectedRef: selectedRefProp }: SandboxTabProps) {
  const [files, setFiles] = useState<SandboxFile[]>([]);
  const [expired, setExpired] = useState(false);
  const [truncated, setTruncated] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [active, setActive] = useState<SandboxFile | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [archiving, setArchiving] = useState(false);

  // Which pane, how All files is sorted, and which groups are COLLAPSED
  // (shut, not open — a new group is expanded by default without having to be
  // added to the set first).
  const [pane, setPane] = useState<"artifacts" | "all">("artifacts");
  const [sort, setSort] = useState<SortKey>("name");
  const [shut, setShut] = useState<Set<string>>(new Set());
  // Sub-folders inside an All files directory group — OPEN ones, so every
  // sub-folder starts collapsed.
  const [openDirs, setOpenDirs] = useState<Set<string>>(new Set());
  const toggleDir = useCallback((path: string) => {
    setOpenDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  // ── Ref (version tag) selection (Requirement 17/19) ──────────────────────
  // ``selectedRef=null`` means "live working tree". When a ref is selected the
  // listing is read-only (Requirement 18) and all file reads go through
  // git show <ref>:<path> — HEAD never moves. The RunHeader VersionMenu is the
  // ONLY selector (task U1) — this tab purely mirrors the controlled prop.
  const [selectedRef, setSelectedRef] = useState<string | null>(selectedRefProp ?? null);
  useEffect(() => {
    if (selectedRefProp !== undefined) {
      setSelectedRef(selectedRefProp ?? null);
    }
  }, [selectedRefProp]);

  // Images and PDFs are shown, not just offered as a download — the validator
  // writes its evidence as `.verify/slide-NN.png` and `.verify/presentation.pdf`,
  // and "binary file, use Download" is a useless answer for something a human
  // came here to look at. They arrive as a Blob through the SAME authed fetch a
  // download uses (an <img src> at the endpoint sends no Authorization and
  // renders the API's 401 body — BUG-031), then get an object URL.
  //
  // The live URL is held in a ref, not derived from state: revoking has to
  // happen exactly once per URL, and doing it inside a setState updater runs
  // twice under StrictMode and kills the URL that just replaced it.
  // Markdown opens rendered, HTML opens as source with a Preview button — the
  // one you want by default in each case. Either can be toggled.
  const [rendered, setRendered] = useState(false);
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const mediaUrlRef = useRef<string | null>(null);
  const setMedia = useCallback((url: string | null) => {
    if (mediaUrlRef.current) URL.revokeObjectURL(mediaUrlRef.current);
    mediaUrlRef.current = url;
    setMediaUrl(url);
  }, []);
  useEffect(
    () => () => {
      if (mediaUrlRef.current) URL.revokeObjectURL(mediaUrlRef.current);
      mediaUrlRef.current = null;
    },
    [],
  );

  useEffect(() => {
    if (!runId) return;
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    setListLoading(true);
    setListError(null);
    // A new run is a new workspace: drop whatever file was open.
    setActive(null);
    setContent(null);
    setMedia(null);
    // ISS-830: StrictMode's dev remount runs the cleanup below before any
    // microtask does — list one tick late, from the surviving mount only.
    Promise.resolve()
      .then(() => (cancelled ? null : getRunSandbox(token, runId, selectedRef ?? undefined)))
      .then((res) => {
        if (!res || cancelled) return;
        // Filter .chain-legacy/ from the listing — it is reserved and must not
        // appear in any Workspace surface (Requirement 18 / task 11.6).
        setFiles(res.files.filter((f) => !f.path.startsWith(CHAIN_LEGACY_PREFIX)));
        setExpired(res.expired);
        setTruncated(res.truncated);
        setShut(new Set());
        setPane("artifacts");
      })
      .catch((err: Error) => {
        if (!cancelled) setListError(err.message);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, selectedRef, setMedia]);

  const handleSelect = useCallback(
    (file: SandboxFile) => {
      const kind = kindOf(file);
      setRendered(textFlavour(file.path) === "markdown");
      setActive(file);
      setContent(null);
      setMedia(null);
      setFileError(null);
      // Anything the viewer cannot render stays a Download; everything else is
      // fetched now — text as a string, an image or a PDF as a Blob.
      if (kind === "binary" || !runId) return;
      const token = getToken();
      if (!token) return;
      setFileLoading(true);
      const ref = selectedRef ?? undefined;
      const read =
        kind === "text"
          ? getRunSandboxFile(token, runId, file.path, ref).then(setContent)
          : getRunSandboxFileBlob(token, runId, file.path, ref).then((blob) =>
              setMedia(URL.createObjectURL(blob)),
            );
      read
        .catch((err: Error) => setFileError(err.message))
        .finally(() => setFileLoading(false));
    },
    [runId, selectedRef, setMedia],
  );

  // Fetched with the auth header, then handed to the browser as an object URL.
  // Pointing an <a href> at the endpoint instead sends no Authorization (the
  // token lives in JS, not a cookie), so the download rendered the API's
  // {"detail":"Not authenticated"} body — BUG-031.
  const handleDownload = useCallback(() => {
    const token = getToken();
    if (!active || !runId || !token) return;
    const name = active.path.split("/").pop() || "file";
    setFileError(null);
    setDownloading(true);
    getRunSandboxFileBlob(token, runId, active.path, selectedRef ?? undefined)
      // Not revoked, matching FilesTab's own blob download: revoking right after
      // the synthetic click races the browser's own read of the URL.
      .then((blob) => downloadBlob(URL.createObjectURL(blob), name, ""))
      .catch((err: Error) => setFileError(err.message))
      .finally(() => setDownloading(false));
  }, [active, runId, selectedRef]);

  const handleDownloadAll = useCallback(() => {
    const token = getToken();
    if (!runId || !token) return;
    setListError(null);
    setArchiving(true);
    getRunSandboxZip(token, runId, selectedRef ?? undefined)
      .then((blob) => downloadBlob(URL.createObjectURL(blob), `workspace-${runId.slice(0, 8)}.zip`, ""))
      .catch((err: Error) => setListError(err.message))
      .finally(() => setArchiving(false));
  }, [runId, selectedRef]);

  const toggleGroup = useCallback((id: string) => {
    setShut((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const groups = useMemo(
    () => (pane === "artifacts" ? artifactGroups(files) : allFileGroups(files)),
    [files, pane],
  );

  const deliverableCount = useMemo(
    () => files.filter((f) => !f.path.includes("/") && f.deliverable !== false).length,
    [files],
  );
  const artifactCount = useMemo(
    () => artifactGroups(files).reduce((n, g) => n + g.files.length, 0),
    [files],
  );

  // The row's label and subline. An agent output is named by its agent, the way
  // FilesTab names it — a raw `.agents/02-ppt-composer.md` in a product surface
  // is the filesystem showing through.
  const describe = useCallback(
    (g: FileGroup, f: SandboxFile) => {
      const base = f.path.split("/").pop() || f.path;
      if (!g.spine) {
        // Inside a directory group, keep the path RELATIVE to that directory —
        // `app/page.tsx`, not a bare `page.tsx` that collides with three others.
        // Chain payload files are grouped as id "chain" but contain multiple
        // run subdirectories (.chain/{run_id}/…), so strip the .chain/ prefix
        // to show `run_id/summary.md` rather than a bare `summary.md` that
        // would be ambiguous across revisions.
        const label = g.id.startsWith("dir:")
          ? f.path.slice(g.label.length + 1)
          : g.id === "chain"
            ? f.path.slice(CHAIN_PREFIX.length)
            : base;
        return { label, sub: undefined, node: undefined };
      }
      const id = agentIdFromPath(f.path);
      const name = agentNameById?.[id] ?? prettifyAgentId(id);
      return { label: base, sub: name, node: agentInitials(name) };
    },
    [agentNameById],
  );

  if (!runId) {
    return (
      <div className="p-6 text-[12px] text-ink-400">
        The workspace appears once a run has started.
      </div>
    );
  }

  if (expired) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1.5 p-6 text-center">
        <p className="text-[13px] font-medium text-ink-700">Workspace expired</p>
        <p className="max-w-[380px] text-[12px] leading-relaxed text-ink-400">
          Run workspaces are cleared after a retention period.
          {hasDeliverable &&
            " The deliverable is still on the Preview and Files tabs — only the raw working files are gone."}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Rail — header, pane segment, topbar (All files only), groups */}
      {/* Proportional with a floor: a fixed 300px rail left ~300px of viewer
          when the run view hands this panel 620px, which is not enough to read
          a line of code in. */}
      <div className="flex w-[clamp(212px,32%,300px)] flex-shrink-0 flex-col border-r border-line-divider bg-surface-paper">
        <div className="flex-shrink-0 border-b border-line-divider px-4 pb-3 pt-3.5">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-[15.5px] font-semibold tracking-[-0.012em] text-ink-900">
                Workspace
              </p>
              <p className="mt-0.5 font-serif text-[11.5px] text-ink-500">
                {deliverableCount} deliverable{deliverableCount !== 1 ? "s" : ""} · {files.length}{" "}
                file{files.length !== 1 ? "s" : ""}
              </p>
            </div>
            {files.length > 0 && (
              <button
                type="button"
                onClick={handleDownloadAll}
                disabled={archiving}
                title="Download the whole workspace as a zip"
                className="flex flex-none items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-2.5 py-1.5 text-[11.5px] font-medium text-ink-700 transition-colors hover:border-line-faint hover:bg-surface-white disabled:opacity-50"
              >
                {archiving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FolderDown className="h-3.5 w-3.5" strokeWidth={1.7} />
                )}
                {archiving ? "Zipping…" : "Download all"}
              </button>
            )}
          </div>
          {/* Read-only notice — the ONE version selector lives in the RunHeader's
              top VersionMenu (task U1); this tab only reflects the controlled
              `selectedRef` prop it is given, never changes it itself. */}
          {selectedRef && (
            <p className="mt-2 font-serif text-[11px] text-ink-400">
              Viewing <span className="font-sans font-medium text-ink-600">{selectedRef}</span> · read-only
            </p>
          )}
          <div className="mt-2.5 flex gap-0.5 rounded-[9px] border border-line-divider bg-surface-warm p-0.5">
            {(
              [
                ["artifacts", "Artifacts", artifactCount],
                ["all", "All files", files.length],
              ] as const
            ).map(([id, label, count]) => (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setPane(id);
                  // All files opens COLLAPSED: five groups and 36 rows is a
                  // wall, and the set of directories is the useful first
                  // answer. Artifacts is short, so it opens expanded.
                  setShut(
                    id === "all" ? new Set(allFileGroups(files).map((g) => g.id)) : new Set(),
                  );
                }}
                aria-selected={pane === id}
                role="tab"
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-[7px] px-2 py-1 text-[11.5px] transition-colors ${
                  pane === id
                    ? "bg-surface-white font-semibold text-ink-900 shadow-sm"
                    : "font-medium text-ink-500 hover:text-ink-800"
                }`}
              >
                {label}
                <span className="text-[10px] tabular-nums text-ink-400">{count}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Sort and bulk expand/collapse belong to All files only. Artifacts is
            a curated pair of groups in a deliberate order — pipeline order for
            the agents — so offering to re-sort it offers to break it. */}
        {pane === "all" && (
          <div className="flex flex-shrink-0 items-center gap-1 border-b border-line-divider bg-surface-warm px-3 py-1.5">
            <button
              type="button"
              onClick={() =>
                setSort((k) => (k === "name" ? "size" : k === "size" ? "type" : "name"))
              }
              className="flex items-center gap-1.5 rounded-[7px] px-1.5 py-1 text-[11px] font-medium text-ink-700 transition-colors hover:bg-surface-card"
            >
              <ArrowUpDown className="h-3 w-3 text-ink-500" strokeWidth={1.8} />
              <span className="font-semibold text-ink-900">
                {sort === "name" ? "Name" : sort === "size" ? "Size" : "Type"}
              </span>
            </button>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => {
                setShut(new Set());
                setOpenDirs(allSubDirs(files));
              }}
              className="flex items-center gap-1 rounded-[7px] px-1.5 py-1 text-[11px] font-medium text-ink-500 transition-colors hover:bg-surface-card hover:text-ink-800"
            >
              <ChevronsUpDown className="h-3 w-3" strokeWidth={1.8} /> Expand all
            </button>
            <button
              type="button"
              onClick={() => {
                setShut(new Set(groups.map((g) => g.id)));
                setOpenDirs(new Set());
              }}
              className="flex items-center gap-1 rounded-[7px] px-1.5 py-1 text-[11px] font-medium text-ink-500 transition-colors hover:bg-surface-card hover:text-ink-800"
            >
              <ChevronsDownUp className="h-3 w-3" strokeWidth={1.8} /> Collapse all
            </button>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {listLoading && (
            <div className="flex items-center gap-1.5 px-1 py-2 text-[11px] text-ink-500">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading workspace…
            </div>
          )}
          {listError && <div className="px-1 py-2 text-[11px] text-status-failed">{listError}</div>}
          {!listLoading && !listError && files.length === 0 && (
            <div className="px-1 py-2 text-[11px] text-ink-500">This run wrote no files.</div>
          )}

          {/* A run whose every file is nested — no root output, no agent
              outputs — has an empty Artifacts pane. Say where its files are
              rather than rendering a blank column. */}
          {!listLoading && !listError && files.length > 0 && groups.length === 0 && (
            <div className="px-1 py-2 font-serif text-[11.5px] leading-relaxed text-ink-500">
              This run wrote nothing at the top level.{" "}
              <button
                type="button"
                onClick={() => setPane("all")}
                className="font-sans font-medium text-brand underline underline-offset-2"
              >
                See all {files.length} files
              </button>
              .
            </div>
          )}

          {groups.map((group) => {
            const open = !shut.has(group.id);
            const rows = pane === "all" ? sortFiles(group.files, sort) : group.files;
            return (
              <GroupBlock key={group.id} group={group} open={open} onToggle={toggleGroup}>
                {group.spine ? (
                  <div className="relative">
                    {/* The rail sits behind the 38px avatar column. */}
                    <div
                      aria-hidden
                      className="absolute bottom-4 left-[19px] top-3 w-0.5 bg-line-divider"
                    />
                    {rows.map((f) => {
                      const d = describe(group, f);
                      return (
                        <FileRow
                          key={f.path}
                          file={f}
                          label={d.label}
                          sub={d.sub}
                          node={d.node}
                          active={active?.path === f.path}
                          onSelect={handleSelect}
                        />
                      );
                    })}
                  </div>
                ) : group.id.startsWith("dir:") ? (
                  <FolderTree
                    files={group.files}
                    prefix={`${group.label}/`}
                    sort={sort}
                    openDirs={openDirs}
                    onToggleDir={toggleDir}
                    activePath={active?.path}
                    onSelect={handleSelect}
                  />
                ) : (
                  rows.map((f) => {
                    const d = describe(group, f);
                    return (
                      <FileRow
                        key={f.path}
                        file={f}
                        label={d.label}
                        active={active?.path === f.path}
                        onSelect={handleSelect}
                      />
                    );
                  })
                )}
              </GroupBlock>
            );
          })}

          {truncated && (
            <p className="px-1 py-2 font-serif text-[10.5px] leading-relaxed text-ink-500">
              Only the first {files.length} files are shown — this workspace is larger than the
              listing limit.
            </p>
          )}
        </div>
      </div>

      {/* Viewer — a WHITE canvas against the rail's warm paper, so the pane
          reads as the file itself rather than as more of the app. The header
          strip stays on paper: it is chrome, and it should look like it. */}
      <div className="flex min-w-0 flex-1 flex-col bg-surface-white">
        {!active && (
          <div className="flex h-full items-center justify-center p-6 text-[12px] text-ink-400">
            Select a file to view it.
          </div>
        )}
        {active && (
          <>
            <div className="flex items-center gap-2 border-b border-line-divider bg-surface-paper px-3 py-2">
              <span className="truncate text-[12px] font-medium text-ink-900">{active.path}</span>
              <span className="flex-shrink-0 text-[10.5px] text-ink-400">
                {formatBytes(active.size)}
              </span>
              <span className="ml-auto flex flex-none items-center gap-1.5">
              {content !== null &&
                (textFlavour(active.path) === "markdown" ||
                  textFlavour(active.path) === "html") && (
                <button
                  type="button"
                  onClick={() => setRendered((r) => !r)}
                  className="flex flex-shrink-0 items-center gap-1 rounded-[6px] border border-line-border px-2 py-1 text-[11px] text-ink-700 transition-colors hover:bg-surface-warm"
                >
                  {rendered ? <Code2 className="h-3 w-3" /> : <Eye className="h-3 w-3" />}{" "}
                  {rendered ? "Code" : "Preview"}
                </button>
              )}
              <button
                type="button"
                onClick={handleDownload}
                disabled={downloading}
                className="flex flex-shrink-0 items-center gap-1 rounded-[6px] border border-line-border px-2 py-1 text-[11px] text-ink-700 transition-colors hover:bg-surface-warm disabled:opacity-50"
              >
                {downloading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Download className="h-3 w-3" />
                )}{" "}
                Download
              </button>
              </span>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {fileLoading && (
                <div className="flex items-center gap-1.5 p-4 text-[11px] text-ink-400">
                  <Loader2 className="h-3 w-3 animate-spin" /> Loading…
                </div>
              )}
              {fileError && <div className="p-4 text-[11px] text-status-failed">{fileError}</div>}
              {kindOf(active) === "binary" && !fileLoading && (
                <div className="p-4 text-[12px] leading-relaxed text-ink-400">
                  This is a binary file — use Download to open it in the app that
                  understands it.
                </div>
              )}
              {mediaUrl && kindOf(active) === "image" && (
                <div className="flex justify-center p-4">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={mediaUrl}
                    alt={active.path}
                    className="max-w-full rounded-[6px] border border-line-border"
                  />
                </div>
              )}
              {mediaUrl && kindOf(active) === "pdf" && (
                <iframe
                  src={mediaUrl}
                  title={active.path}
                  className="h-full min-h-[520px] w-full border-0"
                />
              )}
              {/* Source lands in a <pre>, never in HTML: the bytes are
                  agent-authored. The one place they become live markup is the
                  HTML preview below, inside an iframe with `allow-scripts` and
                  NOT `allow-same-origin` — an opaque origin that cannot reach
                  this document. */}
              {/* EVERY source view is the editor — colours, gutter, folding,
                  ⌘F — not just the extensions that happen to be in CODE_EXTS.
                  An HTML deck read as source is exactly as much code as a
                  build attempt is, and a plain <pre> for one of them and an
                  editor for the other is a distinction with no meaning. */}
              {/* A zero-byte file in an empty editor reads as a failed load.
                  Say which it is. */}
              {content === "" && !fileLoading && (
                <p className="border-b border-line-divider bg-surface-warm px-4 py-2 font-serif text-[11.5px] text-ink-500">
                  This file is empty — the run created it and wrote nothing.
                </p>
              )}
              {content !== null &&
                content !== "" &&
                (textFlavour(active.path) === "code" ||
                  !rendered ||
                  textFlavour(active.path) === "plain") && (
                  <CodeView code={content} lang={extOf(active.path)} fill />
                )}
              {content !== null && rendered && textFlavour(active.path) === "markdown" && (
                <div className="min-w-0 max-w-full px-5 py-4">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                    {fenceAgentPayloads(content)}
                  </ReactMarkdown>
                </div>
              )}
              {content !== null && rendered && textFlavour(active.path) === "html" && (
                <iframe
                  srcDoc={stripStaticPreviewFallback(content)}
                  title={active.path}
                  sandbox="allow-scripts"
                  className="h-full min-h-[520px] w-full border-0 bg-white"
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
