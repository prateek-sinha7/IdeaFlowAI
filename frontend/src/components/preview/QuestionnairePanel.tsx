"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { MessageCircleQuestion, CheckCircle2, ArrowRight, Sparkles, Loader2, ChevronDown, PenLine } from "lucide-react";

export interface MCQQuestion {
  id: string;
  question: string;
  options: string[];
  allowMultiple?: boolean;
  /** "single_choice" | "hybrid" (MCQ suggestions + free-text own answer) */
  answerType?: string;
}

interface QuestionnairePanelProps {
  questions: MCQQuestion[];
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
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string[]>>({});
  // Free-text overrides for hybrid questions (topic questions)
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});
  const [freeformInput, setFreeformInput] = useState("");
  const [expandedQ, setExpandedQ] = useState<string | null>(questions[0]?.id ?? null);

  const handleSelectOption = (questionId: string, option: string) => {
    setSelectedAnswers((prev) => {
      const current = prev[questionId] || [];
      if (current.includes(option)) {
        return { ...prev, [questionId]: current.filter((o) => o !== option) };
      }
      return { ...prev, [questionId]: [option] };
    });
    // Clear custom text when a preset option is selected
    setCustomAnswers((prev) => ({ ...prev, [questionId]: "" }));
    // Auto-advance to next question
    const idx = questions.findIndex(q => q.id === questionId);
    if (idx < questions.length - 1) {
      setTimeout(() => setExpandedQ(questions[idx + 1].id), 300);
    }
  };

  const handleCustomAnswer = (questionId: string, text: string) => {
    setCustomAnswers((prev) => ({ ...prev, [questionId]: text }));
    // Clear MCQ selection when typing custom answer
    if (text.trim()) {
      setSelectedAnswers((prev) => ({ ...prev, [questionId]: [] }));
    }
  };

  // Effective answer: custom text takes priority over MCQ selection
  const getEffectiveAnswer = (questionId: string): string | null => {
    const custom = customAnswers[questionId]?.trim();
    if (custom) return custom;
    const selected = selectedAnswers[questionId];
    return selected?.length ? selected[0] : null;
  };

  const answeredCount = questions.filter(q => getEffectiveAnswer(q.id) !== null).length;
  const pipelineLabel = PIPELINE_LABELS[workflowType] || workflowType;

  // Build final answers for submission: merge MCQ + custom text answers
  const buildFinalAnswers = () => {
    const merged: Record<string, string[]> = {};
    for (const q of questions) {
      const custom = customAnswers[q.id]?.trim();
      if (custom) {
        merged[q.id] = [custom];
      } else if (selectedAnswers[q.id]?.length) {
        merged[q.id] = selectedAnswers[q.id];
      }
    }
    return merged;
  };

  if (isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 bg-white gap-4">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#1B2A4A]/10 to-blue-50 flex items-center justify-center">
          <Loader2 className="h-6 w-6 text-[#1B2A4A] animate-spin" />
        </div>
        <div className="text-center">
          <p className="text-[13px] font-semibold text-gray-900 mb-1">Analyzing your brief…</p>
          <p className="text-[11px] text-gray-400">Preparing smart questions to get the best output</p>
        </div>
      </div>
    );
  }

  if (questions.length === 0) return null;

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
              {pipelineLabel} · {questions.length} questions to personalise your output
            </p>
          </div>
        </div>
        {/* Progress bar */}
        <div className="flex items-center gap-1.5">
          {questions.map((q) => {
            const answered = getEffectiveAnswer(q.id) !== null;
            return (
              <div key={q.id} className={`h-1.5 rounded-full transition-all duration-300 flex-1 ${answered ? "bg-[#1B2A4A]" : "bg-gray-200"}`} />
            );
          })}
        </div>
        <p className="text-[10px] text-gray-400 mt-1.5">{answeredCount} of {questions.length} answered</p>
      </div>

      {/* Questions */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {questions.map((q, idx) => {
          const selected = selectedAnswers[q.id] || [];
          const customText = customAnswers[q.id] || "";
          const effectiveAnswer = getEffectiveAnswer(q.id);
          const isExpanded = expandedQ === q.id;
          const isAnswered = effectiveAnswer !== null;
          const isHybrid = q.answerType === "hybrid";

          return (
            <motion.div
              key={q.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.06 }}
              className={`rounded-xl border overflow-hidden transition-all ${
                isExpanded ? "border-[#1B2A4A]/30 shadow-sm" :
                isAnswered ? "border-emerald-200 bg-emerald-50/30" :
                "border-gray-200"
              }`}
            >
              {/* Question header */}
              <button
                onClick={() => setExpandedQ(isExpanded ? null : q.id)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50/50 transition-colors"
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0 transition-all ${
                  isAnswered ? "bg-emerald-500 text-white" :
                  isExpanded ? "bg-[#1B2A4A] text-white" :
                  "bg-gray-100 text-gray-500"
                }`}>
                  {isAnswered ? <CheckCircle2 className="h-3.5 w-3.5" /> : idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[12px] font-semibold leading-snug ${isAnswered ? "text-gray-700" : "text-gray-900"}`}>
                    {q.question}
                  </p>
                  {isAnswered && !isExpanded && (
                    <p className="text-[10px] text-emerald-600 font-medium mt-0.5 truncate">
                      ✓ {effectiveAnswer}
                    </p>
                  )}
                </div>
                <ChevronDown className={`h-4 w-4 text-gray-400 flex-shrink-0 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
              </button>

              {/* Options + optional text input */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-3 border-t border-gray-100 pt-3 space-y-2">
                      {/* For hybrid questions: show "Describe your own" text input first */}
                      {isHybrid && (
                        <div className={`rounded-xl border-2 transition-all ${customText ? "border-[#1B2A4A] bg-[#1B2A4A]/5" : "border-dashed border-gray-200"}`}>
                          <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
                            <PenLine className={`h-3.5 w-3.5 flex-shrink-0 ${customText ? "text-[#1B2A4A]" : "text-gray-400"}`} />
                            <span className={`text-[10px] font-semibold ${customText ? "text-[#1B2A4A]" : "text-gray-500"}`}>
                              Describe your own topic
                            </span>
                          </div>
                          <input
                            type="text"
                            value={customText}
                            onChange={(e) => handleCustomAnswer(q.id, e.target.value)}
                            placeholder="e.g. Q3 sales results, climate change impact, AI in healthcare…"
                            className="w-full px-3 pb-2.5 pt-1 text-[11px] text-gray-900 placeholder-gray-400 bg-transparent focus:outline-none"
                            autoFocus={isHybrid}
                          />
                        </div>
                      )}

                      {/* Divider for hybrid */}
                      {isHybrid && (
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-px bg-gray-100" />
                          <span className="text-[9px] text-gray-400 font-medium">or pick a suggestion</span>
                          <div className="flex-1 h-px bg-gray-100" />
                        </div>
                      )}

                      {/* MCQ options */}
                      <div className="space-y-1.5">
                        {q.options.map((option, oi) => {
                          const isSelected = selected.includes(option) && !customText;
                          return (
                            <button
                              key={oi}
                              onClick={() => handleSelectOption(q.id, option)}
                              className={`w-full text-left rounded-xl px-3.5 py-2.5 text-[11px] border-2 transition-all duration-150 ${
                                isSelected
                                  ? "border-[#1B2A4A] bg-[#1B2A4A] text-white shadow-sm"
                                  : "border-gray-100 bg-gray-50 text-gray-700 hover:border-[#1B2A4A]/30 hover:bg-white"
                              }`}
                            >
                              <div className="flex items-center gap-2.5">
                                <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                                  isSelected ? "border-white bg-white" : "border-gray-300"
                                }`}>
                                  {isSelected && <div className="w-2 h-2 rounded-full bg-[#1B2A4A]" />}
                                </div>
                                <span className="flex-1 font-medium">{option}</span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}

        {/* Global free-form notes */}
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: questions.length * 0.06 }}
          className="rounded-xl border border-dashed border-gray-200 p-4"
        >
          <div className="flex items-center gap-2 mb-2.5">
            <Sparkles className="h-3.5 w-3.5 text-[#1B2A4A]" />
            <p className="text-[11px] font-semibold text-gray-700">Anything else? <span className="text-gray-400 font-normal">(optional)</span></p>
          </div>
          <textarea
            value={freeformInput}
            onChange={(e) => setFreeformInput(e.target.value)}
            placeholder="Add any specific requirements, constraints, or preferences…"
            rows={2}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-[11px] text-gray-900 placeholder-gray-400 focus:outline-none focus:border-[#1B2A4A]/40 focus:ring-1 focus:ring-[#1B2A4A]/20 transition-all resize-none"
          />
        </motion.div>
      </div>

      {/* Actions */}
      <div className="px-4 py-4 border-t border-gray-100 bg-white flex-shrink-0 space-y-2">
        <button
          onClick={() => onSubmitAnswers(buildFinalAnswers(), freeformInput)}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#1B2A4A] text-white px-4 py-3 text-[12px] font-semibold hover:bg-[#2a3d5e] transition-all shadow-sm"
        >
          <ArrowRight className="h-4 w-4" />
          {answeredCount === questions.length
            ? `Run ${pipelineLabel} Pipeline`
            : answeredCount > 0
            ? `Continue with ${answeredCount}/${questions.length} answered`
            : "Run with defaults"}
        </button>
        <button
          onClick={onSkip}
          className="w-full text-center text-[10px] text-gray-400 hover:text-gray-600 transition-colors py-1"
        >
          Skip all &amp; run directly
        </button>
      </div>
    </div>
  );
}
