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
  gateAsk,
  GateWell,
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
  /**
   * GENERIC artifact kind from the backend (_artifact_kind_for) — "spec",
   * "task_list", "summary", etc. Passed to discriminateArtifact so agents
   * whose output has no XML wrapper tag (e.g. user_stories domain-analyst
   * produces plain markdown with kind="summary") still get the right preview.
   * SC-001: never a workflow/agent literal — structurally derived server-side.
   */
  artifactKind?: string;
  /**
   * ISS-052 — the per-FIRING discriminator from the backend. `gateKey` names a gate
   * SLOT, not a firing, so the gate opened INSIDE a spec-revision pass and the one
   * re-opened after that pass returns arrive with the SAME `gateKey` and the SAME
   * `output`. `revisionCycle` is which cycle this firing belongs to (0 = none has run);
   * `revisionInFlight` is whether the pass is still on the stack. Two jobs here: the
   * badge (so the two do not read identically) and the re-arm dependency below (so the
   * one-action latch releases when the second gate opens). SC-001: generic run state.
   */
  revisionCycle?: number;
  revisionInFlight?: boolean;
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
  artifactKind,
  revisionCycle = 0,
  revisionInFlight = false,
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

  // Fresh gate only: a new output, a new gateKey, OR a new revision stamp resets
  // everything. A no-echo re-render with all four unchanged leaves the retained edit
  // intact (KAN-98).
  //
  // ISS-052: the stamp is load-bearing, not decorative. When a spec-revision pass
  // returns, the SAME gate re-opens with the SAME gateKey and byte-identical output
  // (live: 11,974 chars, 5 ms after the approve). On `[output, gateKey]` alone nothing
  // in the dependency list changes, so this effect never re-runs, `submitted` stays
  // latched, and the user faces a live gate with every action disabled.
  useEffect(() => {
    setEditedContent(output);
    setHasEdits(false);
    setShowEdit(false);
    setShowRejectConfirm(false);
    setRedoInstructions("");
    setShowRedo(false);
    setSubmitted(false);
  }, [output, gateKey, revisionCycle, revisionInFlight]);

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

  // The artifact kind drives BOTH the well's renderer and the ask (SC-001 —
  // structural kind only, never a workflow/agent literal).
  const resolvedArtifactKind = discriminateArtifact(output, artifactKind);

  // ── Routed human gate: the human IS the router ─────────────────────────────
  // The backend publishes a routed step's declared `route.outcomes` keys on the
  // EXISTING generic carriers — `artifact_kind: "conditional_gate"` as the
  // discriminator, the choices JSON-encoded on `output` (the same channel the
  // approval gate's D-04 snapshot rides). Branch on the RAW prop, not on
  // discriminateArtifact, which only resolves the three preview kinds.
  //
  // Free text here was the defect: the answer must equal a declared outcome key
  // exactly, and nothing told the user what those keys were. A malformed parse
  // falls back to the normal card, so a bad payload degrades rather than breaks.
  const choicePayload = (() => {
    if (artifactKind !== "conditional_gate") return null;
    try {
      const parsed = JSON.parse(output) as { prompt?: string; choices?: unknown };
      const choices = Array.isArray(parsed.choices)
        ? parsed.choices.filter((c): c is string => typeof c === "string" && !!c)
        : [];
      return choices.length ? { prompt: String(parsed.prompt ?? ""), choices } : null;
    } catch {
      return null;
    }
  })();

  // The ask. A routed gate carries its own prompt on the wire, so that wins; an
  // approval gate derives one from the artifact kind (see gateAsk). The caller's
  // approveLabel still overrides the derived button label.
  const derived = gateAsk(artifactKind, resolvedArtifactKind);
  const askText = choicePayload
    ? (choicePayload.prompt || "Which route should the run take?")
    : derived.ask;
  const approveText = hasEdits
    ? "Approve with edits & build"
    : (approveLabel ?? derived.approve);

  // Request changes has exactly one channel behind it — redo-with-instructions —
  // so it is rendered only when that channel is open. Update-specs and cancel are
  // their OWN always-visible quiet actions below; nothing is collapsed behind a
  // disclosure that the user has to discover.
  const slotOpen = showRedo || showRejectConfirm;

  return (
    <div
      data-testid="chat-gate-actions"
      className="overflow-hidden rounded-[12px] border border-brand-border bg-surface-white shadow-[0_1px_2px_rgba(20,20,40,.04),0_12px_28px_-14px_rgba(60,44,218,.28)]"
    >
      {/* ── The decision ────────────────────────────────────────────────────────
          Ask, then actions, then the evidence beneath — the "ask first" order.
          The ask and its actions share ONE brand-filled block closed by a rule
          (the mock's S2 treatment, applied at the top rather than the bottom):
          the decision is a PLACE in the card, not a heading above more reading.
          Before this the card led with "{agentName} · review before continuing",
          which described the card instead of asking the reader anything. */}
      <div className="gate-decision bg-brand-fill border-b border-brand-border">
        <div className="flex items-start gap-3 px-3.5 pt-3">
          <div className="min-w-0 flex-1">
            <p className="m-0 mb-1 text-[9.5px] font-bold uppercase tracking-[0.12em] text-brand">
              Waiting on you
            </p>
            <h4 className="m-0 text-[14px] font-semibold leading-snug tracking-[-0.01em] text-ink-900">
              {askText}
            </h4>
          </div>
          {/* ISS-052: the two spec-revision firings of this gate are otherwise identical
              on screen — same agent, same output, same actions bar. Name the cycle and
              say whether the revision is still running. Dormant (renders nothing) on
              every gate outside a revision cycle. SC-001: server-derived state only. */}
          {revisionCycle > 0 && (
            <span
              data-testid="chat-gate-revision"
              className={`mt-0.5 flex-none rounded border px-1.5 py-1 text-[8.5px] font-semibold uppercase tracking-wider ${
                revisionInFlight
                  ? "text-status-amber bg-status-amber-fill border-status-amber-border"
                  : "text-brand bg-surface-white border-brand-border"
              }`}
            >
              {revisionInFlight
                ? `Revision cycle ${revisionCycle} · in progress`
                : `Revision cycle ${revisionCycle} · complete`}
            </span>
          )}
        </div>

        {/* The actions row. Primaries left, the rarer channels quiet on the right,
            separated by a flexible spacer so the row degrades by wrapping rather
            than by crowding. */}
        <div className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
          {/* A routed gate's declared outcomes ARE the primary action: each
              resolves through the SAME approve channel, the value being the route
              decision the conditional gate reads. */}
          {choicePayload
            ? choicePayload.choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  data-testid={`chat-gate-choice-${choice}`}
                  onClick={() => {
                    if (submitted) return;
                    setSubmitted(true);
                    onApprove(gateKey, JSON.stringify({ decision: choice }));
                  }}
                  disabled={submitted}
                  className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-brand px-4 text-[12px] font-semibold text-white shadow-[0_2px_6px_-2px_rgba(60,44,218,.5)] transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 flex-none" />
                  {choice.charAt(0).toUpperCase() + choice.slice(1)}
                </button>
              ))
            : (
              <button
                type="button"
                data-testid="chat-gate-approve"
                onClick={handleApprove}
                disabled={submitted}
                className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-brand px-4 text-[12px] font-semibold text-white shadow-[0_2px_6px_-2px_rgba(60,44,218,.5)] transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-50"
              >
                <CheckCircle2 className="h-3.5 w-3.5 flex-none" />
                {approveText}
              </button>
            )}

          {/* Request changes — the redo channel, opened as a composer in the slot
              below. Rendered only when the server says the step is redoable; a
              button that cannot send anything is worse than no button. */}
          {canRedo && (
            <button
              type="button"
              data-testid="chat-gate-request-changes"
              onClick={() => { setShowRejectConfirm(false); setShowRedo((v) => !v); }}
              disabled={submitted}
              className="inline-flex h-9 items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-white px-4 text-[12px] font-medium text-ink-800 transition-colors hover:border-ink-300 hover:bg-surface-warm disabled:cursor-not-allowed disabled:opacity-50"
            >
              <MessageSquarePlus className="h-3.5 w-3.5 flex-none" />
              Request changes
            </button>
          )}

          <span className="flex-1" />

          {/* KAN-101 "Update the Specs" — rendered iff the server flag is set
              (updateSpecsEligible, derived generically from artifactKind — SC-001). */}
          {canUpdateSpecs && (
            <>
              <button
                type="button"
                data-testid="chat-gate-update-specs"
                onClick={handleUpdateSpecs}
                disabled={submitted}
                className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 transition-colors hover:text-brand hover:underline disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Update the specs
              </button>
              <span aria-hidden className="text-line-faint">·</span>
            </>
          )}

          {/* KAN-95: cancel is a two-step confirm, opened in the slot below. */}
          <button
            type="button"
            data-testid="chat-gate-cancel"
            onClick={() => { setShowRedo(false); setShowRejectConfirm((v) => !v); }}
            disabled={submitted}
            className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 transition-colors hover:text-status-failed hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            <XCircle className="h-3.5 w-3.5" />
            Cancel run
          </button>
        </div>

        {/* ── The slot ──────────────────────────────────────────────────────────
            Where the composer and the destructive confirm open. It sits INSIDE
            the decision block (and so on its fill) rather than between the
            decision and the evidence — opened there, either one drove a wedge
            through the card and orphaned the "What … wrote" heading from it. */}
        {slotOpen && (
          <div className="px-3.5 pb-3">
            {showRedo && (
              <div className="flex flex-col gap-2.5 rounded-[10px] border border-brand-border bg-surface-white p-3">
                <textarea
                  value={redoInstructions}
                  onChange={(e) => setRedoInstructions(e.target.value)}
                  disabled={submitted}
                  placeholder="What should change? Leave blank to just run the step again."
                  aria-label="Additional instructions for redo"
                  name="redo-instructions"
                  className="min-h-[80px] w-full resize-y rounded-lg border border-line-border bg-surface-warm px-3 py-2 font-serif text-[12px] leading-relaxed text-ink-900 placeholder:text-ink-300 focus:border-brand focus:bg-surface-white focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:opacity-50"
                  spellCheck={false}
                />
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowRedo(false)}
                    className="text-[11px] text-ink-500 transition-colors hover:text-brand hover:underline"
                  >
                    Never mind
                  </button>
                  <button
                    type="button"
                    data-testid="chat-gate-redo"
                    onClick={handleRedo}
                    disabled={submitted}
                    className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-brand px-4 text-[12px] font-semibold text-white shadow-[0_2px_6px_-2px_rgba(60,44,218,.5)] transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <RotateCcw className="h-3.5 w-3.5 flex-none" />
                    Send it back
                  </button>
                </div>
              </div>
            )}

            {showRejectConfirm && (
              <div className="flex flex-col gap-2 rounded-[10px] border border-status-failed-border bg-status-failed-fill p-3">
                <p className="m-0 flex gap-2 font-serif text-[11.5px] leading-snug text-status-failed-strong">
                  <AlertTriangle aria-hidden className="mt-0.5 h-3.5 w-3.5 flex-none" />
                  <span>Cancel this run? It stops here and the work so far is discarded.</span>
                </p>
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowRejectConfirm(false)}
                    className="text-[11px] text-ink-500 transition-colors hover:text-ink-900 hover:underline"
                  >
                    Keep reviewing
                  </button>
                  <button
                    type="button"
                    data-testid="chat-gate-reject"
                    onClick={handleReject}
                    disabled={submitted}
                    className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-status-failed px-4 text-[12px] font-semibold text-white shadow-[0_2px_6px_-2px_rgba(163,58,50,.5)] transition-colors hover:bg-status-failed-strong disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Yes, cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── The evidence ────────────────────────────────────────────────────────
          What the run produced, set apart from the decision above it. A CAPPED
          preview, not the reading surface — the whole artifact is in Preview,
          Files and Workspace. Its TOP edge is shaded (.gate-well-fade, inside
          GateWell) and the decision block casts down onto it (.gate-decision),
          so the well reads as passing UNDER the decision rather than as a
          second flat panel stacked beside it. */}
      <div className="px-3.5 pb-3.5 pt-3">
        <div className="mb-2 flex items-center gap-2.5">
          <span className="flex-1 text-[9.5px] font-bold uppercase tracking-[0.12em] text-ink-400">
            {/* A routed gate's `output` is a JSON envelope of route keys, not an
                artifact — there is nothing authored to show or edit. */}
            {choicePayload ? "The routes" : `What ${agentName} wrote`}
          </span>
          {!choicePayload && (
            <button
              type="button"
              onClick={() => setShowEdit((v) => !v)}
              disabled={submitted}
              className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 transition-colors hover:text-brand hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Edit3 className="h-3.5 w-3.5" />
              {showEdit ? "Editing" : "Edit"}
              {hasEdits && <span className="h-1.5 w-1.5 rounded-full bg-status-amber" />}
            </button>
          )}
        </div>

        {showEdit ? (
          <textarea
            value={editedContent}
            onChange={(e) => handleEdit(e.target.value)}
            disabled={submitted}
            aria-label="Edit gate content"
            name="gate-content"
            className="min-h-[160px] w-full resize-y rounded-[10px] border border-line-border bg-surface-warm px-3 py-2.5 font-mono text-[11px] leading-relaxed text-ink-900 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:opacity-50"
            spellCheck={false}
          />
        ) : choicePayload ? (
          <div data-testid="chat-gate-choice-prompt" className="rounded-[10px] border border-line-border bg-surface-warm px-3 py-2.5 font-serif text-[12px] leading-relaxed text-ink-800">
            {choicePayload.prompt || "The run branches here on the route you pick."}
          </div>
        ) : (
          <div data-testid="chat-gate-preview">
            <GateWell content={output} artifactKind={artifactKind} />
          </div>
        )}

        {hasEdits && (
          <p className="mt-2 text-[11px] text-status-amber">
            You have unsaved edits — approving will use your edited version.
          </p>
        )}
      </div>
    </div>
  );
}
