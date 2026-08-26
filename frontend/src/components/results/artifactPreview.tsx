"use client";

/**
 * artifactPreview — the shared, name-free artifact discriminator + the
 * Spec/Tasks/Analysis read-only preview renderers.
 *
 * Extracted from ReviewGatePanel.tsx (INV-12: one implementation per behavior).
 * The settled artifact cards (42-09) AND the gate plan-preview (42-08) both
 * consume this module — there is exactly one copy of the discriminator and the
 * three parsers.
 *
 * SC-001: `discriminateArtifact` keys ONLY on (output, artifactKind) — the
 * DECLARED structural artifact kind and the artifact's own `<spec>/<tasks>/
 * <analysis>` wrapper tag — NEVER a workflow-name or agent-id literal.
 *
 * Presentation-only: parsers output plain strings rendered as escaped React
 * text (no raw HTML injection). No fetch / data source is introduced here;
 * the consumers pass in-state agent output.
 */

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CheckCircle2, XCircle, Sparkles, AlertTriangle, Code2, Copy, Check } from "lucide-react";

/**
 * discriminateArtifact — pick the artifact card/preview kind from the agent
 * output and its declared artifactKind. Returns null when neither a declared
 * kind nor a recognized wrapper tag is present (an ordinary agent output
 * renders no card — SC-001 generic degrade).
 *
 * artifactKind is authoritative; the content-tag sniff is the name-free
 * fallback when the kind is omitted. Precedence: spec → tasks → analysis.
 */
export function discriminateArtifact(
  output: string,
  artifactKind?: string,
): "spec" | "tasks" | "analysis" | null {
  const isSpec = artifactKind === "spec" || /<spec[\s>]/i.test(output);
  if (isSpec) return "spec";
  const isTasks = artifactKind === "task_list" || /<tasks[\s>]/i.test(output);
  if (isTasks) return "tasks";
  const isAnalysis = artifactKind === "summary" || /<analysis[\s>]/i.test(output);
  if (isAnalysis) return "analysis";
  return null;
}

// Parse <spec>…</spec> into { heading, body } sections. Shared by SpecPreview (the
// list renderer) and the settled pages GRID card in AgentDetailPanel — one parse
// implementation (INV-12). `overview` is the intro text before the first `## `.
export function parseSpecSections(content: string): { heading: string; body: string[] }[] {
  const specMatch = content.match(/<spec>([\s\S]*?)<\/spec>/i);
  const specContent = specMatch ? specMatch[1].trim() : content;
  const lines = specContent.split("\n");
  const sections: { heading: string; body: string[] }[] = [];
  let current: { heading: string; body: string[] } | null = null;
  for (const line of lines) {
    if (line.startsWith("## ")) {
      if (current) sections.push(current);
      current = { heading: line.replace("## ", ""), body: [] };
    } else if (line.startsWith("# ")) {
      // Title — skip
    } else if (current) {
      if (line.trim()) current.body.push(line);
    }
  }
  if (current) sections.push(current);
  return sections;
}

// The spec's intro text (the paragraph between the `# Title` and the first `## `).
export function parseSpecOverview(content: string): string {
  const specMatch = content.match(/<spec>([\s\S]*?)<\/spec>/i);
  const inner = specMatch ? specMatch[1].trim() : content;
  return inner
    .split(/\n##\s/)[0]
    .split("\n")
    .map(l => l.trim())
    .filter(l => l && !l.startsWith("#"))
    .join(" ");
}

// Parse <tasks>…</tasks> into the plan's numbered rows. Shared by TasksPreview (the
// list renderer) and the settled tasks CARD in AgentDetailPanel — one parse
// implementation (INV-12). The card counts the PLAN, so its rows have to come from the
// artifact body; it used to read the build agent's completed-task stream instead, which
// is a different quantity (ISS-087).
export function parseTasks(
  content: string,
): { number: number; title: string; goal: string; raw: string }[] {
  const tasksMatch = content.match(/<tasks>([\s\S]*?)<\/tasks>/i);
  const tasksContent = tasksMatch ? tasksMatch[1].trim() : content;
  return tasksContent
    .split(/(?=##\s+Task\s+\d+)/)
    .filter(b => b.trim())
    .map(block => {
      const numMatch = block.match(/##\s+Task\s+(\d+):\s*(.+)/);
      const goalMatch = block.match(/\*\*Goal\*\*:\s*(.+)/);
      return {
        number: numMatch ? parseInt(numMatch[1]) : 0,
        title: numMatch ? numMatch[2].trim() : block.slice(0, 60),
        goal: goalMatch ? goalMatch[1].trim() : "",
        raw: block,
      };
    })
    .filter(t => t.number > 0);
}

// ─── Spec renderer — parses <spec>...</spec> into readable sections ───────────
export function SpecPreview({ content }: { content: string }) {
  const sections = parseSpecSections(content);
  if (sections.length === 0) {
    const specMatch = content.match(/<spec>([\s\S]*?)<\/spec>/i);
    const specContent = specMatch ? specMatch[1].trim() : content;
    return (
      <pre className="text-[11px] text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
        {specContent.slice(0, 3000)}
      </pre>
    );
  }

  return (
    <div className="space-y-3">
      {sections.map((s, i) => (
        <div key={i} className="rounded-lg border border-line-divider overflow-hidden">
          <div className="px-3 py-2 bg-surface-warm border-b border-line-divider">
            <p className="text-[11px] font-bold text-ink-700">{s.heading}</p>
          </div>
          <div className="px-3 py-2">
            {s.body.map((line, j) => (
              <p key={j} className="text-[11px] text-ink-600 leading-relaxed">{line}</p>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Task list renderer — read-only numbered task rows ────────────────────────
export function TasksPreview({ content }: { content: string }) {
  const tasks = parseTasks(content);

  if (tasks.length === 0) {
    const tasksMatch = content.match(/<tasks>([\s\S]*?)<\/tasks>/i);
    const tasksContent = tasksMatch ? tasksMatch[1].trim() : content;
    return (
      <pre className="text-[11px] text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
        {tasksContent.slice(0, 3000)}
      </pre>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-ink-400 mb-1">
        {tasks.length} task{tasks.length !== 1 ? "s" : ""}
      </p>
      {tasks.map((task, i) => (
        <div key={i} className="flex items-start gap-2 group rounded-lg bg-brand-fill border border-brand-border px-3 py-2">
          <div className="w-5 h-5 rounded-full bg-brand-fill flex items-center justify-center flex-shrink-0 mt-0.5">
            <span className="text-[9px] font-bold text-brand">{i + 1}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold text-brand">{task.title}</p>
            {task.goal && <p className="text-[10px] text-brand mt-0.5">{task.goal.slice(0, 100)}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * The analyzer's `### Readiness verdict` line, and which of the three verdicts
 * it is. ONE parse (INV-12): both AnalysisPreview's banner and the review
 * gate's well read it from here.
 *
 * Structural — it keys on the artifact's own heading and the verdict words the
 * analyzer writes, never on a workflow or agent name (SC-001). `tone` is
 * "neutral" when there is no verdict, so a caller can render nothing.
 */
export function parseReadinessVerdict(
  content: string,
): { verdict: string; tone: "ready" | "caution" | "revision" | "neutral" } {
  const analysisMatch = content.match(/<analysis>([\s\S]*?)<\/analysis>/i);
  const body = analysisMatch ? analysisMatch[1].trim() : content;
  const verdictMatch = body.match(/###\s*Readiness verdict\s*\n([\s\S]*?)(?=\n###|$)/i);
  const verdict = verdictMatch ? verdictMatch[1].trim().split("\n")[0].trim() : "";
  if (!verdict) return { verdict: "", tone: "neutral" };
  if (verdict.includes("READY TO BUILD")) return { verdict, tone: "ready" };
  if (verdict.includes("CAUTION")) return { verdict, tone: "caution" };
  if (verdict.includes("NEEDS REVISION")) return { verdict, tone: "revision" };
  return { verdict, tone: "neutral" };
}

// ─── Analysis report renderer — parses <analysis>...</analysis> ──────────────
export function AnalysisPreview({ content }: { content: string }) {
  const analysisMatch = content.match(/<analysis>([\s\S]*?)<\/analysis>/i);
  const analysisContent = analysisMatch ? analysisMatch[1].trim() : content;

  const { verdict, tone } = parseReadinessVerdict(content);
  const isReady = tone === "ready";
  const isCaution = tone === "caution";
  const needsRevision = tone === "revision";

  const lines = analysisContent.split("\n");
  const sections: { heading: string; body: string }[] = [];
  let current: { heading: string; lines: string[] } | null = null;
  for (const line of lines) {
    if (line.startsWith("### ")) {
      if (current) sections.push({ heading: current.heading, body: current.lines.join("\n").trim() });
      current = { heading: line.replace("### ", ""), lines: [] };
    } else if (line.startsWith("## ") && sections.length === 0 && !current) {
      // Skip top-level heading
    } else if (current) {
      current.lines.push(line);
    }
  }
  if (current) sections.push({ heading: current.heading, body: current.lines.join("\n").trim() });

  if (sections.length === 0) {
    return (
      <pre className="text-[11px] text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
        {analysisContent}
      </pre>
    );
  }

  return (
    <div className="space-y-3">
      {verdict && (
        <div className={`rounded-xl px-4 py-3 border font-semibold text-[12px] flex items-center gap-2 ${
          isReady ? "bg-emerald-50 border-emerald-200 text-emerald-800" :
          isCaution ? "bg-amber-50 border-amber-200 text-amber-800" :
          needsRevision ? "bg-red-50 border-red-200 text-red-800" :
          "bg-surface-warm border-line-border text-ink-800"
        }`}>
          {isReady ? <CheckCircle2 className="h-4 w-4 flex-shrink-0" /> :
           isCaution ? <Sparkles className="h-4 w-4 flex-shrink-0" /> :
           <XCircle className="h-4 w-4 flex-shrink-0" />}
          {verdict}
        </div>
      )}
      {sections.map((s, i) => (
        <div key={i} className="rounded-lg border border-line-divider overflow-hidden">
          <div className={`px-3 py-2 border-b border-line-divider ${
            s.heading.toLowerCase().includes("suggested") ? "bg-brand-fill" :
            s.heading.toLowerCase().includes("risk") ? "bg-amber-50" :
            s.heading.toLowerCase().includes("issues") ? "bg-red-50" :
            "bg-surface-warm"
          }`}>
            <p className="text-[11px] font-bold text-ink-700">{s.heading}</p>
          </div>
          <div className="px-3 py-2.5">
            <pre className="text-[11px] text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
              {s.body}
            </pre>
          </div>
        </div>
      ))}
    </div>
  );
}

// ═══ The gate's evidence well ════════════════════════════════════════════════
//
// `SpecPreview` / `TasksPreview` / `AnalysisPreview` above are STRUCTURAL
// extracts — they pull the sections or the numbered rows out of an artifact and
// draw them as a list. That is the right shape for the settled artifact cards in
// AgentDetailPanel, and those callers are untouched.
//
// It is the wrong shape for a review gate. A gate asks "is this correct?", and
// every one of those renderers ends at a `<pre>` or a per-line `<p>`, so the
// markdown a spec is actually written in — a table, a bulleted list, a quoted
// constraint, an inline `identifier` — arrives as literal pipes, dashes and
// backticks. You cannot check a table you cannot read.
//
// So the gate gets its own well: unwrap the envelope, then render the body as
// what it IS. Prose renders as markdown; source renders as source.
//
// SECURITY (carried verbatim from MarkdownPreview's WR-03 invariant): NO
// `rehype-raw`, and no rehypePlugins of any kind. react-markdown's default
// escapes embedded raw HTML to literal text rather than parsing it into live
// DOM. An agent's output is untrusted content; this well renders it INLINE and
// unsandboxed, so raw-HTML execution here would defeat the `sandbox=
// "allow-scripts"` iframe the HTML deliverable path enforces. Do not add it.

/**
 * Strip an artifact's own wrapper tag so the well shows the body, not the
 * envelope. Uses the same `<spec>/<tasks>/<analysis>` vocabulary
 * `discriminateArtifact` sniffs (SC-001 — a structural tag, never a name).
 * Returns the content unchanged when there is no wrapper.
 */
export function unwrapArtifact(content: string): string {
  const m = content.match(/<(spec|tasks|analysis)>([\s\S]*?)<\/\1>/i);
  return (m ? m[2] : content).trim();
}

// ARTIFACT_KINDS (backend agents/artifacts/graph.py) whose body is SOURCE, not
// prose. `file_bundle` is deliberately absent: it is a markdown carrier of
// ```filename: …``` fenced blocks, so the markdown branch already renders each
// of its files as a code block — routing it here would collapse the whole
// bundle into one undifferentiated blob.
const CODE_ARTIFACT_KINDS = new Set(["html_file", "patch", "repo_diff"]);

const CODE_ARTIFACT_LANG: Record<string, string> = {
  html_file: "html",
  patch: "diff",
  repo_diff: "diff",
};

/** Is this artifact source rather than prose? Declared kind first, then a
 *  name-free shape sniff for the legacy rows that carry no kind. */
export function isCodeArtifact(content: string, artifactKind?: string): boolean {
  if (artifactKind && CODE_ARTIFACT_KINDS.has(artifactKind)) return true;
  return /^\s*(<!DOCTYPE\s|<html[\s>])/i.test(content);
}

/**
 * The gate's ASK — the question above the decision, and the label on the button
 * that answers it.
 *
 * Nothing on the wire carries this today: the gate event publishes the output,
 * the artifact kind and the eligibility flags, but never a question. The card
 * therefore said "{agentName} · review before continuing", which is a label
 * describing the card rather than a question addressed to the person reading
 * it. Deriving it here keys ONLY on the structural artifact kind (SC-001) — a
 * renamed workflow or agent cannot change what is asked. A caller-supplied
 * `approveLabel` still wins over the derived one.
 */
export function gateAsk(
  artifactKind: string | undefined,
  resolved: "spec" | "tasks" | "analysis" | null,
): { ask: string; approve: string } {
  if (resolved === "spec" || artifactKind === "spec")
    return { ask: "Approve this spec to start the build?", approve: "Approve the spec" };
  if (resolved === "tasks" || artifactKind === "task_list" || artifactKind === "plan")
    return { ask: "Approve this plan to start the build?", approve: "Approve the plan" };
  if (resolved === "analysis")
    return { ask: "Approve this analysis and continue?", approve: "Approve the analysis" };
  if (artifactKind === "html_file")
    return { ask: "Ship this screen as built?", approve: "Approve the build" };
  if (artifactKind === "validation_report")
    return { ask: "Accept this verification result?", approve: "Accept the result" };
  return { ask: "Approve this step and continue?", approve: "Approve & build" };
}

// Prose typography for the well. Serif body at reading size — the decision
// chrome around it is sans, so the artifact reads as a quoted document rather
// than as more interface.
const PROSE: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  p: ({ children }) => <p className="mb-[0.7em] last:mb-0">{children}</p>,
  h1: ({ children }) => <h1 className="mb-[0.45em] font-sans text-[13px] font-semibold text-ink-900">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-[0.45em] font-sans text-[12.5px] font-semibold text-ink-900">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-[0.45em] font-sans text-[12px] font-semibold text-ink-900">{children}</h3>,
  ul: ({ children }) => <ul className="mb-[0.7em] list-disc pl-[1.35em]">{children}</ul>,
  ol: ({ children }) => <ol className="mb-[0.7em] list-decimal pl-[1.35em]">{children}</ol>,
  li: ({ children }) => <li className="mb-[0.25em]">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink-900">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="mb-[0.7em] border-l-[3px] border-brand-border pl-[1em] italic text-ink-500">{children}</blockquote>
  ),
  table: ({ children }) => (
    // Its own scroller: a wide table must not widen the card (the gate sits in
    // the Steps spine, which has no horizontal scroll of its own).
    <div className="mb-[0.7em] overflow-x-auto"><table className="w-full border-collapse text-[0.87em]">{children}</table></div>
  ),
  th: ({ children }) => (
    <th className="border border-line-border bg-surface-white px-[0.6em] py-[0.4em] text-left font-sans text-[10.5px] font-semibold text-ink-900">{children}</th>
  ),
  td: ({ children }) => <td className="border border-line-border px-[0.6em] py-[0.4em] text-left align-top">{children}</td>,
  code: ({ children, className }) => {
    // A fenced block arrives with a language class; an inline span does not.
    if (className) {
      return <code className="block whitespace-pre font-mono text-[11.5px] leading-[1.55] text-ink-700">{children}</code>;
    }
    return (
      <code className="rounded-[5px] border border-brand/15 bg-brand/[0.06] px-[0.4em] py-[0.15em] font-mono text-[0.85em] font-normal text-brand">{children}</code>
    );
  },
  pre: ({ children }) => (
    <pre className="mb-[0.7em] overflow-x-auto rounded-[10px] border border-line-border bg-surface-white px-3 py-2.5">{children}</pre>
  ),
  hr: () => <hr className="my-[0.9em] border-0 border-t border-line-border" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand underline underline-offset-2">{children}</a>
  ),
};

/** A source artifact — a labelled block with a copy affordance, scrolling in
 *  both axes so nothing is silently cropped. */
function CodeArtifact({ content, artifactKind }: { content: string; artifactKind?: string }) {
  const [copied, setCopied] = useState(false);
  const lang = (artifactKind && CODE_ARTIFACT_LANG[artifactKind]) || "text";
  return (
    <div className="overflow-hidden rounded-[10px] border border-line-border bg-surface-warm">
      <div className="flex items-center gap-2 border-b border-line-border px-3.5 py-[7px]">
        <Code2 aria-hidden className="h-3.5 w-3.5 flex-none text-ink-500" />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-500">{lang}</span>
        <span className="flex-1" />
        <button
          type="button"
          data-testid="gate-well-copy"
          onClick={() => {
            navigator.clipboard?.writeText(content);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="flex items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[10.5px] text-ink-500 transition-colors hover:bg-surface-white hover:text-ink-800"
        >
          {copied ? <><Check className="h-3 w-3 text-status-done" />Copied</> : <><Copy className="h-3 w-3" />Copy</>}
        </button>
      </div>
      <pre className="m-0 max-h-[220px] overflow-auto whitespace-pre px-3.5 py-2.5 font-mono text-[11.5px] leading-[1.55] text-ink-700">
        {content}
      </pre>
    </div>
  );
}

/**
 * GateWell — "what the run produced", rendered as what it is.
 *
 * Capped and internally scrolling by design: this is the evidence a decision is
 * checked against, not the reading surface. `.gate-well-fade` shades its TOP
 * edge, where it passes under the decision block that casts onto it.
 */
export function GateWell({
  content,
  artifactKind,
}: {
  content: string;
  artifactKind?: string;
}) {
  const body = unwrapArtifact(content);
  if (!body) return null;


  // The analyzer's readiness verdict, hoisted OUT of the prose and above it.
  // AnalysisPreview has always done this and the gate lost it when it stopped
  // using that renderer — which is the worst possible place to lose it: on an
  // approval gate, "CAUTION advised" is the single most decision-relevant line
  // in the artifact, and buried in the body it reads as ordinary text. Same
  // parse as AnalysisPreview (INV-12); token colours rather than that
  // renderer's raw palette so it belongs to the card it now sits in.
  const { verdict, tone } = parseReadinessVerdict(content);
  const banner = verdict ? (
    <div
      data-testid="gate-well-verdict"
      data-verdict-tone={tone}
      // Arbitrary values, not `bg-status-done-fill` utilities: the ramp's
      // fill/border pairs are defined as CSS vars but never mapped into
      // @theme, so those class names generate nothing. Mapping them would
      // switch the colour on in ~50 other files at once — a repaint nobody
      // asked for. Reaching for the var directly keeps that blast radius at
      // this one banner.
      className={`mb-2 flex items-center gap-2 rounded-lg border px-3 py-2 text-[11.5px] font-semibold ${
        tone === "ready"
          ? "border-[var(--status-done-border)] bg-[var(--status-done-fill)] text-status-done"
          : tone === "caution"
          ? "border-[var(--status-amber-border)] bg-[var(--status-amber-fill)] text-status-amber"
          : tone === "revision"
          ? "border-[var(--status-failed-border)] bg-[var(--status-failed-fill)] text-status-failed-strong"
          : "border-line-border bg-surface-warm text-ink-800"
      }`}
    >
      {tone === "ready" ? (
        <CheckCircle2 aria-hidden className="h-3.5 w-3.5 flex-none" />
      ) : tone === "caution" ? (
        <AlertTriangle aria-hidden className="h-3.5 w-3.5 flex-none" />
      ) : tone === "revision" ? (
        <XCircle aria-hidden className="h-3.5 w-3.5 flex-none" />
      ) : (
        <Sparkles aria-hidden className="h-3.5 w-3.5 flex-none" />
      )}
      {verdict}
    </div>
  ) : null;

  if (isCodeArtifact(body, artifactKind)) {
    return (
      <div data-testid="gate-well" data-well-kind="code">
        {banner}
        <CodeArtifact content={body} artifactKind={artifactKind} />
      </div>
    );
  }

  return (
    <div data-testid="gate-well" data-well-kind="prose">
      {banner}
      <div className="gate-well-fade">
        <div className="max-h-[220px] overflow-y-auto rounded-[10px] border border-line-border bg-surface-warm px-3 py-2.5 font-serif text-[12px] leading-[1.6] text-ink-800">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={PROSE}>{body}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
