"use client";

/**
 * InlineClarifyActions — compact in-lane mirror of the Steps `QuestionnairePanel`.
 *
 * Presentational + callback-driven. It renders the clarify question(s) as
 * quick-reply chips + a compact submit INSIDE the chat lane and fires the SAME
 * `submit_questionnaire` answer channel the full panel resolves through — one
 * backend command whether the user answers from chat OR from Steps
 * (LIVE-STATE-CONTRACT §1 clarify row). It mints no second channel.
 *
 * The emitted shape is the canonical answers array the app already routes:
 * `[{ question_id, answer }]`, multi joined by ", ", plus an optional global
 * `question_id: "freeform"` entry — identical to the Steps caller's mapping
 * (DashboardLayout.handleQuestionnaireSubmit). Keyed on the generic question
 * ids only — no workflow/agent-name literal (SC-001).
 */

import { useCallback, useEffect, useState } from "react";
import { Lightbulb, SkipForward, ArrowRight, Sparkles } from "lucide-react";

import type { ClarifyQuestion } from "@/types/index";

export interface ClarifyResponse {
  question_id: string;
  answer: string;
}

interface InlineClarifyActionsProps {
  questions: ClarifyQuestion[];
  onSubmitAnswers: (responses: ClarifyResponse[]) => void;
  /** Optional: skip all questions and run directly. */
  onSkipAll?: () => void;
}

function isMultiQuestion(q: ClarifyQuestion): boolean {
  return q.answerType === "multi_select" || !!q.allowMultiple;
}

function recommendedFor(q: ClarifyQuestion): string {
  return String(
    q.recommendedAnswer ??
      (q.options?.length ? q.options[q.options.length - 1] : "") ??
      "",
  ).trim();
}

export function InlineClarifyActions({
  questions,
  onSubmitAnswers,
  onSkipAll,
}: InlineClarifyActionsProps) {
  // answers keyed by question id → selected option strings (single or multi).
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  // per-question skip.
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  // global "anything else" freeform.
  const [freeform, setFreeform] = useState("");
  const [submitted, setSubmitted] = useState(false);

  // Reset on a fresh clarify round (new question set).
  useEffect(() => {
    setAnswers({});
    setSkipped(new Set());
    setFreeform("");
    setSubmitted(false);
  }, [questions]);

  const toggleOption = useCallback(
    (q: ClarifyQuestion, option: string) => {
      const qid = q.id;
      setSkipped((prev) => {
        if (!prev.has(qid)) return prev;
        const next = new Set(prev);
        next.delete(qid);
        return next;
      });
      setAnswers((prev) => {
        const cur = prev[qid] || [];
        if (isMultiQuestion(q)) {
          return cur.includes(option)
            ? { ...prev, [qid]: cur.filter((o) => o !== option) }
            : { ...prev, [qid]: [...cur, option] };
        }
        return { ...prev, [qid]: [option] };
      });
    },
    [],
  );

  const useRecommended = useCallback((q: ClarifyQuestion) => {
    const rec = recommendedFor(q);
    if (!rec) return;
    setSkipped((prev) => {
      if (!prev.has(q.id)) return prev;
      const next = new Set(prev);
      next.delete(q.id);
      return next;
    });
    if (isMultiQuestion(q)) {
      const parts = rec
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean);
      setAnswers((prev) => ({ ...prev, [q.id]: parts.length ? parts : [rec] }));
    } else {
      setAnswers((prev) => ({ ...prev, [q.id]: [rec] }));
    }
  }, []);

  const skipQuestion = useCallback((qid: string) => {
    setAnswers((prev) => {
      if (!prev[qid]) return prev;
      const next = { ...prev };
      delete next[qid];
      return next;
    });
    setSkipped((prev) => new Set(prev).add(qid));
  }, []);

  const handleSubmit = useCallback(() => {
    if (submitted) return;
    setSubmitted(true);
    const responses: ClarifyResponse[] = [];
    for (const q of questions) {
      if (skipped.has(q.id)) continue;
      const sel = answers[q.id];
      if (sel?.length) {
        responses.push({ question_id: q.id, answer: sel.join(", ") });
      }
    }
    const freeText = freeform.trim();
    if (freeText) {
      responses.push({ question_id: "freeform", answer: freeText });
    }
    onSubmitAnswers(responses);
  }, [submitted, questions, skipped, answers, freeform, onSubmitAnswers]);

  if (!questions.length) return null;

  return (
    <div
      data-testid="chat-clarify-actions"
      className="rounded-2xl border border-gray-200 bg-white px-4 py-3 space-y-3"
    >
      {questions.map((q) => {
        const rec = recommendedFor(q);
        const selected = answers[q.id] || [];
        const isSkipped = skipped.has(q.id);
        const multi = isMultiQuestion(q);
        return (
          <div key={q.id} className="space-y-1.5">
            <p className="text-[12px] font-semibold text-gray-900 leading-snug">
              {q.question}
            </p>
            {multi && (
              <p className="text-[10px] text-gray-400">Select all that apply</p>
            )}
            <div className="flex flex-wrap gap-1.5">
              {q.options?.map((option, oi) => {
                const active = selected.includes(option) && !isSkipped;
                return (
                  <button
                    key={oi}
                    type="button"
                    data-testid="chat-clarify-chip"
                    onClick={() => toggleOption(q, option)}
                    disabled={submitted}
                    className={`rounded-full px-3 py-1.5 text-[11px] font-medium border transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
                      active
                        ? "border-[#1B2A4A] bg-[#1B2A4A] text-white"
                        : "border-gray-200 bg-gray-50 text-gray-700 hover:border-[#1B2A4A]/30 hover:bg-white"
                    }`}
                  >
                    {option}
                    {option === rec && !active && (
                      <span className="ml-1 text-[9px] text-blue-500 font-semibold">
                        Rec.
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center gap-3">
              {rec && (
                <button
                  type="button"
                  onClick={() => useRecommended(q)}
                  disabled={submitted}
                  className="flex items-center gap-1 text-[10px] font-semibold text-blue-700 hover:text-blue-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Lightbulb className="h-3 w-3" /> Use recommended
                </button>
              )}
              <button
                type="button"
                onClick={() => skipQuestion(q.id)}
                disabled={submitted}
                className={`flex items-center gap-1 text-[10px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                  isSkipped
                    ? "text-gray-600 font-semibold"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                <SkipForward className="h-3 w-3" />
                {isSkipped ? "Skipped" : "Skip"}
              </button>
            </div>
          </div>
        );
      })}

      {/* Global freeform → question_id: "freeform". */}
      <div className="rounded-xl border border-dashed border-gray-200 px-3 py-2">
        <div className="flex items-center gap-1.5 mb-1.5">
          <Sparkles className="h-3 w-3 text-[#1B2A4A]" />
          <p className="text-[10px] font-semibold text-gray-600">
            Anything else?{" "}
            <span className="text-gray-400 font-normal">(optional)</span>
          </p>
        </div>
        <textarea
          value={freeform}
          onChange={(e) => setFreeform(e.target.value)}
          disabled={submitted}
          placeholder="Add any specific requirements or preferences…"
          rows={2}
          aria-label="Additional notes"
          className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-[11px] text-gray-900 placeholder-gray-400 focus:outline-none focus:border-[#1B2A4A]/40 resize-none disabled:opacity-50"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          data-testid="chat-clarify-submit"
          onClick={handleSubmit}
          disabled={submitted}
          className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ArrowRight className="h-3.5 w-3.5" />
          Send answers
        </button>
        {onSkipAll && (
          <button
            type="button"
            onClick={onSkipAll}
            disabled={submitted}
            className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors py-1 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <SkipForward className="h-3 w-3" /> Skip all
          </button>
        )}
      </div>
    </div>
  );
}
