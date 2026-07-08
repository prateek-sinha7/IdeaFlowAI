"use client";

/**
 * ReviewGatePanel — Human review/edit/approve gate between pipeline agents.
 *
 * Shown when an agent with `gate: Human_Gate` completes. The user can:
 * - Read the agent's output (spec document or task list)
 * - Edit it directly in a textarea
 * - Approve (continue pipeline with original or edited content)
 * - Reject (cancel the pipeline)
 */

import { useState, useCallback, useEffect } from "react";
import { motion } from "motion/react";
import {
  CheckCircle2, XCircle, Edit3, Eye, FileText,
  ListChecks, Sparkles, RotateCcw, AlertTriangle, RefreshCw,
} from "lucide-react";

interface ReviewGatePanelProps {
  agentId: string;
  agentName: string;
  output: string;
  gateKey: string;
  onApprove: (gateKey: string, editedContent?: string) => void;
  onReject: (gateKey: string) => void;
  /**
   * REDO-GATE (F-fe1): re-run the gated agent in place with optional extra
   * instructions. The Redo control renders IFF this handler is provided AND the
   * server marked the gate `redoable` (the generic F1b fence — a declared/
   * user-composed `gate:human` gets `redoable=false` and shows no Redo button).
   */
  onRedo?: (gateKey: string, instructions: string) => void;
  /** Server-set generic discriminator (REDO-GATE F1b). Default false. */
  redoable?: boolean;
  /**
   * KAN-101: Trigger the spec revision sub-pipeline with the current analysis
   * report as context. Rendered off the generic `updateSpecsEligible` flag below
   * (SC-001), never a workflow/agent-name literal.
   */
  onUpdateSpecs?: (gateKey: string, analysisReport: string) => void;
  /**
   * SC-001 (plan 08): the DECLARED structural artifact kind for this gate's output
   * (`spec` / `task_list` / `summary` / `html_file` / `validation_report` — from
   * the backend `_artifact_kind_for`), used to pick the icon/label/description +
   * preview renderer WITHOUT any prototype-* agent-id literal. Undefined → generic.
   */
  artifactKind?: string;
  /**
   * SC-001 / KAN-101: the generic server-set eligibility flag — the "Update the
   * Specs" affordance renders IFF this is true AND onUpdateSpecs is wired (mirrors
   * InlineGateActions; a renamed workflow cannot smuggle the affordance).
   */
  updateSpecsEligible?: boolean;
}

// ─── Spec renderer — parses <spec>...</spec> into readable sections ───────────
function SpecPreview({ content }: { content: string }) {
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

// ─── Task list renderer with delete support ──────────────────────────────────
function TasksPreview({ content, onTasksChange }: { content: string; onTasksChange?: (newContent: string) => void }) {
  const tasksMatch = content.match(/<tasks>([\s\S]*?)<\/tasks>/i);
  const tasksContent = tasksMatch ? tasksMatch[1].trim() : content;
  const hasWrapper = !!tasksMatch;

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

  const handleDelete = (indexToDelete: number) => {
    if (!onTasksChange) return;
    const remaining = tasks.filter((_, i) => i !== indexToDelete);
    const renumbered = remaining.map((t, i) => {
      const newNum = i + 1;
      return t.raw.replace(/##\s+Task\s+\d+/, `## Task ${newNum}`);
    });
    const newContent = renumbered.join("\n");
    const newFull = hasWrapper ? `<tasks>\n${newContent}\n</tasks>` : newContent;
    onTasksChange(newFull);
  };

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
        {tasks.length} task{tasks.length !== 1 ? "s" : ""} · Click <span className="text-red-400">✕</span> to remove a task before building
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
          {onTasksChange && (
            <button
              onClick={() => handleDelete(i)}
              className="flex-shrink-0 mt-0.5 w-5 h-5 rounded flex items-center justify-center text-ink-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
              title="Remove this task"
            >
              <XCircle className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Analysis report renderer — parses <analysis>...</analysis> ──────────────
function AnalysisPreview({ content }: { content: string }) {
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


export function ReviewGatePanel({
  agentName, output, gateKey, onApprove, onReject, onRedo, redoable, onUpdateSpecs,
  artifactKind, updateSpecsEligible,
}: ReviewGatePanelProps) {
  const [mode, setMode] = useState<"preview" | "edit">("preview");
  const [editedContent, setEditedContent] = useState(output);
  const [hasEdits, setHasEdits] = useState(false);
  // REDO-GATE (F-fe1): free-text additional instructions for the re-run.
  const [redoInstructions, setRedoInstructions] = useState("");
  // REDO-GATE (F8 / T13): one-action latch — once any resolve action fires we
  // disable the controls until the panel is re-opened by the next
  // review_gate_ready (output changes ⇒ fresh re-run), preventing a double-send.
  const [submitted, setSubmitted] = useState(false);

  // Confirmation dialog before rejecting.
  const [showRejectConfirm, setShowRejectConfirm] = useState(false);

  // The Redo control is shown ONLY when a handler is wired AND the server marked
  // this gate redoable (the generic F1b fence — no workflow/agent literal here).
  const canRedo = !!onRedo && !!redoable;

  // SC-001 (plan 08): the icon/label/description + preview renderer are chosen off
  // the DECLARED structural artifact kind and the artifact's own wrapper tag in the
  // output — NEVER a prototype-* agent-id literal. artifactKind is authoritative;
  // the content-tag sniff is the name-free fallback when the kind is omitted.
  const isSpec = artifactKind === "spec" || /<spec[\s>]/i.test(output);
  const isTasks = artifactKind === "task_list" || /<tasks[\s>]/i.test(output);
  const isAnalysis =
    (!isSpec && !isTasks) && (artifactKind === "summary" || /<analysis[\s>]/i.test(output));

  const handleEdit = useCallback((value: string) => {
    setEditedContent(value);
    setHasEdits(value !== output);
  }, [output]);

  const handleTasksChange = useCallback((newContent: string) => {
    setEditedContent(newContent);
    setHasEdits(newContent !== output);
  }, [output]);

  // KAN-98: reset editedContent + hasEdits on fresh gate so stale edits are never
  // forwarded. Also reset latch, redo instructions, and confirm state.
  useEffect(() => {
    setSubmitted(false);
    setRedoInstructions("");
    setShowRejectConfirm(false);
    setEditedContent(output);
    setHasEdits(false);
  }, [output, gateKey]);

  const handleApprove = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onApprove(gateKey, hasEdits ? editedContent : undefined);
  }, [submitted, gateKey, hasEdits, editedContent, onApprove]);

  const handleReject = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onReject(gateKey);
  }, [submitted, gateKey, onReject]);

  // REDO-GATE (F-fe1 / T13): send the optional instructions and latch the panel.
  const handleRedo = useCallback(() => {
    if (submitted || !onRedo) return;
    setSubmitted(true);
    onRedo(gateKey, redoInstructions);
  }, [submitted, onRedo, gateKey, redoInstructions]);

  // KAN-101: trigger spec revision sub-pipeline with the current analysis output.
  // Passes the raw `output` (not editedContent) as the analysis report so the
  // backend gets the original analyzer verdict, not any edits made in the panel.
  const handleUpdateSpecs = useCallback(() => {
    if (submitted || !onUpdateSpecs) return;
    setSubmitted(true);
    onUpdateSpecs(gateKey, output);
  }, [submitted, onUpdateSpecs, gateKey, output]);

  const icon = isSpec ? FileText : isTasks ? ListChecks : isAnalysis ? Sparkles : FileText;
  const Icon = icon;
  const label = isSpec ? "Specification Review" : isTasks ? "Task Plan Review" : isAnalysis ? "Spec Kit Analysis" : "Review";
  const description = isSpec
    ? "Review the generated specification. Edit if needed, then approve to proceed to task planning."
    : isTasks
    ? "Review the build task list. Edit if needed, then approve to start building."
    : isAnalysis
    ? "Review the analysis report. Accept to proceed to build, or update the specs to trigger an AI-driven revision cycle."
    : "Review the agent output before continuing.";

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-line-divider flex-shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-xl bg-brand flex items-center justify-center flex-shrink-0">
            <Icon className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="text-[13px] font-bold text-ink-900">{label}</h2>
            <p className="text-[10px] text-ink-400">{agentName} · Review before continuing</p>
          </div>
        </div>
        <p className="text-[11px] text-ink-500 leading-relaxed">{description}</p>

        {/* Mode toggle */}
        <div className="flex items-center gap-1 mt-3 bg-surface-warm rounded-lg p-0.5 w-fit">
          <button
            onClick={() => setMode("preview")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all ${
              mode === "preview" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-700"
            }`}
          >
            <Eye className="h-3 w-3" /> Preview
          </button>
          <button
            onClick={() => setMode("edit")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all ${
              mode === "edit" ? "bg-white text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-700"
            }`}
          >
            <Edit3 className="h-3 w-3" /> Edit
            {hasEdits && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {mode === "preview" ? (
          <motion.div
            key="preview"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
          >
            {(hasEdits ? editedContent : output)?.trim() ? (
              <>
                {isSpec && <SpecPreview content={hasEdits ? editedContent : output} />}
                {isTasks && <TasksPreview content={hasEdits ? editedContent : output} onTasksChange={handleTasksChange} />}
                {isAnalysis && <AnalysisPreview content={hasEdits ? editedContent : output} />}
                {!isSpec && !isTasks && !isAnalysis && (
                  <pre className="text-[11px] text-ink-700 whitespace-pre-wrap leading-relaxed font-mono">
                    {(hasEdits ? editedContent : output).slice(0, 4000)}
                  </pre>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                <p className="text-[12px] font-medium text-ink-500">No content was produced for review.</p>
                <p className="text-[11px] text-ink-400">
                  The agent returned an empty result. Reject to cancel the pipeline, or approve to continue anyway.
                </p>
              </div>
            )}
          </motion.div>
        ) : (
          <motion.div
            key="edit"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
            className="h-full"
          >
            <p className="text-[10px] text-ink-400 mb-2">
              Edit the {isSpec ? "specification" : isTasks ? "task list" : isAnalysis ? "analysis report" : "content"} directly. Changes will be used by the next agent.
            </p>
            <textarea
              value={editedContent}
              onChange={(e) => handleEdit(e.target.value)}
              className="w-full h-[calc(100%-2rem)] min-h-[300px] rounded-xl border border-line-border bg-surface-warm px-4 py-3 text-[11px] text-ink-900 font-mono leading-relaxed focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/20 resize-none"
              spellCheck={false}
            />
          </motion.div>
        )}
      </div>

      {/* Actions */}
      <div className="px-5 py-4 border-t border-line-divider bg-white flex-shrink-0 space-y-2">
        {hasEdits && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
            <Sparkles className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
            <p className="text-[10px] text-amber-700">
              You have unsaved edits — approving will use your edited version.
            </p>
          </div>
        )}

        {/* Primary action — "Accept and Continue" for analysis; "Approve & continue" otherwise */}
        <button
          onClick={handleApprove}
          disabled={submitted}
          className="w-full flex items-center justify-center gap-2 rounded-[var(--radius-button)] bg-brand text-white px-4 py-3 text-[12px] font-semibold hover:bg-brand-pressed transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-brand"
        >
          <CheckCircle2 className="h-4 w-4" />
          {isAnalysis
            ? (hasEdits ? "Accept with edits & continue to build" : "Accept & continue to build")
            : (hasEdits ? "Approve with edits & continue" : "Approve & continue")}
        </button>

        {/* KAN-101 / SC-001: "Update the Specs" — triggers a spec revision
            sub-pipeline with the report as context, re-opening this gate with the
            new output. Rendered off the GENERIC updateSpecsEligible flag + the
            wired onUpdateSpecs handler (mirrors InlineGateActions) — never keyed on
            a prototype-* agent-id literal. */}
        {!!onUpdateSpecs && !!updateSpecsEligible && (
          <button
            onClick={handleUpdateSpecs}
            disabled={submitted}
            className="w-full flex items-center justify-center gap-2 rounded-[var(--radius-button)] border border-brand-border text-brand px-4 py-2.5 text-[11px] font-semibold hover:bg-brand-fill transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Update the Specs
          </button>
        )}

        {/* REDO-GATE (F-fe1): re-run the gated agent with optional extra
            instructions. Rendered IFF onRedo AND server-set redoable (F1b fence). */}
        {canRedo && (
          <div className="space-y-2 rounded-xl border border-violet-100 bg-violet-50/50 px-3 py-3">
            <label className="block text-[10px] font-medium text-violet-700">
              Redo with additional instructions{" "}
              <span className="text-violet-400 font-normal">(optional — leave blank to just regenerate)</span>
            </label>
            <textarea
              value={redoInstructions}
              onChange={(e) => setRedoInstructions(e.target.value)}
              disabled={submitted}
              placeholder="e.g. add a dark-mode variant; tighten the spacing; focus on mobile"
              className="w-full min-h-[60px] rounded-lg border border-violet-200 bg-white px-3 py-2 text-[11px] text-ink-900 leading-relaxed focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-300 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
              spellCheck={false}
              aria-label="Additional instructions for redo"
            />
            <button
              onClick={handleRedo}
              disabled={submitted}
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-violet-300 text-violet-700 px-4 py-2.5 text-[11px] font-semibold hover:bg-violet-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Redo this step
            </button>
          </div>
        )}

        <button
          onClick={() => setShowRejectConfirm(true)}
          disabled={submitted}
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-red-200 text-red-600 px-4 py-2.5 text-[11px] font-medium hover:bg-red-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
        >
          <XCircle className="h-3.5 w-3.5" />
          Reject & cancel pipeline
        </button>

        {/* Confirmation dialog for reject */}
        {showRejectConfirm && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 space-y-3">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-[12px] font-semibold text-red-700">Cancel this pipeline?</p>
                <p className="text-[11px] text-red-600 mt-0.5 leading-relaxed">
                  This will stop execution and discard all progress. This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowRejectConfirm(false)}
                className="flex-1 rounded-lg border border-line-border bg-white text-ink-600 px-3 py-2 text-[11px] font-medium hover:bg-surface-warm transition-all"
              >
                Keep reviewing
              </button>
              <button
                onClick={handleReject}
                disabled={submitted}
                className="flex-1 rounded-lg bg-red-600 text-white px-3 py-2 text-[11px] font-semibold hover:bg-red-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Yes, cancel pipeline
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
