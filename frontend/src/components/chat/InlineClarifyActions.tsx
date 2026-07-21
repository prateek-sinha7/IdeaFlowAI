"use client";

/**
 * InlineClarifyActions — compact in-lane mirror of the Steps `QuestionnairePanel`.
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
 * Mock (Hexaware Run - Live.dc.html :229) is a single "Submit answers & start
 * the build" — the per-question skip toggle, the recommended-answer fill/badge,
 * the optional freeform block, and the skip-all control are intentionally
 * omitted (Phase 42-06, CONTEXT §G / §8 decision 3). The re-homed
 * Cancel-Workflow affordance (42-02) survives.
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";

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

  const handleSubmit = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    const responses: ClarifyResponse[] = [];
    for (const q of questions) {
      const sel = answers[q.id];
      if (sel?.length) {
        responses.push({ question_id: q.id, answer: sel.join(", ") });
      }
    }
    onSubmitAnswers(responses);
  }, [submitted, questions, answers, onSubmitAnswers]);

  if (!questions.length) return null;

  return (
    <div
      data-testid="chat-clarify-actions"
      className="rounded-2xl border border-line-border bg-surface-white px-4 py-3 space-y-3"
    >
      {questions.map((q) => {
        const selected = answers[q.id] || [];
        const multi = isMultiQuestion(q);
        return (
          <div key={q.id} className="space-y-1.5">
            <p className="text-[12px] font-semibold text-ink-900 leading-snug">
              {q.question}
            </p>
            {multi && (
              <p className="text-[10px] text-ink-400">Select all that apply</p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {q.options?.map((option, oi) => {
                const active = selected.includes(option);
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
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      <button
        type="button"
        data-testid="chat-clarify-submit"
        onClick={handleSubmit}
        disabled={submitted}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-brand text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-brand-pressed transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <ArrowRight className="h-3.5 w-3.5" />
        Submit answers & start the build
      </button>

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
