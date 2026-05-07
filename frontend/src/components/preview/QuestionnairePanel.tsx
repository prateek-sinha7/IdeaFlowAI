"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { MessageCircleQuestion, CheckCircle2, Send, ArrowRight, Sparkles } from "lucide-react";

export interface MCQQuestion {
  id: string;
  question: string;
  options: string[];
  allowMultiple?: boolean;
}

interface QuestionnairePanelProps {
  questions: MCQQuestion[];
  isLoading: boolean;
  onSubmitAnswers: (answers: Record<string, string[]>, freeformInput: string) => void;
  onSkip: () => void;
  workflowType: string;
}

export function QuestionnairePanel({ questions, isLoading, onSubmitAnswers, onSkip, workflowType }: QuestionnairePanelProps) {
  const [selectedAnswers, setSelectedAnswers] = useState<Record<string, string[]>>({});
  const [freeformInput, setFreeformInput] = useState("");

  const handleSelectOption = (questionId: string, option: string) => {
    setSelectedAnswers((prev) => {
      const current = prev[questionId] || [];
      if (current.includes(option)) {
        return { ...prev, [questionId]: current.filter((o) => o !== option) };
      }
      // Single select — replace
      return { ...prev, [questionId]: [option] };
    });
  };

  const answeredCount = Object.keys(selectedAnswers).filter((k) => selectedAnswers[k].length > 0).length;
  const allAnswered = answeredCount === questions.length;

  if (isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
          className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#c96442]/10 to-[#c96442]/5 border border-[#c96442]/20 mb-4"
        >
          <MessageCircleQuestion className="h-6 w-6 text-[#c96442]" />
        </motion.div>
        <p className="text-sm font-medium text-[#141413]">Preparing questions...</p>
        <p className="text-[11px] text-[#87867f] mt-1">Analyzing your idea to ask the right questions</p>
      </div>
    );
  }

  if (questions.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col h-full bg-[#faf9f5]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#e8e6dc] bg-white flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-[#c96442]/10">
            <MessageCircleQuestion className="h-3.5 w-3.5 text-[#c96442]" />
          </div>
          <div>
            <h2 className="text-[12px] font-semibold text-[#141413]">Quick Questions</h2>
            <p className="text-[9px] text-[#87867f]">Help us understand your needs better ({answeredCount}/{questions.length} answered)</p>
          </div>
        </div>
      </div>

      {/* Questions */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {questions.map((q, idx) => {
          const selected = selectedAnswers[q.id] || [];
          return (
            <motion.div
              key={q.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="rounded-xl border border-[#e8e6dc] bg-white p-3"
            >
              <p className="text-[11px] font-semibold text-[#141413] mb-2 flex items-start gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded-md bg-[#c96442]/10 text-[#c96442] text-[9px] font-bold flex-shrink-0">{idx + 1}</span>
                {q.question}
              </p>
              <div className="space-y-1.5 ml-7">
                {q.options.map((option, oi) => {
                  const isSelected = selected.includes(option);
                  return (
                    <button
                      key={oi}
                      onClick={() => handleSelectOption(q.id, option)}
                      className={`w-full text-left rounded-lg px-3 py-2 text-[10px] border transition-all ${
                        isSelected
                          ? "border-[#c96442] bg-[#c96442]/5 text-[#141413] font-medium"
                          : "border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:border-[#c96442]/30 hover:bg-white"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <div className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                          isSelected ? "border-[#c96442] bg-[#c96442]" : "border-[#c9c8c3]"
                        }`}>
                          {isSelected && <CheckCircle2 className="h-2.5 w-2.5 text-white" />}
                        </div>
                        {option}
                      </div>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          );
        })}

        {/* Free-form input */}
        <div className="rounded-xl border border-[#e8e6dc] bg-white p-3">
          <p className="text-[11px] font-semibold text-[#141413] mb-2 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-[#c96442]" />
            Anything else we should know? (optional)
          </p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={freeformInput}
              onChange={(e) => setFreeformInput(e.target.value)}
              placeholder="E.g., focus on enterprise features, keep it minimal..."
              className="flex-1 rounded-lg border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-[10px] text-[#141413] placeholder-[#87867f] focus:outline-none focus:border-[#c96442]/40"
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="px-4 py-3 border-t border-[#e8e6dc] bg-white flex-shrink-0 space-y-2">
        <button
          onClick={() => onSubmitAnswers(selectedAnswers, freeformInput)}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#c96442] text-white px-4 py-2.5 text-[12px] font-medium hover:bg-[#b5573a] transition-all"
        >
          <ArrowRight className="h-3.5 w-3.5" />
          {allAnswered ? "Run Pipeline" : `Continue (${answeredCount}/${questions.length} answered)`}
        </button>
        <button
          onClick={onSkip}
          className="w-full text-center text-[10px] text-[#87867f] hover:text-[#5e5d59] transition-colors py-1"
        >
          Skip questions & run directly
        </button>
      </div>
    </div>
  );
}
