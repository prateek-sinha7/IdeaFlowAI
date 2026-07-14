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

import { CheckCircle2, XCircle, Sparkles } from "lucide-react";

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

// ─── Spec renderer — parses <spec>...</spec> into readable sections ───────────
export function SpecPreview({ content }: { content: string }) {
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

  if (sections.length === 0) {
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
  const tasksMatch = content.match(/<tasks>([\s\S]*?)<\/tasks>/i);
  const tasksContent = tasksMatch ? tasksMatch[1].trim() : content;

  const taskBlocks = tasksContent.split(/(?=##\s+Task\s+\d+)/);
  const tasks = taskBlocks
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

  if (tasks.length === 0) {
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

// ─── Analysis report renderer — parses <analysis>...</analysis> ──────────────
export function AnalysisPreview({ content }: { content: string }) {
  const analysisMatch = content.match(/<analysis>([\s\S]*?)<\/analysis>/i);
  const analysisContent = analysisMatch ? analysisMatch[1].trim() : content;

  const verdictMatch = analysisContent.match(/###\s*Readiness verdict\s*\n([\s\S]*?)(?=\n###|$)/i);
  const verdict = verdictMatch ? verdictMatch[1].trim().split("\n")[0].trim() : "";
  const isReady = verdict.includes("READY TO BUILD");
  const isCaution = verdict.includes("CAUTION");
  const needsRevision = verdict.includes("NEEDS REVISION");

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
