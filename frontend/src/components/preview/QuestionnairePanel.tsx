"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  MessageCircleQuestion, CheckCircle2, ArrowRight, Sparkles, Loader2,
  ChevronLeft, ChevronRight, PenLine, Lightbulb, SkipForward,
} from "lucide-react";

export interface ClarifyQuestion {
  id: string;
  question: string;
  options: string[];
  allowMultiple?: boolean;
  /** "single_choice" | "multi_select" | "short_text" | "hybrid" */
  answerType?: string;
  recommendedAnswer?: string;
  recommendedReasoning?: string;
  recommendedDisplay?: string;
  ambiguityCategory?: string;
  impactLevel?: string;
}

// Legacy alias — kept for callers that use MCQQuestion type name
export type MCQQuestion = ClarifyQuestion;

interface QuestionnairePanelProps {
  questions: ClarifyQuestion[];
  isLoading: boolean;
  onSubmitAnswers: (answers: Record<string, string[]>, freeformInput: string) => void;
  onSkip: () => void;
  workflowType: string;
}

const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation", od_ppt: "Presentation", ppt_revision: "Presentation",
  prototype: "Prototype", od_prototype: "Prototype",
  app_builder: "App Builder",
  custom: "Custom Workflow",
};

export function QuestionnairePanel({ questions, isLoading, onSubmitAnswers, onSkip, workflowType }: QuestionnairePanelProps) {
  const [currentIdx, setCurrentIdx] = useState(0);
  // answers keyed by question id: array of strings (single or multi)
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  // free-text for short_text and hybrid custom answers
  const [textAnswers, setTextAnswers] = useState<Record<string, string>>({});
  // global freeform "anything else" box shown on the summary slide
  const [freeformInput, setFreeformInput] = useState("");
  // whether user is on the final summary/submit slide
  const [showSummary, setShowSummary] = useState(false);

  // Reset when questions change (new round)
  useEffect(() => {
    setCurrentIdx(0);
    setAnswers({});
    setTextAnswers({});
    setFreeformInput("");
    setShowSummary(false);
  }, [questions]);

  const pipelineLabel = PIPELINE_LABELS[workflowType] || workflowType;
  const current = questions[currentIdx];
  const answeredCount = questions.filter(q => getEffectiveAnswer(q.id) !== null).length;
  const isLast = currentIdx === questions.length - 1;

  function getEffectiveAnswer(id: string): string | null {
    const txt = textAnswers[id]?.trim();
    if (txt) return txt;
    const sel = answers[id];
    return sel?.length ? sel.join(", ") : null;
  }

  function handleSelectOption(qid: string, option: string, isMulti: boolean) {
    if (isMulti) {
      setAnswers(prev => {
        const cur = prev[qid] || [];
        return cur.includes(option)
          ? { ...prev, [qid]: cur.filter(o => o !== option) }
          : { ...prev, [qid]: [...cur, option] };
      });
    } else {
      setAnswers(prev => ({ ...prev, [qid]: [option] }));
      // Clear text answer when picking an option
      setTextAnswers(prev => ({ ...prev, [qid]: "" }));
    }
  }

  function handleTextChange(qid: string, val: string) {
    setTextAnswers(prev => ({ ...prev, [qid]: val }));
    // Clear MCQ selection when user types
    if (val.trim()) {
      setAnswers(prev => ({ ...prev, [qid]: [] }));
    }
  }

  function handleUseRecommended(qid: string, recommended: string) {
    setAnswers(prev => ({ ...prev, [qid]: [recommended] }));
    setTextAnswers(prev => ({ ...prev, [qid]: "" }));
  }

  function handleNext() {
    if (isLast) {
      setShowSummary(true);
    } else {
      setCurrentIdx(i => i + 1);
    }
  }

  function handleBack() {
    if (showSummary) {
      setShowSummary(false);
    } else if (currentIdx > 0) {
      setCurrentIdx(i => i - 1);
    }
  }

  function handleSubmit() {
    const merged: Record<string, string[]> = {};
    for (const q of questions) {
      const txt = textAnswers[q.id]?.trim();
      if (txt) {
        merged[q.id] = [txt];
      } else if (answers[q.id]?.length) {
        merged[q.id] = answers[q.id];
      }
    }
    onSubmitAnswers(merged, freeformInput);
  }

  if (isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 bg-white gap-4">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#1B2A4A]/10 to-blue-50 flex items-center justify-center">
          <Loader2 className="h-6 w-6 text-[#1B2A4A] animate-spin" />
        </div>
        <div className="text-center">
          <p className="text-[13px] font-semibold text-gray-900 mb-1">Analysing your brief…</p>
          <p className="text-[11px] text-gray-400">Generating targeted questions to improve the output</p>
        </div>
      </div>
    );
  }

  if (questions.length === 0) return null;

  // ── Summary / submit slide ─────────────────────────────────────────────────
  if (showSummary) {
    return (
      <div className="flex flex-col h-full bg-white">
        <div className="px-5 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#1B2A4A] to-blue-600 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="h-4 w-4 text-white" />
            </div>
            <div>
              <h2 className="text-[13px] font-bold text-gray-900">Review & Confirm</h2>
              <p className="text-[10px] text-gray-400">{pipelineLabel} · {answeredCount} of {questions.length} answered</p>
            </div>
          </div>
          {/* Progress all filled */}
          <div className="flex items-center gap-1.5">
            {questions.map((q) => (
              <div key={q.id} className={`h-1.5 rounded-full flex-1 ${getEffectiveAnswer(q.id) !== null ? "bg-[#1B2A4A]" : "bg-gray-200"}`} />
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {questions.map((q, i) => {
            const ans = getEffectiveAnswer(q.id);
            return (
              <div
                key={q.id}
                className={`rounded-xl border px-4 py-3 cursor-pointer hover:border-[#1B2A4A]/30 transition-all ${ans ? "border-emerald-200 bg-emerald-50/30" : "border-gray-200"}`}
                onClick={() => { setShowSummary(false); setCurrentIdx(i); }}
              >
                <p className="text-[11px] text-gray-500 mb-0.5">Q{i + 1}</p>
                <p className="text-[12px] font-semibold text-gray-800 leading-snug">{q.question}</p>
                {ans
                  ? <p className="text-[11px] text-emerald-600 font-medium mt-1">✓ {ans}</p>
                  : <p className="text-[10px] text-gray-400 mt-1 italic">Not answered — will use default</p>
                }
              </div>
            );
          })}

          {/* Global freeform */}
          <div className="rounded-xl border border-dashed border-gray-200 p-4">
            <div className="flex items-center gap-2 mb-2.5">
              <Sparkles className="h-3.5 w-3.5 text-[#1B2A4A]" />
              <p className="text-[11px] font-semibold text-gray-700">Anything else? <span className="text-gray-400 font-normal">(optional)</span></p>
            </div>
            <textarea
              value={freeformInput}
              onChange={(e) => setFreeformInput(e.target.value)}
              placeholder="Add any specific requirements, constraints, or preferences…"
              rows={2}
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-[11px] text-gray-900 placeholder-gray-400 focus:outline-none focus:border-[#1B2A4A]/40 resize-none"
            />
          </div>
        </div>

        <div className="px-4 py-4 border-t border-gray-100 bg-white flex-shrink-0 space-y-2">
          <button
            onClick={handleSubmit}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-3 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm"
          >
            <ArrowRight className="h-4 w-4" />
            {answeredCount > 0 ? `Run ${pipelineLabel} Pipeline` : "Run with defaults"}
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={handleBack}
              className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors py-1"
            >
              <ChevronLeft className="h-3 w-3" /> Back
            </button>
            <div className="flex-1" />
            <button onClick={onSkip} className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors py-1">
              <SkipForward className="h-3 w-3" /> Skip all &amp; run directly
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Single question slide ─────────────────────────────────────────────────
  const answerType = current.answerType || "single_choice";
  const isMulti = answerType === "multi_select";
  const isShortText = answerType === "short_text";
  const isHybrid = answerType === "hybrid";
  const selected = answers[current.id] || [];
  const textVal = textAnswers[current.id] || "";
  const effective = getEffectiveAnswer(current.id);
  const recommended = current.recommendedAnswer || (current.options?.length ? current.options[current.options.length - 1] : "");
  const reasoning = current.recommendedReasoning || current.recommendedDisplay || "";

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#1B2A4A] to-blue-600 flex items-center justify-center flex-shrink-0">
            <MessageCircleQuestion className="h-4 w-4 text-white" />
          </div>
          <div>
            <h2 className="text-[13px] font-bold text-gray-900">Quick Setup</h2>
            <p className="text-[10px] text-gray-400">
              {pipelineLabel} · Question {currentIdx + 1} of {questions.length}
            </p>
          </div>
        </div>
        {/* Progress dots */}
        <div className="flex items-center gap-1.5">
          {questions.map((q, i) => (
            <button
              key={q.id}
              onClick={() => setCurrentIdx(i)}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === currentIdx ? "flex-[2] bg-[#1B2A4A]" :
                getEffectiveAnswer(q.id) !== null ? "flex-1 bg-emerald-400" :
                "flex-1 bg-gray-200"
              }`}
            />
          ))}
        </div>
        <p className="text-[10px] text-gray-400 mt-1.5">{answeredCount} of {questions.length} answered</p>
      </div>

      {/* Question body */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <AnimatePresence mode="wait">
          <motion.div
            key={current.id}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.18 }}
          >
            {/* Impact badge */}
            {current.impactLevel === "high" && (
              <span className="inline-flex items-center gap-1 text-[9px] font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 mb-3">
                ★ High impact
              </span>
            )}
            {current.ambiguityCategory && (
              <span className="inline-flex items-center gap-1 text-[9px] text-gray-400 ml-2">
                {current.ambiguityCategory}
              </span>
            )}

            <h3 className="text-[14px] font-bold text-gray-900 leading-snug mb-4">
              {current.question}
            </h3>

            {/* Recommended answer banner */}
            {recommended && !effective && (
              <div className="flex items-start gap-2.5 rounded-xl bg-blue-50 border border-blue-200 px-3.5 py-2.5 mb-4">
                <Lightbulb className="h-3.5 w-3.5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-semibold text-blue-700">Recommended</p>
                  <p className="text-[11px] text-blue-900 font-medium">{recommended}</p>
                  {reasoning && reasoning !== recommended && (
                    <p className="text-[10px] text-blue-600 mt-0.5 leading-snug">{reasoning.replace(`${recommended} — `, "")}</p>
                  )}
                </div>
                <button
                  onClick={() => handleUseRecommended(current.id, recommended)}
                  className="text-[10px] font-semibold text-blue-700 bg-blue-100 hover:bg-blue-200 rounded-lg px-2.5 py-1.5 transition-colors flex-shrink-0 self-center"
                >
                  Use
                </button>
              </div>
            )}

            {/* short_text: pure text input */}
            {isShortText && (
              <div className="rounded-xl border-2 border-dashed border-gray-200 focus-within:border-[#1B2A4A] transition-all p-4">
                <div className="flex items-center gap-2 mb-2">
                  <PenLine className="h-3.5 w-3.5 text-gray-400" />
                  <span className="text-[10px] text-gray-500 font-medium">Type your answer</span>
                </div>
                <textarea
                  value={textVal}
                  onChange={(e) => handleTextChange(current.id, e.target.value)}
                  placeholder={recommended ? `e.g. ${recommended}` : "Your answer…"}
                  rows={3}
                  autoFocus
                  className="w-full text-[12px] text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none resize-none"
                />
              </div>
            )}

            {/* hybrid: custom text + MCQ suggestions */}
            {isHybrid && (
              <>
                <div className={`rounded-xl border-2 transition-all mb-3 ${textVal ? "border-[#1B2A4A] bg-[#1B2A4A]/5" : "border-dashed border-gray-200"}`}>
                  <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
                    <PenLine className={`h-3.5 w-3.5 flex-shrink-0 ${textVal ? "text-[#1B2A4A]" : "text-gray-400"}`} />
                    <span className={`text-[10px] font-semibold ${textVal ? "text-[#1B2A4A]" : "text-gray-500"}`}>Describe your own</span>
                  </div>
                  <input
                    type="text"
                    value={textVal}
                    onChange={(e) => handleTextChange(current.id, e.target.value)}
                    placeholder="Type your specific answer…"
                    autoFocus
                    className="w-full px-3 pb-2.5 pt-1 text-[11px] text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none"
                  />
                </div>
                {current.options.length > 0 && (
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex-1 h-px bg-gray-100" />
                    <span className="text-[9px] text-gray-400 font-medium">or pick a suggestion</span>
                    <div className="flex-1 h-px bg-gray-100" />
                  </div>
                )}
              </>
            )}

            {/* MCQ options (single_choice, multi_select, hybrid) */}
            {(answerType !== "short_text") && current.options.length > 0 && (
              <div className="space-y-1.5">
                {isMulti && (
                  <p className="text-[10px] text-gray-400 mb-2">Select all that apply</p>
                )}
                {current.options.map((option, oi) => {
                  const isSelected = selected.includes(option) && !textVal;
                  return (
                    <button
                      key={oi}
                      onClick={() => handleSelectOption(current.id, option, isMulti)}
                      className={`w-full text-left rounded-xl px-3.5 py-2.5 text-[11px] border-2 transition-all duration-150 ${
                        isSelected
                          ? "border-[#1B2A4A] bg-[#1B2A4A] text-white shadow-sm"
                          : "border-gray-100 bg-gray-50 text-gray-700 hover:border-[#1B2A4A]/30 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <div className={`flex-shrink-0 flex items-center justify-center transition-all ${
                          isMulti
                            ? `w-4 h-4 rounded border-2 ${isSelected ? "border-white bg-white" : "border-gray-300"}`
                            : `w-4 h-4 rounded-full border-2 ${isSelected ? "border-white bg-white" : "border-gray-300"}`
                        }`}>
                          {isSelected && (
                            isMulti
                              ? <div className="w-2 h-2 bg-[#1B2A4A] rounded-sm" />
                              : <div className="w-2 h-2 rounded-full bg-[#1B2A4A]" />
                          )}
                        </div>
                        <span className="flex-1 font-medium">{option}</span>
                        {option === recommended && !isSelected && (
                          <span className="text-[9px] text-blue-500 font-semibold">Rec.</span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <div className="px-4 py-4 border-t border-gray-100 bg-white flex-shrink-0 space-y-2">
        <div className="flex items-center gap-2">
          {currentIdx > 0 && (
            <button
              onClick={handleBack}
              className="flex items-center gap-1 rounded-xl border border-gray-200 px-3 py-2.5 text-[11px] text-gray-600 hover:bg-gray-50 transition-all"
            >
              <ChevronLeft className="h-3.5 w-3.5" /> Back
            </button>
          )}
          <button
            onClick={handleNext}
            className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-2.5 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm"
          >
            {effective ? (
              isLast ? <>Review answers <CheckCircle2 className="h-3.5 w-3.5" /></> : <>Next <ChevronRight className="h-3.5 w-3.5" /></>
            ) : (
              isLast ? <>Skip &amp; review <ChevronRight className="h-3.5 w-3.5" /></> : <>Skip question <ChevronRight className="h-3.5 w-3.5" /></>
            )}
          </button>
        </div>
        <button onClick={onSkip} className="w-full text-center text-[10px] text-gray-400 hover:text-gray-600 transition-colors py-1 flex items-center justify-center gap-1">
          <SkipForward className="h-3 w-3" /> Skip all &amp; run directly
        </button>
      </div>
    </div>
  );
}
