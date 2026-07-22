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
 * FIX-094 (KAN-117): Added recommended-answer display, Use recommended button,
 *   Skip all affordance, and High-impact badge.
 * FIX-095: Fixed multi-select chip highlighting when "Use recommended" clicked —
 *   backend can send a comma-separated string for multi-select recommendations;
 *   split+match against chip options. All .split() calls guarded with String()
 *   coercion to handle non-string values (array, null, etc.) from the API.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
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

/**
 * FIX-095: safely coerce a recommended-answer value to a plain string.
 * The backend sometimes sends an array ["option A", "option B"] or a number
 * instead of a string — String() handles all of those without crashing.
 * An array becomes "option A,option B" which the split will then re-tokenise.
 */
function toRecString(val: unknown): string {
  if (val == null) return "";
  if (Array.isArray(val)) return val.join(", ");
  return String(val);
}

/**
 * FIX-095: split a (possibly non-string) recommended-answer value into tokens
 * and return only those that exactly match one of the available chip options.
 * Falls back to the whole value as a single selection if no tokens match.
 */
function splitRecToChips(rec: unknown, options: string[]): string[] {
  const str = toRecString(rec);
  if (!str) return [];
  const tokens = str.split(/,\s*/).map((t) => t.trim()).filter(Boolean);
  const matched = tokens.filter((t) => options.includes(t));
  return matched.length > 0 ? matched : [str];
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

  // FIX-094/095: "Use recommended" — selects the server-supplied recommended
  // answer. For multi-select, splits the comma-separated recommendation into
  // individual chip selections. All coercions go through toRecString/splitRecToChips
  // so non-string API values (arrays, numbers) never crash.
  const useRecommended = useCallback((q: ClarifyQuestion) => {
    const rec = q.recommendedAnswer ?? q.recommendedDisplay;
    if (rec == null || rec === "") return;
    let selections: string[];
    if (isMultiQuestion(q) && q.options?.length) {
      selections = splitRecToChips(rec, q.options);
    } else {
      selections = [toRecString(rec)];
    }
    setAnswers((prev) => ({ ...prev, [q.id]: selections }));
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

  // "Skip all" — submits only answered questions; unanswered are skipped.
  // Semantically identical to handleSubmit; separate label makes intent clear.
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

        // FIX-095: coerce recommended values to plain strings before ANY operation.
        const recRaw = q.recommendedAnswer ?? q.recommendedDisplay;
        const recStr = toRecString(recRaw);
        // Display label: prefer recommendedDisplay if it differs from raw value.
        const recDisplay = toRecString(q.recommendedDisplay || q.recommendedAnswer);
        const hasRec = recStr.length > 0;

        // FIX-095: split tokens for multi-select; used for chip ★ marker and
        // recIsSelected detection. Always uses String-safe helper.
        const recTokens = hasRec && q.options?.length
          ? splitRecToChips(recRaw, q.options)
          : hasRec ? [recStr] : [];

        // The "✓ Using recommended" indicator fires when any of the recommended
        // chip tokens (or the whole string for single-select) is in the selection.
        const recIsSelected =
          hasRec &&
          selected.length > 0 &&
          (recTokens.some((t) => selected.includes(t)) ||
            selected.some((s) => s === recStr));

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

            {/* Recommended-answer hint — shown before any selection is made. */}
            {hasRec && selected.length === 0 && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-brand/5 border border-brand/15">
                <span className="flex-1 text-[10.5px] text-brand/80 leading-snug">
                  Recommended:{" "}
                  <span className="font-semibold text-brand">{recDisplay}</span>
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

            {/* Confirmation shown after "Use recommended" is accepted. */}
            {hasRec && recIsSelected && (
              <p className="text-[10px] text-brand/70 px-1">
                ✓ Using recommended answer
              </p>
            )}

            <div className="flex flex-wrap gap-1.5">
              {q.options?.map((option, oi) => {
                const active = selected.includes(option);
                // FIX-095: isRec checks the split tokens, not the raw string.
                const isRec = hasRec && recTokens.includes(option);
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
                    {/* subtle ★ on the recommended chip when not yet selected */}
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

      {/* Primary action */}
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

      {/* Skip all — visible only while there are unanswered questions. */}
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
          42-02 §A2 / §8 decision 1). */}
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
