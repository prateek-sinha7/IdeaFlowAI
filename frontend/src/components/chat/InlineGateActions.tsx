"use client";

/**
 * InlineGateActions — compact in-lane mirror of the Steps `ReviewGatePanel`.
 *
 * Presentational + callback-driven ONLY. It renders the gate quick-actions
 * INSIDE the chat lane and fires the EXACT same callback props the full-panel
 * overlay receives — so an approve/reject/redo/update-specs from chat and the
 * same action from Steps both resolve through ONE `approve_review` backend
 * channel (LIVE-STATE-CONTRACT §1). This component never mints a new command
 * path; it reuses the channel the caller already owns.
 *
 * Gate fidelity (42-08, CONTEXT §F): the mock's review gate is TWO primary
 * buttons — "Approve & build" / "Request changes" — plus a task-plan PREVIEW
 * block. The redo / update-specs / reject CHANNELS are preserved verbatim,
 * only collapsed under the single "Request changes" affordance (they still
 * ride `approve_review {approved, action}`). The plan preview REUSES the
 * shared `artifactPreview` module (INV-12 — no second parser); the
 * discriminator keys only on the output + wrapper tag (SC-001), never a
 * workflow/agent-name literal.
 *
 * Behaviors carried (post-merge KAN cluster):
 * - KAN-101: the "Update the Specs" action — rendered off the GENERIC
 *   caller-supplied `updateSpecsEligible` flag, NEVER a workflow/agent-name
 *   literal (SC-001, the CONTEXT invariant). A renamed workflow cannot smuggle
 *   a hidden action; the server still fences the actual command.
 * - KAN-100: terminal fence — when `!isPipelineRunning` the actions render
 *   NOTHING (a gate action after terminal is `pipeline_not_running`).
 * - KAN-98: retained edit — an edit is kept in local state; the backend
 *   persists it but never re-emits it over WS, so the client retains it for
 *   display reconciliation (it is NOT wiped by a no-echo re-render; it resets
 *   only on a genuinely fresh gate = new `output`/`gateKey`).
 * - KAN-95: reject via a two-step confirm.
 * - KAN-94: event-driven — the caller renders this only when a gate fired.
 */

import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Edit3,
  RotateCcw,
  AlertTriangle,
  RefreshCw,
  MessageSquarePlus,
} from "lucide-react";

import {
  discriminateArtifact,
  SpecPreview,
  TasksPreview,
  AnalysisPreview,
} from "@/components/results/artifactPreview";

interface InlineGateActionsProps {
  agentId: string;
  agentName: string;
  output: string;
  gateKey: string;
  /** Server-set generic discriminator (mirrors ReviewGatePanel F1b). */
  redoable?: boolean;
  /**
   * GENERIC caller-derived flag (SC-001): true when this gate event is eligible
   * for the KAN-101 spec-revision loop. Derived by the CALLER from the gate
   * event — this component adds NO workflow/agent-name literal of its own.
   */
  updateSpecsEligible?: boolean;
  /** KAN-100 terminal fence: actions render only while the pipeline is live. */
  isPipelineRunning: boolean;
  /** Caller-supplied primary-action label (e.g. "Accept & continue to build"). */
  approveLabel?: string;
  onApprove: (gateKey: string, editedContent?: string) => void;
  onReject: (gateKey: string) => void;
  onRedo?: (gateKey: string, instructions: string) => void;
  onUpdateSpecs?: (gateKey: string, analysisReport: string) => void;
}

export function InlineGateActions({
  agentName,
  output,
  gateKey,
  redoable,
  updateSpecsEligible,
  isPipelineRunning,
  approveLabel,
  onApprove,
  onReject,
  onRedo,
  onUpdateSpecs,
}: InlineGateActionsProps) {
  // KAN-98: the edit is retained client-side (the backend never echoes it back
  // over WS). It resets ONLY on a genuinely fresh gate (new output/gateKey).
  const [editedContent, setEditedContent] = useState(output);
  const [hasEdits, setHasEdits] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  // "Request changes" affordance: reveals the redo/update-specs/reject channels.
  const [showRequestChanges, setShowRequestChanges] = useState(false);
  // KAN-95: two-step reject confirm.
  const [showRejectConfirm, setShowRejectConfirm] = useState(false);
  // Free-text instructions for the redo re-run.
  const [redoInstructions, setRedoInstructions] = useState("");
  const [showRedo, setShowRedo] = useState(false);
  // One-action latch — once any resolve action fires, disable until re-armed by
  // the next gate event (fresh output), preventing a double-send.
  const [submitted, setSubmitted] = useState(false);

  // Fresh gate only: new output OR new gateKey resets everything. A no-echo
  // re-render with the SAME output leaves the retained edit intact (KAN-98).
  useEffect(() => {
    setEditedContent(output);
    setHasEdits(false);
    setShowEdit(false);
    setShowRequestChanges(false);
    setShowRejectConfirm(false);
    setRedoInstructions("");
    setShowRedo(false);
    setSubmitted(false);
  }, [output, gateKey]);

  const canRedo = !!onRedo && !!redoable;
  const canUpdateSpecs = !!onUpdateSpecs && !!updateSpecsEligible;

  const handleEdit = useCallback(
    (value: string) => {
      setEditedContent(value);
      setHasEdits(value !== output);
    },
    [output],
  );

  const handleApprove = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onApprove(gateKey, hasEdits ? editedContent : undefined);
  }, [submitted, onApprove, gateKey, hasEdits, editedContent]);

  const handleReject = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onReject(gateKey);
  }, [submitted, onReject, gateKey]);

  const handleRedo = useCallback(() => {
    if (submitted || !onRedo) return;
    setSubmitted(true);
    onRedo(gateKey, redoInstructions);
  }, [submitted, onRedo, gateKey, redoInstructions]);

  // KAN-101: send the raw analysis report (the original `output`, not the
  // edited copy) so the backend gets the analyzer verdict verbatim.
  const handleUpdateSpecs = useCallback(() => {
    if (submitted || !onUpdateSpecs) return;
    setSubmitted(true);
    onUpdateSpecs(gateKey, output);
  }, [submitted, onUpdateSpecs, gateKey, output]);

  // KAN-100 terminal fence: post-terminal, no actions are available.
  if (!isPipelineRunning) return null;

  // Plan-preview block — reuse the shared artifactPreview discriminator +
  // renderers (INV-12: no second parser). The discriminator keys only on the
  // output's own wrapper tag (SC-001); an ordinary output renders no preview.
  const artifactKind = discriminateArtifact(output);

  return (
    <div
      data-testid="chat-gate-actions"
      className="rounded-2xl border border-line-border bg-surface-white px-4 py-3 space-y-2.5"
    >
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-lg bg-brand flex items-center justify-center flex-shrink-0">
          <CheckCircle2 className="h-3.5 w-3.5 text-white" />
        </div>
        <p className="text-[11px] font-semibold text-ink-900 flex-1 min-w-0 truncate">
          {agentName} · review before continuing
        </p>
        <button
          type="button"
          onClick={() => setShowEdit((v) => !v)}
          disabled={submitted}
          className="flex items-center gap-1 text-[10px] text-ink-500 hover:text-ink-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Edit3 className="h-3 w-3" /> Edit
          {hasEdits && <span className="w-1.5 h-1.5 rounded-full bg-status-amber" />}
        </button>
      </div>

      {showEdit && (
        <textarea
          value={editedContent}
          onChange={(e) => handleEdit(e.target.value)}
          disabled={submitted}
          aria-label="Edit gate content"
          className="w-full min-h-[120px] rounded-lg border border-line-border bg-surface-warm px-3 py-2 text-[11px] text-ink-900 font-mono leading-relaxed focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/20 resize-none disabled:opacity-50"
          spellCheck={false}
        />
      )}

      {/* Task-plan PREVIEW block — reused artifactPreview renderers (no parser). */}
      {artifactKind && !showEdit && (
        <div
          data-testid="chat-gate-preview"
          className="rounded-lg border border-line-border bg-surface-warm/60 px-3 py-2.5 max-h-64 overflow-y-auto"
        >
          {artifactKind === "spec" && <SpecPreview content={output} />}
          {artifactKind === "tasks" && <TasksPreview content={output} />}
          {artifactKind === "analysis" && <AnalysisPreview content={output} />}
        </div>
      )}

      {hasEdits && (
        <p className="text-[10px] text-status-amber">
          You have unsaved edits — approving will use your edited version.
        </p>
      )}

      {/* The mock's TWO primary buttons — Approve & build / Request changes. */}
      <div className="flex gap-2">
        {/* 1. Approve — the shared approve_review channel (approved:true). */}
        <button
          type="button"
          data-testid="chat-gate-approve"
          onClick={handleApprove}
          disabled={submitted}
          className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-brand text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-brand-pressed transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <CheckCircle2 className="h-4 w-4" />
          {approveLabel ??
            (hasEdits ? "Approve with edits & build" : "Approve & build")}
        </button>

        {/* 2. Request changes — reveals the redo/update-specs/reject channels. */}
        <button
          type="button"
          data-testid="chat-gate-request-changes"
          onClick={() => setShowRequestChanges((v) => !v)}
          disabled={submitted}
          className="flex-1 flex items-center justify-center gap-2 rounded-xl border border-line-control text-ink-700 px-4 py-2.5 text-[12px] font-semibold hover:border-ink-300 hover:bg-surface-warm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <MessageSquarePlus className="h-4 w-4" />
          Request changes
        </button>
      </div>

      {/* The collapsed change channels — redo / update-specs / reject. These
          fire the EXACT same handlers/channels as before; only the presentation
          is folded under "Request changes" (CONTEXT §F preserve-the-channels). */}
      {showRequestChanges && (
        <div className="space-y-2 rounded-xl border border-line-border bg-surface-warm/60 px-3 py-2.5">
          {/* KAN-101 Update the Specs — rendered off the GENERIC flag (SC-001). */}
          {canUpdateSpecs && (
            <button
              type="button"
              data-testid="chat-gate-update-specs"
              onClick={handleUpdateSpecs}
              disabled={submitted}
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-brand/30 text-brand px-4 py-2 text-[11px] font-semibold hover:bg-brand-fill transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Update the Specs
            </button>
          )}

          {/* Redo — rendered IFF onRedo AND server-set redoable (generic fence). */}
          {canRedo && (
            <div className="space-y-1.5">
              {showRedo ? (
                <>
                  <textarea
                    value={redoInstructions}
                    onChange={(e) => setRedoInstructions(e.target.value)}
                    disabled={submitted}
                    placeholder="Optional instructions — leave blank to just regenerate"
                    aria-label="Additional instructions for redo"
                    className="w-full min-h-[52px] rounded-lg border border-brand-border bg-surface-white px-3 py-2 text-[11px] text-ink-900 leading-relaxed focus:outline-none focus:border-brand focus:ring-1 focus:ring-brand/40 resize-none disabled:opacity-50"
                    spellCheck={false}
                  />
                  <button
                    type="button"
                    data-testid="chat-gate-redo"
                    onClick={handleRedo}
                    disabled={submitted}
                    className="w-full flex items-center justify-center gap-2 rounded-xl border border-brand-border text-brand px-4 py-2 text-[11px] font-semibold hover:bg-brand-fill transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Redo this step
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowRedo(true)}
                  disabled={submitted}
                  className="w-full flex items-center justify-center gap-2 rounded-xl border border-brand-border text-brand px-4 py-2 text-[11px] font-medium hover:bg-brand-fill transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Redo with instructions
                </button>
              )}
            </div>
          )}

          {/* Reject — KAN-95 two-step confirm. */}
          {showRejectConfirm ? (
            <div className="rounded-xl border border-status-failed-border bg-status-failed-fill px-3 py-2.5 space-y-2">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-3.5 w-3.5 text-status-failed flex-shrink-0 mt-0.5" />
                <p className="text-[11px] font-medium text-status-failed-strong">
                  Cancel this pipeline? This stops execution and discards progress.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowRejectConfirm(false)}
                  className="flex-1 rounded-lg border border-line-border bg-surface-white text-ink-600 px-3 py-1.5 text-[11px] font-medium hover:bg-surface-warm transition-all"
                >
                  Keep reviewing
                </button>
                <button
                  type="button"
                  data-testid="chat-gate-reject"
                  onClick={handleReject}
                  disabled={submitted}
                  className="flex-1 rounded-lg bg-status-failed text-white px-3 py-1.5 text-[11px] font-semibold hover:bg-status-failed-strong transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Yes, cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowRejectConfirm(true)}
              disabled={submitted}
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-status-failed-border text-status-failed px-4 py-2 text-[11px] font-medium hover:bg-status-failed-fill transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <XCircle className="h-3.5 w-3.5" />
              Reject & cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}
