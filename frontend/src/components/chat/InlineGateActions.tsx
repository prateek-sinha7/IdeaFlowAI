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
 * Behaviors carried (post-merge KAN cluster):
 * - KAN-101: the FOURTH action "Update the Specs" — rendered off the GENERIC
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
} from "lucide-react";

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

  return (
    <div
      data-testid="chat-gate-actions"
      className="rounded-2xl border border-gray-200 bg-white px-4 py-3 space-y-2"
    >
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-[#1B2A4A] to-violet-600 flex items-center justify-center flex-shrink-0">
          <CheckCircle2 className="h-3.5 w-3.5 text-white" />
        </div>
        <p className="text-[11px] font-semibold text-gray-900 flex-1 min-w-0 truncate">
          {agentName} · review before continuing
        </p>
        <button
          type="button"
          onClick={() => setShowEdit((v) => !v)}
          disabled={submitted}
          className="flex items-center gap-1 text-[10px] text-gray-500 hover:text-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Edit3 className="h-3 w-3" /> Edit
          {hasEdits && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
        </button>
      </div>

      {showEdit && (
        <textarea
          value={editedContent}
          onChange={(e) => handleEdit(e.target.value)}
          disabled={submitted}
          aria-label="Edit gate content"
          className="w-full min-h-[120px] rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-[11px] text-gray-900 font-mono leading-relaxed focus:outline-none focus:border-[#1B2A4A]/40 focus:ring-1 focus:ring-[#1B2A4A]/20 resize-none disabled:opacity-50"
          spellCheck={false}
        />
      )}

      {hasEdits && (
        <p className="text-[10px] text-amber-700">
          You have unsaved edits — approving will use your edited version.
        </p>
      )}

      {/* 1. Approve — the shared approve_review channel. */}
      <button
        type="button"
        data-testid="chat-gate-approve"
        onClick={handleApprove}
        disabled={submitted}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <CheckCircle2 className="h-4 w-4" />
        {approveLabel ??
          (hasEdits ? "Approve with edits & continue" : "Approve & continue")}
      </button>

      {/* 2. KAN-101 Update the Specs — rendered off the GENERIC flag (SC-001). */}
      {canUpdateSpecs && (
        <button
          type="button"
          data-testid="chat-gate-update-specs"
          onClick={handleUpdateSpecs}
          disabled={submitted}
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-[#1B2A4A]/30 text-[#1B2A4A] px-4 py-2 text-[11px] font-semibold hover:bg-[#E8EDF5] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Update the Specs
        </button>
      )}

      {/* 3. Redo — rendered IFF onRedo AND server-set redoable (generic fence). */}
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
                className="w-full min-h-[52px] rounded-lg border border-violet-200 bg-white px-3 py-2 text-[11px] text-gray-900 leading-relaxed focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-300 resize-none disabled:opacity-50"
                spellCheck={false}
              />
              <button
                type="button"
                data-testid="chat-gate-redo"
                onClick={handleRedo}
                disabled={submitted}
                className="w-full flex items-center justify-center gap-2 rounded-xl border border-violet-300 text-violet-700 px-4 py-2 text-[11px] font-semibold hover:bg-violet-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-violet-200 text-violet-700 px-4 py-2 text-[11px] font-medium hover:bg-violet-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Redo with instructions
            </button>
          )}
        </div>
      )}

      {/* 4. Reject — KAN-95 two-step confirm. */}
      {showRejectConfirm ? (
        <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] font-medium text-red-700">
              Cancel this pipeline? This stops execution and discards progress.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowRejectConfirm(false)}
              className="flex-1 rounded-lg border border-gray-200 bg-white text-gray-600 px-3 py-1.5 text-[11px] font-medium hover:bg-gray-50 transition-all"
            >
              Keep reviewing
            </button>
            <button
              type="button"
              data-testid="chat-gate-reject"
              onClick={handleReject}
              disabled={submitted}
              className="flex-1 rounded-lg bg-red-600 text-white px-3 py-1.5 text-[11px] font-semibold hover:bg-red-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
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
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-red-200 text-red-600 px-4 py-2 text-[11px] font-medium hover:bg-red-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <XCircle className="h-3.5 w-3.5" />
          Reject & cancel
        </button>
      )}
    </div>
  );
}
