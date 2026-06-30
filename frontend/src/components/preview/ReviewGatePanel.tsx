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
  ListChecks, ChevronDown, ChevronRight, Sparkles, Trash2, RotateCcw,
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
}

// ─── Spec renderer — parses <spec>...</spec> into readable sections ───────────
function SpecPreview({ content }: { content: string }) {
  const specMatch = content.match(/<spec>([\s\S]*?)<\/spec>/i);
  const specContent = specMatch ? specMatch[1].trim() : content;

  // Extract sections
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
      <pre className="text-[11px] text-gray-700 whitespace-pre-wrap leading-relaxed font-mono">
        {specContent.slice(0, 3000)}
      </pre>
    );
  }

  return (
    <div className="space-y-3">
      {sections.map((s, i) => (
        <div key={i} className="rounded-lg border border-gray-100 overflow-hidden">
          <div className="px-3 py-2 bg-gray-50 border-b border-gray-100">
            <p className="text-[11px] font-bold text-gray-700">{s.heading}</p>
          </div>
          <div className="px-3 py-2">
            {s.body.map((line, j) => (
              <p key={j} className="text-[11px] text-gray-600 leading-relaxed">{line}</p>
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
    // Renumber remaining tasks sequentially (1, 2, 3...)
    const renumbered = remaining.map((t, i) => {
      const newNum = i + 1;
      // Replace the task number in the raw block
      return t.raw.replace(/##\s+Task\s+\d+/, `## Task ${newNum}`);
    });
    const newContent = renumbered.join("\n");
    const newFull = hasWrapper ? `<tasks>\n${newContent}\n</tasks>` : newContent;
    onTasksChange(newFull);
  };

  if (tasks.length === 0) {
    return (
      <pre className="text-[11px] text-gray-700 whitespace-pre-wrap leading-relaxed font-mono">
        {tasksContent.slice(0, 3000)}
      </pre>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-gray-400 mb-1">
        {tasks.length} task{tasks.length !== 1 ? "s" : ""} · Click <span className="text-red-400">✕</span> to remove a task before building
      </p>
      {tasks.map((task, i) => (
        <div key={i} className="flex items-start gap-2 group rounded-lg bg-blue-50 border border-blue-100 px-3 py-2">
          <div className="w-5 h-5 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 mt-0.5">
            <span className="text-[9px] font-bold text-blue-700">{i + 1}</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-semibold text-blue-900">{task.title}</p>
            {task.goal && <p className="text-[10px] text-blue-700 mt-0.5">{task.goal.slice(0, 100)}</p>}
          </div>
          {onTasksChange && (
            <button
              onClick={() => handleDelete(i)}
              className="flex-shrink-0 mt-0.5 w-5 h-5 rounded flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
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

// ─── Main component ───────────────────────────────────────────────────────────
export function ReviewGatePanel({
  agentId, agentName, output, gateKey, onApprove, onReject, onRedo, redoable,
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

  // The Redo control is shown ONLY when a handler is wired AND the server marked
  // this gate redoable (the generic F1b fence — no workflow/agent literal here).
  const canRedo = !!onRedo && !!redoable;

  const isSpec = agentId === "prototype-specify";
  const isTasks = agentId === "prototype-plan";

  const handleEdit = useCallback((value: string) => {
    setEditedContent(value);
    setHasEdits(value !== output);
  }, [output]);

  // Called when user deletes a task from the task list preview — updates edited content
  const handleTasksChange = useCallback((newContent: string) => {
    setEditedContent(newContent);
    setHasEdits(newContent !== output);
  }, [output]);

  // REDO-GATE (T13 / F8): a fresh review_gate_ready re-opens the panel with new
  // output — reset the one-action latch + the instructions box so the re-paused
  // gate is interactive again. Keyed on `output` (the re-run's new content) and
  // `gateKey` (a brand-new gate).
  useEffect(() => {
    setSubmitted(false);
    setRedoInstructions("");
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

  // REDO-GATE (F-fe1 / T13): send the optional instructions and latch the panel
  // closed against a double-send until the next review_gate_ready arrives.
  const handleRedo = useCallback(() => {
    if (submitted || !onRedo) return;
    setSubmitted(true);
    onRedo(gateKey, redoInstructions);
  }, [submitted, onRedo, gateKey, redoInstructions]);

  const icon = isSpec ? FileText : ListChecks;
  const Icon = icon;
  const label = isSpec ? "Specification Review" : "Task Plan Review";
  const description = isSpec
    ? "Review the generated specification. Edit if needed, then approve to proceed to task planning."
    : "Review the build task list. Edit if needed, then approve to start building.";

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#1B2A4A] to-violet-600 flex items-center justify-center flex-shrink-0">
            <Icon className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="text-[13px] font-bold text-gray-900">{label}</h2>
            <p className="text-[10px] text-gray-400">{agentName} · Review before continuing</p>
          </div>
        </div>
        <p className="text-[11px] text-gray-500 leading-relaxed">{description}</p>

        {/* Mode toggle */}
        <div className="flex items-center gap-1 mt-3 bg-gray-100 rounded-lg p-0.5 w-fit">
          <button
            onClick={() => setMode("preview")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all ${
              mode === "preview" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <Eye className="h-3 w-3" /> Preview
          </button>
          <button
            onClick={() => setMode("edit")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-medium transition-all ${
              mode === "edit" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
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
                {!isSpec && !isTasks && (
                  <pre className="text-[11px] text-gray-700 whitespace-pre-wrap leading-relaxed font-mono">
                    {(hasEdits ? editedContent : output).slice(0, 4000)}
                  </pre>
                )}
              </>
            ) : (
              /* Defensive empty-state: the agent produced no content to review.
                 With the runner no-delta fallback this should not occur for a
                 model that returned text, but never present a silently blank
                 panel with live Approve/Reject buttons. */
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
                <p className="text-[12px] font-medium text-gray-500">No content was produced for review.</p>
                <p className="text-[11px] text-gray-400">
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
            <p className="text-[10px] text-gray-400 mb-2">
              Edit the {isSpec ? "specification" : "task list"} directly. Changes will be used by the next agent.
            </p>
            <textarea
              value={editedContent}
              onChange={(e) => handleEdit(e.target.value)}
              className="w-full h-[calc(100%-2rem)] min-h-[300px] rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-[11px] text-gray-900 font-mono leading-relaxed focus:outline-none focus:border-[#1B2A4A]/40 focus:ring-1 focus:ring-[#1B2A4A]/20 resize-none"
              spellCheck={false}
            />
          </motion.div>
        )}
      </div>

      {/* Actions */}
      <div className="px-5 py-4 border-t border-gray-100 bg-white flex-shrink-0 space-y-2">
        {hasEdits && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
            <Sparkles className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
            <p className="text-[10px] text-amber-700">
              You have unsaved edits — approving will use your edited version.
            </p>
          </div>
        )}

        <button
          onClick={handleApprove}
          disabled={submitted}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-3 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[#1B2A4A]"
        >
          <CheckCircle2 className="h-4 w-4" />
          {hasEdits ? "Approve with edits & continue" : "Approve & continue"}
        </button>

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
              className="w-full min-h-[60px] rounded-lg border border-violet-200 bg-white px-3 py-2 text-[11px] text-gray-900 leading-relaxed focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-300 resize-none disabled:opacity-50 disabled:cursor-not-allowed"
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
          onClick={handleReject}
          disabled={submitted}
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-red-200 text-red-600 px-4 py-2.5 text-[11px] font-medium hover:bg-red-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
        >
          <XCircle className="h-3.5 w-3.5" />
          Reject & cancel pipeline
        </button>
      </div>
    </div>
  );
}
