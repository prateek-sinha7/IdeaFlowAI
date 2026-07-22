"use client";

/**
 * InlineClarifyActions — compact in-lane mirror of the Steps clarify panel.
 *
 * Presentational + callback-driven. It renders the clarify question(s) as
 * quick-reply chips + a single submit INSIDE the chat lane and fires the SAME
 * `submit_questionnaire` answer channel the full panel resolves through — one
 * backend command whether the user answers from chat OR from Steps
 * (LIVE-STATE-CONTRACT §1 clarify row). It mints no second channel.
 *
 * The emitted shape is the canonical answers array the app already routes:
 * `[{ question_id, answer }]`, multi joined by ", ". Keyed on the generic
 * question ids only — no workflow/agent-name literal (SC-001).
 *
 * FIX-094 (KAN-117): Added:
 *   1. Recommended-answer pre-fill — each question shows the server-supplied
 *      `recommendedDisplay` hint in a muted chip; clicking it selects it.
 *   2. Per-question "Use recommended" one-click affordance when a recommended
 *      answer exists but the user hasn't selected anything.
 *   3. "Skip all & start build" button — submits only the questions the user
 *      explicitly answered (same behaviour as before), but now clearly
 *      labelled so the user knows they CAN proceed without answering everything.
 *   4. High-impact badge on questions whose `impactLevel === "high"` so users
 *      can prioritise which questions to answer.
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Zap } from "lucide-react";

import type { ClarifyQuestion } from "@/types/index";

export interface ClarifyResponse {
  question_id: string;
  answer: string;
}

interface InlineClarifyActionsProps {
  questions: ClarifyQuestion[];
  onSubmitAnswers: (responses: ClarifyResponse[]) => void;
  /**
   * Optional: cancel the active pipeline run entirely. Re-homed here (Phase 42-02)
   * from the deleted QuestionnairePanel so the Cancel-Workflow affordance is not
   * lost when the legacy full-screen clarify takeover was removed. Bound by the
   * caller to the existing owner-scoped `handleCancelWorkflow` (no new channel).
   */
  onCancelWorkflow?: () => void;
}

function isMultiQuestion(q: ClarifyQuestion): boolean {
  return q.answerType === "multi_select" || !!q.allowMultiple;
}

export function InlineClarifyActions({
  questions,
  onSubmitAnswers,
  onCancelWorkflow,
}: InlineClarifyActionsProps) {
  // answers keyed by question id → selected option strings (single or multi).
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [submitted, setSubmitted] = useState(false);

  // Reset on a fresh clarify round (new question set).
  useEffect(() => {
    setAnswers({});
    setSubmitted(false);
  }, [questions]);

  const toggleOption = useCallback((q: ClarifyQuestion, option: string) => {
    const qid = q.id;
    setAnswers((prev) => {
      const cur = prev[qid] || [];
      if (isMultiQuestion(q)) {
        return cur.includes(option)
          ? { ...prev, [qid]: cur.filter((o) => o !== option) }
          : { ...prev, [qid]: [...cur, option] };
      }
      return { ...prev, [qid]: [option] };
    });
  }, []);

  // FIX-094: "Use recommended" — selects the server-supplied recommended answer
  // for a single question, replacing whatever was selected.
  const useRecommended = useCallback((q: ClarifyQuestion) => {
    const rec = q.recommendedAnswer || q.recommendedDisplay;
    if (!rec) return;
    setAnswers((prev) => ({ ...prev, [q.id]: [rec] }));
  }, []);

  // Submit only the questions that have a selected answer (skipped ones are
  // omitted — same behaviour as before, just now explicitly surfaced as "skip").
  const buildResponses = useCallback((): ClarifyResponse[] => {
    const responses: ClarifyResponse[] = [];
    for (const q of questions) {
      const sel = answers[q.id];
      if (sel?.length) {
        responses.push({ question_id: q.id, answer: sel.join(", ") });
      }
    }
    return responses;
  }, [questions, answers]);

  const handleSubmit = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onSubmitAnswers(buildResponses());
  }, [submitted, buildResponses, onSubmitAnswers]);

  // FIX-094: "Skip all" — submits with only answered questions (unanswered skipped).
  // Semantically identical to handleSubmit; the separate button makes the intent
  // visible. The backend already handles partial answers gracefully.
  const handleSkipAll = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    onSubmitAnswers(buildResponses());
  }, [submitted, buildResponses, onSubmitAnswers]);

  if (!questions.length) return null;

  const answeredCount = questions.filter((q) => (answers[q.id]?.length ?? 0) > 0).length;

  return (
    <div
      data-testid="chat-clarify-actions"
      className="rounded-2xl border border-line-border bg-surface-white px-4 py-3 space-y-4"
    >
      {questions.map((q) => {
        const selected = answers[q.id] || [];
        const multi = isMultiQuestion(q);
        const isHighImpact = q.impactLevel === "high";
        // The recommended display label (may differ from the raw value).
        const recDisplay = q.recommendedDisplay || q.recommendedAnswer;
        const hasRec = !!recDisplay;
        const recIsSelected =
          hasRec && selected.some(
            (s) => s === q.recommendedAnswer || s === q.recommendedDisplay,
          );

        return (
          <div key={q.id} className="space-y-1.5">
            {/* Question label + optional high-impact badge */}
            <div className="flex items-start gap-2">
              <p className="text-[12px] font-semibold text-ink-900 leading-snug flex-1">
                {q.question}
              </p>
              {isHighImpact && (
                <span
                  className="flex-none inline-flex items-center gap-0.5 text-[9px] font-semibold text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-0.5 rounded-[5px]"
                  title="High-impact question — answering this improves output quality"
                >
                  <Zap aria-hidden className="h-2.5 w-2.5" />
                  High impact
                </span>
              )}
            </div>

            {multi && (
              <p className="text-[10px] text-ink-400">Select all that apply</p>
            )}

            {/* FIX-094: Recommended-answer hint row — shown when a recommendation
                exists AND hasn't been selected yet. One-click "Use recommended"
                affordance so the user can accept the suggestion without hunting
                for the matching chip. Hidden once the user selects any option
                for this question so it doesn't clutter an already-answered row. */}
            {hasRec && selected.length === 0 && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-brand/5 border border-brand/15">
                <span className="flex-1 text-[10.5px] text-brand/80 leading-snug">
                  Recommended: <span className="font-semibold text-brand">{recDisplay}</span>
                </span>
                <button
                  type="button"
                  onClick={() => useRecommended(q)}
                  disabled={submitted}
                  className="flex-none text-[10px] font-semibold text-brand hover:text-brand-pressed border border-brand/30 bg-white rounded-md px-2 py-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Use recommended
                </button>
              </div>
            )}

            {/* FIX-094: When the recommended answer IS selected, show a subtle
                confirmation so the user sees they accepted the suggestion. */}
            {hasRec && recIsSelected && (
              <p className="text-[10px] text-brand/70 px-1">
                ✓ Using recommended answer
              </p>
            )}

            <div className="flex flex-wrap gap-1.5">
              {q.options?.map((option, oi) => {
                const active = selected.includes(option);
                const isRec =
                  hasRec &&
                  (option === q.recommendedAnswer || option === q.recommendedDisplay);
                return (
                  <button
                    key={oi}
                    type="button"
                    data-testid="chat-clarify-chip"
                    onClick={() => toggleOption(q, option)}
                    disabled={submitted}
                    className={`rounded-full px-3 py-1.5 text-[11px] font-medium border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                      active
                        ? "border-brand bg-brand text-white"
                        : "border-line-border bg-surface-warm text-ink-700 hover:border-brand/30 hover:bg-surface-white"
                    }`}
                  >
                    {option}
                    {/* FIX-094: subtle star marker on the recommended option chip */}
                    {isRec && !active && (
                      <span className="ml-1 text-brand/60 text-[9px]">★</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Primary action: submit all answered questions */}
      <button
        type="button"
        data-testid="chat-clarify-submit"
        onClick={handleSubmit}
        disabled={submitted}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-brand-pressed transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <ArrowRight className="h-3.5 w-3.5" />
        {answeredCount > 0
          ? `Submit ${answeredCount} answer${answeredCount !== 1 ? "s" : ""} & start the build`
          : "Submit answers & start the build"}
      </button>

      {/* FIX-094: "Skip all" — clearly surfaces that answering is optional. Only
          shown when the user hasn't answered everything yet. Submits partial
          answers (same as the primary button — backend handles unanswered questions
          with its own defaults). */}
      {answeredCount < questions.length && !submitted && (
        <button
          type="button"
          data-testid="chat-clarify-skip-all"
          onClick={handleSkipAll}
          disabled={submitted}
          className="w-full text-center text-[11px] text-ink-400 hover:text-ink-700 transition-colors py-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Skip questions &amp; start the build →
        </button>
      )}

      {/* Cancel-Workflow — re-homed from the deleted QuestionnairePanel (Phase
          42-02 §A2 / §8 decision 1). Subtle muted text affordance on the brand
          status-failed token (42-10 reskin); fires the existing owner-scoped handler. */}
      {onCancelWorkflow && (
        <button
          type="button"
          data-testid="chat-clarify-cancel-workflow"
          onClick={onCancelWorkflow}
          disabled={submitted}
          className="w-full text-center text-[10px] text-status-failed/70 hover:text-status-failed transition-colors py-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Cancel workflow
        </button>
      )}
    </div>
  );
}
