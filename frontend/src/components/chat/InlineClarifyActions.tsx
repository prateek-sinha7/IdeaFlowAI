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
import { ArrowRight, Zap, XCircle } from "lucide-react";

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
 * Does this question need a free-text field?
 *
 * `clarify_engine.py` declares four answer types and emits all of them:
 * "short_text" ("options can be [] — user types freely") and "hybrid" ("MCQ
 * suggestions plus the free-text field will be shown automatically") both need
 * one, and neither had it — a short_text question rendered as a question with
 * no way to answer it. The `!options.length` arm also catches a question that
 * declares no type but ships no options, which can only be free text.
 */
function hasTextField(q: ClarifyQuestion): boolean {
  return q.answerType === "short_text" || q.answerType === "hybrid" || !q.options?.length;
}

// Small numbers read better as words in the heading; anything larger falls back
// to the digit rather than growing a lookup table nobody will maintain.
const NUM_WORDS: Record<number, string> = {
  2: "Two", 3: "Three", 4: "Four", 5: "Five",
  6: "Six", 7: "Seven", 8: "Eight", 9: "Nine",
};

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

  // Free text shares the SAME answers slot as the chips — a typed value simply
  // is not one of the options, which is how the render side tells them apart.
  // That keeps a hybrid question's chip and its override mutually exclusive
  // without a second piece of state that could drift out of sync with the first.
  const setText = useCallback((q: ClarifyQuestion, value: string) => {
    setAnswers((prev) => ({ ...prev, [q.id]: value.trim() ? [value] : [] }));
  }, []);

  // FIX-094/095: "Use recommended" — selects the server-supplied recommended
  // answer. For multi-select, splits the comma-separated recommendation into
  // individual chip selections. All coercions go through toRecString/splitRecToChips
  // so non-string API values (arrays, numbers) never crash.
  // NB: deliberately NOT named `useRecommended` — a `use*` identifier makes the
  // Rules of Hooks linter treat this plain callback as a React Hook, so calling
  // it from an `onClick` reads as a conditional hook call (react-hooks/rules-of-hooks).
  const applyRecommended = useCallback((q: ClarifyQuestion) => {
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
  const total = questions.length;
  const heading =
    total === 1
      ? "One thing to lock down first"
      : `${NUM_WORDS[total] ?? total} things to lock down first`;

  return (
    <div
      data-testid="chat-clarify-actions"
      className="overflow-hidden rounded-[12px] border border-brand-border bg-surface-white shadow-[0_1px_2px_rgba(20,20,40,.04),0_12px_28px_-14px_rgba(60,44,218,.28)]"
    >
      {/* ── The ask ─────────────────────────────────────────────────────────────
          Same "ask first" order and same brand-filled, ruled block the review
          gate uses, so the two places a run stops and waits on you read as one
          language. The submit sits at the FOOT here rather than beside the ask:
          unlike an approval, this decision cannot be made before the questions
          are answered, so putting its button above them would be a button that
          does nothing yet. */}
      <div className="gate-decision border-b border-brand-border bg-brand-fill px-3.5 pb-3 pt-3">
        <p className="m-0 mb-1 text-[9.5px] font-bold uppercase tracking-[0.12em] text-brand">
          Before I build
        </p>
        <h4 className="m-0 text-[14px] font-semibold leading-snug tracking-[-0.01em] text-ink-900">
          {heading}
        </h4>
      </div>

      <div className="px-3.5 py-3.5">
        {questions.map((q, qi) => {
          const selected = answers[q.id] || [];
          const multi = isMultiQuestion(q);
          const isHighImpact = q.impactLevel === "high";
          const options = q.options ?? [];
          const showsText = hasTextField(q);
          // The free-text value IS the answer when it is not one of the offered
          // options — so a hybrid question's chips and its text override share
          // one slot without a second piece of state to keep in sync.
          const textValue = selected.length && !options.includes(selected[0]) ? selected[0] : "";

          // FIX-095: coerce recommended values to plain strings before ANY operation.
          const recRaw = q.recommendedAnswer ?? q.recommendedDisplay;
          const recStr = toRecString(recRaw);
          const recDisplay = toRecString(q.recommendedDisplay || q.recommendedAnswer);
          const hasRec = recStr.length > 0;

          const recTokens = hasRec && options.length
            ? splitRecToChips(recRaw, options)
            : hasRec ? [recStr] : [];

          const recIsSelected =
            hasRec &&
            selected.length > 0 &&
            (recTokens.some((t) => selected.includes(t)) ||
              selected.some((s) => s === recStr));

          return (
            <div
              key={q.id}
              className={qi > 0 ? "mt-3.5 border-t border-line-border pt-3.5" : undefined}
            >
              <div className="flex items-start gap-2">
                <p className="m-0 min-w-0 flex-1 font-serif text-[12.5px] font-semibold leading-[1.45] text-ink-900">
                  {q.question}
                </p>
                {isHighImpact && (
                  <span
                    className="inline-flex flex-none items-center gap-1 rounded-[var(--radius-tag)] border border-status-amber-border bg-status-amber-fill px-1.5 py-[2px] text-[9px] font-bold text-status-amber"
                    title="High-impact question — answering this improves output quality"
                  >
                    <Zap aria-hidden className="h-2 w-2" />
                    High impact
                  </span>
                )}
              </div>

              {multi && <p className="m-0 mt-1 text-[10.5px] text-ink-500">Select all that apply</p>}

              {/* Recommended-answer hint — shown before any selection is made. */}
              {hasRec && selected.length === 0 && (
                <div className="mt-1.5 flex items-center gap-2 rounded-lg border border-brand-border bg-brand-fill px-2.5 py-1.5">
                  <span className="flex-1 text-[10.5px] text-brand">
                    Recommended: <b className="font-bold">{recDisplay}</b>
                  </span>
                  <button
                    type="button"
                    onClick={() => applyRecommended(q)}
                    disabled={submitted}
                    className="h-[26px] flex-none rounded-md border border-brand-border bg-surface-white px-2 text-[10px] font-semibold text-brand transition-colors hover:bg-brand-fill disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Use recommended
                  </button>
                </div>
              )}

              {hasRec && recIsSelected && (
                <p className="m-0 mt-1.5 px-1 text-[10px] text-brand/70">✓ Using recommended answer</p>
              )}

              {options.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {options.map((option, oi) => {
                    const active = selected.includes(option);
                    const isRec = hasRec && recTokens.includes(option);
                    return (
                      <button
                        key={oi}
                        type="button"
                        data-testid="chat-clarify-chip"
                        aria-pressed={active}
                        onClick={() => toggleOption(q, option)}
                        disabled={submitted}
                        className={`h-[30px] rounded-full border px-3 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                          active
                            ? "border-brand bg-brand text-white shadow-[0_2px_8px_-3px_rgba(60,44,218,.6)]"
                            : "border-line-control bg-surface-white text-ink-700 hover:border-brand-border hover:bg-brand-fill"
                        }`}
                      >
                        {option}
                        {isRec && !active && <span className="ml-1 text-[9px] text-brand/50">★</span>}
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Free text. The backend emits `short_text` (options deliberately
                  empty — "user types freely") and `hybrid` ("MCQ suggestions plus
                  the free-text field will be shown automatically") from
                  clarify_engine.py, and neither had any input here: a short_text
                  question rendered as a question with nothing to answer it with.
                  Typing REPLACES a chip selection, which is what "override" means. */}
              {showsText && (
                <input
                  type="text"
                  data-testid="chat-clarify-text"
                  value={textValue}
                  onChange={(e) => setText(q, e.target.value)}
                  disabled={submitted}
                  aria-label={q.question}
                  placeholder={options.length ? "…or type your own answer" : "Type your answer"}
                  className="mt-2 h-[32px] w-full rounded-lg border border-line-control bg-surface-white px-3 font-serif text-[11.5px] text-ink-900 placeholder:text-ink-300 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:cursor-not-allowed disabled:opacity-50"
                />
              )}
            </div>
          );
        })}
      </div>

      {/* ── The decision ────────────────────────────────────────────────────────
          A footer band on the same fill as the ask, so the block of questions is
          framed by the two places you act. */}
      <div className="flex flex-wrap items-center gap-2 border-t border-brand-border bg-brand-fill px-3.5 py-2.5">
        <button
          type="button"
          data-testid="chat-clarify-submit"
          onClick={handleSubmit}
          disabled={submitted}
          className="inline-flex h-9 items-center gap-1.5 rounded-[10px] bg-brand px-4 text-[12px] font-semibold text-white shadow-[0_2px_6px_-2px_rgba(60,44,218,.5)] transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ArrowRight className="h-3.5 w-3.5 flex-none" />
          {answeredCount > 0
            ? `Submit ${answeredCount} answer${answeredCount !== 1 ? "s" : ""} & proceed`
            : "Submit answers & proceed"}
        </button>

        <span className="flex-1" />

        {answeredCount < total && !submitted && (
          <>
            <button
              type="button"
              data-testid="chat-clarify-skip-all"
              onClick={handleSkipAll}
              disabled={submitted}
              className="inline-flex items-center text-[11px] text-ink-500 transition-colors hover:text-brand hover:underline disabled:cursor-not-allowed disabled:opacity-50"
            >
              Skip the rest
            </button>
            {onCancelWorkflow && <span aria-hidden className="text-line-faint">·</span>}
          </>
        )}

        {onCancelWorkflow && (
          <button
            type="button"
            data-testid="chat-clarify-cancel-workflow"
            onClick={onCancelWorkflow}
            disabled={submitted}
            className="inline-flex items-center gap-1.5 text-[11px] text-ink-500 transition-colors hover:text-status-failed hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            <XCircle className="h-3.5 w-3.5" />
            Cancel run
          </button>
        )}
      </div>
    </div>
  );
}
