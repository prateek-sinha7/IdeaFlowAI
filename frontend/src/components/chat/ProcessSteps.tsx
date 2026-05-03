"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, XCircle, ChevronRight, Loader2 } from "lucide-react";
import type { ProcessStep } from "@/types/index";

export interface ProcessStepsProps {
  steps: ProcessStep[];
}

function StepIcon({ step }: { step: ProcessStep }) {
  if (step.status === "running") {
    return (
      <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: "var(--theme-accent)" }} />
    );
  }
  if (step.status === "done") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />;
  }
  return <XCircle className="h-3.5 w-3.5 text-red-400" />;
}

function StepItem({ step, index }: { step: ProcessStep; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25, delay: index * 0.05 }}
    >
      <button
        onClick={() => step.detail && setExpanded(!expanded)}
        className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left transition-colors duration-150 hover:bg-white/[0.03]"
        style={{ minHeight: "28px", cursor: step.detail ? "pointer" : "default" }}
        aria-expanded={expanded}
        type="button"
      >
        {/* Emoji icon */}
        {step.icon && <span className="text-xs flex-shrink-0">{step.icon}</span>}

        {/* Label */}
        <span
          className="text-xs flex-1 truncate"
          style={{
            color: step.status === "running" ? "var(--theme-fg)" : "var(--theme-muted)",
          }}
        >
          {step.status === "done"
            ? step.label.replace(/\.{3}$/, "").replace(/ing\b/, "ed")
            : step.label}
        </span>

        {/* Status indicator */}
        <StepIcon step={step} />

        {/* Expand chevron */}
        {step.detail && (
          <motion.span
            animate={{ rotate: expanded ? 90 : 0 }}
            transition={{ duration: 0.15 }}
            className="flex-shrink-0"
          >
            <ChevronRight className="h-3 w-3" style={{ color: "var(--theme-muted)" }} />
          </motion.span>
        )}
      </button>

      {/* Expandable detail */}
      <AnimatePresence>
        {expanded && step.detail && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <p
              className="text-xs pl-8 pr-2 pb-1.5 leading-relaxed"
              style={{ color: "var(--theme-muted)" }}
            >
              {step.detail}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/**
 * Renders a vertical list of collapsible process steps with status indicators.
 * Inspired by Claude's artifact generation step display.
 */
export function ProcessSteps({ steps }: ProcessStepsProps) {
  if (steps.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="my-3 rounded-lg border-l-2 py-1.5"
      style={{
        borderColor: "var(--theme-accent)",
        backgroundColor: "rgba(0, 31, 63, 0.15)",
      }}
    >
      {steps.map((step, index) => (
        <StepItem key={step.id} step={step} index={index} />
      ))}
    </motion.div>
  );
}
